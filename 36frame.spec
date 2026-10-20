# Recette PyInstaller de 36Frame (utilisée par compiler.ps1).
#
#   MODE=dossier  -> dist\<NOM>\<NOM>.exe + _internal   (démarrage le plus rapide)
#   MODE=unique   -> <DIST>\<NOM>.exe                   (un seul fichier, décompressé à chaque lancement)
#
# On retire tout ce que 36Frame n'utilise jamais : moins à lire au démarrage, moins à analyser
# pour l'antivirus et, pour l'exe unique, moins à décompresser à chaque image ouverte.

import os
import sys

MODE = os.environ.get("MODE", "dossier")
NOM = os.environ.get("NOM", "36Frame")
RACINE = os.path.abspath(os.path.join(SPECPATH))
WINDOWS = sys.platform == "win32"

MODULES_EXCLUS = [
    "tkinter", "unittest", "pydoc", "pydoc_data", "doctest", "lib2to3", "test",
    "ssl", "_ssl", "_hashlib",                    # aucun accès réseau chiffré (36Frame ne va pas sur Internet)
    "bz2", "_bz2", "lzma", "_lzma", "compression.zstd", "_zstd",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtOpenGL", "PySide6.QtPdf",
    "PIL.ImageQt", "PIL.ImageTk", "PIL.ImageShow",
    "numpy",
]
if WINDOWS:
    MODULES_EXCLUS.append("PySide6.QtDBus")      # sert seulement sous Linux (veille de l'écran)

# fichiers embarqués à écarter (comparaison sur le chemin, en minuscules)
FICHIERS_EXCLUS = (
    "opengl32sw.dll",                 # rendu OpenGL logiciel de secours (36Frame n'utilise pas OpenGL)
    "qdirect2d",                      # 2e moteur d'affichage Windows, inutile (qwindows suffit)
    "plugins\\tls", "plugins/tls",    # chiffrement réseau
    "libssl", "libcrypto",
    "qt6dbus.dll" if WINDOWS else "\0",
    "plugins\\generic", "plugins\\networkinformation", "plugins/networkinformation",
    "qt6pdf", "qt6qml", "qt6quick", "qt6opengl",
)


def garder(entree) -> bool:
    chemin = (entree[0] + "|" + entree[1]).lower()
    if any(x in chemin for x in FICHIERS_EXCLUS):
        return False
    # traductions de Qt : seulement le français (boutons « Oui / Non »…)
    if "translations" in chemin and ".qm" in chemin and "qtbase_fr.qm" not in chemin:
        return False
    return True


a = Analysis(
    [os.path.join(RACINE, "lancer.pyw")],
    pathex=[RACINE],
    excludes=MODULES_EXCLUS,
    noarchive=False,
    optimize=1,
)
a.binaries = [b for b in a.binaries if garder(b)]
a.datas = [d for d in a.datas if garder(d)]

pyz = PYZ(a.pure)
icone = os.path.join(RACINE, "assets", "36frame.ico") if WINDOWS else None

if MODE == "unique":
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name=NOM, icon=icone, console=False,
              upx=False, runtime_tmpdir=None)
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=NOM, icon=icone, console=False, upx=False)
    coll = COLLECT(exe, a.binaries, a.datas, name=NOM, upx=False)
