"""Windows : déclarer 36Frame comme visionneuse pour les extensions d'images.

Windows 10/11 interdit à un programme de se choisir lui-même par défaut (le choix de
l'utilisateur est protégé par une signature). La voie officielle, utilisée ici :
  1. 36Frame se déclare (registre de l'utilisateur, sans droits administrateur) : type de fichier
     « 36Frame.Image », liste « Ouvrir avec », et « Capacités » pour la page Applications par défaut ;
  2. on ouvre Paramètres > Applications par défaut > 36Frame, où l'utilisateur valide d'un clic
     (« Définir par défaut » sous Windows 11).
Fonctionne pour la version installée, la version portable et le lancement depuis les sources.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROGID = "36Frame.Image"
NOM_ENREGISTRE = "36Frame"          # nom dans « RegisteredApplications »
CAPACITES = r"Software\36Frame\Capabilities"

# (extension, description) : tout ce que 36Frame sait ouvrir
GROUPES = {
    "Photos": [(".jpg", "JPEG"), (".jpeg", "JPEG"), (".jpe", "JPEG"), (".jfif", "JPEG"), (".png", "PNG"),
               (".webp", "WebP"), (".avif", "AVIF"), (".bmp", "Bitmap"), (".dib", "Bitmap"),
               (".tif", "TIFF"), (".tiff", "TIFF")],
    "Animations": [(".gif", "GIF")],
    "Icônes": [(".ico", "Icône"), (".cur", "Curseur"), (".icns", "Icône macOS")],
    "Autres": [(".tga", "Targa"), (".psd", "Photoshop (aplati)"), (".dds", "DirectDraw"), (".jp2", "JPEG 2000"),
               (".pcx", "PCX"), (".ppm", "Netpbm"), (".pgm", "Netpbm"), (".pbm", "Netpbm"),
               (".xbm", "X Bitmap"), (".xpm", "X Pixmap"), (".wbmp", "WBMP"), (".svg", "SVG")],
}
PAR_DEFAUT = {".jpg", ".jpeg", ".jpe", ".jfif", ".png", ".webp", ".avif", ".bmp", ".gif", ".tif", ".tiff"}
TOUTES = [e for g in GROUPES.values() for e, _ in g]


def disponible() -> bool:
    return sys.platform == "win32"


def commande() -> tuple[str, str]:
    """(exécutable à déclarer, commande d'ouverture « … "%1" »)."""
    if getattr(sys, "frozen", False):
        exe = os.path.abspath(sys.executable)
        return exe, f'"{exe}" "%1"'
    # depuis les sources : pythonw.exe lancer.pyw
    python = Path(sys.executable)
    pythonw = python.with_name("pythonw.exe")
    if pythonw.exists():
        python = pythonw
    script = Path(__file__).resolve().parent.parent / "lancer.pyw"
    return str(python), f'"{python}" "{script}" "%1"'


def _icone() -> str:
    exe, _ = commande()
    if getattr(sys, "frozen", False):
        return f"{exe},0"
    ico = Path(__file__).resolve().parent.parent / "assets" / "36frame.ico"
    return str(ico) if ico.exists() else f"{exe},0"


def _nom_application() -> str:
    """Clé « Applications\\<nom de l'exe> » (36Frame.exe, 36Frame-Portable.exe…)."""
    exe, _ = commande()
    return os.path.basename(exe) if getattr(sys, "frozen", False) else "36Frame.exe"


def _ecrire(cle_racine, chemin: str, valeurs: dict):
    import winreg
    with winreg.CreateKeyEx(cle_racine, chemin, 0, winreg.KEY_WRITE) as k:
        for nom, val in valeurs.items():
            winreg.SetValueEx(k, nom, 0, winreg.REG_SZ, val)


def _supprimer_arbre(cle_racine, chemin: str):
    import winreg
    try:
        with winreg.OpenKey(cle_racine, chemin, 0, winreg.KEY_ALL_ACCESS) as k:
            while True:
                try:
                    sous = winreg.EnumKey(k, 0)
                except OSError:
                    break
                _supprimer_arbre(cle_racine, chemin + "\\" + sous)
        winreg.DeleteKey(cle_racine, chemin)
    except FileNotFoundError:
        pass


def _supprimer_valeur(cle_racine, chemin: str, nom: str):
    import winreg
    try:
        with winreg.OpenKey(cle_racine, chemin, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, nom)
    except FileNotFoundError:
        pass


def _prevenir_explorateur():
    """Rafraîchit les icônes et les menus de l'Explorateur."""
    try:
        import ctypes
        SHCNE_ASSOCCHANGED, SHCNF_IDLIST = 0x08000000, 0
        ctypes.windll.shell32.SHChangeNotify(SHCNE_ASSOCCHANGED, SHCNF_IDLIST, None, None)
    except Exception:
        pass


def declarer(extensions: list[str], prefixe: str = "") -> None:
    """Déclare 36Frame pour ces extensions (registre de l'utilisateur, aucun droit admin).
    prefixe : sous-clé de test (les essais n'écrivent pas dans les vraies clés)."""
    import winreg
    R = winreg.HKEY_CURRENT_USER
    classes = prefixe + r"Software\Classes"
    _, cmd = commande()
    icone = _icone()
    app = _nom_application()

    _ecrire(R, rf"{classes}\{PROGID}", {"": "Image (36Frame)", "FriendlyTypeName": "Image (36Frame)"})
    _ecrire(R, rf"{classes}\{PROGID}\DefaultIcon", {"": icone})
    _ecrire(R, rf"{classes}\{PROGID}\shell", {"": "open"})
    _ecrire(R, rf"{classes}\{PROGID}\shell\open", {"FriendlyAppName": "36Frame"})
    _ecrire(R, rf"{classes}\{PROGID}\shell\open\command", {"": cmd})

    _ecrire(R, rf"{classes}\Applications\{app}", {"FriendlyAppName": "36Frame"})
    _ecrire(R, rf"{classes}\Applications\{app}\DefaultIcon", {"": icone})
    _ecrire(R, rf"{classes}\Applications\{app}\shell\open\command", {"": cmd})

    _ecrire(R, prefixe + CAPACITES, {"ApplicationName": "36Frame",
                                     "ApplicationDescription": "Liseuse d'images inspirée de Picasa",
                                     "ApplicationIcon": icone})
    # on repart d'une liste propre (des extensions ont pu être décochées)
    _supprimer_arbre(R, prefixe + CAPACITES + r"\FileAssociations")
    _supprimer_arbre(R, rf"{classes}\Applications\{app}\SupportedTypes")
    for ext in TOUTES:
        if ext not in extensions:
            _supprimer_valeur(R, rf"{classes}\{ext}\OpenWithProgids", PROGID)
    for ext in extensions:
        _ecrire(R, rf"{classes}\{ext}\OpenWithProgids", {PROGID: ""})
        _ecrire(R, rf"{classes}\Applications\{app}\SupportedTypes", {ext: ""})
        _ecrire(R, prefixe + CAPACITES + r"\FileAssociations", {ext: PROGID})
    _ecrire(R, prefixe + r"Software\RegisteredApplications", {NOM_ENREGISTRE: CAPACITES})
    if not prefixe:
        _prevenir_explorateur()


def retirer(prefixe: str = "") -> None:
    """Efface toutes les déclarations de 36Frame (les choix par défaut reviennent à Windows)."""
    import winreg
    R = winreg.HKEY_CURRENT_USER
    classes = prefixe + r"Software\Classes"
    for ext in TOUTES:
        _supprimer_valeur(R, rf"{classes}\{ext}\OpenWithProgids", PROGID)
    _supprimer_arbre(R, rf"{classes}\{PROGID}")
    for app in ("36Frame.exe", "36Frame-Portable.exe", _nom_application()):
        _supprimer_arbre(R, rf"{classes}\Applications\{app}")
    _supprimer_valeur(R, prefixe + r"Software\RegisteredApplications", NOM_ENREGISTRE)
    _supprimer_arbre(R, prefixe + r"Software\36Frame")
    if not prefixe:
        _prevenir_explorateur()


def declarees(prefixe: str = "") -> list[str]:
    """Extensions actuellement déclarées pour 36Frame."""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, prefixe + CAPACITES + r"\FileAssociations") as k:
            n = winreg.QueryInfoKey(k)[1]
            return [winreg.EnumValue(k, i)[0] for i in range(n)]
    except OSError:
        return []


def ouvrir_parametres() -> None:
    """Paramètres > Applications par défaut > 36Frame (Windows 11 : bouton « Définir par défaut »)."""
    try:
        os.startfile("ms-settings:defaultapps?registeredAppUser=" + NOM_ENREGISTRE)
    except OSError:
        os.startfile("ms-settings:defaultapps")
