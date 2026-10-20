"""« Mosaïque Dossier » : les images du dossier en plein écran, en rangées ajustées, qu'on fait
défiler à la molette (ou automatiquement : Panorama).

Les images gardent leurs proportions. En défilement vertical, chaque rangée remplit la largeur
de l'écran ; en défilement horizontal, chaque colonne remplit la hauteur. Seules les images
visibles (et une demi-page autour) sont décodées, à la taille d'affichage, en arrière-plan.

Le calcul se fait dans un repère abstrait : « p » le long du défilement, « c » en travers.
"""

from __future__ import annotations

import os
from collections import OrderedDict

from PySide6.QtCore import (QBuffer, QElapsedTimer, QIODevice, QObject, QPoint, QPointF, QRectF, QRunnable, Qt,
                            QThreadPool, QTimer, Signal)
from PySide6.QtGui import (QColor, QFont, QGuiApplication, QImage, QImageReader, QKeySequence, QPainter, QPen,
                           QShortcut)
from PySide6.QtWidgets import QHBoxLayout, QMenu, QToolTip, QWidget

from . import actions, veille
from .barre import Bouton, _Panneau
from .chargement import charger_apercu, dimensions, est_anime

PALIERS = (160, 240, 320, 400, 480, 640, 800, 960, 1280, 1600, 1920, 2560)   # hauteurs de décodage
RANGEES_MIN, RANGEES_MAX = 1.2, 10.0
MARGE_BOUT = 16          # marge au début et à la fin du défilement
BUDGET = 256 * 1024 ** 2


def _palier(hauteur_px: float) -> int:
    for p in PALIERS:
        if p >= hauteur_px:
            return p
    return PALIERS[-1]


class _Signaux(QObject):
    fini = Signal(str, int, QImage, bool)       # chemin, palier, image fixe, animée ?
    animation = Signal(str, int, object)       # chemin, palier, [(données, délai ms)]


class _Tache(QRunnable):
    def __init__(self, chemin: str, palier: int, voulus: set, signaux: _Signaux):
        super().__init__()
        self.chemin, self.palier, self.voulus, self.signaux = chemin, palier, voulus, signaux

    def run(self):
        # l'image a quitté l'écran entre-temps : on ne la décode pas
        anime = False
        if (self.chemin, self.palier) in self.voulus:
            image = charger_apercu(self.chemin, self.palier)
            anime = os.path.splitext(self.chemin)[1].lower() in TYPES_ANIMES and est_anime(self.chemin)
        else:
            image = QImage()
        try:
            self.signaux.fini.emit(self.chemin, self.palier, image, anime)
        except RuntimeError:
            pass


# ---------------------------------------------------------------------- animations (GIF, WebP)
TYPES_ANIMES = (".gif", ".webp")
BUDGET_ANIMATIONS = 96 * 1024 ** 2
IMAGES_MAX = 900                  # au-delà, l'animation est tronquée (très longs GIF)


def decoder_animation(chemin: str, hauteur: int, continuer) -> list:
    """Décode toute l'animation UNE fois, à la taille de la tuile, et garde chaque image
    compressée en JPEG (≈ 25 Ko au lieu de 400 Ko) : la relire coûte ~1 ms, alors que
    re-décoder un WebP animé coûte ~13 ms par image. Les animations avec transparence
    restent non compressées pour ne pas perdre l'alpha."""
    lecteur = QImageReader(chemin)
    images, transparente = [], None
    while len(images) < IMAGES_MAX:
        im = lecteur.read()
        if im.isNull():
            break
        if not continuer():
            return []                 # la tuile a quitté l'écran : on abandonne
        delai = lecteur.nextImageDelay()
        delai = 100 if delai <= 0 else max(20, delai)
        if transparente is None:     # avant la réduction : le lissage crée des bords semi-transparents
            transparente = im.hasAlphaChannel() and _a_de_la_transparence(im)
        if not transparente and im.hasAlphaChannel():
            im = im.convertToFormat(QImage.Format.Format_RGB32)
        if im.height() > hauteur:
            im = im.scaledToHeight(hauteur, Qt.TransformationMode.SmoothTransformation)
        if transparente:
            images.append((im.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied), delai))
        else:
            tampon = QBuffer()
            tampon.open(QIODevice.OpenModeFlag.WriteOnly)
            im.save(tampon, "JPG", 85)
            images.append((bytes(tampon.data()), delai))
    return images


