"""Lecture des fichiers : liste du dossier, images complètes, miniatures (en arrière-plan)."""

from __future__ import annotations

import hashlib
import os
import re
from collections import OrderedDict
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QSize, Qt, QThreadPool, Signal
from PySide6.QtGui import QImage, QImageIOHandler, QImageReader

from .config import dossier_cache

# Plafond mémoire par image : 2 Go (≈ 500 mégapixels). Le défaut de Qt (256 Mo) refuserait une
# photo de 8566 x 4818 ; sans plafond, un fichier piégé annonçant des dimensions géantes ferait
# tenter une allocation énorme (plantage). Au-delà, l'image est simplement déclarée illisible.
QImageReader.setAllocationLimit(2048)

# Pillow : formats que Qt ne lit pas (AVIF, PSD aplati…). Chargé seulement à la première
# image qui en a besoin : le démarrage n'attend pas.
import importlib.util as _iu

_PIL_DISPONIBLE = _iu.find_spec("PIL") is not None
_PIL = None


def _pil():
    global _PIL
    if _PIL is None and _PIL_DISPONIBLE:
        from PIL import Image
        _PIL = Image
    return _PIL

_EXT_QT = {bytes(f).decode().lower() for f in QImageReader.supportedImageFormats()}
_EXT_PIL = {"avif", "psd", "dds", "jp2", "pcx"} if _PIL_DISPONIBLE else set()
EXTENSIONS = ({"." + e for e in (_EXT_QT | _EXT_PIL)} | {".jpe", ".dib"}) - {".svgz"}   # .jpe/.dib : alias JPEG/BMP
# Prévu pour la vidéo : EXTENSIONS_VIDEO = {".mp4", ".mkv", ".webm", ...}


def ram_totale() -> int:
    """Mémoire physique du PC en octets (8 Go si inconnue)."""
    try:
        if os.name == "nt":
            import ctypes

            class _Etat(ctypes.Structure):
                _fields_ = [("l", ctypes.c_ulong), ("charge", ctypes.c_ulong), ("total", ctypes.c_ulonglong),
                            ("libre", ctypes.c_ulonglong), ("r", ctypes.c_ulonglong * 5)]
            e = _Etat()
            e.l = ctypes.sizeof(e)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(e)):
                return int(e.total)
        else:
            return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except Exception:
        pass
    return 8 * 1024 ** 3


