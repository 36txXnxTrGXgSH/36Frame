"""Fenêtre « Ouvrir des dossiers » : un ou plusieurs dossiers, sous-dossiers compris."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QPushButton, QVBoxLayout)


class _ListeDepot(QListWidget):
    """Liste qui accepte les dossiers glissés depuis l'Explorateur."""

    def __init__(self, ajouter, parent=None):
        super().__init__(parent)
        self._ajouter = ajouter
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        for url in e.mimeData().urls():
            p = url.toLocalFile()
            if p and os.path.isdir(p):
                self._ajouter(p)
        e.acceptProposedAction()


class DialogueDossiers(QDialog):
    def __init__(self, depart: str = "", precedents: list[str] | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ouvrir des dossiers — 36Frame")
        self.setMinimumSize(620, 380)
        self.depart = depart
        self.precedents = [d for d in (precedents or []) if os.path.isdir(d)]

        info = QLabel("Toutes les images de ces dossiers <b>et de leurs sous-dossiers</b> seront réunies.<br>"
                      "Ajoutez des dossiers (Ctrl+clic pour en choisir plusieurs à la fois), même depuis des disques<br>"
                      "différents, ou glissez-les ici depuis l'Explorateur.")
        info.setWordWrap(True)
        self.liste = _ListeDepot(self.ajouter)
        self.liste.itemSelectionChanged.connect(self._maj)

        b_ajouter = QPushButton("Ajouter des dossiers…")
        b_ajouter.clicked.connect(self._choisir)
        self.b_retirer = QPushButton("Retirer")
        self.b_retirer.clicked.connect(self._retirer)
        self.b_reprendre = QPushButton(f"Reprendre la dernière sélection ({len(self.precedents)})")
        self.b_reprendre.setVisible(bool(self.precedents))
        self.b_reprendre.clicked.connect(lambda: [self.ajouter(d) for d in self.precedents])
        lb = QHBoxLayout()
        lb.addWidget(b_ajouter)
        lb.addWidget(self.b_retirer)
        lb.addStretch()
        lb.addWidget(self.b_reprendre)

        self.boutons = QDialogButtonBox(QDialogButtonBox.StandardButton.Open | QDialogButtonBox.StandardButton.Cancel)
        self.boutons.button(QDialogButtonBox.StandardButton.Open).setText("Ouvrir")
        self.boutons.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuler")
        self.boutons.accepted.connect(self.accept)
        self.boutons.rejected.connect(self.reject)

        v = QVBoxLayout(self)
        v.addWidget(info)
        v.addWidget(self.liste, 1)
        v.addLayout(lb)
        v.addWidget(self.boutons)
        self._maj()

    def dossiers(self) -> list[str]:
        return [self.liste.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.liste.count())]

    def ajouter(self, dossier: str):
        dossier = os.path.abspath(dossier)
        cle = os.path.normcase(dossier)
        if any(os.path.normcase(d) == cle for d in self.dossiers()):
            return
        it = QListWidgetItem(dossier)
        it.setData(Qt.ItemDataRole.UserRole, dossier)
        it.setToolTip(dossier)
        self.liste.addItem(it)
        self.depart = os.path.dirname(dossier)
        self._maj()

    def _choisir(self):
        from .choix_dossiers import choisir_dossiers
        for d in choisir_dossiers(self, "Ajouter des dossiers (Ctrl+clic pour en choisir plusieurs)", self.depart):
            self.ajouter(d)

    def _retirer(self):
        for it in self.liste.selectedItems():
            self.liste.takeItem(self.liste.row(it))
        self._maj()

    def _maj(self):
        self.b_retirer.setEnabled(bool(self.liste.selectedItems()))
        self.boutons.button(QDialogButtonBox.StandardButton.Open).setEnabled(self.liste.count() > 0)
