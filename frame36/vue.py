"""Zone d'affichage : dessin de l'image, zoom, déplacement, rotation, gestes souris.

La vue ne connaît que des QImage : une photo, une image d'un GIF animé…
et demain une image de vidéo (QVideoSink → QImage) sans rien changer ici.

Zoom fluide : chaque image fixe reçoit, en arrière-plan, une « pyramide » de versions
réduites de moitié en moitié. Pendant l'animation du zoom, on dessine depuis le niveau
juste plus grand que l'affichage : rapide et sans crénelage, même sur une photo de 40 Mpx.
"""

from __future__ import annotations

import math

from PySide6.QtCore import (QEasingCurve, QObject, QPoint, QPointF, QRectF, QRunnable, QSize, QSizeF, Qt,
                            QThreadPool, QTimer, QVariantAnimation, Signal)
from PySide6.QtGui import QBrush, QColor, QCursor, QFont, QImage, QPainter, QPixmap, QTransform
from PySide6.QtWidgets import QWidget

ZOOM_MIN, ZOOM_MAX = 0.01, 40.0
PAS_ZOOM = 1.12           # par cran de molette (12 %)
DUREE_ZOOM = 170          # ms d'animation
MARGE_BORD = 6            # px sensibles au redimensionnement (fenêtré)
SEUIL_GLISSER = 4         # px avant de considérer un clic comme un glisser
NIVEAU_MIN = 384          # plus petit côté d'un niveau de pyramide


# ---------------------------------------------------------------------- pyramide
class _SignalPyramide(QObject):
    prete = Signal(int, list)