def budget_images() -> int:
    """Cache des images décodées : 3 % de la RAM, entre 150 et 400 Mo."""
    return max(150 * 1024 ** 2, min(400 * 1024 ** 2, ram_totale() // 33))


def octets_estimes(chemin: str) -> int:
    t = QImageReader(chemin).size()
    return t.width() * t.height() * 4 if t.isValid() else 0


def est_image(chemin: str | os.PathLike) -> bool:
    return Path(chemin).suffix.lower() in EXTENSIONS


def _cle_naturelle(nom: str):
    return [int(t) if t.isdigit() else t.casefold() for t in re.split(r"(\d+)", nom)]


def lister_dossier(dossier: str | os.PathLike) -> list[str]:
    """Images du dossier, triées comme l'Explorateur (« img2 » avant « img10 »)."""
    try:
        with os.scandir(dossier) as it:
            noms = [e.path for e in it if e.is_file() and est_image(e.name)]
    except OSError:
        return []
    return sorted(noms, key=_cle_fichier)


def _cle_fichier(p: str):
    # nom sans extension d'abord : « photo.png » avant « photo1.png », comme l'Explorateur
    return (_cle_naturelle(os.path.splitext(os.path.basename(p))[0]), os.path.splitext(p)[1].lower())


_DOSSIERS_IGNORES = {"$recycle.bin", "system volume information", "__pycache__", "node_modules"}


def _cache_ou_cache_systeme(entree: os.DirEntry) -> bool:
    nom = entree.name.lower()
    if nom.startswith(".") or nom in _DOSSIERS_IGNORES or nom.startswith("$"):
        return True
    if os.name == "nt":
        try:   # dossiers cachés ou système de Windows
            return bool(entree.stat(follow_symlinks=False).st_file_attributes & 0x6)
        except (OSError, AttributeError):
            return False
    return False


def lister_arborescence(racine: str, progression=None) -> list[str]:
    """Toutes les images du dossier ET de ses sous-dossiers, dans l'ordre de l'Explorateur :
    les images d'un dossier, puis celles de chacun de ses sous-dossiers (ordre naturel).
    Les dossiers cachés / système (corbeille…) sont ignorés, les raccourcis ne sont pas suivis.
    progression(n) est appelée régulièrement avec le nombre d'images trouvées ; si elle renvoie
    False, la recherche s'arrête (on garde ce qui a été trouvé)."""
    resultat: list[str] = []
    pile = [os.path.abspath(racine)]
    while pile:
        dossier = pile.pop()
        try:
            with os.scandir(dossier) as it:
                entrees = list(it)
        except OSError:
            continue
        fichiers, sous = [], []
        for e in entrees:
            try:
                if e.is_dir(follow_symlinks=False):
                    if not _cache_ou_cache_systeme(e):
                        sous.append(e.path)
                elif e.is_file() and est_image(e.name):
                    fichiers.append(e.path)
            except OSError:
                continue
        resultat.extend(sorted(fichiers, key=_cle_fichier))
        # pile : on empile à l'envers pour visiter les sous-dossiers dans l'ordre
        pile.extend(sorted(sous, key=lambda p: _cle_naturelle(os.path.basename(p)), reverse=True))
        if progression is not None and progression(len(resultat)) is False:
            break
    return resultat


def est_anime(chemin: str) -> bool:
    lecteur = QImageReader(chemin)
    return lecteur.supportsAnimation() and lecteur.imageCount() != 1


def dimensions(chemin: str) -> QSize:
    lecteur = QImageReader(chemin)
    lecteur.setAutoTransform(True)
    taille = lecteur.size()
    if taille.isValid() and lecteur.transformation() & QImageIOHandler.Transformation.TransformationRotate90:
        taille.transpose()
    return taille


def _pillow(chemin: str, maxi: int | None = None) -> QImage:
    pil = _pil()
    if pil is None:
        return QImage()
    try:
        with pil.open(chemin) as im:
            if maxi:
                im.draft("RGB", (maxi, maxi))
                im.thumbnail((maxi, maxi))
            im = im.convert("RGBA")
            # copie directe des octets (sans PIL.ImageQt, qui dépend de la version de Qt)
            q = QImage(im.tobytes("raw", "RGBA"), im.width, im.height, im.width * 4,
                       QImage.Format.Format_RGBA8888)
            return q.copy()
    except Exception:
        return QImage()


def charger_image(chemin: str) -> QImage:
    lecteur = QImageReader(chemin)
    lecteur.setAutoTransform(True)       # orientation EXIF des photos de téléphone
    image = lecteur.read()
    if image.isNull():
        image = _pillow(chemin)
    if image.isNull():
        return image
    return image.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)


def charger_apercu(chemin: str, hauteur: int) -> QImage:
    """Image réduite à « hauteur » pixels (Mosaïque Dossier). Les JPEG sont décodés
    directement à cette taille, ce qui est bien plus rapide qu'un décodage complet."""
    lecteur = QImageReader(chemin)
    lecteur.setAutoTransform(True)
    taille = lecteur.size()             # taille avant la rotation EXIF éventuelle
    if taille.isValid():
        tourne = bool(lecteur.transformation() & QImageIOHandler.Transformation.TransformationRotate90)
        h_affichee = taille.width() if tourne else taille.height()
        if h_affichee > hauteur:
            e = hauteur / h_affichee
            lecteur.setScaledSize(QSize(max(1, round(taille.width() * e)), max(1, round(taille.height() * e))))
    image = lecteur.read()
    if image.isNull():
        image = _pillow(chemin, hauteur * 3)
        if not image.isNull() and image.height() > hauteur:
            image = image.scaledToHeight(hauteur, Qt.TransformationMode.SmoothTransformation)
    if image.isNull():
        return image
    return image.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)


# ----------------------------------------------------------------------
# Miniatures : cache disque (PNG 128 px) indexé par chemin + taille + date.
TAILLE_MINIATURE = 128


def _fichier_cache(chemin: str) -> Path | None:
    try:
        st = os.stat(chemin)
    except OSError:
        return None
    cle = f"{os.path.normcase(os.path.abspath(chemin))}|{st.st_size}|{st.st_mtime_ns}"
    return dossier_cache() / (hashlib.sha1(cle.encode("utf-8")).hexdigest() + ".png")


