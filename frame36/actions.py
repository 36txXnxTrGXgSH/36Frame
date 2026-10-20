"""Partage, ouverture avec un logiciel tiers, impression, dossier."""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QMimeData, QRectF, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication, QImage, QPainter
from PySide6.QtWidgets import QWidget

WINDOWS = sys.platform == "win32"


def _lancer(commande: list[str]) -> bool:
    try:
        options = {}
        if WINDOWS:
            options["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            options["start_new_session"] = True
        subprocess.Popen(commande, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, close_fds=True, **options)
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------- presse-papiers
def copier_image(image: QImage) -> None:
    QGuiApplication.clipboard().setImage(image)


def copier_fichier(chemin: str) -> None:
    """Copie le fichier lui-même : Ctrl+V dans Discord, Teams, un mail, l'Explorateur…"""
    donnees = QMimeData()
    donnees.setUrls([QUrl.fromLocalFile(chemin)])
    donnees.setText(chemin)
    QGuiApplication.clipboard().setMimeData(donnees)


# ---------------------------------------------------------------------------- e-mail
def _app_path_windows(exe: str) -> str | None:
    if not WINDOWS:
        return None
    import winreg
    for racine in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(racine, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe}") as k:
                valeur, _ = winreg.QueryValueEx(k, "")
                valeur = os.path.expandvars(valeur.strip('"'))
                if os.path.exists(valeur):
                    return valeur
        except OSError:
            continue
    return None


def _thunderbird() -> str | None:
    if WINDOWS:
        trouve = _app_path_windows("thunderbird.exe")
        if trouve:
            return trouve
        for base in (os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", "")):
            p = Path(base) / "Mozilla Thunderbird" / "thunderbird.exe"
            if base and p.exists():
                return str(p)
        return None
    return shutil.which("thunderbird")


def envoyer_mail(chemin: str) -> str:
    """Ouvre un nouveau message avec la pièce jointe. Renvoie un message pour l'utilisateur."""
    outlook = _app_path_windows("OUTLOOK.EXE")
    if outlook and _lancer([outlook, "/a", chemin]):
        return "Nouveau message Outlook créé avec la pièce jointe."
    if not WINDOWS and shutil.which("xdg-email") and _lancer(["xdg-email", "--attach", chemin]):
        return "Nouveau message créé avec la pièce jointe."
    tb = _thunderbird()
    if tb and _lancer([tb, "-compose", f"attachment='{QUrl.fromLocalFile(chemin).toString()}'"]):
        return "Nouveau message Thunderbird créé avec la pièce jointe."
    # Nouvel Outlook, Gmail web… : pas de pièce jointe automatique possible.
    copier_fichier(chemin)
    QDesktopServices.openUrl(QUrl(f"mailto:?subject={QUrl.toPercentEncoding(os.path.basename(chemin)).data().decode()}"))
    return "Fichier copié : collez-le (Ctrl+V) dans le message qui vient de s'ouvrir."


def envoyer_discord(chemin: str) -> str:
    copier_fichier(chemin)
    if not QDesktopServices.openUrl(QUrl("discord://")):
        exe = shutil.which("discord")
        if exe:
            _lancer([exe])
    return "Fichier copié : collez-le (Ctrl+V) dans la conversation Discord."


def afficher_dans_dossier(chemin: str) -> None:
    if WINDOWS:
        _lancer(["explorer.exe", "/select,", os.path.normpath(chemin)])
    else:
        # gestionnaires de fichiers compatibles (Nautilus, Dolphin, Nemo…) : fichier sélectionné
        if shutil.which("dbus-send") and _lancer([
                "dbus-send", "--session", "--dest=org.freedesktop.FileManager1", "--type=method_call",
                "/org/freedesktop/FileManager1", "org.freedesktop.FileManager1.ShowItems",
                f"array:string:{QUrl.fromLocalFile(chemin).toString()}", "string:"]):
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(chemin)))


# ---------------------------------------------------------------------------- ouvrir avec
def _premier(*motifs: str) -> str | None:
    for motif in motifs:
        trouves = sorted(glob.glob(os.path.expandvars(motif)), reverse=True)   # version la plus récente
        if trouves:
            return trouves[0]
    return None


def applications_detectees() -> list[dict]:
    apps: list[dict] = []

    def ajouter(nom, chemin):
        if chemin and all(a["chemin"] != chemin for a in apps):
            apps.append({"nom": nom, "chemin": chemin})

    if WINDOWS:
        pf = r"%ProgramFiles%"
        ajouter("Paint", shutil.which("mspaint") or "mspaint.exe")
        ajouter("Photoshop", _app_path_windows("Photoshop.exe")
                or _premier(pf + r"\Adobe\Adobe Photoshop*\Photoshop.exe"))
        ajouter("GIMP", _premier(pf + r"\GIMP*\bin\gimp-?.*.exe", pf + r"\GIMP*\bin\gimp*.exe"))
        ajouter("Krita", _premier(pf + r"\Krita*\bin\krita.exe"))
        ajouter("Paint.NET", _app_path_windows("paintdotnet.exe") or _premier(pf + r"\paint.net\paintdotnet.exe"))
        ajouter("Affinity Photo", _premier(pf + r"\Affinity\Photo*\Photo.exe", pf + r"\Affinity\Affinity\Affinity.exe"))
    else:
        for nom, exe in (("GIMP", "gimp"), ("Krita", "krita"), ("Pinta", "pinta"), ("Inkscape", "inkscape"),
                         ("darktable", "darktable"), ("Photoshop (Wine)", "photoshop")):
            ajouter(nom, shutil.which(exe))
    return apps


def ouvrir_avec(executable: str, chemin: str) -> bool:
    return _lancer([executable, chemin])


def ouvrir_avec_choix_systeme(chemin: str) -> bool:
    """Boîte « Ouvrir avec » de Windows."""
    if WINDOWS:
        return _lancer(["rundll32.exe", "shell32.dll,OpenAs_RunDLL", os.path.normpath(chemin)])
    return QDesktopServices.openUrl(QUrl.fromLocalFile(chemin))


# ---------------------------------------------------------------------------- impression
def imprimer(image: QImage, parent: QWidget, titre: str) -> None:
    from PySide6.QtPrintSupport import QPrintDialog, QPrinter
    from PySide6.QtGui import QPageLayout

    imprimante = QPrinter(QPrinter.PrinterMode.HighResolution)
    imprimante.setDocName(titre)
    imprimante.setPageOrientation(QPageLayout.Orientation.Landscape if image.width() > image.height()
                                  else QPageLayout.Orientation.Portrait)
    dlg = QPrintDialog(imprimante, parent)
    dlg.setWindowTitle("Imprimer " + titre)
    if dlg.exec() != QPrintDialog.DialogCode.Accepted:
        return
    p = QPainter(imprimante)
    page = QRectF(imprimante.pageLayout().paintRectPixels(imprimante.resolution()))
    page.moveTo(0, 0)
    taille = image.size().scaled(page.size().toSize(), Qt.AspectRatioMode.KeepAspectRatio)
    cible = QRectF(0, 0, taille.width(), taille.height())
    cible.moveCenter(page.center())
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    p.drawImage(cible, image)
    p.end()
