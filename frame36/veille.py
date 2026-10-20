"""Empêche la mise en veille de l'écran pendant un défilement automatique (Panorama, diaporama),
comme le fait un lecteur vidéo. Compteur : plusieurs demandes simultanées sont possibles."""

from __future__ import annotations

import sys

_demandes = 0
_cookie_linux = None

# Windows : SetThreadExecutionState
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002


def _windows(actif: bool):
    import ctypes
    etat = ES_CONTINUOUS | (ES_DISPLAY_REQUIRED | ES_SYSTEM_REQUIRED if actif else 0)
    ctypes.windll.kernel32.SetThreadExecutionState(etat)


def _linux(actif: bool):
    """Interface standard org.freedesktop.ScreenSaver (GNOME, KDE, Cinnamon, XFCE…)."""
    global _cookie_linux
    try:
        from PySide6.QtDBus import QDBusConnection, QDBusInterface
    except ImportError:
        return
    iface = QDBusInterface("org.freedesktop.ScreenSaver", "/org/freedesktop/ScreenSaver",
                           "org.freedesktop.ScreenSaver", QDBusConnection.sessionBus())
    if not iface.isValid():
        return
    if actif and _cookie_linux is None:
        rep = iface.call("Inhibit", "36Frame", "Défilement automatique des images")
        args = rep.arguments()
        _cookie_linux = args[0] if args else None
    elif not actif and _cookie_linux is not None:
        iface.call("UnInhibit", _cookie_linux)
        _cookie_linux = None


def _appliquer(actif: bool):
    try:
        if sys.platform == "win32":
            _windows(actif)
        elif sys.platform.startswith("linux"):
            _linux(actif)
    except Exception:
        pass


def empecher(oui: bool):
    """empecher(True) au début du défilement, empecher(False) à la fin (toujours par paires)."""
    global _demandes
    _demandes = max(0, _demandes + (1 if oui else -1))
    _appliquer(_demandes > 0)