def charger_miniature(chemin: str) -> QImage:
    cache = _fichier_cache(chemin)
    if cache and cache.exists():
        image = QImage(str(cache))
        if not image.isNull():
            return image

    lecteur = QImageReader(chemin)
    lecteur.setAutoTransform(True)
    taille = lecteur.size()
    if taille.isValid() and max(taille.width(), taille.height()) > TAILLE_MINIATURE:
        # Les JPEG sont décodés directement à petite taille : très rapide.
        lecteur.setScaledSize(taille.scaled(TAILLE_MINIATURE, TAILLE_MINIATURE, Qt.AspectRatioMode.KeepAspectRatio))
    image = lecteur.read()
    if image.isNull():
        image = _pillow(chemin, TAILLE_MINIATURE)
    if image.isNull():
        return image
    if max(image.width(), image.height()) > TAILLE_MINIATURE:
        image = image.scaled(TAILLE_MINIATURE, TAILLE_MINIATURE, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
    if cache:
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            image.save(str(cache), "PNG")
        except OSError:
            pass
    return image


# ----------------------------------------------------------------------
class _Signaux(QObject):
    fini = Signal(str, QImage)


class _Tache(QRunnable):
    def __init__(self, chemin: str, fonction, signaux: _Signaux):
        super().__init__()
        self.chemin, self.fonction, self.signaux = chemin, fonction, signaux
        self.setAutoDelete(True)

    def run(self):
        try:
            image = self.fonction(self.chemin)
        except Exception:
            image = QImage()
        try:
            self.signaux.fini.emit(self.chemin, image)
        except RuntimeError:   # l'appli se ferme
            pass


class ChargeurImages(QObject):
    """Décode les images complètes en arrière-plan, avec un petit cache (≈ 700 Mo)."""

    prete = Signal(str, QImage)

    def __init__(self, parent=None, budget_octets: int | None = None):
        super().__init__(parent)
        budget_octets = budget_octets or budget_images()
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(2)
        self._signaux = _Signaux(self)
        self._signaux.fini.connect(self._recu)
        self._cache: OrderedDict[str, QImage] = OrderedDict()
        self._en_cours: set[str] = set()
        self._budget = budget_octets
        self.proteges: set[str] = set()      # images affichées : jamais évincées

    @property
    def budget(self) -> int:
        return self._budget

    def en_cache(self, chemin: str) -> QImage | None:
        image = self._cache.get(chemin)
        if image is not None:
            self._cache.move_to_end(chemin)
        return image

    def demander(self, chemin: str, prioritaire: bool = True) -> None:
        if chemin in self._cache:
            if prioritaire:
                self.prete.emit(chemin, self._cache[chemin])
            return
        if chemin in self._en_cours:
            return
        self._en_cours.add(chemin)
        self._pool.start(_Tache(chemin, charger_image, self._signaux), 1 if prioritaire else 0)

    def oublier(self, chemin: str) -> None:
        self._cache.pop(chemin, None)

    def _recu(self, chemin: str, image: QImage) -> None:
        self._en_cours.discard(chemin)
        if not image.isNull():
            self._cache[chemin] = image
            self._cache.move_to_end(chemin)
            self._evincer()
        self.prete.emit(chemin, image)

    def _evincer(self):
        total = sum(i.sizeInBytes() for i in self._cache.values())
        for cle in list(self._cache):
            if total <= self._budget:
                break
            if cle not in self.proteges:
                total -= self._cache.pop(cle).sizeInBytes()

    def proteger(self, ancien: str | None, nouveau: str | None):
        """La fenêtre passe de « ancien » à « nouveau » : seul le nouveau reste protégé."""
        if ancien:
            self.proteges.discard(ancien)
        if nouveau:
            self.proteges.add(nouveau)
        self._evincer()


class ChargeurMiniatures(QObject):
    prete = Signal(str, QImage)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(max(2, min(4, (os.cpu_count() or 2) // 2)))
        self._signaux = _Signaux(self)
        self._signaux.fini.connect(self._recu)
        # 128 px max : ~64 Ko chacune ; 1500 en mémoire ≈ 90 Mo au pire (le reste est sur disque)
        self.cache: OrderedDict[str, QImage] = OrderedDict()
        self._max = 1500
        self._en_cours: set[str] = set()

    def demander(self, chemin: str, priorite: int = 0) -> None:
        if chemin in self.cache or chemin in self._en_cours:
            return
        self._en_cours.add(chemin)
        self._pool.start(_Tache(chemin, charger_miniature, self._signaux), priorite)

    def vider_file(self) -> None:
        self._pool.clear()
        self._en_cours.clear()

    def _recu(self, chemin: str, image: QImage) -> None:
        self._en_cours.discard(chemin)
        self.cache[chemin] = image
        while len(self.cache) > self._max:
            self.cache.popitem(last=False)
        self.prete.emit(chemin, image)