def _a_de_la_transparence(im: QImage) -> bool:
    """Vrai si un pixel est (au moins un peu) transparent. Les octets de bourrage en fin de
    ligne sont ignorés."""
    alpha = im.convertToFormat(QImage.Format.Format_Alpha8)
    donnees, bpl, w = bytes(alpha.constBits()), alpha.bytesPerLine(), alpha.width()
    return any(min(donnees[y * bpl:y * bpl + w]) < 250 for y in range(alpha.height()))


class _TacheAnimation(QRunnable):
    def __init__(self, chemin: str, palier: int, voulues: set, signaux: _Signaux):
        super().__init__()
        self.chemin, self.palier, self.voulues, self.signaux = chemin, palier, voulues, signaux

    def run(self):
        cle = (self.chemin, self.palier)
        images = decoder_animation(self.chemin, self.palier, lambda: cle in self.voulues) \
            if cle in self.voulues else []
        try:
            self.signaux.animation.emit(self.chemin, self.palier, images)
        except RuntimeError:
            pass


class _Film:
    """Lecture d'une animation déjà décodée."""
    __slots__ = ("palier", "images", "rang", "prochain", "image", "octets")

    def __init__(self, palier: int, images: list):
        self.palier, self.images, self.rang, self.prochain = palier, images, 0, 0
        self.image = self._decoder(0)
        self.octets = sum(len(d) if isinstance(d, bytes) else d.sizeInBytes() for d, _ in images)

    def _decoder(self, rang: int) -> QImage:
        d = self.images[rang][0]
        return QImage.fromData(d, "JPG") if isinstance(d, bytes) else d

    def rembobiner(self):
        """Retour à la première image (au survol : la souris a quitté la tuile)."""
        if self.rang != 0:
            self.rang, self.image = 0, self._decoder(0)
        self.prochain = 0

    def avancer(self, maintenant: int) -> bool:
        """Passe à l'image suivante si son heure est venue. Renvoie True si l'image a changé."""
        if len(self.images) < 2:
            return False
        if self.prochain == 0:
            self.prochain = maintenant + self.images[0][1]
            return False
        if maintenant < self.prochain:
            return False
        self.rang = (self.rang + 1) % len(self.images)
        self.prochain += self.images[self.rang][1]
        if self.prochain < maintenant - 250:          # gros retard (machine chargée) : on ne rattrape pas
            self.prochain = maintenant + self.images[self.rang][1]
        self.image = self._decoder(self.rang)
        return True


class _BoutonPanorama(_Panneau):
    """Bouton en bas de l'écran, visible seulement quand la souris passe dessus."""

    def __init__(self, parent):
        super().__init__(parent)
        self.bouton = Bouton("lecture", "Panorama : défilement automatique  (Espace)", texte="Panorama")
        l = QHBoxLayout(self)
        l.setContentsMargins(60, 14, 60, 14)    # zone de survol plus large que le bouton
        l.addWidget(self.bouton)
        self.delai_masquage = 500


