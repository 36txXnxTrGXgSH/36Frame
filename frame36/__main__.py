"""Lancement : python -m frame36 [image | dossier]

Rien de Qt n'est chargé avant d'avoir vérifié qu'aucun 36Frame ne tourne déjà : ouvrir une autre
image depuis l'Explorateur ne coûte ainsi que le démarrage de Python (voir instance.py).
"""

from __future__ import annotations

import os
import sys

from . import NOM_APPLI


def _palette_sombre(app):
    from PySide6.QtGui import QColor, QPalette

    app.setStyle("Fusion")
    p = QPalette()
    for role, c in ((QPalette.ColorRole.Window, "#2b2b2b"), (QPalette.ColorRole.WindowText, "#eeeeee"),
                    (QPalette.ColorRole.Base, "#1f1f1f"), (QPalette.ColorRole.AlternateBase, "#2b2b2b"),
                    (QPalette.ColorRole.Text, "#eeeeee"), (QPalette.ColorRole.Button, "#3a3a3a"),
                    (QPalette.ColorRole.ButtonText, "#eeeeee"), (QPalette.ColorRole.Highlight, "#3d6db5"),
                    (QPalette.ColorRole.HighlightedText, "#ffffff"), (QPalette.ColorRole.ToolTipBase, "#262626"),
                    (QPalette.ColorRole.ToolTipText, "#eeeeee"), (QPalette.ColorRole.PlaceholderText, "#888888")):
        p.setColor(role, QColor(c))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor("#777777"))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor("#777777"))
    app.setPalette(p)


def _traduction_francaise(app):
    """Boutons standards de Qt en français (« Oui / Non / Annuler »…)."""
    from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator

    trad = QTranslator(app)
    if trad.load(QLocale(QLocale.Language.French), "qtbase", "_",
                 QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(trad)


def principal() -> int:
    chemins = [os.path.abspath(a) for a in sys.argv[1:] if not a.startswith("-") and os.path.exists(a)]

    # 1) Chemin rapide : 36Frame tourne déjà → on lui passe les images et on s'arrête là.
    from .instance import NOM_SERVEUR, envoyer_rapide
    if envoyer_rapide(chemins):
        return 0

    # 2) Sinon : démarrage complet.
    if sys.platform == "win32":
        try:  # icône propre dans la barre des tâches (sinon celle de python.exe)
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("36.Frame")
        except Exception:
            pass
    elif sys.platform.startswith("linux"):
        # Sous Wayland, une application ne peut pas placer ses fenêtres elle-même (mosaïque,
        # plein écran sur le bon écran). On passe par XWayland quand il est disponible.
        if os.environ.get("WAYLAND_DISPLAY") and os.environ.get("DISPLAY") and not os.environ.get("QT_QPA_PLATFORM"):
            os.environ["QT_QPA_PLATFORM"] = "xcb"

    from PySide6.QtCore import QDir, QLockFile, QThread, QTimer
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    app.setApplicationName(NOM_APPLI)
    app.setDesktopFileName("36frame")      # Linux : relie les fenêtres au lanceur (icône du dock)
    from .icones import icone_appli
    app.setWindowIcon(icone_appli())
    _palette_sombre(app)
    _traduction_francaise(app)

    from .config import Configuration
    from .gestion import Gestionnaire, envoyer_a_instance

    # Le verrou départage deux lancements simultanés (plusieurs fichiers ouverts d'un coup).
    verrou = QLockFile(os.path.join(QDir.tempPath(), NOM_SERVEUR + ".lock"))
    if not verrou.tryLock(0):
        for _ in range(30):            # l'autre instance démarre à l'instant : on attend son serveur
            QThread.msleep(100)
            if envoyer_a_instance(chemins):
                return 0

    config = Configuration.charger()
    gestion = Gestionnaire(config)
    gestion.ecouter()
    if chemins:
        gestion.ouvrir_chemins(chemins)
    else:
        fenetre = gestion.nouvelle_fenetre()
        fenetre.vue.vider("Glissez une image ou un dossier ici.\nCtrl+O : une image   •   Ctrl+Maj+O : un dossier")
        QTimer.singleShot(150, fenetre.dialogue_demarrage)
    code = app.exec()
    verrou.unlock()
    return code


if __name__ == "__main__":
    sys.exit(principal())
