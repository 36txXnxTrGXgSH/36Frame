"""Barre d'outils façon Picasa (boutons + bande de miniatures) et petits boutons de fenêtre."""

from __future__ import annotations

import os

from PySide6.QtCore import (QEasingCurve, QPoint, QPointF, QPropertyAnimation, QRectF, QSize, Qt,
                            QTimer, QVariantAnimation, Signal)
from PySide6.QtGui import QColor, QCursor, QFont, QImage, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QToolButton, QToolTip,
                               QVBoxLayout, QWidget)

from .icones import icone

CELLULE = 46          # largeur d'une miniature + espacement
VIGNETTE = 40


class Bouton(QToolButton):
    """Bouton gris arrondi, comme ceux de Picasa."""

    def __init__(self, nom_icone: str, info: str, parent=None, rond: bool = False, texte: str = ""):
        super().__init__(parent)
        self.rond = rond
        self.setIcon(icone(nom_icone))
        self.setToolTip(info)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAutoRaise(True)
        if texte:
            self.setText(texte)
            self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        cote = 40 if rond else 28
        self.setIconSize(QSize(26, 26) if rond else QSize(18, 18))
        self.setFixedHeight(cote)
        if not texte:
            self.setFixedWidth(cote if rond else 30)

    def changer_icone(self, nom: str):
        self.setIcon(icone(nom))

    def compacter(self, oui: bool, texte: str):
        """Bouton à texte → icône seule quand la place manque."""
        if oui and self.text():
            self.setText("")
            self.setFixedWidth(30)
        elif not oui and not self.text():
            self.setText(texte)
            self.setMinimumWidth(0)
            self.setMaximumWidth(16777215)
            self.setFixedWidth(self.sizeHint().width())

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        survol = self.underMouse()
        enfonce = self.isDown()
        g = QLinearGradient(r.topLeft(), r.bottomLeft())
        haut, bas = (QColor(95, 95, 95), QColor(55, 55, 55)) if not enfonce else (QColor(45, 45, 45), QColor(70, 70, 70))
        if survol and not enfonce:
            haut, bas = haut.lighter(125), bas.lighter(125)
        g.setColorAt(0, haut)
        g.setColorAt(1, bas)
        p.setBrush(g)
        p.setPen(QPen(QColor(20, 20, 20, 200), 1))
        if self.rond:
            p.drawEllipse(r)
        else:
            p.drawRoundedRect(r, 5, 5)
        taille = self.iconSize()
        pix = self.icon().pixmap(taille)
        if self.text():
            x = 8
            p.drawPixmap(QPoint(x, (self.height() - taille.height()) // 2), pix)
            p.setPen(QColor(235, 235, 235))
            p.drawText(QRectF(x + taille.width() + 5, 0, self.width(), self.height()),
                       Qt.AlignmentFlag.AlignVCenter, self.text())
        else:
            p.drawPixmap(QPoint((self.width() - taille.width()) // 2, (self.height() - taille.height()) // 2), pix)

    def sizeHint(self):
        if self.text():
            return QSize(self.fontMetrics().horizontalAdvance(self.text()) + 40, self.height())
        return super().sizeHint()


class BandeMiniatures(QWidget):
    choisi = Signal(int)
    choisi_nouvelle = Signal(int)     # clic molette / Ctrl+clic : ouvrir dans une nouvelle fenêtre
    defiler = Signal(int)

    def __init__(self, chargeur, parent=None):
        super().__init__(parent)
        self.chargeur = chargeur
        self.chargeur.prete.connect(self._miniature_prete)
        self.chemins: list[str] = []
        self.index = -1
        self.position = 0.0          # index (flottant) affiché au centre, animé
        self.setFixedHeight(VIGNETTE + 8)
        self.setMouseTracking(True)
        self._anim = QVariantAnimation(self, duration=180, easingCurve=QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._bouger)
        self._survol = -1

    def definir(self, chemins: list[str], index: int):
        if chemins is not self.chemins:
            self.chargeur.vider_file()
        self.chemins = chemins
        self.index = index
        self._anim.stop()
        self.position = float(index)
        self.update()

    def aller(self, index: int):
        self.index = index
        self._anim.stop()
        self._anim.setStartValue(self.position)
        self._anim.setEndValue(float(index))
        self._anim.start()

    def _bouger(self, v):
        self.position = float(v)
        self.update()

    def _miniature_prete(self, chemin, _image):
        self.update()

    def _index_en(self, x: float) -> int:
        i = round(self.position + (x - self.width() / 2) / CELLULE)
        return i if 0 <= i < len(self.chemins) else -1

    def paintEvent(self, e):
        if not self.chemins:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        demi = self.width() / 2
        n_visibles = int(demi / CELLULE) + 2
        premier = max(0, int(self.position) - n_visibles)
        dernier = min(len(self.chemins) - 1, int(self.position) + n_visibles)
        # demander d'abord les plus proches de l'image courante
        for d in range(0, n_visibles + 6):
            for i in (int(self.position) + d, int(self.position) - d):
                if 0 <= i < len(self.chemins):
                    self.chargeur.demander(self.chemins[i], priorite=-d)
        y = 4
        for i in range(premier, dernier + 1):
            cx = demi + (i - self.position) * CELLULE
            cellule = QRectF(cx - VIGNETTE / 2, y, VIGNETTE, VIGNETTE)
            image = self.chargeur.cache.get(self.chemins[i])
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(40, 40, 40))
            p.drawRect(cellule)
            if image is not None and not image.isNull():
                # recadrage carré centré, comme Picasa
                cote = min(image.width(), image.height())
                src = QRectF((image.width() - cote) / 2, (image.height() - cote) / 2, cote, cote)
                p.drawImage(cellule, image, src)
            if i == self.index:
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(QColor(255, 170, 40), 2.5))
                p.drawRect(cellule.adjusted(-1.5, -1.5, 1.5, 1.5))
            elif i == self._survol:
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(QColor(255, 255, 255, 160), 1.5))
                p.drawRect(cellule.adjusted(-1, -1, 1, 1))
            else:
                p.fillRect(cellule, QColor(0, 0, 0, 70))


    def mouseMoveEvent(self, e):
        i = self._index_en(e.position().x())
        if i != self._survol:
            self._survol = i
            self.update()
            if i >= 0:
                QToolTip.showText(e.globalPosition().toPoint(), os.path.basename(self.chemins[i])
                                  + "\nClic molette : nouvelle fenêtre", self)
            else:
                QToolTip.hideText()

    def leaveEvent(self, e):
        self._survol = -1
        self.update()

    def mousePressEvent(self, e):
        i = self._index_en(e.position().x())
        if i < 0:
            return
        nouvelle = e.button() == Qt.MouseButton.MiddleButton or (
            e.button() == Qt.MouseButton.LeftButton and e.modifiers() & Qt.KeyboardModifier.ControlModifier)
        if nouvelle:
            self.choisi_nouvelle.emit(i)
        elif e.button() == Qt.MouseButton.LeftButton:
            self.choisi.emit(i)

    def wheelEvent(self, e):
        d = e.angleDelta().y() or e.angleDelta().x() or e.pixelDelta().y()
        if d:
            # molette vers l'avant = image précédente, vers l'arrière = image suivante
            self.defiler.emit(-1 if d > 0 else 1)
        e.accept()


class _Panneau(QWidget):
    """Widget superposé qui apparaît au survol et s'efface en fondu."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self._effet = QGraphicsOpacityEffect(self)
        self._effet.setOpacity(0.0)
        self.setGraphicsEffect(self._effet)
        self._anim = QPropertyAnimation(self._effet, b"opacity", self, duration=150)
        self._minuteur = QTimer(self, singleShot=True, timeout=lambda: self._fondu(0.0))
        self.delai_masquage = 600
        self.garder_visible = False      # reste visible (ex. : menu ouvert)
        # Sonde : tant que le panneau est visible, on vérifie nous-mêmes où est le curseur.
        # Windows ne signale pas toujours la sortie de la souris (fenêtre épinglée au-dessus
        # d'un jeu qui a pris la souris, fenêtre inactive…) : sans ça, la barre restait affichée.
        self._sonde = QTimer(self, interval=150, timeout=self._sonder)

    def visible(self) -> bool:
        return self._effet.opacity() > 0.01 or self._anim.endValue() == 1.0

    def montrer(self):
        self._minuteur.stop()
        self._fondu(1.0)
        self._sonde.start()

    def masquer(self, immediat: bool = False):
        if self.garder_visible:
            return
        if immediat:
            self._minuteur.stop()
            self._fondu(0.0)
        elif not self._minuteur.isActive():      # (ne pas repousser un masquage déjà prévu)
            self._minuteur.start(self.delai_masquage)

    def _sonder(self):
        if self._effet.opacity() <= 0.01 and self._anim.endValue() == 0.0:
            self._sonde.stop()                   # complètement caché : plus rien à surveiller
            return
        if self.garder_visible or not self.isVisible():
            return
        dedans = self.rect().contains(self.mapFromGlobal(QCursor.pos()))
        if dedans:
            self._minuteur.stop()
        else:
            self.masquer()

    def _fondu(self, cible: float):
        if self._anim.endValue() == cible and self._anim.state() == QPropertyAnimation.State.Running:
            return
        self._anim.stop()
        self._anim.setStartValue(self._effet.opacity())
        self._anim.setEndValue(cible)
        self._anim.start()

    def enterEvent(self, e):
        self.montrer()

    def leaveEvent(self, e):
        self._minuteur.stop()
        self.masquer()


class BarreOutils(_Panneau):
    def __init__(self, chargeur_miniatures, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)

        self.nom = QLabel()
        self.nom.setAlignment(Qt.AlignmentFlag.AlignCenter)
        f = QFont(self.font())
        f.setBold(True)
        self.nom.setFont(f)
        self.nom.setStyleSheet("color: #f0f0f0; background: transparent;")

        self.bande = BandeMiniatures(chargeur_miniatures)

        self.zoom_plus = Bouton("plus", "Zoom avant  (+ / molette)")
        self.zoom_moins = Bouton("moins", "Zoom arrière  (- / molette)")
        self.un_un = Bouton("un_un", "Taille d'origine 1:1 / ajuster  (1)")
        self.recadrer = Bouton("recadrer", "Ajuster la fenêtre à la taille de l'image  (W)")
        self.recadrer.hide()
        self.epingle = Bouton("epingle", "Épingler au premier plan : l'image reste au-dessus de tout,\n"
                                         "même d'un jeu en plein écran fenêtré  (T)")
        self.recadrer_utile = False     # la fenêtre n'a pas la taille de l'image
        self.precedent = Bouton("precedent", "Image précédente  (←)")
        self.lecture = Bouton("lecture", "Diaporama du dossier  (Espace)", rond=True)
        self.suivant = Bouton("suivant", "Image suivante  (→)")
        self.partager = Bouton("partager", "Partager (e-mail, Discord, copier…)", texte="Partager")
        self.rot_gauche = Bouton("rot_gauche", "Rotation à gauche  (Ctrl+L)")
        self.rot_droite = Bouton("rot_droite", "Rotation à droite  (Ctrl+R)")
        self.favori = Bouton("etoile", "Ajouter aux favoris  (Ctrl+D)")
        self.options = Bouton("menu", "Autres options")
        self.mosaique = Bouton("mosaique", "Mosaïque : disposer toutes les fenêtres 36Frame à l'écran  (Ctrl+M)",
                               texte="Mosaïque")
        self.mosaique.hide()
        # sans bandeau, le nom reste lisible grâce à une ombre portée
        ombre = QGraphicsDropShadowEffect(self.nom)
        ombre.setBlurRadius(6)
        ombre.setOffset(0, 1)
        ombre.setColor(QColor(0, 0, 0, 255))
        self.nom.setGraphicsEffect(ombre)

        ligne = QHBoxLayout()
        ligne.setContentsMargins(0, 0, 0, 0)
        ligne.setSpacing(4)
        for b in (self.zoom_plus, self.zoom_moins, self.un_un, self.recadrer, self.epingle):
            ligne.addWidget(b)
        ligne.addStretch(1)
        for b in (self.precedent, self.lecture, self.suivant):
            ligne.addWidget(b)
        ligne.addStretch(1)
        ligne.addWidget(self.mosaique)
        ligne.addWidget(self.partager)
        ligne.addSpacing(4)
        for b in (self.rot_gauche, self.rot_droite, self.favori, self.options):
            ligne.addWidget(b)

        col = QVBoxLayout(self)
        col.setContentsMargins(10, 6, 10, 8)
        col.setSpacing(4)
        col.addWidget(self.nom)
        col.addWidget(self.bande)
        col.addLayout(ligne)
        self.arrondi = 0
        self.fond = False           # bandeau sombre derrière la barre (option de configuration)
        self._compact = None

    def hauteur(self) -> int:
        return self.sizeHint().height()

    def adapter(self, largeur: int, plusieurs_fenetres: bool):
        """Fenêtre étroite (mosaïque) : on retire progressivement ce qui est secondaire."""
        self.mosaique.setVisible(plusieurs_fenetres and largeur >= 420)
        etroit = largeur < 640 + (90 if plusieurs_fenetres else 0)
        for b, texte in ((self.partager, "Partager"), (self.mosaique, "Mosaïque")):
            b.compacter(etroit, texte)
        for b in (self.zoom_plus, self.zoom_moins, self.un_un):
            b.setVisible(largeur >= 470)
        self.recadrer.setVisible(largeur >= 330 and self.recadrer_utile)    # gardé plus longtemps que le zoom
        self.epingle.setVisible(largeur >= 260)
        for b in (self.rot_gauche, self.rot_droite):
            b.setVisible(largeur >= 360)
        self.partager.setVisible(largeur >= 300)
        self.bande.setVisible(largeur >= 260)
        self.nom.setVisible(largeur >= 200)

    def mousePressEvent(self, e):
        # zone vide de la barre : elle se comporte comme le fond (déplace la fenêtre)
        fen = self.window()
        if (e.button() == Qt.MouseButton.LeftButton and not fen.isFullScreen()
                and fen.windowHandle() is not None):
            fen.windowHandle().startSystemMove()

    def paintEvent(self, e):
        if not self.fond:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        chemin = QPainterPath()
        chemin.addRoundedRect(QRectF(self.rect()), self.arrondi, self.arrondi)
        g = QLinearGradient(QPointF(0, 0), QPointF(0, self.height()))
        g.setColorAt(0, QColor(30, 30, 30, 205))
        g.setColorAt(1, QColor(18, 18, 18, 235))
        p.fillPath(chemin, g)


class BoutonsFenetre(_Panneau):
    """Réduire / plein écran / fermer, en haut à droite (la fenêtre n'a pas de cadre)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.reduire = Bouton("reduire", "Réduire")
        self.plein = Bouton("plein_ecran", "Plein écran  (F11 / double-clic)")
        self.fermer = Bouton("fermer", "Fermer  (Échap)")
        l = QHBoxLayout(self)
        l.setContentsMargins(6, 6, 6, 6)
        l.setSpacing(4)
        for b in (self.reduire, self.plein, self.fermer):
            l.addWidget(b)
        self.adjustSize()
