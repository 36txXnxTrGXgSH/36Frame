"""Choisir PLUSIEURS dossiers d'un coup dans la fenêtre « Sélectionner un dossier » de Windows
(Ctrl+clic, Maj+clic, Ctrl+A).

Qt ne sait demander qu'un seul dossier. La boîte de dialogue de Windows (IFileOpenDialog) le
permet avec les options FOS_PICKFOLDERS | FOS_ALLOWMULTISELECT : on l'appelle directement par
COM, en ctypes (aucune dépendance supplémentaire). Sous Linux : boîte de Qt, sélection multiple.
"""

from __future__ import annotations

import ctypes
import os
import sys
import uuid


def choisir_dossiers(parent=None, titre: str = "Sélectionner un ou plusieurs dossiers",
                     depart: str = "") -> list[str]:
    """Renvoie les dossiers choisis ([] si annulé)."""
    if sys.platform == "win32":
        try:
            return _windows(parent, titre, depart)
        except OSError:
            pass                     # (Windows très ancien) : boîte de Qt
    return _qt(parent, titre, depart)


# ---------------------------------------------------------------------------- Windows (COM)
def _guid(texte: str):
    class GUID(ctypes.Structure):
        _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort),
                    ("Data3", ctypes.c_ushort), ("Data4", ctypes.c_ubyte * 8)]
    u = uuid.UUID(texte)
    g = GUID()
    g.Data1, g.Data2, g.Data3 = u.fields[0], u.fields[1], u.fields[2]
    g.Data4[:] = list(u.bytes[8:])
    return g


CLSID_FileOpenDialog = "DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7"
IID_IFileOpenDialog = "D57C7288-D4AD-4768-BE02-9D969532D960"
IID_IShellItem = "43826D1E-E718-42EE-BC55-A1E261C37BFE"
FOS_PICKFOLDERS, FOS_FORCEFILESYSTEM, FOS_ALLOWMULTISELECT, FOS_PATHMUSTEXIST = 0x20, 0x40, 0x200, 0x800
SIGDN_FILESYSPATH = 0x80058000
ERREUR_ANNULE = 0x800704C7 - (1 << 32)        # HRESULT de « Annuler », en entier signé


def _methode(objet, rang: int, *types):
    """Méthode n° rang de la table virtuelle d'un objet COM."""
    vtable = ctypes.cast(ctypes.cast(objet, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))
    proto = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *types)
    f = proto(vtable[rang])
    return lambda *args: f(objet, *args)


def _verifier(hr: int):
    if hr < 0:
        raise OSError(f"COM 0x{hr & 0xFFFFFFFF:08X}")


def _liberer(objet):
    if objet:
        _methode(objet, 2)()                 # IUnknown::Release


def _windows(parent, titre: str, depart: str) -> list[str]:
    ole32, shell32 = ctypes.windll.ole32, ctypes.windll.shell32
    ole32.CoInitialize(None)                  # déjà fait par Qt : sans effet dans ce cas
    dlg = ctypes.c_void_p()
    _verifier(ole32.CoCreateInstance(ctypes.byref(_guid(CLSID_FileOpenDialog)), None, 1,  # CLSCTX_INPROC_SERVER
                                     ctypes.byref(_guid(IID_IFileOpenDialog)), ctypes.byref(dlg)))
    try:
        options = ctypes.c_uint()
        _methode(dlg, 10, ctypes.POINTER(ctypes.c_uint))(ctypes.byref(options))          # GetOptions
        _methode(dlg, 9, ctypes.c_uint)(options.value | FOS_PICKFOLDERS | FOS_ALLOWMULTISELECT
                                        | FOS_FORCEFILESYSTEM | FOS_PATHMUSTEXIST)       # SetOptions
        _methode(dlg, 17, ctypes.c_wchar_p)(titre)                                         # SetTitle
        _methode(dlg, 18, ctypes.c_wchar_p)("Sélectionner")                                # SetOkButtonLabel
        if depart and os.path.isdir(depart):
            dossier = ctypes.c_void_p()
            if shell32.SHCreateItemFromParsingName(ctypes.c_wchar_p(os.path.abspath(depart)), None,
                                                   ctypes.byref(_guid(IID_IShellItem)), ctypes.byref(dossier)) >= 0:
                _methode(dlg, 12, ctypes.c_void_p)(dossier)                                # SetFolder
                _liberer(dossier)
        hwnd = int(parent.window().winId()) if parent is not None else 0
        hr = _methode(dlg, 3, ctypes.c_void_p)(hwnd)                                       # Show
        if hr == ERREUR_ANNULE:
            return []
        _verifier(hr)
        resultats = ctypes.c_void_p()
        _verifier(_methode(dlg, 27, ctypes.POINTER(ctypes.c_void_p))(ctypes.byref(resultats)))  # GetResults
        try:
            nombre = ctypes.c_uint()
            _methode(resultats, 7, ctypes.POINTER(ctypes.c_uint))(ctypes.byref(nombre))   # GetCount
            chemins = []
            for i in range(nombre.value):
                element = ctypes.c_void_p()
                if _methode(resultats, 8, ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p))(i, ctypes.byref(element)) < 0:
                    continue                                                               # GetItemAt
                texte = ctypes.c_void_p()
                if _methode(element, 5, ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p))(
                        SIGDN_FILESYSPATH, ctypes.byref(texte)) >= 0:                      # GetDisplayName
                    chemins.append(ctypes.wstring_at(texte))
                    ole32.CoTaskMemFree(texte)
                _liberer(element)
            return chemins
        finally:
            _liberer(resultats)
    finally:
        _liberer(dlg)


# ---------------------------------------------------------------------------- Linux / repli
def _qt(parent, titre: str, depart: str) -> list[str]:
    from PySide6.QtWidgets import QAbstractItemView, QFileDialog, QListView, QTreeView
    dlg = QFileDialog(parent, titre, depart)
    dlg.setFileMode(QFileDialog.FileMode.Directory)
    dlg.setOption(QFileDialog.Option.ShowDirsOnly, True)
    dlg.setOption(QFileDialog.Option.DontUseNativeDialog, True)   # seule la boîte de Qt permet la multi-sélection
    for vue in dlg.findChildren(QListView) + dlg.findChildren(QTreeView):
        vue.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
    if not dlg.exec():
        return []
    return [d for d in dlg.selectedFiles() if os.path.isdir(d)]