class MosaiqueDossier(QWidget):
    image_choisie = Signal(str)          # clic : ouvrir cette image dans la liseuse
    image_nouvelle_fenetre = Signal(str)

    def __init__(self, liseuse, chemins: list[str], index: int):
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMouseTracking(True)
        self.setWindowTitle("Mosaïque Dossier — 36Frame")
        self.setWindowIcon(liseuse.windowIcon())
        self.setStyleSheet(liseuse.styleSheet())      # menus sombres
        self.liseuse = liseuse
        self.config = liseuse.config
        self.chemins = chemins
        self.courant = index
        self.miniatures = liseuse.miniatures
        self.horizontal = self.config.mosaique_dossier_orientation == "horizontale"

        rot = liseuse.rotations
        # largeur / hauteur de chaque image (lecture des en-têtes seulement, en parallèle :
        # un dossier ouvert avec ses sous-dossiers peut compter des milliers d'images)
        def ratio(c):
            t = dimensions(c)
            r = t.width() / t.height() if t.isValid() and t.height() > 0 else 1.5
            if rot.get(c, 0) in (90, 270):
                r = 1 / r
            return max(0.1, min(10.0, r))

        if len(chemins) > 200:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=min(16, (os.cpu_count() or 4) * 2)) as ex:
                self.ratios = list(ex.map(ratio, chemins, chunksize=64))
        else:
            self.ratios = [ratio(c) for c in chemins]

        # rangées (ou colonnes) : (p, épaisseur, [(index, c, longueur)])
        self.rangees: list[tuple[float, float, list[tuple[int, float, float]]]] = []
        self.longueur_totale = 0.0
        self.defilement = 0.0
        self.cible = 0.0
        self._survol = -1
        self._appui: QPointF | None = None
        self._ferme = False
        self._panorama_actif = False

        self._cache: OrderedDict[str, tuple[int, QImage]] = OrderedDict()
        self._en_cours: set[tuple[str, int]] = set()
        self._voulus: set[tuple[str, int]] = set()
        self._priorite = 0
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(max(2, min(6, (os.cpu_count() or 4) - 1)))
        self._signaux = _Signaux(self)
        self._signaux.fini.connect(self._recu)
        self._signaux.animation.connect(self._animation_recue)

        # animations : décodées à part (tâches longues), lues par une horloge commune
        self._animes: set[str] = set()                  # fichiers reconnus comme animés
        self._films: OrderedDict[str, _Film] = OrderedDict()
        self._films_en_cours: set[tuple[str, int]] = set()
        self._films_voulus: set[tuple[str, int]] = set()
        self._pool_anim = QThreadPool(self)
        # décodage des animations : la moitié des cœurs (le reste pour l'affichage et le système)
        self._pool_anim.setMaxThreadCount(max(2, (os.cpu_count() or 4) // 2))
        self._horloge = QElapsedTimer()
        self._horloge.start()
        self._minuteur_films = QTimer(self, interval=15, timeout=self._pas_films)

        self._anim = QTimer(self, interval=8, timeout=self._pas)
        self._anim.setTimerType(Qt.TimerType.PreciseTimer)
        self._chrono_defil = QElapsedTimer()
        self._vitesse = 0.0
        self._minuteur_pastille = QTimer(self, singleShot=True, interval=1200, timeout=self.update)

        # Panorama
        self._panorama = QTimer(self, interval=16, timeout=self._pas_panorama)     # 60 images/s
        self._chrono = QElapsedTimer()
        self.btn_panorama = _BoutonPanorama(self)
        self.btn_panorama.bouton.clicked.connect(self.basculer_panorama)

        for touches, f in ((["Escape", "Return", "Enter"], self.close),
                           (["PgDown", "Down", "Right"], lambda: self.defiler(self._pas_page(1))),
                           (["PgUp", "Up", "Left"], lambda: self.defiler(self._pas_page(-1))),
                           (["Space"], self.basculer_panorama),
                           (["Home"], lambda: self.aller_a(0)),
                           (["End"], lambda: self.aller_a(self.longueur_totale)),
                           (["+", "=", "Ctrl++"], lambda: self.changer_rangees(-1)),
                           (["-", "Ctrl+-"], lambda: self.changer_rangees(1)),
                           (["Delete"], lambda: self.supprimer(self._survol))):
            for t in touches:
                QShortcut(QKeySequence(t), self, f)

        ecran = liseuse.screen() or QGuiApplication.primaryScreen()
        self.setGeometry(ecran.geometry())

    # ------------------------------------------------------------------ repère
    def _vue(self) -> float:
        """Longueur visible le long du défilement."""
        return self.width() if self.horizontal else self.height()

    def _travers(self) -> float:
        return self.height() if self.horizontal else self.width()

    def _rect_abstrait(self, c: float, p: float, longueur: float, epaisseur: float) -> QRectF:
        if self.horizontal:
            return QRectF(p - self.defilement, c, epaisseur, longueur)
        return QRectF(c, p - self.defilement, longueur, epaisseur)

    def _ratio(self, i: int) -> float:
        """Longueur en travers / épaisseur : largeur/hauteur en vertical, l'inverse en horizontal."""
        return 1 / self.ratios[i] if self.horizontal else self.ratios[i]

    # ------------------------------------------------------------------ disposition
    def _marge(self) -> int:
        return max(4, self.config.mosaique_marge)

    def _epaisseur_cible(self) -> float:
        m = self._marge()
        n = max(RANGEES_MIN, min(RANGEES_MAX, self.config.mosaique_dossier_rangees))
        return (self._vue() - MARGE_BOUT * 2 - m * (n - 1)) / n

    def disposer(self):
        """Rangées « justifiées » : chaque rangée pleine remplit exactement la largeur (ou la hauteur)."""
        m = self._marge()
        T = self._travers() - 2 * m
        cible = self._epaisseur_cible()
        self.rangees = []
        p = MARGE_BOUT
        ligne, somme = [], 0.0
        for i in range(len(self.ratios)):
            ligne.append(i)
            somme += self._ratio(i)
            e = (T - m * (len(ligne) - 1)) / somme
            if e <= cible:
                self._ajouter_rangee(ligne, e, p, m, justifiee=True)
                p += e + m
                ligne, somme = [], 0.0
        if ligne:   # dernière rangée incomplète : épaisseur normale, centrée
            self._ajouter_rangee(ligne, cible, p, m, justifiee=False)
            p += cible + m
        self.longueur_totale = p - m + MARGE_BOUT
        # tout tient à l'écran : on centre plutôt que de laisser un grand vide
        if self.longueur_totale < self._vue():
            dp = (self._vue() - self.longueur_totale) / 2
            self.rangees = [(p + dp, e, el) for p, e, el in self.rangees]

    def _ajouter_rangee(self, ligne, e, p, m, justifiee):
        longueur = sum(self._ratio(i) * e for i in ligne) + m * (len(ligne) - 1)
        c = m + (0 if justifiee else (self._travers() - 2 * m - longueur) / 2)
        elements = []
        for i in ligne:
            l = self._ratio(i) * e
            elements.append((i, c, l))
            c += l + m
        self.rangees.append((p, e, elements))

    def _rangee_de(self, index: int) -> int:
        for k, (_, _, el) in enumerate(self.rangees):
            if any(i == index for i, _, _ in el):
                return k
        return 0

    def _max_defilement(self) -> float:
        return max(0.0, self.longueur_totale - self._vue())

    def montrer(self):
        self.disposer()
        k = self._rangee_de(self.courant)
        # l'image ouverte au début de l'écran : les suivantes du dossier ensuite
        self.defilement = self.cible = max(0.0, min(self._max_defilement(), self.rangees[k][0] - MARGE_BOUT)) \
            if self.rangees else 0.0
        self.showFullScreen()
        self.activateWindow()
        self._montrer_pastille()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        ancre = self._index_au_debut()
        self.disposer()
        if ancre >= 0:
            self.aller_a(self.rangees[self._rangee_de(ancre)][0] - MARGE_BOUT, anime=False)
        self.btn_panorama.adjustSize()
        b = self.btn_panorama.size()
        self.btn_panorama.move((self.width() - b.width()) // 2, self.height() - b.height() - 4)
        self.btn_panorama.raise_()

    # ------------------------------------------------------------------ défilement
    def _pas_page(self, sens: int) -> float:
        return sens * self._vue() * 0.85

    def defiler(self, delta: float):
        self.aller_a(self.cible + delta)

    def aller_a(self, p: float, anime: bool = True):
        self.cible = max(0.0, min(self._max_defilement(), p))
        if anime:
            if not self._anim.isActive():
                self._chrono_defil.start()
                self._anim.start()
        else:
            self.defilement = self.cible
            self._vitesse = 0.0
            self._anim.stop()
            self.update()
        self._montrer_pastille()

    def _pas(self):
        """Ressort à amortissement critique : le mouvement accélère puis ralentit en douceur,
        sans dépasser la cible ; les crans de molette successifs s'enchaînent sans à-coup.
        Calculé sur le temps réel écoulé : même rendu quelle que soit la charge du PC."""
        dt = min(0.05, self._chrono_defil.restart() / 1000.0)
        douceur = max(1, min(10, self.config.mosaique_douceur))
        omega = 4.0 / (0.12 + 0.065 * douceur)        # 5 → arrivée en ≈ 0,45 s
        ecart = self.cible - self.defilement
        # intégration en petits pas (stable même si une image a pris du retard)
        n = max(1, int(dt / 0.004))
        h = dt / n
        for _ in range(n):
            acceleration = omega * omega * ecart - 2 * omega * self._vitesse
            self._vitesse += acceleration * h
            self.defilement += self._vitesse * h
            ecart = self.cible - self.defilement
        self.defilement = max(0.0, min(self._max_defilement(), self.defilement))
        if abs(ecart) < 0.4 and abs(self._vitesse) < 8:
            self.defilement, self._vitesse = self.cible, 0.0
            self._anim.stop()
        self.update()

    def _index_au_debut(self) -> int:
        for p, e, el in self.rangees:
            if p + e > self.defilement:
                return el[0][0]
        return -1

    def changer_rangees(self, delta: float, ancre: QPointF | None = None):
        """Plus ou moins de rangées à l'écran, en gardant l'image sous le curseur en place."""
        n = max(RANGEES_MIN, min(RANGEES_MAX, self.config.mosaique_dossier_rangees + delta))
        if n == self.config.mosaique_dossier_rangees:
            return
        ancre = ancre or QPointF(self.width() / 2, self.height() / 2)
        i = self._element_en(ancre)
        if i < 0:
            i = self._index_au_debut()
        avant = self._debut(i) if i >= 0 else 0
        self.config.mosaique_dossier_rangees = n
        self.config.enregistrer()
        self.disposer()
        if i >= 0:
            self.aller_a(self.defilement + (self._debut(i) - avant), anime=False)
        self.update()

    def _debut(self, i: int) -> float:
        r = self._rect(i)
        return r.left() if self.horizontal else r.top()

    # ------------------------------------------------------------------ panorama
    def basculer_panorama(self):
        if self._panorama_actif:
            self.arreter_panorama()
        else:
            self.lancer_panorama()

    def lancer_panorama(self):
        if self._max_defilement() <= 0:
            self._montrer_pastille()
            return
        if self.cible >= self._max_defilement() - 1:
            self.aller_a(0)                      # déjà au bout : on repart du début
        self._panorama_actif = True
        self._veille(True)
        self._chrono.start()
        self._panorama.start()
        self.btn_panorama.bouton.changer_icone("pause")
        self.btn_panorama.bouton.setToolTip("Arrêter le panorama  (Espace)")

    def arreter_panorama(self):
        self._panorama_actif = False
        self._veille(False)
        self._panorama.stop()
        self.btn_panorama.bouton.changer_icone("lecture")
        self.btn_panorama.bouton.setToolTip("Panorama : défilement automatique  (Espace)")

    def _pas_panorama(self):
        dt = self._chrono.restart() / 1000.0
        if self._anim.isActive():           # retour au début animé (ou molette) : on attend
            return
        vitesse = self._vue() / max(1.0, self.config.panorama_duree)    # un écran en « durée » secondes
        nouveau = self.defilement + vitesse * dt
        if nouveau >= self._max_defilement():
            self.defilement = self.cible = self._max_defilement()
            if self.config.diaporama_boucle:
                # petite pause au bout, puis retour animé au début et ça repart
                self._panorama.stop()
                QTimer.singleShot(1500, self._reprendre_panorama)
            else:
                self.arreter_panorama()
            self.update()
            return
        self.defilement = self.cible = nouveau
        self.update()

    def _veille(self, empecher: bool):
        """Pas de mise en veille de l'écran tant que le panorama défile."""
        if empecher != getattr(self, "_veille_bloquee", False):
            self._veille_bloquee = empecher
            veille.empecher(empecher)

    def _reprendre_panorama(self):
        if self._ferme or not self._panorama_actif:
            return          # arrêté entre-temps
        self.aller_a(0)
        self._chrono.restart()
        self._panorama.start()

    # ------------------------------------------------------------------ chargement
    def _image(self, chemin: str, palier: int) -> QImage | None:
        e = self._cache.get(chemin)
        if e is not None:
            self._cache.move_to_end(chemin)
            if e[0] < palier and (chemin, palier) not in self._en_cours:
                self._demander(chemin, palier)
            return e[1]
        if (chemin, palier) not in self._en_cours:
            self._demander(chemin, palier)
        return None

    def _demander(self, chemin: str, palier: int):
        cle = (chemin, palier)
        self._en_cours.add(cle)
        self._voulus.add(cle)
        self._pool.start(_Tache(chemin, palier, self._voulus, self._signaux), self._priorite)

    def _recu(self, chemin: str, palier: int, image: QImage, anime: bool = False):
        self._en_cours.discard((chemin, palier))
        if image.isNull() or self._ferme:
            return
        if anime:
            self._animes.add(chemin)
        ancien = self._cache.get(chemin)
        if ancien is None or ancien[0] <= palier:
            self._cache[chemin] = (palier, image)
            self._cache.move_to_end(chemin)
            total = sum(im.sizeInBytes() for _, im in self._cache.values())
            while total > BUDGET and len(self._cache) > 1:
                _, (_, vieux) = self._cache.popitem(last=False)
                total -= vieux.sizeInBytes()
        self.update()

    # ------------------------------------------------------------------ animations
    def _doit_animer(self, i: int) -> bool:
        """Réglage « Mosaïque Dossier, animations » : toujours, au survol (toutes pendant le
        Panorama), ou jamais."""
        mode = self.config.mosaique_animation
        if mode == "jamais" or i < 0 or self.chemins[i] not in self._animes:
            return False
        return mode != "survol" or self._panorama_actif or i == self._survol

    def _animer_visibles(self, visibles: list, autour: list, dpr: float):
        """Lance le décodage des animations à jouer et l'horloge de lecture."""
        if self.config.mosaique_animation == "jamais" or not self._animes:
            return
        # au survol, on ne prépare que l'image sous la souris (le reste du processeur est libre)
        marge = autour if self.config.mosaique_animation != "survol" or self._panorama_actif else visibles
        voulues = {(self.chemins[i], _palier(r.height() * dpr)) for i, r in marge if self._doit_animer(i)}
        self._films_voulus.intersection_update(voulues)
        self._films_voulus |= voulues
        for i, r in visibles:
            chemin = self.chemins[i]
            if not self._doit_animer(i):
                continue
            palier = _palier(r.height() * dpr)
            film = self._films.get(chemin)
            if film is not None:
                self._films.move_to_end(chemin)
                if film.palier >= palier:
                    continue
            if (chemin, palier) not in self._films_en_cours:
                self._films_en_cours.add((chemin, palier))
                self._pool_anim.start(_TacheAnimation(chemin, palier, self._films_voulus, self._signaux))
        if not self._minuteur_films.isActive():
            self._minuteur_films.start()

    def _animation_recue(self, chemin: str, palier: int, images: list):
        self._films_en_cours.discard((chemin, palier))
        if self._ferme or not images:
            return
        ancien = self._films.get(chemin)
        if ancien is not None and ancien.palier > palier:
            return
        self._films[chemin] = _Film(palier, images)
        self._films.move_to_end(chemin)
        self._cache.pop(chemin, None)        # l'image fixe ne sert plus : l'animation la remplace
        # on chasse d'abord les animations hors écran ; jamais celles qu'on regarde
        # (sinon elles seraient redécodées en boucle)
        visibles = {self.chemins[i] for i, _ in self._visibles(self._vue() * 0.6)}
        total = sum(f.octets for f in self._films.values())
        for cle in list(self._films):
            if total <= BUDGET_ANIMATIONS:
                break
            if cle not in visibles:
                total -= self._films.pop(cle).octets
        self.update()

    def _pas_films(self):
        """Fait avancer les animations visibles ; ne redessine que les tuiles qui ont changé."""
        if not self._films:
            return
        maintenant = self._horloge.elapsed()
        zone, actives = None, False
        for i, r in self._visibles():
            film = self._films.get(self.chemins[i])
            if film is None or not self._doit_animer(i):
                continue
            actives = True
            if film.avancer(maintenant):
                rr = r.toAlignedRect()
                zone = rr if zone is None else zone.united(rr)
        if zone is not None and not self._anim.isActive() and not self._panorama.isActive():
            self.update(zone)       # (en défilement, l'écran entier est déjà redessiné)
        if not actives and not any(self._doit_animer(i) for i, _ in self._visibles()):
            self._minuteur_films.stop()

    # ------------------------------------------------------------------ dessin
    def _rect(self, index: int) -> QRectF:
        for p, e, el in self.rangees:
            for i, c, l in el:
                if i == index:
                    return self._rect_abstrait(c, p, l, e)
        return QRectF()

    def _visibles(self, marge: float = 0.0):
        debut, fin = self.defilement - marge, self.defilement + self._vue() + marge
        for p, e, el in self.rangees:
            if p + e >= debut and p <= fin:
                for i, c, l in el:
                    yield i, self._rect_abstrait(c, p, l, e)

    def _element_en(self, pos: QPointF) -> int:
        for i, r in self._visibles():
            if r.contains(pos):
                return i
        return -1

    def _montrer_pastille(self):
        self._minuteur_pastille.start()

    def paintEvent(self, e):
        p = QPainter(self)
        fond = QColor(self.config.plein_ecran_couleur)
        fond.setAlpha(max(1, round(self.config.plein_ecran_opacite * 2.55)))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.fillRect(self.rect(), fond)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        dpr = self.devicePixelRatioF()
        self._priorite += 1
        visibles = list(self._visibles())
        autour = list(self._visibles(self._vue() * 0.6))
        # ce qui est à l'écran est décodé d'abord ; une demi-page autour, ensuite ; le reste est oublié
        voulus = {(self.chemins[i], _palier(r.height() * dpr)) for i, r in autour}
        self._voulus.intersection_update(voulus)
        self._voulus |= voulus

        self._animer_visibles(visibles, autour, dpr)
        for i, r in visibles:
            chemin = self.chemins[i]
            film = self._films.get(chemin) if self.config.mosaique_animation != "jamais" else None
            image = film.image if film is not None else self._image(chemin, _palier(r.height() * dpr))
            if image is None:
                image = self.miniatures.cache.get(chemin)      # miniature floue en attendant
                if image is None:
                    self.miniatures.demander(chemin, 5)
            if image is not None and not image.isNull():
                p.drawImage(r, image)
            else:
                p.fillRect(r, QColor(45, 45, 45, 220))
            if i == self.courant:
                p.setPen(QPen(QColor(255, 170, 40), 3))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(r.adjusted(-1.5, -1.5, 1.5, 1.5))
            elif i == self._survol:
                p.fillRect(r, QColor(255, 255, 255, 28))
                p.setPen(QPen(QColor(255, 255, 255, 200), 2))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(r.adjusted(-1, -1, 1, 1))
        for i, r in autour:                    # préchargement hors écran
            self._image(self.chemins[i], _palier(r.height() * dpr))

        self._dessiner_barre_defilement(p)
        if self._minuteur_pastille.isActive() and visibles:
            premier = min(i for i, _ in visibles) + 1
            dernier = max(i for i, _ in visibles) + 1
            self._pastille(p, f"{premier} – {dernier}  sur  {len(self.chemins)}")

    def _dessiner_barre_defilement(self, p: QPainter):
        if self.longueur_totale <= self._vue():
            return
        v = self._vue()
        poignee = max(40.0, v * v / self.longueur_totale)
        pos = (v - poignee) * self.defilement / self._max_defilement()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 110))
        if self.horizontal:
            p.drawRoundedRect(QRectF(pos + 2, self.height() - 7, poignee - 4, 4), 2, 2)
        else:
            p.drawRoundedRect(QRectF(self.width() - 7, pos + 2, 4, poignee - 4), 2, 2)

    def _pastille(self, p: QPainter, texte: str):
        f = QFont(self.font())
        f.setPixelSize(16)
        p.setFont(f)
        m = p.fontMetrics()
        l, h = m.horizontalAdvance(texte) + 26, m.height() + 12
        r = QRectF((self.width() - l) / 2, 24, l, h)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(40, 40, 40, 220))
        p.drawRoundedRect(r, 7, 7)
        p.setPen(QColor(245, 245, 245))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, texte)

    # ------------------------------------------------------------------ souris
    def wheelEvent(self, e):
        d = e.angleDelta().y() or e.angleDelta().x()
        if not d:
            d = e.pixelDelta().y() * 2
        if not d:
            return
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # Ctrl+molette : images plus grandes (avant) ou plus petites (arrière)
            self.changer_rangees(-0.5 if d > 0 else 0.5, e.position())
        else:
            # molette vers l'arrière = la suite du dossier, vers l'avant = retour vers le début
            self.defiler(-d / 120 * self._epaisseur_cible() * 0.4)
        e.accept()

    def mouseMoveEvent(self, e):
        i = self._element_en(e.position())
        if i != self._survol:
            ancien = self._survol
            self._survol = i
            if 0 <= ancien < len(self.chemins) and not self._doit_animer(ancien):
                film = self._films.get(self.chemins[ancien])
                if film is not None:
                    film.rembobiner()          # elle redevient une vignette fixe
            self.setCursor(Qt.CursorShape.PointingHandCursor if i >= 0 else Qt.CursorShape.ArrowCursor)
            if i >= 0:
                QToolTip.showText(e.globalPosition().toPoint(), os.path.basename(self.chemins[i]), self)
            else:
                QToolTip.hideText()
            self.update()

    def mousePressEvent(self, e):
        self._appui = e.position()

    def mouseReleaseEvent(self, e):
        if self._appui is None:
            return
        deplace = (e.position() - self._appui).manhattanLength() > 6
        self._appui = None
        if deplace:
            return
        i = self._element_en(e.position())
        if e.button() == Qt.MouseButton.RightButton:
            self._menu(i, e.globalPosition().toPoint())
            return
        if e.button() == Qt.MouseButton.MiddleButton or (
                e.button() == Qt.MouseButton.LeftButton and e.modifiers() & Qt.KeyboardModifier.ControlModifier):
            if i >= 0:
                self.image_nouvelle_fenetre.emit(self.chemins[i])
            return
        if e.button() != Qt.MouseButton.LeftButton:
            return
        if i >= 0:
            self.image_choisie.emit(self.chemins[i])
        self.close()        # clic sur le fond : retour à la liseuse

    def _menu(self, i: int, pos: QPoint):
        m = QMenu(self)
        if i >= 0:
            chemin = self.chemins[i]
            m.addAction(os.path.basename(chemin)).setEnabled(False)
            m.addSeparator()
            m.addAction("Ouvrir dans la liseuse", lambda: (self.image_choisie.emit(chemin), self.close()))
            m.addAction("Ouvrir dans une nouvelle fenêtre", lambda: self.image_nouvelle_fenetre.emit(chemin))
            m.addAction("Afficher dans le dossier", lambda: actions.afficher_dans_dossier(chemin))
            m.addAction("Copier le fichier", lambda: actions.copier_fichier(chemin))
            m.addSeparator()
            m.addAction("Supprimer (mettre à la corbeille)\tSuppr", lambda: self.supprimer(i))
            m.addSeparator()
        m.addAction(("Arrêter le panorama" if self._panorama_actif else "Panorama (défilement automatique)")
                    + "\tEspace", self.basculer_panorama)
        sens = m.addAction("Défilement horizontal" if not self.horizontal else "Défilement vertical",
                           self.changer_orientation)
        sens.setToolTip("Réglable aussi dans Configuration")
        m.addAction("Images plus grandes\t+", lambda: self.changer_rangees(-0.5))
        m.addAction("Images plus petites\t-", lambda: self.changer_rangees(0.5))
        m.addSeparator()
        m.addAction("Quitter la mosaïque\tÉchap", self.close)
        m.exec(pos)

    def changer_orientation(self):
        ancre = self._index_au_debut()
        self.horizontal = not self.horizontal
        self.config.mosaique_dossier_orientation = "horizontale" if self.horizontal else "verticale"
        self.config.enregistrer()
        self.disposer()
        if ancre >= 0:
            self.aller_a(self.rangees[self._rangee_de(ancre)][0] - MARGE_BOUT, anime=False)
        self.update()

    def supprimer(self, i: int):
        if 0 <= i < len(self.chemins):
            # la liseuse demande confirmation, met à la corbeille et prévient tout le monde (dont nous)
            self.liseuse.supprimer(self.chemins[i], parent=self)

    def retirer(self, chemin: str):
        if chemin not in self.chemins:
            return
        i = self.chemins.index(chemin)
        self.chemins.pop(i)
        self.ratios.pop(i)
        self._cache.pop(chemin, None)
        self._films.pop(chemin, None)
        if i < self.courant or self.courant >= len(self.chemins):
            self.courant = max(0, self.courant - 1)
        self._survol = -1
        if not self.chemins:
            self.close()
            return
        self.disposer()
        self.aller_a(self.cible, anime=False)
        self.update()

    def closeEvent(self, e):
        # rendre la mémoire tout de suite (l'objet Python peut survivre un peu à la fenêtre)
        self._ferme = True
        self.arreter_panorama()
        self._anim.stop()
        self._voulus.clear()
        self._pool.clear()
        self._cache.clear()
        self._minuteur_films.stop()
        self._films_voulus.clear()
        self._pool_anim.clear()
        self._films.clear()
        self.liseuse.reprendre_film()
        if getattr(self.liseuse, "_mosaique_dossier", None) is self:
            self.liseuse._mosaique_dossier = None
        super().closeEvent(e)
        self.liseuse.raise_()
        self.liseuse.activateWindow()
