"""Fenêtre principale : sans cadre, translucide, mode fenêtré / plein écran, diaporama."""

from __future__ import annotations

import copy
import os
import sys

from PySide6.QtCore import QElapsedTimer, QEvent, QFile, QPoint, QPointF, QRect, QSize, Qt, QThread, QTimer
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QImage, QKeySequence, QMovie, QShortcut
from PySide6.QtWidgets import QApplication, QCheckBox, QFileDialog, QLabel, QMenu, QMessageBox, QWidget

from . import NOM_APPLI, __version__, actions, veille
from .barre import BarreOutils, BoutonsFenetre
from .chargement import (EXTENSIONS, ChargeurImages, ChargeurMiniatures, dimensions, est_anime,
                         est_image, lister_arborescence, lister_dossier, octets_estimes)
from .config import Configuration
from .icones import icone, icone_appli
from .vue import MARGE_BORD, Vue

TAILLE_MIN = QSize(160, 120)            # petit : la mosaïque peut réduire beaucoup les fenêtres
TAILLE_MIN_OUVERTURE = QSize(520, 360)  # taille minimale à l'ouverture d'une image (mode PICASA)
# Mode adaptatif : la barre d'outils a une largeur FIXE (elle ne bouge pas d'une image à l'autre) et
# la fenêtre est au moins assez large pour l'afficher en entier ; autour d'une petite image, le
# surplus est transparent (invisible).
LARGEUR_BARRE_ADAPTATIF = 780
TAILLE_MIN_ADAPTATIF = QSize(LARGEUR_BARRE_ADAPTATIF + 2 * MARGE_BORD, 320)

STYLE_MENU = """
QMenu { background: #262626; color: #eeeeee; border: 1px solid #444; padding: 4px; }
QMenu::item { padding: 6px 26px 6px 22px; border-radius: 4px; }
QMenu::item:selected { background: #3d6db5; }
QMenu::item:disabled { color: #777; }
QMenu::separator { height: 1px; background: #444; margin: 4px 8px; }
QToolTip { background: #262626; color: #eeeeee; border: 1px solid #555; padding: 3px; }
"""