class _TachePyramide(QRunnable):
    def __init__(self, generation: int, image: QImage, signal: _SignalPyramide):
        super().__init__()
        self.generation, self.image, self.signal = generation, image, signal

    def run(self):
        niveaux = []
        im = self.image
        while min(im.width(), im.height()) // 2 >= NIVEAU_MIN // 2 and max(im.width(), im.height()) > NIVEAU_MIN:
            im = im.scaled(max(1, im.width() // 2), max(1, im.height() // 2),
                           Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
            niveaux.append(im)
        try:
            self.signal.prete.emit(self.generation, niveaux)
        except RuntimeError:
            pass


_POOL_PYRAMIDE = QThreadPool()
_POOL_PYRAMIDE.setMaxThreadCount(1)


def image_transparente(image: QImage) -> bool:
    """Vrai si l'image a de vrais pixels transparents (beaucoup de PNG ont un canal alpha
    entièrement opaque). Test sur une copie réduite : quelques millisecondes."""
    if image is None or image.isNull() or not image.hasAlphaChannel():
        return False
    petite = image if max(image.width(), image.height()) <= 256 else \
        image.scaled(256, 256, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation)
    alpha = petite.convertToFormat(QImage.Format.Format_Alpha8)
    donnees, bpl, w = bytes(alpha.constBits()), alpha.bytesPerLine(), alpha.width()
    return any(min(donnees[y * bpl:y * bpl + w]) < 250 for y in range(alpha.height()))


_MOTIF_DAMIER: QPixmap | None = None


def _damier(p: QPainter, r: QRectF, cote: int = 10):
    """Fond à carreaux gris clair / gris, comme dans les logiciels de retouche (motif répété :
    un seul remplissage, même pour une très grande image)."""
    global _MOTIF_DAMIER
    if _MOTIF_DAMIER is None:
        _MOTIF_DAMIER = QPixmap(cote * 2, cote * 2)
        _MOTIF_DAMIER.fill(QColor(205, 205, 205))
        q = QPainter(_MOTIF_DAMIER)
        q.fillRect(0, 0, cote, cote, QColor(160, 160, 160))
        q.fillRect(cote, cote, cote, cote, QColor(160, 160, 160))
        q.end()
    p.fillRect(r, QBrush(_MOTIF_DAMIER))


class Vue(QWidget):
    zoom_change = Signal(float)
    ctrl_molette = Signal(float, QPointF)     # Ctrl+molette : la fenêtre et l'image ensemble (mode adaptatif)
    double_clic = Signal()
    clic_fond = Signal()               # clic (sans glisser) sur le fond
    menu_demande = Signal(QPoint)
    souris_bouge = Signal(QPoint)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.source: QImage | None = None      # image telle que lue
        self.image: QImage | None = None       # après rotation
        self.apercu: QImage | None = None      # miniature floue pendant le chargement
        self.taille_attendue = QSize()
        self.rotation = 0
        self.zoom = 1.0
        self.auto = True                       # zoom recalculé à chaque redimensionnement
        self.decalage = QPointF(0, 0)          # centre image - centre vue
        self.fond = QColor(127, 127, 127)
        self.plein_ecran = False
        self.lissage = True
        self.ombre = True
        # images détourées : « derriere » (on voit ce qu'il y a derrière la fenêtre), « fond », « damier »
        self.mode_transparence = "derriere"
        self.agrandir_auto = False
        self.ctrl_redimensionne = False        # Ctrl+molette réservé à la fenêtre (mode adaptatif)
        self.transparente = False
        self.message = ""

        self._niveaux: list[QImage] = []       # pyramide (du plus grand au plus petit)
        self._generation = 0
        self._signal_pyr = _SignalPyramide(self)
        self._signal_pyr.prete.connect(self._pyramide_prete)

        self._lisse: QImage | None = None
        self._lisse_cle = None
        self._minuteur_lisse = QTimer(self, singleShot=True, interval=60, timeout=self._calculer_lisse)

        # animation du zoom (interpolation logarithmique : vitesse perçue constante)
        self._anim = QVariantAnimation(self, duration=DUREE_ZOOM, startValue=0.0, endValue=1.0,
                                       easingCurve=QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._pas_animation)
        self._anim.finished.connect(self._fin_animation)
        self._z0 = self._z1 = 1.0
        self._ancre = QPointF()
        self._d0 = self._d1 = None             # décalages de départ / arrivée (mode « centrer »)
        self._auto_apres = False

        # pastille « 26 % »
        self._pct_opacite = 0.0
        self._pct_fondu = QVariantAnimation(self, duration=300, startValue=1.0, endValue=0.0)
        self._pct_fondu.valueChanged.connect(self._maj_pct)
        self._pct_minuteur = QTimer(self, singleShot=True, interval=900, timeout=self._pct_fondu.start)

        self._appui: QPointF | None = None
        self._appui_decalage = QPointF()
        self._mode_glisser = None              # "image" | "fenetre" | "fond_plein" | None
        self._a_glisse = False

    # ------------------------------------------------------------------ données
    def vider(self, message: str = ""):
        self.source = self.image = self.apercu = None
        self._lisse = None
        self._niveaux = []
        self.message = message
        self.update()

    def definir_apercu(self, miniature: QImage | None, taille_reelle: QSize, rotation: int = 0):
        """Affiche la miniature agrandie en attendant le décodage complet."""
        self._anim.stop()
        self.source = self.image = None
        self._lisse = None
        self._niveaux = []
        self.message = ""
        self.rotation = rotation
        self.apercu = miniature if miniature is not None and not miniature.isNull() else None
        self.transparente = self.apercu is not None and image_transparente(self.apercu)
        if self.apercu is not None and rotation:
            self.apercu = self.apercu.transformed(QTransform().rotate(rotation))
        t = QSize(taille_reelle)
        if rotation in (90, 270) and t.isValid():
            t.transpose()
        self.taille_attendue = t if t.isValid() else (self.apercu.size() if self.apercu else QSize())
        self.auto = True
        self.decalage = QPointF()
        self._ajuster_si_auto()
        self.update()

    def definir_image(self, image: QImage, nouvelle: bool = True, rotation: int | None = None):
        """nouvelle=False : image suivante d'une animation (on garde zoom et position)."""
        self.source = image
        if rotation is not None:
            self.rotation = rotation
        self.image = self._tourner(image)
        self.apercu = None
        self.message = ""
        self.taille_attendue = self.image.size()
        if nouvelle:
            self.transparente = image_transparente(self.image)
            self._anim.stop()
            self.auto = True
            self.decalage = QPointF()
            self._ajuster_si_auto()
            self._nouvelle_pyramide()
            self._minuteur_lisse.start(0)
        else:
            self._niveaux = []
            self._lisse = None
            self._calculer_lisse()
        self.update()

    def _nouvelle_pyramide(self):
        self._generation += 1
        self._niveaux = []
        self._lisse = None
        if self.image is not None and max(self.image.width(), self.image.height()) > NIVEAU_MIN * 2:
            _POOL_PYRAMIDE.start(_TachePyramide(self._generation, self.image, self._signal_pyr))

    def _pyramide_prete(self, generation: int, niveaux: list):
        if generation == self._generation:
            self._niveaux = niveaux
            self._minuteur_lisse.start(0)

    def _tourner(self, image: QImage) -> QImage:
        if not self.rotation:
            return image
        return image.transformed(QTransform().rotate(self.rotation), Qt.TransformationMode.SmoothTransformation)

    def tourner(self, degres: int):
        self._anim.stop()
        self.rotation = (self.rotation + degres) % 360
        if self.source is not None:
            self.image = self._tourner(self.source)
            self.taille_attendue = self.image.size()
            self._nouvelle_pyramide()
        elif self.apercu is not None:
            self.apercu = self.apercu.transformed(QTransform().rotate(degres))
            self.taille_attendue.transpose()
        self.auto = True
        self.decalage = QPointF()
        self._ajuster_si_auto()
        self._lisse = None
        self._minuteur_lisse.start(0)
        self.update()

    # ------------------------------------------------------------------ zoom
    def _taille_image(self) -> QSizeF:
        """Taille en pixels logiques : zoom 1 = 1 pixel de l'image pour 1 pixel de l'écran,
        même avec la mise à l'échelle Windows à 125 / 150 %."""
        t = self.image.size() if self.image is not None else self.taille_attendue
        if not t.isValid():
            return QSizeF()
        d = self.devicePixelRatioF()
        return QSizeF(t.width() / d, t.height() / d)

    def zoom_ajuste(self) -> float:
        t = self._taille_image()
        if not t.isValid() or t.isEmpty() or self.width() <= 0:
            return 1.0
        return min(self.width() / t.width(), self.height() / t.height())

    def zoom_auto(self) -> float:
        """Plus grande que la zone : on réduit ; plus petite : taille d'origine.
        agrandir_auto (fenêtre agrandie à la main en mode adaptatif) : l'image remplit la fenêtre."""
        return self.zoom_ajuste() if self.agrandir_auto else min(1.0, self.zoom_ajuste())

    def _ajuster_si_auto(self):
        if self.auto:
            ancien = self.zoom
            self.zoom = self.zoom_auto()
            self.decalage = QPointF()
            if abs(ancien - self.zoom) > 1e-9:
                self.zoom_change.emit(self.zoom)

    def _appliquer_zoom(self, z: float, ancre: QPointF):
        """Change le zoom en gardant sous l'ancre le même point de l'image."""
        centre = QPointF(self.width() / 2, self.height() / 2) + self.decalage
        nouveau_centre = ancre + (centre - ancre) * (z / self.zoom)
        self.zoom = z
        self.decalage = nouveau_centre - QPointF(self.width() / 2, self.height() / 2)
        self._borner()

    def animer_zoom(self, z: float, ancre: QPointF | None = None, decalage: QPointF | None = None,
                    auto_apres: bool = False):
        """Zoom animé vers z. decalage donné : on glisse aussi vers cette position."""
        if self._taille_image().isEmpty():
            return
        z = max(ZOOM_MIN, min(ZOOM_MAX, z))
        self._anim.stop()
        self._z0, self._z1 = self.zoom, z
        self._ancre = ancre if ancre is not None else QPointF(self.width() / 2, self.height() / 2)
        self._d0, self._d1 = (QPointF(self.decalage), decalage) if decalage is not None else (None, None)
        self._auto_apres = auto_apres
        self.auto = False
        self._lisse = None
        self._montrer_pct(z)
        self._anim.start()

    def _pas_animation(self, t):
        t = float(t)
        z = self._z0 * (self._z1 / self._z0) ** t if self._z0 > 0 else self._z1
        if self._d1 is not None:
            self.zoom = z
            self.decalage = self._d0 * (1 - t) + self._d1 * t
            self._borner()
        else:
            self._appliquer_zoom(z, self._ancre)
        self.zoom_change.emit(self.zoom)
        self.update()

    def _fin_animation(self):
        if self._auto_apres:
            self.auto = True
            self._ajuster_si_auto()
        self._minuteur_lisse.start()
        self.update()

    def zoom_vise(self) -> float:
        """Zoom d'arrivée si une animation est en cours (les crans de molette s'additionnent)."""
        return self._z1 if self._anim.state() == QVariantAnimation.State.Running else self.zoom

    def zoomer(self, facteur: float, ancre: QPointF | None = None):
        base = self.zoom_vise()
        z = base * facteur
        # petit « cran » magnétique sur 100 % et sur l'ajustement
        for cible in (1.0, self.zoom_ajuste()):
            if (base - cible) * (z - cible) < 0 and abs(math.log(z / cible)) < math.log(PAS_ZOOM) * 0.6:
                z = cible
                break
        self.animer_zoom(z, ancre)

    def definir_zoom(self, z: float, ancre: QPointF | None = None):
        self.animer_zoom(z, ancre)

    def basculer_un_un(self):
        """1:1 → taille d'origine ; deuxième appui → retour à l'ajustement."""
        if abs(self.zoom_vise() - 1.0) < 1e-6 and not self.auto:
            self.ajuster()
        else:
            ancre = self.mapFromGlobal(QCursor.pos())
            ancre = QPointF(ancre) if self.rect().contains(ancre) else None
            self.animer_zoom(1.0, ancre)

    def ajuster(self):
        self.animer_zoom(self.zoom_auto(), decalage=QPointF(), auto_apres=True)

    def pourcentage(self) -> float:
        return self.zoom * 100

    # ------------------------------------------------------------------ pastille %
    def _montrer_pct(self, z: float):
        self._pct_fondu.stop()
        self._pct_opacite = 1.0
        self._pct_minuteur.start()

    def _maj_pct(self, v):
        self._pct_opacite = float(v)
        self.update()

    def _dessiner_pct(self, p: QPainter):
        if self._pct_opacite <= 0.01:
            return
        pct = self.zoom * 100
        texte = f"{pct:.1f}%" if pct < 10 else f"{round(pct)}%"
        f = QFont(self.font())
        f.setPixelSize(17)
        p.setFont(f)
        m = p.fontMetrics()
        l, h = m.horizontalAdvance(texte) + 22, m.height() + 10
        r = QRectF((self.width() - l) / 2, (self.height() - h) / 2, l, h)
        p.setOpacity(self._pct_opacite)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(70, 70, 70, 215))
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.drawRoundedRect(r, 6, 6)
        p.setPen(QColor(245, 245, 245))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, texte)
        p.setOpacity(1.0)

    # ------------------------------------------------------------------ géométrie
    def rect_image(self) -> QRectF:
        t = self._taille_image()
        if t.isEmpty():
            return QRectF()
        l, h = t.width() * self.zoom, t.height() * self.zoom
        c = QPointF(self.width() / 2, self.height() / 2) + self.decalage
        # alignement sur le pixel physique : évite le flou d'un demi-pixel à 100 %
        d = self.devicePixelRatioF()
        return QRectF(round((c.x() - l / 2) * d) / d, round((c.y() - h / 2) * d) / d,
                      max(1, round(l * d)) / d, max(1, round(h * d)) / d)

    def deborde(self) -> bool:
        r = self.rect_image()
        return r.width() > self.width() + 1 or r.height() > self.height() + 1

    def couvre_tout(self) -> bool:
        r = self.rect_image()
        return not r.isEmpty() and r.adjusted(-1, -1, 1, 1).contains(QRectF(self.rect()))

    def _borner(self):
        """Empêche l'image de partir hors de la vue."""
        t = self._taille_image()
        if t.isEmpty():
            return
        l, h = t.width() * self.zoom, t.height() * self.zoom
        dx, dy = self.decalage.x(), self.decalage.y()
        limites = []
        for taille_img, taille_vue in ((l, self.width()), (h, self.height())):
            if taille_img > taille_vue:
                lim = (taille_img - taille_vue) / 2      # pas de bord vide quand on déborde
            else:
                lim = max(0, taille_vue / 2 - 40)        # 40 px restent visibles
            limites.append(lim)
        self.decalage = QPointF(max(-limites[0], min(limites[0], dx)), max(-limites[1], min(limites[1], dy)))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.auto:
            self._ajuster_si_auto()
            self._lisse = None
            self._minuteur_lisse.start()
        else:
            self._borner()

    # ------------------------------------------------------------------ dessin
    def _niveau_pour(self, largeur_px: float) -> QImage:
        """Plus petit niveau de la pyramide encore plus large que l'affichage."""
        meilleur = self.image
        for n in self._niveaux:
            if n.width() >= largeur_px:
                meilleur = n
            else:
                break
        return meilleur

    def _calculer_lisse(self):
        """Rendu exact de qualité, une fois le zoom immobile (réductions uniquement)."""
        if (self.image is None or not self.lissage or self.zoom >= 1.0
                or self._anim.state() == QVariantAnimation.State.Running):
            self._lisse = None
            return
        cle = (self.image.cacheKey(), len(self._niveaux)) + self._taille_lisse()
        if cle == self._lisse_cle and self._lisse is not None:
            return
        l, h = cle[2:]
        self._lisse = self._niveau_pour(l).scaled(l, h, Qt.AspectRatioMode.IgnoreAspectRatio,
                                                  Qt.TransformationMode.SmoothTransformation)
        self._lisse.setDevicePixelRatio(self.devicePixelRatioF())
        self._lisse_cle = cle
        self.update()

    def _taille_lisse(self) -> tuple[int, int]:
        r = self.rect_image()
        d = self.devicePixelRatioF()
        return round(r.width() * d), round(r.height() * d)

    def voir_derriere(self) -> bool:
        """Image détourée en mode fenêtré : la fenêtre n'a plus de fond, seul le sujet est visible."""
        return self.transparente and self.mode_transparence == "derriere" and not self.plein_ecran

    def paintEvent(self, e):
        p = QPainter(self)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        fond = QColor(0, 0, 0, 0) if self.voir_derriere() else QColor(self.fond)
        if fond.alpha() == 0:
            fond.setAlpha(1)     # alpha 0 = les clics traverseraient la fenêtre (Windows)
        p.fillRect(self.rect(), fond)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        r = self.rect_image()
        img = self.image if self.image is not None else self.apercu
        if img is None or r.isEmpty():
            if self.message:
                p.setPen(QColor(230, 230, 230))
                p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self.message)
            return

        if self.transparente and self.mode_transparence == "damier":
            _damier(p, r.intersected(QRectF(self.rect())))
        elif self.ombre and not self.couvre_tout() and not self.transparente:
            # (pas d'ombre rectangulaire autour d'un sujet détouré)
            p.setPen(Qt.PenStyle.NoPen)
            for i in range(8, 0, -1):
                p.setBrush(QColor(0, 0, 0, 10))
                p.drawRoundedRect(r.adjusted(-i, -i + 2, i, i + 2), i, i)

        if img is self.image and self._lisse is not None and \
                (self._lisse.width(), self._lisse.height()) == self._taille_lisse():
            p.drawImage(r.topLeft(), self._lisse)
        else:
            if img is self.image:
                img = self._niveau_pour(r.width() * self.devicePixelRatioF())
            lisser = self.lissage and (img is self.apercu or self.zoom < 3.0)   # au-delà : pixels nets
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, lisser)
            # ne dessiner que la partie visible (gros gain sur les très grandes images zoomées)
            visible = r.intersected(QRectF(self.rect()))
            if not visible.isEmpty():
                sx = img.width() / r.width()
                sy = img.height() / r.height()
                src = QRectF((visible.x() - r.x()) * sx, (visible.y() - r.y()) * sy,
                             visible.width() * sx, visible.height() * sy)
                p.drawImage(visible, img, src)
        self._dessiner_pct(p)

    # ------------------------------------------------------------------ souris
    def _bords(self, pos: QPoint) -> Qt.Edge:
        fen = self.window()
        if self.plein_ecran or fen.isMaximized():
            return Qt.Edge(0)
        m = MARGE_BORD
        bords = Qt.Edge(0)
        if pos.x() < m:
            bords |= Qt.Edge.LeftEdge
        elif pos.x() >= self.width() - m:
            bords |= Qt.Edge.RightEdge
        if pos.y() < m:
            bords |= Qt.Edge.TopEdge
        elif pos.y() >= self.height() - m:
            bords |= Qt.Edge.BottomEdge
        return bords

    _CURSEURS = {
        Qt.Edge.LeftEdge.value: Qt.CursorShape.SizeHorCursor,
        Qt.Edge.RightEdge.value: Qt.CursorShape.SizeHorCursor,
        Qt.Edge.TopEdge.value: Qt.CursorShape.SizeVerCursor,
        Qt.Edge.BottomEdge.value: Qt.CursorShape.SizeVerCursor,
        (Qt.Edge.LeftEdge | Qt.Edge.TopEdge).value: Qt.CursorShape.SizeFDiagCursor,
        (Qt.Edge.RightEdge | Qt.Edge.BottomEdge).value: Qt.CursorShape.SizeFDiagCursor,
        (Qt.Edge.RightEdge | Qt.Edge.TopEdge).value: Qt.CursorShape.SizeBDiagCursor,
        (Qt.Edge.LeftEdge | Qt.Edge.BottomEdge).value: Qt.CursorShape.SizeBDiagCursor,
    }

    def _maj_curseur(self, pos: QPoint):
        bords = self._bords(pos)
        if bords:
            self.setCursor(self._CURSEURS.get(bords.value, Qt.CursorShape.ArrowCursor))
        elif self._mode_glisser == "image" and self._a_glisse:
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        elif self.rect_image().contains(QPointF(pos)) and self.deborde():
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.RightButton:
            self.menu_demande.emit(e.globalPosition().toPoint())
            return
        if e.button() != Qt.MouseButton.LeftButton:
            return
        pos = e.position()
        bords = self._bords(pos.toPoint())
        if bords and self.window().windowHandle():
            self.window().windowHandle().startSystemResize(bords)
            return

        self._anim.stop()
        self._appui = pos
        self._appui_decalage = QPointF(self.decalage)
        self._a_glisse = False
        sur_image = self.rect_image().contains(pos)
        if sur_image and (self.deborde() or not self.couvre_tout()):
            # image zoomée (on la parcourt) ou plus petite que la zone (on la déplace)
            self._mode_glisser = "image"
        elif self.plein_ecran:
            self._mode_glisser = "image" if sur_image else "fond_plein"
        else:
            # fond, ou image qui remplit exactement la fenêtre : on déplace la fenêtre
            # (le déplacement système démarre au premier mouvement : le double-clic reste possible)
            self._mode_glisser = "fenetre"

    def mouseMoveEvent(self, e):
        pos = e.position()
        self.souris_bouge.emit(pos.toPoint())
        if self._appui is not None and e.buttons() & Qt.MouseButton.LeftButton:
            delta = pos - self._appui
            if not self._a_glisse and (abs(delta.x()) + abs(delta.y())) >= SEUIL_GLISSER:
                self._a_glisse = True
            if self._a_glisse and self._mode_glisser == "fenetre":
                fen = self.window()
                if fen.windowHandle() and not fen.isMaximized():
                    fen.windowHandle().startSystemMove()
                self._appui = None
                self._mode_glisser = None
            elif self._a_glisse and self._mode_glisser == "image":
                self.decalage = self._appui_decalage + delta
                self._borner()
                self.update()
        self._maj_curseur(pos.toPoint())

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            if self._mode_glisser == "fond_plein" and not self._a_glisse:
                self.clic_fond.emit()
            self._appui = None
            self._mode_glisser = None
            self._a_glisse = False
            self._maj_curseur(e.position().toPoint())

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and not self._bords(e.position().toPoint()):
            self.double_clic.emit()

    def wheelEvent(self, e):
        # angleDelta : 120 par cran ; les molettes fines et pavés tactiles envoient moins, en continu
        d = e.angleDelta().y() or e.angleDelta().x()
        if not d:
            d = e.pixelDelta().y() * 2
        if not d:
            return
        if self.ctrl_redimensionne and e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.ctrl_molette.emit(PAS_ZOOM ** (d / 120), e.position())
        else:
            self.zoomer(PAS_ZOOM ** (d / 120), e.position())
        e.accept()

    def leaveEvent(self, e):
        self.souris_bouge.emit(QPoint(-1, -1))
        super().leaveEvent(e)