class Liseuse(QWidget):
    def __init__(self, config: Configuration, gestion=None):
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.config = config
        self.gestion = gestion
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowIcon(icone_appli())
        self.setWindowTitle(NOM_APPLI)
        self.setMinimumSize(TAILLE_MIN)
        self.setAcceptDrops(True)
        self.setStyleSheet(STYLE_MENU)

        self.chemins: list[str] = []
        self.index = -1
        self.collection = ""            # "" = dossier, sinon nom affiché (ex. « Favoris »)
        self.racines: list[str] = []    # dossiers ouverts avec leurs sous-dossiers
        self.multi = False              # plusieurs fenêtres ouvertes
        self.rotations: dict[str, int] = {}
        self.film: QMovie | None = None
        self._premiere_image_film = True
        self.plein_ecran = False
        self._geometrie_fenetre: QRect | None = None
        self._diapo_plein_ecran_auto = False

        # cache partagé entre toutes les fenêtres
        self.images = gestion.images if gestion else ChargeurImages(self)
        self.images.prete.connect(self._image_prete)
        self.miniatures = gestion.miniatures if gestion else ChargeurMiniatures(self)

        self.vue = Vue(self)
        self.barre = BarreOutils(self.miniatures, self)
        self.btn_fenetre = BoutonsFenetre(self)
        self.toast = QLabel(self)
        self.toast.setStyleSheet("background: rgba(20,20,20,220); color: #f0f0f0; padding: 8px 14px;"
                                 "border-radius: 8px;")
        self.toast.hide()
        self._minuteur_toast = QTimer(self, singleShot=True, timeout=self.toast.hide)

        self.diaporama = QTimer(self, timeout=self._diapo_suivante)

        # épingle (toujours au premier plan) : réaffirmée chaque seconde, car un jeu qui se
        # remet lui-même au premier plan passerait sinon devant
        self.epinglee = False
        self._redim_interne = False      # redimensionnement décidé par 36Frame (pas par la souris)
        self._ancre_bas: QPoint | None = None   # bas-centre fixe de la fenêtre (mode adaptatif)
        self._minuteur_epingle = QTimer(self, interval=1000, timeout=self._reaffirmer_epingle)

        self._connecter()
        self._raccourcis()
        self.appliquer_config()

    # ================================================================== câblage
    def _connecter(self):
        b = self.barre
        b.zoom_plus.clicked.connect(lambda: self.vue.zoomer(1.25))
        b.zoom_moins.clicked.connect(lambda: self.vue.zoomer(1 / 1.25))
        b.un_un.clicked.connect(self.vue.basculer_un_un)
        b.recadrer.clicked.connect(self.ajuster_fenetre)
        b.epingle.clicked.connect(self.basculer_epingle)
        self.vue.zoom_change.connect(lambda _z: self._maj_recadrer())
        self.vue.zoom_change.connect(lambda _z: self._suivre_dezoom())
        self.vue.ctrl_molette.connect(self.redimensionner_ensemble)
        b.precedent.clicked.connect(lambda: self.aller_relatif(-1))
        b.suivant.clicked.connect(lambda: self.aller_relatif(1))
        b.lecture.clicked.connect(self.basculer_diaporama)
        b.partager.clicked.connect(lambda: self._montrer_menu(self._menu_partage(), b.partager))
        b.rot_gauche.clicked.connect(lambda: self.tourner(-90))
        b.rot_droite.clicked.connect(lambda: self.tourner(90))
        b.favori.clicked.connect(self._clic_favori)
        b.options.clicked.connect(lambda: self._montrer_menu(self._menu_options(), b.options))
        b.mosaique.clicked.connect(self.mosaique)
        b.favori.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        b.favori.customContextMenuRequested.connect(
            lambda _p: self._montrer_menu(self._menu_ajouter_a(), b.favori))
        b.bande.choisi.connect(self.aller)
        b.bande.choisi_nouvelle.connect(lambda i: self.nouvelle_fenetre(self.chemins[i]))
        b.bande.defiler.connect(self.aller_relatif)

        f = self.btn_fenetre
        f.reduire.clicked.connect(self.showMinimized)
        f.plein.clicked.connect(self.basculer_plein_ecran)
        f.fermer.clicked.connect(self.close)

        self.vue.double_clic.connect(self.basculer_plein_ecran)
        self.vue.clic_fond.connect(self._clic_fond_plein_ecran)
        self.vue.menu_demande.connect(lambda pos: self._menu_options().exec(pos))

    def _raccourcis(self):
        def r(touches, fonction):
            for t in touches if isinstance(touches, (list, tuple)) else [touches]:
                QShortcut(QKeySequence(t), self, fonction)

        r(["Right", "PgDown", "Down"], lambda: self.aller_relatif(1))
        r(["Left", "PgUp", "Up", "Backspace"], lambda: self.aller_relatif(-1))
        r("Home", lambda: self.aller(0))
        r("End", lambda: self.aller(len(self.chemins) - 1))
        r(["+", "=", "Ctrl++", "Ctrl+="], lambda: self.vue.zoomer(1.25))
        r(["-", "Ctrl+-"], lambda: self.vue.zoomer(1 / 1.25))
        r(["1", "Ctrl+1"], self.vue.basculer_un_un)
        r(["0", "Ctrl+0"], self.vue.ajuster)
        r("W", self.ajuster_fenetre)
        r("T", self.basculer_epingle)
        r(["F11", "F", "Return", "Enter"], self.basculer_plein_ecran)
        r("Escape", self._echap)
        r("Space", self.basculer_diaporama)
        r(["Ctrl+L", "Ctrl+Shift+R"], lambda: self.tourner(-90))
        r("Ctrl+R", lambda: self.tourner(90))
        r("Ctrl+D", self.basculer_favori)
        r("Ctrl+C", self.copier_image)
        r("Ctrl+Shift+C", self.copier_fichier)
        r("Ctrl+P", self.imprimer)
        r("Ctrl+O", self.dialogue_ouvrir)
        r("Ctrl+Shift+O", self.dialogue_dossier)
        r("Ctrl+E", lambda: self._chemin() and actions.afficher_dans_dossier(self._chemin()))
        r("Ctrl+Q", self.tout_fermer)
        r("Ctrl+W", self.close)
        r("Ctrl+N", lambda: self.nouvelle_fenetre(self._chemin()))
        r("Ctrl+M", self.mosaique)
        r("Ctrl+G", self.mosaique_dossier)
        r("Delete", lambda: self.supprimer())

    # ================================================================== apparence
    def appliquer_config(self):
        c = self.config
        if self.plein_ecran:
            fond = QColor(c.plein_ecran_couleur)
            fond.setAlpha(round(c.plein_ecran_opacite * 2.55))
        elif c.fenetre_fond == "transparent" or c.mode_affichage == "adaptatif":
            fond = QColor(0, 0, 0, 0)      # adaptatif : la fenêtre épouse l'image, pas de fond
        else:
            fond = QColor(c.fenetre_couleur)
            fond.setAlpha(round(c.fenetre_opacite * 2.55))
        self.vue.fond = fond
        self.vue.plein_ecran = self.plein_ecran
        self.vue.lissage = c.lissage
        self.vue.ombre = c.ombre_image
        self.vue.mode_transparence = c.transparence
        self.vue.ctrl_redimensionne = c.mode_affichage == "adaptatif"
        self.barre.fond = c.barre_fond
        self.barre.update()
        self.vue._lisse = None
        self.vue._minuteur_lisse.start(0)
        self.barre.delai_masquage = self.btn_fenetre.delai_masquage = c.barre_delai_masquage
        self.btn_fenetre.plein.changer_icone("fenetre" if self.plein_ecran else "plein_ecran")
        self.btn_fenetre.plein.setToolTip("Mode fenêtré  (F11 / Échap)" if self.plein_ecran
                                          else "Plein écran  (F11 / double-clic)")
        self._placer_panneaux()
        self._maj_recadrer()
        self.vue.update()

    def _placer_panneaux(self):
        w, h = self.width(), self.height()
        self.vue.setGeometry(0, 0, w, h)
        m = MARGE_BORD
        # (on laisse en fenêtré la marge de redimensionnement libre autour de la barre)
        if self.plein_ecran:
            bw = min(1100, w - 40)
        elif self.config.mode_affichage == "adaptatif":
            bw = min(LARGEUR_BARRE_ADAPTATIF, w - 2 * m)     # largeur fixe : la barre reste en place
        else:
            bw = w - 2 * m
        self.barre.adapter(bw, self.multi)
        bh = self.barre.hauteur()
        self.barre.arrondi = 10 if self.plein_ecran else 8
        if self.plein_ecran:
            self.barre.setGeometry((w - bw) // 2, h - bh - 16, bw, bh)
        else:
            self.barre.setGeometry((w - bw) // 2, h - bh - m, bw, bh)
        self.btn_fenetre.adjustSize()
        bf = self.btn_fenetre.size()
        self.btn_fenetre.move(w - bf.width() - MARGE_BORD - 2, MARGE_BORD + 2)
        self.btn_fenetre.raise_()
        self.barre.raise_()
        self._placer_toast()

    # ---------------------------------------------------------------- mode adaptatif
    def adaptatif(self) -> bool:
        """La fenêtre épouse l'image (sinon : mode PICASA, fenêtre fixe et fond gris)."""
        return (self.config.mode_affichage == "adaptatif" and not self.plein_ecran
                and not self.isMaximized() and not self.isMinimized())

    def _geometrie_interne(self, rect: QRect):
        self._redim_interne = True
        try:
            self.setGeometry(rect)
        finally:
            self._redim_interne = False

    def _ecran(self):
        """Écran de la fenêtre ; avant son affichage : celui choisi à l'ouverture (sous la souris)."""
        if not self.isVisible() and getattr(self, "_ecran_ouverture", None) is not None:
            return self._ecran_ouverture
        return self.screen() or QGuiApplication.screenAt(self.geometry().center()) or QGuiApplication.primaryScreen()

    def _zone_ecran(self) -> QRect:
        return self._ecran().availableGeometry()

    def _point_ancrage(self) -> QPoint:
        """Bas-centre de la fenêtre : c'est là qu'est la barre d'outils. En mode adaptatif, la
        fenêtre change de taille autour de ce point, pour que la barre (et les miniatures sous la
        souris) ne bougent pas d'une image à l'autre."""
        if self._ancre_bas is None:
            g = self.geometry()
            self._ancre_bas = QPoint(g.center().x(), g.bottom())
        return self._ancre_bas

    def _rect_ancre(self, l: int, h: int) -> QRect:
        """Rectangle l x h dont le bas-centre est sur le point d'ancrage (ramené dans l'écran)."""
        ancre = self._point_ancrage()
        dispo = self._zone_ecran()
        l, h = min(l, dispo.width()), min(h, dispo.height())
        r = QRect(ancre.x() - l // 2, ancre.y() - h + 1, l, h)
        r.moveLeft(max(dispo.left(), min(r.left(), dispo.right() - l + 1)))
        r.moveTop(max(dispo.top(), min(r.top(), dispo.bottom() - h + 1)))
        return r

    def moveEvent(self, e):
        super().moveEvent(e)
        if not self._redim_interne:
            self._ancre_bas = None          # déplacée à la main : nouveau point d'ancrage

    def _rect_autour(self, centre: QPoint, l: int, h: int) -> QRect:
        """Rectangle l x h centré sur « centre », ramené dans l'écran."""
        dispo = self._zone_ecran()
        l, h = min(l, dispo.width()), min(h, dispo.height())
        r = QRect(0, 0, l, h)
        r.moveCenter(centre)
        r.moveLeft(max(dispo.left(), min(r.left(), dispo.right() - l + 1)))
        r.moveTop(max(dispo.top(), min(r.top(), dispo.bottom() - h + 1)))
        return r

    def taille_adaptee(self, taille_px: QSize) -> QSize:
        """Taille de fenêtre pour une image : sa taille réelle, sans dépasser N % de l'écran."""
        dispo = self._zone_ecran()
        d = self._ecran().devicePixelRatio()
        logique = QSize(max(1, round(taille_px.width() / d)), max(1, round(taille_px.height() / d)))
        pct = max(30, min(100, self.config.fenetre_max_ecran)) / 100
        maxi = QSize(int(dispo.width() * pct), int(dispo.height() * pct))
        if logique.width() > maxi.width() or logique.height() > maxi.height():
            logique = logique.scaled(maxi, Qt.AspectRatioMode.KeepAspectRatio)
        return logique.expandedTo(TAILLE_MIN_ADAPTATIF)

    def adapter_fenetre(self, taille_px: QSize):
        """Nouvelle image (ou rotation) : la fenêtre prend sa taille, autour du même centre."""
        if not self.adaptatif() or not taille_px.isValid() or taille_px.isEmpty():
            return
        t = self.taille_adaptee(taille_px)
        self.vue.agrandir_auto = False
        self.vue.auto = True
        if t != self.size():
            self._geometrie_interne(self._rect_ancre(t.width(), t.height()))

    def _readapter(self):
        """Après un changement de réglage : la fenêtre reprend la taille de son image."""
        v = self.vue
        t = v.image.size() if v.image is not None else v.taille_attendue
        if self.adaptatif() and t.isValid():
            self.adapter_fenetre(t)
            v.ajuster()

    def _suivre_dezoom(self):
        """Dézoom à la molette : quand l'image devient plus petite que la fenêtre, la fenêtre
        rétrécit avec elle (elle reste collée à l'image, qu'on déplace donc avec elle)."""
        if not self.adaptatif() or self._redim_interne:
            return
        r = self.vue.rect_image()
        if r.isEmpty():
            return
        l = max(TAILLE_MIN_ADAPTATIF.width(), min(self.width(), round(r.width())))
        h = max(TAILLE_MIN_ADAPTATIF.height(), min(self.height(), round(r.height())))
        if l >= self.width() - 1 and h >= self.height() - 1:
            return
        self._geometrie_interne(self._rect_ancre(l, h))           # la barre ne bouge pas
        self.vue.decalage = QPointF()
        self.vue._ancre = QPointF(self.vue.width() / 2, self.vue.height() / 2)
        self.vue._borner()

    def redimensionner_ensemble(self, facteur: float, _ancre: QPointF | None = None):
        """Ctrl+molette : la fenêtre et l'image grandissent / rétrécissent ensemble,
        en tenant compte du zoom déjà fait."""
        if not self.adaptatif():
            self.vue.zoomer(facteur, _ancre)
            return
        v = self.vue
        v._anim.stop()
        r = v.rect_image()
        if r.isEmpty():
            return
        # image plus petite que la fenêtre (dans les deux sens) : on l'ajuste d'abord à la fenêtre
        if r.width() < self.width() - 1 and r.height() < self.height() - 1:
            v.zoom = v.zoom_ajuste()
            v.decalage = QPointF()
            r = v.rect_image()
        # « boîte » actuelle : la fenêtre, ou l'image si elle est plus étroite dans un sens
        base_l, base_h = min(self.width(), r.width()), min(self.height(), r.height())
        dispo = self._zone_ecran()
        if facteur > 1:
            f = min(facteur, dispo.width() / base_l, dispo.height() / base_h)
        else:
            f = max(facteur, 64 / min(base_l, base_h))        # l'image ne descend pas sous 64 px
        if abs(f - 1) < 1e-3:
            self.notifier("Taille maximale atteinte (écran)." if facteur > 1 else "Taille minimale atteinte.", 1200)
            return
        v.auto = False                    # (sinon la vue recalculerait son zoom au redimensionnement)
        v.zoom *= f
        v.decalage = v.decalage * f
        # la fenêtre suit l'image, sans descendre sous la taille qui affiche toute la barre
        l = max(TAILLE_MIN_ADAPTATIF.width(), round(base_l * f))
        h = max(TAILLE_MIN_ADAPTATIF.height(), round(base_h * f))
        self._redim_interne = True
        try:
            self.setGeometry(self._rect_ancre(l, h))              # bas-centre fixe : la barre ne bouge pas
            v._borner()
            # fenêtre = image : ensuite, l'image suivra la fenêtre si on la redimensionne à la main
            r = v.rect_image()
            colle = abs(r.width() - v.width()) <= 1.5 or abs(r.height() - v.height()) <= 1.5
            v.auto = v.agrandir_auto = colle
            v._lisse = None
            v._minuteur_lisse.start()
            v._montrer_pct(v.zoom)
            v.zoom_change.emit(v.zoom)
        finally:
            self._redim_interne = False
        v.update()

    def nativeEvent(self, type_evenement, message):
        """Windows : pendant un redimensionnement à la souris (mode adaptatif), la fenêtre garde
        les proportions de l'image — elle reste collée à l'image, sans bandes vides."""
        if sys.platform == "win32" and self.config.mode_affichage == "adaptatif" and not self.plein_ecran:
            try:
                from ctypes import wintypes
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == 0x0214 and not self.vue.deborde():          # WM_SIZING
                    r = self.vue.rect_image()
                    if not r.isEmpty():
                        ratio = r.width() / r.height()
                        rect = wintypes.RECT.from_address(msg.lParam)
                        l, h = rect.right - rect.left, rect.bottom - rect.top
                        bord = msg.wParam      # 1 g, 2 d, 3 haut, 4 haut-g, 5 haut-d, 6 bas, 7 bas-g, 8 bas-d
                        if bord in (3, 6):
                            rect.right = rect.left + round(h * ratio)
                        elif bord in (4, 5):
                            rect.top = rect.bottom - round(l / ratio)
                        else:
                            rect.bottom = rect.top + round(l / ratio)
                        return True, 1
            except Exception:
                pass
        return super().nativeEvent(type_evenement, message)

    # ---------------------------------------------------------------- épingle (premier plan)
    def basculer_epingle(self):
        self.epinglee = not self.epinglee
        self._appliquer_epingle()
        b = self.barre.epingle
        b.changer_icone("epingle_active" if self.epinglee else "epingle")
        b.setToolTip(("Désépingler : la fenêtre redevient normale  (T)" if self.epinglee else
                      "Épingler au premier plan : l'image reste au-dessus de tout,\n"
                      "même d'un jeu en plein écran fenêtré  (T)"))
        if self.epinglee:
            self._minuteur_epingle.start()
            self.notifier("📌 Épinglée au premier plan. (Jeu : réglez-le en « plein écran fenêtré / sans bordure ».)",
                          4500)
        else:
            self._minuteur_epingle.stop()
            self.notifier("Épingle retirée.", 1500)

    def _appliquer_epingle(self, reaffirmer: bool = False):
        if sys.platform == "win32":
            # Windows : on change le rang de la fenêtre sans la recréer (pas de clignotement)
            # et sans l'activer (le jeu garde le clavier et la souris).
            import ctypes
            from ctypes import wintypes
            SetWindowPos = ctypes.windll.user32.SetWindowPos
            SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                     ctypes.c_int, ctypes.c_int, ctypes.c_uint]
            HWND_TOPMOST, HWND_NOTOPMOST = wintypes.HWND(-1), wintypes.HWND(-2)
            SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x0001, 0x0002, 0x0010
            SetWindowPos(int(self.winId()), HWND_TOPMOST if self.epinglee else HWND_NOTOPMOST,
                         0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE)
        elif not reaffirmer:
            geo = self.geometry()
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, self.epinglee)
            self.show()                  # (Qt recrée la fenêtre pour appliquer l'option)
            self.setGeometry(geo)

    def _reaffirmer_epingle(self):
        if self.epinglee and self.isVisible() and not self.isMinimized():
            self._appliquer_epingle(reaffirmer=True)

    # ---------------------------------------------------------------- fenêtre = image
    def _taille_recadree(self) -> QRect | None:
        """Rectangle (écran) que prendrait la fenêtre recadrée autour de l'image affichée."""
        r = self.vue.rect_image()
        if r.isEmpty():
            return None
        ecran = self.screen() or QGuiApplication.primaryScreen()
        dispo = ecran.availableGeometry()
        l = max(TAILLE_MIN.width(), min(round(r.width()), dispo.width()))
        h = max(TAILLE_MIN.height(), min(round(r.height()), dispo.height()))
        # l'image reste où elle est à l'écran : la fenêtre se resserre autour d'elle
        centre = self.vue.mapToGlobal(r.center().toPoint())
        cible = QRect(0, 0, l, h)
        cible.moveCenter(centre)
        cible.moveLeft(max(dispo.left(), min(cible.left(), dispo.right() - l + 1)))
        cible.moveTop(max(dispo.top(), min(cible.top(), dispo.bottom() - h + 1)))
        return cible

    def _maj_recadrer(self):
        utile = False
        if not self.plein_ecran and not self.isMaximized():
            cible = self._taille_recadree()
            utile = cible is not None and (abs(cible.width() - self.width()) > 2
                                           or abs(cible.height() - self.height()) > 2)
        if utile != self.barre.recadrer_utile:
            self.barre.recadrer_utile = utile
            self._placer_panneaux()

    def ajuster_fenetre(self):
        """Bouton à côté de 1:1 : la fenêtre prend la taille de l'image affichée (zoom conservé)."""
        if self.plein_ecran:
            return
        cible = self._taille_recadree()
        if cible is None:
            return
        auto, zoom = self.vue.auto, self.vue.zoom
        if self.isMaximized():
            self.showNormal()
        self.setGeometry(cible)
        if not auto:            # zoom choisi à la main : on le garde, image centrée
            self.vue.zoom = zoom
            self.vue.decalage = QPointF()
            self.vue._borner()
            self.vue.update()
        self._maj_recadrer()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.adaptatif() and not self._redim_interne:
            # agrandie / réduite à la main : l'image suit la fenêtre (même au-delà de 100 %) ;
            # le zoom est recalculé par la vue elle-même, une fois à sa nouvelle taille
            self.vue.agrandir_auto = True
        self._placer_panneaux()
        self._maj_recadrer()

    def notifier(self, texte: str, duree_ms: int = 3200):
        self.toast.setText(texte)
        self.toast.adjustSize()
        self._placer_toast()
        self.toast.show()
        self.toast.raise_()
        self._minuteur_toast.start(duree_ms)

    def _placer_toast(self):
        self.toast.move((self.width() - self.toast.width()) // 2, 24)

    # ================================================================== ouverture
    def ouvrir(self, chemin: str):
        chemin = os.path.abspath(chemin)
        if os.path.isdir(chemin):
            self.ouvrir_dossier(chemin)
            return
        liste = lister_dossier(os.path.dirname(chemin))
        if chemin not in liste:      # extension inconnue mais lisible ? on tente quand même
            liste.append(chemin)
        self.config.dernier_dossier = os.path.dirname(chemin)
        self.collection = ""
        self.racines = []
        self._definir_liste(liste, liste.index(chemin))

    def ouvrir_dossier(self, dossier: str):
        """Toutes les images du dossier et de ses sous-dossiers."""
        self.ouvrir_dossiers([dossier])

    def ouvrir_dossiers(self, dossiers: list[str]):
        """Toutes les images de plusieurs dossiers et de leurs sous-dossiers, réunies."""
        dossiers = [os.path.abspath(d) for d in dossiers if os.path.isdir(d)]
        # un dossier déjà inclus dans un autre de la liste serait parcouru deux fois : on l'écarte
        cles = [os.path.normcase(d).rstrip("\\/") + os.sep for d in dossiers]
        racines = []
        for d, c in zip(dossiers, cles):
            if not any(c != a and c.startswith(a) for a in cles) and d not in racines:
                racines.append(d)
        if not racines:
            return
        noms = [os.path.basename(d.rstrip("\\/")) or d for d in racines]
        titre = f"« {noms[0]} »" if len(noms) == 1 else f"{len(noms)} dossiers"
        self.vue.vider(f"Recherche des images dans {titre} et leurs sous-dossiers…\n(Échap pour arrêter)")
        self.vue.repaint()
        chrono = QElapsedTimer()
        chrono.start()
        self._recherche_annulee = False
        self._recherche_en_cours = True
        liste: list[str] = []
        deja = 0

        def progression(n):
            if chrono.elapsed() > 150:          # l'interface reste vivante sur un très gros disque
                chrono.restart()
                self.vue.vider(f"Recherche des images dans {titre}…   {deja + n} trouvée(s)\n"
                               "(Échap pour arrêter et garder celles déjà trouvées)")
                QApplication.processEvents()
            return not self._recherche_annulee

        try:
            for d in racines:
                liste.extend(lister_arborescence(d, progression))
                deja = len(liste)
                if self._recherche_annulee:
                    break
        finally:
            self._recherche_en_cours = False
        if not liste:
            self.vue.vider(f"Aucune image dans {titre} ni dans les sous-dossiers." if not self._recherche_annulee
                           else "Recherche arrêtée avant de trouver une image.")
            return
        self.config.dernier_dossier = racines[0]
        self.config.derniers_dossiers = racines
        self.config.enregistrer()
        self.collection = f"📁 {noms[0]}" if len(noms) == 1 else f"📁 {len(noms)} dossiers"
        self.racines = racines
        self._definir_liste(liste, 0)
        nb_dossiers = len({os.path.dirname(p) for p in liste})
        self.notifier(f"{len(liste)} image(s) dans {nb_dossiers} dossier(s)"
                      + (" — recherche arrêtée." if self._recherche_annulee else "."), 3000)

    def _depart_dossiers(self) -> str:
        return self.racines[0] if self.racines else \
            (os.path.dirname(self._chemin()) if self._chemin() else self.config.dernier_dossier)

    def dialogue_dossier(self):
        """Fenêtre « Sélectionner un dossier » de Windows, où l'on peut en choisir plusieurs
        d'un coup (Ctrl+clic, Maj+clic, Ctrl+A) ; sous-dossiers compris."""
        from .choix_dossiers import choisir_dossiers
        depart = self.racines[0] if self.racines else self.config.dernier_dossier
        if depart and len(self.racines) <= 1:
            depart = os.path.dirname(depart.rstrip("\\/")) or depart   # on montre le dossier parent
        dossiers = choisir_dossiers(self, "Ouvrir un ou plusieurs dossiers (Ctrl+clic pour en choisir plusieurs)",
                                    depart)
        if dossiers:
            self.ouvrir_dossiers(dossiers)

    def dialogue_selection_dossiers(self):
        """Liste de dossiers à composer (plusieurs disques, glisser-déposer, dernière sélection)."""
        from .dialogue_dossiers import DialogueDossiers
        dlg = DialogueDossiers(self._depart_dossiers(), self.config.derniers_dossiers, self)
        if dlg.exec() and dlg.dossiers():
            self.ouvrir_dossiers(dlg.dossiers())

    def dialogue_demarrage(self):
        """Au lancement sans image : une image, ou des dossiers entiers."""
        boite = QMessageBox(QMessageBox.Icon.NoIcon, NOM_APPLI, "Que voulez-vous ouvrir ?", parent=self)
        boite.setInformativeText("Des dossiers : toutes leurs images, sous-dossiers compris.")
        b_image = boite.addButton("Une image…", QMessageBox.ButtonRole.AcceptRole)
        b_dossier = boite.addButton("Un ou plusieurs dossiers…", QMessageBox.ButtonRole.AcceptRole)
        boite.addButton("Annuler", QMessageBox.ButtonRole.RejectRole)
        boite.setDefaultButton(b_image)
        boite.exec()
        if boite.clickedButton() is b_image:
            self.dialogue_ouvrir()
        elif boite.clickedButton() is b_dossier:
            self.dialogue_dossier()
    def ouvrir_favoris(self, depart: str | None = None, dossier: str | None = None):
        """dossier None = « Favoris » ; sinon un dossier de favoris créé par l'utilisateur."""
        liste = [f for f in self.config.liste_favoris(dossier) if os.path.isfile(f)]
        if not liste:
            self.notifier("Ce dossier de favoris est vide." if dossier else
                          "Aucun favori pour l'instant : ★ sur une image pour l'ajouter.")
            return
        self.collection = dossier or "Favoris"
        self.racines = []
        self._definir_liste(liste, liste.index(depart) if depart in liste else 0)

    def _definir_liste(self, liste: list[str], index: int):
        self.chemins = liste
        self.index = index
        self.barre.bande.definir(self.chemins, index)
        self.afficher()

    def dialogue_ouvrir(self):
        motifs = " ".join("*" + e for e in sorted(EXTENSIONS))
        depart = os.path.dirname(self._chemin()) if self._chemin() else self.config.dernier_dossier
        chemin, _ = QFileDialog.getOpenFileName(self, "Ouvrir une image", depart,
                                                f"Images ({motifs});;Tous les fichiers (*)")
        if chemin:
            self.ouvrir(chemin)

    def _chemin(self) -> str | None:
        if 0 <= self.index < len(self.chemins):
            return self.chemins[self.index]
        return None

    def aller(self, index: int):
        if not self.chemins:
            return
        index = max(0, min(len(self.chemins) - 1, index))
        if index == self.index:
            return
        self._sens = 1 if index > self.index else -1
        self.index = index
        self.afficher()
        if self.diaporama.isActive():
            self.diaporama.start()      # repart pour une durée complète

    def aller_relatif(self, pas: int):
        if not self.chemins:
            return
        n = len(self.chemins)
        cible = self.index + pas
        if self.diaporama.isActive() and self.config.diaporama_boucle:
            cible %= n
        self.aller(cible)

    def afficher(self):
        chemin = self._chemin()
        if chemin is None:
            return
        self._arreter_film()
        self.images.proteger(getattr(self, "_protege", None), chemin)
        self._protege = chemin
        self.barre.bande.aller(self.index)
        rotation = self.rotations.get(chemin, 0)
        taille = dimensions(chemin)
        nom = os.path.basename(chemin)
        details = f"{taille.width()} x {taille.height()}" if taille.isValid() else ""
        rang = f"{self.index + 1} / {len(self.chemins)}"
        if self.racines:     # sous-dossiers : on montre où se trouve l'image
            racine = next((r for r in self.racines
                           if os.path.normcase(chemin).startswith(os.path.normcase(r).rstrip("\\/") + os.sep)),
                          self.racines[0])
            rel = os.path.relpath(os.path.dirname(chemin), racine)
            if len(self.racines) > 1:          # plusieurs dossiers : on précise lequel
                rel = os.path.basename(racine.rstrip("\\/")) + ("" if rel == "." else "/" + rel)
            if rel != ".":
                nom = rel.replace("\\", "/") + "/" + nom
            prefixe = f"{self.collection} — "
        else:
            prefixe = f"★ {self.collection} — " if self.collection else ""
        self.barre.nom.setText(f"{prefixe}{nom}  ({details})    {rang}" if details else f"{prefixe}{nom}    {rang}")
        self.setWindowTitle(f"{nom} — {NOM_APPLI}")
        self._maj_favori()

        if taille.isValid():
            t = QSize(taille.height(), taille.width()) if rotation in (90, 270) else taille
            self.adapter_fenetre(t)
        if est_anime(chemin):
            self._lancer_film(chemin, rotation)
        else:
            image = self.images.en_cache(chemin)
            if image is not None:
                self.vue.definir_image(image, nouvelle=True, rotation=rotation)
                self._maj_recadrer()
            else:
                self.vue.definir_apercu(self.miniatures.cache.get(chemin), taille, rotation)
                self.images.demander(chemin)
        self._precharger()

    def _precharger(self):
        """Décode à l'avance les voisines… sauf les énormes, qui feraient exploser la RAM
        pour un gain minime (elles s'affichent d'abord floues, puis nettes une seconde après)."""
        # seulement dans le sens où l'on avance (l'autre voisine, si elle est petite)
        sens = getattr(self, "_sens", 1)
        for d, place in ((sens, self.images.budget // 4), (-sens, 16 * 1024 ** 2)):
            i = self.index + d
            if 0 <= i < len(self.chemins) and not est_anime(self.chemins[i]) \
                    and octets_estimes(self.chemins[i]) <= place:
                self.images.demander(self.chemins[i], prioritaire=False)

    def _image_prete(self, chemin: str, image: QImage):
        if chemin != self._chemin() or self.film is not None:
            return
        if image.isNull():
            self.vue.vider(f"Impossible de lire « {os.path.basename(chemin)} ».")
            return
        self.vue.definir_image(image, nouvelle=True, rotation=self.rotations.get(chemin, 0))
        self._maj_recadrer()

    # ---------------------------------------------------------------- animations
    def _lancer_film(self, chemin: str, rotation: int):
        film = QMovie(chemin, parent=self)
        film.setCacheMode(QMovie.CacheMode.CacheNone)
        self.film = film
        self._premiere_image_film = True
        self.vue.rotation = rotation
        film.frameChanged.connect(self._image_film)
        film.start()
        if not film.isValid():
            self._arreter_film()
            self.vue.vider(f"Impossible de lire « {os.path.basename(chemin)} ».")

    def _image_film(self, _n):
        if self.film is None:
            return
        image = self.film.currentImage()
        if image.isNull():
            return
        if self._premiere_image_film:
            QTimer.singleShot(0, self._maj_recadrer)
        self.vue.definir_image(image, nouvelle=self._premiere_image_film)
        self._premiere_image_film = False

    def _arreter_film(self):
        if self.film is not None:
            self.film.stop()
            self.film.frameChanged.disconnect(self._image_film)
            self.film.setFileName("")       # ferme le fichier tout de suite (sinon : à la destruction)
            self.film.deleteLater()
            self.film = None

    # ================================================================== actions
    def tourner(self, degres: int):
        chemin = self._chemin()
        if chemin is None:
            return
        self.rotations[chemin] = (self.rotations.get(chemin, 0) + degres) % 360
        self.vue.tourner(degres)
        t = self.vue.image.size() if self.vue.image is not None else self.vue.taille_attendue
        self.adapter_fenetre(t)
        self._maj_recadrer()

    def _maj_favori(self):
        chemin = self._chemin()
        dossiers = [None] + list(self.config.dossiers_favoris)
        dans = [d or "Favoris" for d in dossiers if chemin and self.config.dans_dossier(d, chemin)]
        self.barre.favori.changer_icone("etoile_pleine" if dans else "etoile")
        if self.config.dossiers_favoris:
            info = "Choisir le dossier de favoris de cette image"
            if dans:
                info += "\nDéjà dans : " + ", ".join(dans)
            info += "\nCtrl+D : ajouter / retirer de « Favoris »"
        else:
            info = ("Retirer des favoris  (Ctrl+D)" if dans else "Ajouter aux favoris  (Ctrl+D)") \
                + "\nClic droit : créer un dossier de favoris"
        self.barre.favori.setToolTip(info)

    def _clic_favori(self):
        """Un seul dossier (« Favoris ») : ajout direct. Plusieurs : petit menu pour choisir."""
        if self.config.dossiers_favoris and self._chemin():
            self._montrer_menu(self._menu_ajouter_a(), self.barre.favori)
        else:
            self.basculer_favori()

    def basculer_favori(self):
        chemin = self._chemin()
        if chemin is None:
            return
        etat = self.config.basculer_favori(chemin)
        self._maj_favori()
        self.notifier("★ Ajoutée aux favoris" if etat else "Retirée des favoris", 1600)

    def image_courante(self) -> QImage | None:
        return self.vue.image

    def copier_image(self):
        if self.vue.image is not None:
            actions.copier_image(self.vue.image)
            self.notifier("Image copiée dans le presse-papiers.")

    def copier_fichier(self):
        if self._chemin():
            actions.copier_fichier(self._chemin())
            self.notifier("Fichier copié : collez-le (Ctrl+V) dans Discord, un mail, un dossier…")

    def imprimer(self):
        if self.vue.image is not None:
            actions.imprimer(self.vue.image, self, os.path.basename(self._chemin() or ""))

    # ---------------------------------------------------------------- menus
    def _montrer_menu(self, menu: QMenu, bouton: QWidget):
        self.barre.garder_visible = True
        self.barre.montrer()
        # menu au-dessus du bouton, aligné sur son bord droit
        taille = menu.sizeHint()
        menu.exec(bouton.mapToGlobal(QPoint(bouton.width() - taille.width(), -taille.height() - 4)))
        self.barre.garder_visible = False
        if not self.barre.rect().contains(self.barre.mapFromGlobal(QCursor.pos())):
            self.barre.masquer()

    def _menu_partage(self) -> QMenu:
        m = QMenu(self)
        chemin = self._chemin()
        if chemin is None:
            m.addAction("Aucune image").setEnabled(False)
            return m
        m.addAction("Envoyer par e-mail (Outlook, Thunderbird…)",
                    lambda: self.notifier(actions.envoyer_mail(chemin), 5000))
        m.addAction("Envoyer sur Discord", lambda: self.notifier(actions.envoyer_discord(chemin), 5000))
        m.addSeparator()
        m.addAction("Copier le fichier (à coller dans n'importe quelle appli)\tCtrl+Maj+C", self.copier_fichier)
        m.addAction("Copier l'image\tCtrl+C", self.copier_image)
        m.addSeparator()
        m.addAction("Afficher dans le dossier\tCtrl+E", lambda: actions.afficher_dans_dossier(chemin))
        return m

    def _menu_options(self) -> QMenu:
        m = QMenu(self)
        chemin = self._chemin()
        m.addAction(icone("mosaique"), "Mosaïque Dossier\tCtrl+G", self.mosaique_dossier) \
            .setEnabled(len(self.chemins) > 1)
        m.addSeparator()
        m.addAction("Ouvrir une image…\tCtrl+O", self.dialogue_ouvrir)
        m.addAction("Ouvrir des dossiers (sous-dossiers compris)…\tCtrl+Maj+O", self.dialogue_dossier)
        m.addAction("Composer une sélection de dossiers (plusieurs disques)…", self.dialogue_selection_dossiers)
        if self.racines and self._chemin():
            m.addAction("Revenir au seul dossier de cette image", lambda c=self._chemin(): self.ouvrir(c))
        m.addAction("Ouvrir dans une nouvelle fenêtre\tCtrl+N",
                    lambda: self.nouvelle_fenetre(chemin)).setEnabled(chemin is not None)
        m.addAction("Nouvelle fenêtre (choisir une image)…", lambda: self.nouvelle_fenetre(None, choisir=True))
        if self.multi:
            mos = m.addMenu(icone("mosaique"), "Mosaïque\tCtrl+M")
            self._remplir_menu_mosaique(mos)
        m.addSeparator()

        m.addMenu(self._menu_favoris())
        m.addSeparator()

        avec = m.addMenu("Ouvrir avec")
        avec.setEnabled(chemin is not None)
        apps = actions.applications_detectees() + [a for a in self.config.applications if a.get("chemin")]
        for a in apps:
            avec.addAction(a["nom"], lambda a=a: actions.ouvrir_avec(a["chemin"], chemin)
                           or self.notifier(f"Impossible de lancer {a['nom']}."))
        avec.addSeparator()
        avec.addAction("Autre application…", lambda: actions.ouvrir_avec_choix_systeme(chemin))
        avec.addAction("Ajouter un logiciel à cette liste…", self.ouvrir_configuration)

        m.addAction("Afficher dans le dossier\tCtrl+E",
                    lambda: actions.afficher_dans_dossier(chemin)).setEnabled(chemin is not None)
        m.addAction("Copier l'image\tCtrl+C", self.copier_image).setEnabled(self.vue.image is not None)
        m.addAction("Imprimer…\tCtrl+P", self.imprimer).setEnabled(self.vue.image is not None)
        m.addSeparator()
        m.addAction("Supprimer (mettre à la corbeille)\tSuppr", lambda: self.supprimer()) \
            .setEnabled(chemin is not None)
        m.addSeparator()
        m.addAction(("Mode fenêtré" if self.plein_ecran else "Plein écran") + "\tF11", self.basculer_plein_ecran)
        a = m.addAction("Épingler au premier plan\tT", self.basculer_epingle)
        a.setCheckable(True)
        a.setChecked(self.epinglee)
        m.addAction("Configuration…", self.ouvrir_configuration)
        if sys.platform == "win32":
            m.addAction("Visionneuse par défaut de Windows…", self.ouvrir_configuration)
        m.addAction(f"À propos de {NOM_APPLI}", self._a_propos)
        m.addSeparator()
        m.addAction("Fermer cette fenêtre\tCtrl+W", self.close)
        if self.multi:
            m.addAction("Fermer toutes les fenêtres\tCtrl+Q", self.tout_fermer)
        return m

    # ---------------------------------------------------------------- favoris
    def _menu_ajouter_a(self, parent: QMenu | None = None) -> QMenu:
        """Cases à cocher : dans quels dossiers de favoris se trouve l'image."""
        m = parent.addMenu("Ajouter cette image à") if parent else QMenu(self)
        chemin = self._chemin()
        m.setEnabled(chemin is not None)
        if chemin is None:
            return m
        for dossier in [None] + sorted(self.config.dossiers_favoris, key=str.casefold):
            a = m.addAction("★ Favoris" if dossier is None else dossier)
            a.setCheckable(True)
            a.setChecked(self.config.dans_dossier(dossier, chemin))
            a.toggled.connect(lambda oui, d=dossier: self._classer(d, oui))
        m.addSeparator()
        m.addAction("Nouveau dossier de favoris…", self._nouveau_dossier_favoris)
        return m

    def _menu_favoris(self) -> QMenu:
        fav = QMenu("Favoris", self)
        fav.setIcon(icone("etoile_pleine"))
        self._menu_ajouter_a(fav)
        fav.addSeparator()
        if self.collection and self._chemin():
            fav.addAction("Revenir au dossier de l'image", lambda c=self._chemin(): self.ouvrir(c))
            fav.addSeparator()

        def sous_menu(nom_affiche: str, dossier: str | None):
            liste = self.config.liste_favoris(dossier)
            existants = [p for p in liste if os.path.isfile(p)]
            sm = fav.addMenu(f"{nom_affiche}  ({len(existants)})")
            sm.addAction("Parcourir ce dossier", lambda: self.ouvrir_favoris(None, dossier)) \
                .setEnabled(bool(existants))
            sm.addAction("Parcourir dans une nouvelle fenêtre",
                         lambda: self.nouvelle_fenetre(existants[0], favoris=dossier or "")) \
                .setEnabled(bool(existants))
            if existants:
                sm.addSeparator()
                for p in existants[-25:][::-1]:
                    sm.addAction(os.path.basename(p), lambda p=p: self.ouvrir_favoris(p, dossier)).setToolTip(p)
            sm.addSeparator()
            sm.addAction("Vider les favoris…" if dossier is None else "Vider ce dossier…",
                         lambda: self._vider_favoris(dossier)).setEnabled(bool(liste))
            if dossier is not None:
                sm.addAction("Renommer…", lambda: self._renommer_dossier_favoris(dossier))
                sm.addAction("Supprimer ce dossier de favoris…", lambda: self._supprimer_dossier_favoris(dossier))

        sous_menu("★ Favoris", None)
        for nom in sorted(self.config.dossiers_favoris, key=str.casefold):
            sous_menu(nom, nom)
        fav.addSeparator()
        fav.addAction("Nouveau dossier de favoris…", lambda: self._nouveau_dossier_favoris(ajouter=False))
        tous = self.config.favoris + [p for l in self.config.dossiers_favoris.values() for p in l]
        if any(not os.path.isfile(p) for p in tous):
            fav.addAction("Oublier les favoris introuvables", self._nettoyer_favoris)
        return fav

    def _classer(self, dossier: str | None, oui: bool):
        chemin = self._chemin()
        if chemin is None:
            return
        nom = dossier or "Favoris"
        if oui:
            self.config.ajouter_au_dossier(dossier, chemin)
            self.notifier(f"★ Ajoutée à « {nom} »", 1600)
        else:
            self.config.retirer_du_dossier(dossier, chemin)
            self.notifier(f"Retirée de « {nom} »", 1600)
        self._maj_favori_partout()

    def _demander_nom(self, titre: str, texte: str = "") -> str | None:
        from PySide6.QtWidgets import QInputDialog
        nom, ok = QInputDialog.getText(self, titre, "Nom du dossier de favoris :", text=texte)
        nom = nom.strip()
        if not ok or not nom:
            return None
        if nom.casefold() == "favoris" or (nom in self.config.dossiers_favoris and nom != texte):
            self.notifier(f"Le dossier « {nom} » existe déjà.")
            return None
        return nom

    def _vider_favoris(self, dossier: str | None):
        nom = dossier or "Favoris"
        n = len(self.config.liste_favoris(dossier))
        if QMessageBox.question(self, NOM_APPLI, f"Retirer les {n} image(s) de « {nom} » ?\n\n"
                                "Les images elles-mêmes ne sont pas supprimées.") != QMessageBox.StandardButton.Yes:
            return
        if dossier is None:
            self.config.favoris = []
        else:
            self.config.dossiers_favoris[dossier] = []
        self.config.enregistrer()
        self._maj_favori_partout()
        self.notifier(f"« {nom} » est vide.", 2000)

    def _nouveau_dossier_favoris(self, ajouter: bool = True):
        nom = self._demander_nom("Nouveau dossier de favoris")
        if nom is None:
            return
        self.config.dossiers_favoris[nom] = []
        if ajouter and self._chemin():
            self.config.ajouter_au_dossier(nom, self._chemin())
            self.notifier(f"★ Ajoutée au nouveau dossier « {nom} »", 1800)
        else:
            self.config.enregistrer()
            self.notifier(f"Dossier « {nom} » créé : ★ clic droit sur une image pour l'y ranger.", 3000)
        self._maj_favori_partout()

    def _renommer_dossier_favoris(self, ancien: str):
        nom = self._demander_nom("Renommer le dossier de favoris", ancien)
        if nom is None or nom == ancien:
            return
        self.config.dossiers_favoris[nom] = self.config.dossiers_favoris.pop(ancien, [])
        self.config.enregistrer()
        if self.collection == ancien:
            self.collection = nom
            self.afficher()

    def _supprimer_dossier_favoris(self, nom: str):
        n = len(self.config.dossiers_favoris.get(nom, []))
        if QMessageBox.question(self, NOM_APPLI, f"Supprimer le dossier de favoris « {nom} » ({n} image(s)) ?\n\n"
                                "Les images elles-mêmes ne sont pas supprimées.") != QMessageBox.StandardButton.Yes:
            return
        self.config.dossiers_favoris.pop(nom, None)
        self.config.enregistrer()
        self._maj_favori_partout()

    def _maj_favori_partout(self):
        for f in (self.gestion.fenetres if self.gestion else [self]):
            f._maj_favori()

    def _nettoyer_favoris(self):
        self.config.favoris = [f for f in self.config.favoris if os.path.isfile(f)]
        for nom, liste in self.config.dossiers_favoris.items():
            self.config.dossiers_favoris[nom] = [f for f in liste if os.path.isfile(f)]
        self.config.enregistrer()

    # ---------------------------------------------------------------- plusieurs fenêtres
    def nouvelle_fenetre(self, chemin: str | None, choisir: bool = False, favoris: str | None = None):
        if self.gestion is None:
            return
        if choisir:
            motifs = " ".join("*" + e for e in sorted(EXTENSIONS))
            depart = os.path.dirname(self._chemin()) if self._chemin() else self.config.dernier_dossier
            chemin, _ = QFileDialog.getOpenFileName(self, "Ouvrir dans une nouvelle fenêtre", depart,
                                                    f"Images ({motifs});;Tous les fichiers (*)")
            if not chemin:
                return
        f = self.gestion.nouvelle_fenetre(chemin, depuis=self)
        if favoris is not None:
            f.ouvrir_favoris(chemin, favoris or None)
        if chemin and chemin in f.chemins:
            f.rotations[chemin] = self.rotations.get(chemin, 0)

    # ---------------------------------------------------------------- suppression
    def supprimer(self, chemin: str | None = None, parent: QWidget | None = None) -> bool:
        """Met l'image à la corbeille (récupérable), puis passe à la suivante."""
        chemin = chemin or self._chemin()
        if not chemin or not os.path.exists(chemin):
            return False
        parent = parent or self
        nom = os.path.basename(chemin)
        if self.config.confirmer_suppression:
            boite = QMessageBox(QMessageBox.Icon.Question, NOM_APPLI,
                                f"Mettre « {nom} » à la corbeille ?", parent=parent)
            oui = boite.addButton("Mettre à la corbeille", QMessageBox.ButtonRole.AcceptRole)
            boite.addButton("Annuler", QMessageBox.ButtonRole.RejectRole)
            ne_plus = QCheckBox("Ne plus demander")
            boite.setCheckBox(ne_plus)
            boite.setDefaultButton(oui)
            boite.exec()
            if boite.clickedButton() is not oui:
                return False
            if ne_plus.isChecked():
                self.config.confirmer_suppression = False
                self.config.enregistrer()
        if chemin == self._chemin():
            self._arreter_film()            # un GIF en cours de lecture garde le fichier ouvert
        ok = QFile.moveToTrash(chemin)
        if not ok:      # un décodage en arrière-plan lisait peut-être le fichier : on réessaie
            QThread.msleep(250)
            ok = QFile.moveToTrash(chemin)
        if not ok:
            self.notifier(f"Impossible de supprimer « {nom} » (fichier protégé ou utilisé ?).", 4000)
            return False
        if self.gestion is not None:
            self.gestion.fichier_supprime(chemin)
        else:
            self.retirer_chemin(chemin)
        self.notifier(f"« {nom} » est dans la corbeille.", 2200)
        return True

    def retirer_chemin(self, chemin: str):
        """Le fichier n'existe plus : on le retire de la liste et on passe à l'image suivante."""
        mos = getattr(self, "_mosaique_dossier", None)
        if mos is not None:
            try:
                mos.retirer(chemin)
            except RuntimeError:        # mosaïque déjà fermée
                self._mosaique_dossier = None
        if chemin not in self.chemins:
            return
        i = self.chemins.index(chemin)
        courant = i == self.index
        self.chemins.pop(i)
        self.rotations.pop(chemin, None)
        if i < self.index:
            self.index -= 1
        if not self.chemins:
            self.index = -1
            self._arreter_film()
            self.barre.bande.definir(self.chemins, -1)
            self.barre.nom.setText("")
            self.vue.vider("Plus aucune image ici. Ctrl+O pour en ouvrir une autre.")
            return
        self.index = min(self.index, len(self.chemins) - 1)
        self.barre.bande.definir(self.chemins, self.index)
        if courant:
            self.afficher()
        else:
            self.barre.bande.update()

    def mosaique_dossier(self):
        """Toutes les images du dossier (ou du dossier de favoris) en mosaïque plein écran."""
        if len(self.chemins) < 2:
            self.notifier("Une seule image dans ce dossier.")
            return
        from .mosaique_dossier import MosaiqueDossier

        self.arreter_diaporama()
        mos = MosaiqueDossier(self, list(self.chemins), self.index)
        mos.image_choisie.connect(lambda c: c in self.chemins and self.aller(self.chemins.index(c)))
        mos.image_nouvelle_fenetre.connect(self.nouvelle_fenetre)
        self._mosaique_dossier = mos
        if self.film is not None:
            self.film.setPaused(True)        # cachée derrière la mosaïque : inutile de l'animer
        mos.montrer()

    def reprendre_film(self):
        if self.film is not None and not self.isMinimized():
            self.film.setPaused(False)

    def changeEvent(self, e):
        # fenêtre réduite : l'animation s'arrête (processeur), et repart quand on la rouvre
        if e.type() == QEvent.Type.WindowStateChange and self.film is not None:
            self.film.setPaused(self.isMinimized() or getattr(self, "_mosaique_dossier", None) is not None)
        super().changeEvent(e)

    def maj_multi(self, multi: bool):
        self.multi = multi
        self._placer_panneaux()

    def mosaique(self, mode: str | None = None):
        if self.gestion is None or len(self.gestion.fenetres) < 2:
            self.notifier("Ouvrez au moins deux fenêtres (Ctrl+N, ou clic molette sur une miniature).")
            return
        self.gestion.mosaique(mode, depuis=self)

    def _remplir_menu_mosaique(self, menu: QMenu):
        from .gestion import MODES_MOSAIQUE
        for cle, texte in MODES_MOSAIQUE.items():
            a = menu.addAction(texte, lambda c=cle: self.mosaique(c))
            a.setCheckable(True)
            a.setChecked(cle == self.config.mosaique_mode)

    def taille_native(self) -> tuple[float, float]:
        """Taille de l'image à 100 % (pixels logiques), au moins la taille minimale de fenêtre."""
        t = self.vue._taille_image()
        if t.isEmpty():
            return (640.0, 480.0)
        w, h = t.width(), t.height()
        e = max(1.0, TAILLE_MIN.width() / w, TAILLE_MIN.height() / h)
        return (w * e, h * e)

    def placer(self, rect: QRect):
        """Position imposée par la mosaïque : fenêtré, image ajustée à la fenêtre."""
        self.arreter_diaporama()
        if self.plein_ecran:
            self.quitter_plein_ecran()
        if self.isMinimized() or self.isMaximized():
            self.showNormal()
        # jamais plus grande que l'image à 100 % (sinon du fond gris apparaîtrait autour)
        t = self.vue._taille_image()
        if not t.isEmpty() and (rect.width() > t.width() or rect.height() > t.height()):
            centre = rect.center()
            rect = QRect(0, 0, round(t.width()), round(t.height()))
            rect.moveCenter(centre)
        self._geometrie_interne(rect)
        self.vue.ajuster()

    def tout_fermer(self):
        for f in list(self.gestion.fenetres if self.gestion else [self]):
            f.close()
    def ouvrir_configuration(self):
        from .dialogue_config import DialogueConfig

        sauvegarde = copy.deepcopy(self.config.__dict__)
        dlg = DialogueConfig(self.config, self)
        dlg.setStyleSheet("")
        fenetres = self.gestion.fenetres if self.gestion else [self]
        dlg.apercu.connect(lambda: [f.appliquer_config() for f in fenetres])
        if not dlg.exec():
            self.config.__dict__.update(sauvegarde)
        for f in fenetres:
            f.appliquer_config()
            f._readapter()
        if self.diaporama.isActive():
            self.diaporama.setInterval(int(self.config.diaporama_delai * 1000))

    def _a_propos(self):
        QMessageBox.about(self, NOM_APPLI,
                          f"<b>{NOM_APPLI}</b> {__version__}<br>Liseuse d'images inspirée de Picasa.<br><br>"
                          "Molette : zoom • Molette sur les miniatures : arrière = suivante, avant = précédente<br>"
                          "Double-clic / F11 : plein écran • Espace : diaporama • Échap : sortir")

    # ================================================================== modes
    def basculer_plein_ecran(self):
        if self.plein_ecran:
            self.quitter_plein_ecran()
        else:
            self.entrer_plein_ecran()

    def entrer_plein_ecran(self):
        if self.plein_ecran:
            return
        self._geometrie_fenetre = self.geometry()
        self.plein_ecran = True
        self.appliquer_config()
        ecran = self.screen() or QGuiApplication.primaryScreen()
        self.setGeometry(ecran.geometry())
        self.showFullScreen()

    def quitter_plein_ecran(self):
        if not self.plein_ecran:
            return
        self.plein_ecran = False
        self._redim_interne = True
        try:
            self.showNormal()
            if self._geometrie_fenetre is not None:
                self.setGeometry(self._geometrie_fenetre)
        finally:
            self._redim_interne = False
        self.appliquer_config()

    def _clic_fond_plein_ecran(self):
        if self.diaporama.isActive():
            self.arreter_diaporama()
        self.quitter_plein_ecran()

    def _echap(self):
        if getattr(self, "_recherche_en_cours", False):
            self._recherche_annulee = True
            return
        if self.diaporama.isActive():
            self.arreter_diaporama()
            if self._diapo_plein_ecran_auto:
                self.quitter_plein_ecran()
        elif self.plein_ecran:
            self.quitter_plein_ecran()
        elif self.config.echap_ferme:
            self.close()

    # ---------------------------------------------------------------- diaporama
    def basculer_diaporama(self):
        if self.diaporama.isActive():
            self.arreter_diaporama()
        else:
            self.lancer_diaporama()

    def lancer_diaporama(self):
        if len(self.chemins) < 2:
            self.notifier("Une seule image dans le dossier.")
            return
        self._diapo_plein_ecran_auto = self.config.diaporama_plein_ecran and not self.plein_ecran
        if self._diapo_plein_ecran_auto:
            self.entrer_plein_ecran()
        self.diaporama.start(int(self.config.diaporama_delai * 1000))
        if not getattr(self, "_veille_bloquee", False):
            self._veille_bloquee = True
            veille.empecher(True)          # l'écran ne s'éteint pas pendant le diaporama
        self.barre.lecture.changer_icone("pause")
        self.barre.lecture.setToolTip("Arrêter le diaporama  (Espace)")
        self.notifier("Diaporama — Espace ou Échap pour arrêter", 1800)

    def arreter_diaporama(self):
        self.diaporama.stop()
        if getattr(self, "_veille_bloquee", False):
            self._veille_bloquee = False
            veille.empecher(False)
        self.barre.lecture.changer_icone("lecture")
        self.barre.lecture.setToolTip("Diaporama du dossier  (Espace)")

    def _diapo_suivante(self):
        if self.index >= len(self.chemins) - 1 and not self.config.diaporama_boucle:
            self.arreter_diaporama()
            return
        self.aller((self.index + 1) % len(self.chemins))

    # ================================================================== fenêtre
    def taille_initiale(self, chemin: str | None):
        """Fenêtre ajustée à l'image (comme Picasa), sans dépasser 85 % de l'écran."""
        ecran = QGuiApplication.screenAt(self.cursor().pos()) or QGuiApplication.primaryScreen()
        self._ecran_ouverture = ecran
        dispo = ecran.availableGeometry()
        taille = dimensions(chemin) if chemin else QSize()
        if taille.isValid() and not taille.isEmpty() and self.config.mode_affichage == "adaptatif":
            # bas de la fenêtre (= la barre) un peu au-dessus du bas de l'écran ; les images
            # suivantes grandiront vers le haut sans déplacer la barre
            marge = round(dispo.height() * (100 - max(30, min(100, self.config.fenetre_max_ecran))) / 200)
            self._ancre_bas = QPoint(dispo.center().x(), dispo.bottom() - marge)
            t = self.taille_adaptee(taille)
            rect = self._rect_ancre(t.width(), t.height())
        elif taille.isValid() and not taille.isEmpty():
            d = ecran.devicePixelRatio()
            logique = QSize(round(taille.width() / d), round(taille.height() / d))
            taille = logique.scaled(QSize(int(dispo.width() * 0.85), int(dispo.height() * 0.85)),
                                    Qt.AspectRatioMode.KeepAspectRatio) \
                if logique.width() > dispo.width() * 0.85 or logique.height() > dispo.height() * 0.85 else logique
            taille = taille.expandedTo(TAILLE_MIN_OUVERTURE)
            rect = QRect(QPoint(0, 0), taille)
            rect.moveCenter(dispo.center())
        elif len(self.config.geometrie) == 4:
            rect = QRect(*self.config.geometrie)
        else:
            rect = QRect(0, 0, 960, 640)
            rect.moveCenter(dispo.center())
        self._geometrie_interne(rect)

    def showEvent(self, e):
        super().showEvent(e)
        QTimer.singleShot(50, self._accueil)

    def _accueil(self):
        # la barre se montre un instant au démarrage pour qu'on sache qu'elle existe
        if not getattr(self, "_accueilli", False):
            self._accueilli = True
            self.barre.montrer()
            self.barre.masquer()
            self.barre._minuteur.start(1500)

    def closeEvent(self, e):
        self.images.proteger(getattr(self, "_protege", None), None)
        mos = getattr(self, "_mosaique_dossier", None)
        if mos is not None:
            try:
                mos.close()
            except RuntimeError:
                pass
            self._mosaique_dossier = None
        if self.gestion is not None:
            self.gestion.retirer(self)
        self.arreter_diaporama()
        self._arreter_film()
        g = self._geometrie_fenetre if self.plein_ecran and self._geometrie_fenetre else self.geometry()
        self.config.geometrie = [g.x(), g.y(), g.width(), g.height()]
        self.config.enregistrer()
        super().closeEvent(e)

    # glisser-déposer d'un fichier ou d'un dossier
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        dossiers = [u.toLocalFile() for u in e.mimeData().urls() if u.toLocalFile() and os.path.isdir(u.toLocalFile())]
        if len(dossiers) > 1:          # plusieurs dossiers glissés d'un coup : on les réunit
            self.ouvrir_dossiers(dossiers)
            return
        for url in e.mimeData().urls():
            p = url.toLocalFile()
            if p and (os.path.isdir(p) or est_image(p) or os.path.isfile(p)):
                self.ouvrir(p)
                break
