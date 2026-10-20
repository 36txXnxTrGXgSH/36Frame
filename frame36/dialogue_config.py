"""Fenêtre « Configuration »."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
                               QInputDialog, QListWidget, QListWidgetItem, QPushButton, QSlider,
                               QSpinBox, QVBoxLayout, QWidget, QLabel)

from .config import Configuration


class BoutonCouleur(QPushButton):
    change = Signal()

    def __init__(self, couleur: str, parent=None):
        super().__init__(parent)
        self.setFixedWidth(70)
        self.couleur = QColor(couleur)
        self.clicked.connect(self._choisir)
        self._peindre()

    def _peindre(self):
        self.setStyleSheet(f"background: {self.couleur.name()}; border: 1px solid #555; min-height: 20px;")

    def _choisir(self):
        c = QColorDialog.getColor(self.couleur, self, "Couleur")
        if c.isValid():
            self.couleur = c
            self._peindre()
            self.change.emit()


def _curseur(valeur: int) -> tuple[QWidget, QSlider]:
    boite = QWidget()
    l = QHBoxLayout(boite)
    l.setContentsMargins(0, 0, 0, 0)
    s = QSlider(Qt.Orientation.Horizontal)
    s.setRange(0, 100)
    s.setValue(valeur)
    lbl = QLabel(f"{valeur} %")
    lbl.setFixedWidth(40)
    s.valueChanged.connect(lambda v: lbl.setText(f"{v} %"))
    l.addWidget(s)
    l.addWidget(lbl)
    return boite, s


class DialogueConfig(QDialog):
    apercu = Signal()     # changement visible en direct

    def __init__(self, config: Configuration, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuration — 36Frame")
        self.config = config
        self.setMinimumWidth(860)

        # --- fenêtré
        g1 = QGroupBox("Mode fenêtré")
        f1 = QFormLayout(g1)
        self.fen_fond = QComboBox()
        self.fen_fond.addItems(["Couleur (gris par défaut)", "Transparent"])
        self.fen_fond.setCurrentIndex(1 if config.fenetre_fond == "transparent" else 0)
        self.fen_couleur = BoutonCouleur(config.fenetre_couleur)
        defaut = QPushButton("Gris Picasa")
        defaut.clicked.connect(self._gris)
        ligne = QHBoxLayout()
        ligne.addWidget(self.fen_couleur)
        ligne.addWidget(defaut)
        ligne.addStretch()
        boite, self.fen_opacite = _curseur(config.fenetre_opacite)
        self.mode = QComboBox()
        self.mode.addItem("Adaptatif : la fenêtre épouse l'image (Ctrl+molette : fenêtre + image)", "adaptatif")
        self.mode.addItem("PICASA : fenêtre de taille fixe, fond gris autour de l'image", "picasa")
        self.mode.setCurrentIndex(max(0, self.mode.findData(config.mode_affichage)))
        self.taille_max = QSpinBox()
        self.taille_max.setRange(30, 100)
        self.taille_max.setSuffix(" % de l'écran")
        self.taille_max.setValue(config.fenetre_max_ecran)
        self.taille_max.setToolTip("Mode adaptatif : une image plus grande que cela est réduite pour tenir")
        f1.addRow("Mode d'affichage :", self.mode)
        f1.addRow("Grande image, au maximum :", self.taille_max)
        f1.addRow("Fond (mode PICASA) :", self.fen_fond)
        f1.addRow("Couleur :", ligne)
        f1.addRow("Opacité du fond :", boite)
        self.transparence = QComboBox()
        self.transparence.addItem("Voir ce qu'il y a derrière la fenêtre", "derriere")
        self.transparence.addItem("Fond de la fenêtre (gris…)", "fond")
        self.transparence.addItem("Damier (comme un logiciel de retouche)", "damier")
        self.transparence.setCurrentIndex(max(0, self.transparence.findData(config.transparence)))
        self.transparence.setToolTip("PNG, WebP, GIF… détourés (fond transparent).\n"
                                     "« Voir derrière » : la fenêtre n'a plus de fond, seul le sujet reste visible.")
        f1.addRow("Images détourées :", self.transparence)

        # --- plein écran
        g2 = QGroupBox("Mode plein écran")
        f2 = QFormLayout(g2)
        self.pe_couleur = BoutonCouleur(config.plein_ecran_couleur)
        boite2, self.pe_opacite = _curseur(config.plein_ecran_opacite)
        f2.addRow("Teinte du fond :", self.pe_couleur)
        f2.addRow("Opacité (0 % = transparent) :", boite2)

        # --- affichage / diaporama
        g3 = QGroupBox("Affichage et diaporama")
        f3 = QFormLayout(g3)
        self.lissage = QCheckBox("Lissage de qualité (zoom)")
        self.lissage.setChecked(config.lissage)
        self.ombre = QCheckBox("Ombre autour de l'image")
        self.ombre.setChecked(config.ombre_image)
        self.delai = QDoubleSpinBox()
        self.delai.setRange(0.5, 120)
        self.delai.setSuffix(" s")
        self.delai.setValue(config.diaporama_delai)
        self.boucle = QCheckBox("Recommencer au début à la fin du dossier")
        self.boucle.setChecked(config.diaporama_boucle)
        self.dia_pe = QCheckBox("Lancer le diaporama en plein écran")
        self.dia_pe.setChecked(config.diaporama_plein_ecran)
        self.masquage = QSpinBox()
        self.masquage.setRange(0, 5000)
        self.masquage.setSingleStep(100)
        self.masquage.setSuffix(" ms")
        self.masquage.setValue(config.barre_delai_masquage)
        self.echap = QCheckBox("Échap ferme la liseuse en mode fenêtré")
        self.echap.setChecked(config.echap_ferme)
        f3.addRow(self.lissage)
        f3.addRow(self.ombre)
        f3.addRow("Durée par image :", self.delai)
        f3.addRow(self.boucle)
        f3.addRow(self.dia_pe)
        f3.addRow("Masquer la barre après :", self.masquage)
        self.barre_fond = QCheckBox("Bandeau sombre derrière la barre d'outils")
        self.barre_fond.setChecked(config.barre_fond)
        f3.addRow(self.barre_fond)
        f3.addRow(self.echap)
        self.confirmer = QCheckBox("Demander confirmation avant de mettre une image à la corbeille")
        self.confirmer.setChecked(config.confirmer_suppression)
        f3.addRow(self.confirmer)
        self.b_cache = QPushButton()
        self.b_cache.setAutoDefault(False)
        self.b_cache.setToolTip("Efface les miniatures gardées sur le disque (elles sont recréées pour les images\n"
                                "que vous ouvrirez). Réglages et favoris ne sont pas touchés.")
        self.b_cache.clicked.connect(self._vider_cache)
        self._maj_bouton_cache()
        f3.addRow("Miniatures sur le disque :", self.b_cache)

        # --- plusieurs fenêtres
        from .gestion import MODES_MOSAIQUE
        g5 = QGroupBox("Plusieurs fenêtres")
        f5 = QFormLayout(g5)
        self.nouvelle = QCheckBox("Une image ouverte depuis l'Explorateur s'ouvre dans une nouvelle fenêtre")
        self.nouvelle.setChecked(config.nouvelle_fenetre)
        self.mosaique = QComboBox()
        for cle, texte in MODES_MOSAIQUE.items():
            self.mosaique.addItem(texte, cle)
        self.mosaique.setCurrentIndex(max(0, self.mosaique.findData(config.mosaique_mode)))
        self.marge = QSpinBox()
        self.marge.setRange(0, 60)
        self.marge.setSuffix(" px")
        self.marge.setValue(config.mosaique_marge)
        f5.addRow(self.nouvelle)
        f5.addRow("Mosaïque :", self.mosaique)
        f5.addRow("Espace entre les fenêtres :", self.marge)
        self.rangees = QDoubleSpinBox()
        self.rangees.setRange(1.2, 10)
        self.rangees.setSingleStep(0.5)
        self.rangees.setDecimals(1)
        self.rangees.setValue(config.mosaique_dossier_rangees)
        self.rangees.setToolTip("Nombre de rangées d'images à l'écran (aussi : Ctrl+molette dans la mosaïque)")
        f5.addRow("Mosaïque Dossier, rangées :", self.rangees)
        self.orientation = QComboBox()
        self.orientation.addItem("Vertical (rangées, défilement de haut en bas)", "verticale")
        self.orientation.addItem("Horizontal (colonnes, défilement de gauche à droite)", "horizontale")
        self.orientation.setCurrentIndex(max(0, self.orientation.findData(config.mosaique_dossier_orientation)))
        f5.addRow("Mosaïque Dossier, défilement :", self.orientation)
        self.panorama = QDoubleSpinBox()
        self.panorama.setRange(2, 300)
        self.panorama.setDecimals(0)
        self.panorama.setSuffix(" s par écran")
        self.panorama.setValue(config.panorama_duree)
        self.panorama.setToolTip("Temps mis par le Panorama pour faire défiler un écran entier d'images")
        f5.addRow("Vitesse du Panorama :", self.panorama)
        boite_d, self.douceur = _curseur(config.mosaique_douceur * 10)
        self.douceur.setRange(10, 100)
        self.douceur.setSingleStep(10)
        self.douceur.setPageStep(10)
        self.douceur.setToolTip("Défilement à la molette dans la Mosaïque Dossier : à gauche vif, à droite très doux")
        f5.addRow("Douceur du défilement :", boite_d)
        self.animer = QComboBox()
        self.animer.addItem("Toujours (toutes les images visibles)", "toujours")
        self.animer.addItem("Au survol de la souris (toutes pendant le Panorama)", "survol")
        self.animer.addItem("Jamais (images fixes)", "jamais")
        self.animer.setCurrentIndex(max(0, self.animer.findData(config.mosaique_animation)))
        self.animer.setToolTip("GIF et WebP animés dans la Mosaïque Dossier.\n"
                               "« Au survol » économise le processeur : seule l'image sous la souris s'anime.")
        f5.addRow("Mosaïque Dossier, animations :", self.animer)

        # --- applications
        g4 = QGroupBox("Logiciels « Ouvrir avec » ajoutés")
        v4 = QVBoxLayout(g4)
        self.apps = QListWidget()
        self.apps.setMaximumHeight(110)
        for a in config.applications:
            self._ajouter_item(a["nom"], a["chemin"])
        b_aj = QPushButton("Ajouter…")
        b_aj.clicked.connect(self._ajouter_app)
        b_sup = QPushButton("Retirer")
        b_sup.clicked.connect(lambda: [self.apps.takeItem(self.apps.row(i)) for i in self.apps.selectedItems()])
        lb = QHBoxLayout()
        lb.addWidget(b_aj)
        lb.addWidget(b_sup)
        lb.addStretch()
        v4.addWidget(self.apps)
        v4.addLayout(lb)

        # --- visionneuse par défaut (Windows)
        from . import associations
        g6 = None
        if associations.disponible():
            g6 = QGroupBox("Visionneuse par défaut de Windows")
            v6 = QVBoxLayout(g6)
            info = QLabel("Cochez les types d'images à ouvrir avec 36Frame. Windows demande ensuite une "
                          "dernière validation : sur la page qui s'ouvre, cliquez sur « Définir par défaut ».")
            info.setWordWrap(True)
            self.extensions = QListWidget()
            self.extensions.setMaximumHeight(150)
            deja = set(associations.declarees())
            for groupe, liste in associations.GROUPES.items():
                for ext, desc in liste:
                    it = QListWidgetItem(f"{ext}   {desc}   ({groupe})")
                    it.setData(Qt.ItemDataRole.UserRole, ext)
                    it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    coche = ext in deja if deja else ext in associations.PAR_DEFAUT
                    it.setCheckState(Qt.CheckState.Checked if coche else Qt.CheckState.Unchecked)
                    self.extensions.addItem(it)
            b_tout = QPushButton("Tout cocher")
            b_tout.clicked.connect(lambda: [self.extensions.item(i).setCheckState(Qt.CheckState.Checked)
                                            for i in range(self.extensions.count())])
            b_def = QPushButton("Définir 36Frame par défaut…")
            b_def.setDefault(False)
            b_def.setAutoDefault(False)
            b_def.clicked.connect(self._definir_par_defaut)
            b_ret = QPushButton("Retirer")
            b_ret.setAutoDefault(False)
            b_ret.setToolTip("Efface les déclarations de 36Frame (Windows reprend ses applications habituelles)")
            b_ret.clicked.connect(self._retirer_associations)
            self.etat_assoc = QLabel(f"{len(deja)} type(s) déclaré(s) pour 36Frame." if deja
                                     else "36Frame n'est pas encore déclaré à Windows.")
            lb6 = QHBoxLayout()
            lb6.addWidget(b_tout)
            lb6.addStretch()
            lb6.addWidget(b_ret)
            lb6.addWidget(b_def)
            v6.addWidget(info)
            v6.addWidget(self.extensions)
            v6.addLayout(lb6)
            v6.addWidget(self.etat_assoc)

        boutons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        boutons.accepted.connect(self.accept)
        boutons.rejected.connect(self.reject)

        gauche, droite = QVBoxLayout(), QVBoxLayout()
        for g in (g1, g2, g5, g4):
            gauche.addWidget(g)
        for g in (g3,) + ((g6,) if g6 is not None else ()):
            droite.addWidget(g)
        gauche.addStretch()
        droite.addStretch()
        colonnes = QHBoxLayout()
        colonnes.addLayout(gauche)
        colonnes.addLayout(droite)
        v = QVBoxLayout(self)
        v.addLayout(colonnes)
        v.addWidget(boutons)

        for signal in (self.fen_fond.currentIndexChanged, self.fen_opacite.valueChanged,
                       self.transparence.currentIndexChanged, self.mode.currentIndexChanged,
                       self.pe_opacite.valueChanged, self.fen_couleur.change, self.pe_couleur.change,
                       self.lissage.toggled, self.ombre.toggled, self.barre_fond.toggled):
            signal.connect(self._appliquer_apercu)

    def _gris(self):
        self.fen_couleur.couleur = QColor("#7f7f7f")
        self.fen_couleur._peindre()
        self.fen_fond.setCurrentIndex(0)
        self.fen_opacite.setValue(100)
        self._appliquer_apercu()

    def _ajouter_item(self, nom, chemin):
        it = QListWidgetItem(f"{nom}  —  {chemin}")
        it.setData(Qt.ItemDataRole.UserRole, {"nom": nom, "chemin": chemin})
        self.apps.addItem(it)

    def _ajouter_app(self):
        filtre = "Programmes (*.exe *.bat *.cmd)" if os.name == "nt" else "Tous les fichiers (*)"
        chemin, _ = QFileDialog.getOpenFileName(self, "Choisir un logiciel", "", filtre)
        if not chemin:
            return
        nom, ok = QInputDialog.getText(self, "Nom du logiciel", "Nom affiché :",
                                       text=os.path.splitext(os.path.basename(chemin))[0])
        if ok and nom:
            self._ajouter_item(nom, chemin)

    def _ecrire(self):
        c = self.config
        c.mode_affichage = self.mode.currentData()
        c.fenetre_max_ecran = self.taille_max.value()
        c.fenetre_fond = "transparent" if self.fen_fond.currentIndex() == 1 else "couleur"
        c.fenetre_couleur = self.fen_couleur.couleur.name()
        c.fenetre_opacite = self.fen_opacite.value()
        c.transparence = self.transparence.currentData()
        c.plein_ecran_couleur = self.pe_couleur.couleur.name()
        c.plein_ecran_opacite = self.pe_opacite.value()
        c.lissage = self.lissage.isChecked()
        c.ombre_image = self.ombre.isChecked()
        c.barre_fond = self.barre_fond.isChecked()

    def _appliquer_apercu(self, *_):
        self._ecrire()
        self.apercu.emit()

    def _extensions_cochees(self) -> list[str]:
        return [self.extensions.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.extensions.count())
                if self.extensions.item(i).checkState() == Qt.CheckState.Checked]

    def _maj_bouton_cache(self):
        from .config import dossier_cache
        n, taille = 0, 0
        try:
            with os.scandir(dossier_cache()) as it:
                for e in it:
                    if e.is_file():
                        n += 1
                        taille += e.stat().st_size
        except OSError:
            pass
        self.b_cache.setText(f"Vider le cache des miniatures ({n} — {taille / 2**20:.1f} Mo)")
        self.b_cache.setEnabled(n > 0)

    def _vider_cache(self):
        from PySide6.QtWidgets import QMessageBox
        from .config import dossier_cache
        if QMessageBox.question(self, "36Frame", "Effacer toutes les miniatures enregistrées sur le disque ?\n\n"
                                "Elles seront recréées pour les images que vous ouvrirez.") \
                != QMessageBox.StandardButton.Yes:
            return
        restants = 0
        try:
            with os.scandir(dossier_cache()) as it:
                for e in it:
                    if e.is_file():
                        try:
                            os.remove(e.path)
                        except OSError:
                            restants += 1
        except OSError:
            pass
        # miniatures déjà en mémoire dans les fenêtres ouvertes
        gestion = getattr(self.parent(), "gestion", None)
        if gestion is not None:
            gestion.miniatures.cache.clear()
        self._maj_bouton_cache()
        if restants:
            QMessageBox.warning(self, "36Frame", f"{restants} miniature(s) n'ont pas pu être effacées (fichier utilisé ?).")

    def _definir_par_defaut(self):
        from PySide6.QtWidgets import QMessageBox
        from . import associations
        exts = self._extensions_cochees()
        if not exts:
            QMessageBox.information(self, "36Frame", "Cochez au moins un type d'image.")
            return
        try:
            associations.declarer(exts)
        except OSError as e:
            QMessageBox.warning(self, "36Frame", f"Windows a refusé la déclaration :\n{e}")
            return
        self.etat_assoc.setText(f"{len(exts)} type(s) déclaré(s). Dernière étape dans la fenêtre Paramètres : "
                                "« Définir par défaut ».")
        associations.ouvrir_parametres()

    def _retirer_associations(self):
        from PySide6.QtWidgets import QMessageBox
        from . import associations
        if QMessageBox.question(self, "36Frame", "Retirer 36Frame des applications d'images de Windows ?\n\n"
                                "Les images s'ouvriront de nouveau avec l'application choisie par Windows.") \
                != QMessageBox.StandardButton.Yes:
            return
        try:
            associations.retirer()
        except OSError as e:
            QMessageBox.warning(self, "36Frame", f"Impossible de tout retirer :\n{e}")
            return
        self.etat_assoc.setText("36Frame n'est plus déclaré à Windows.")

    def accept(self):
        self._ecrire()
        c = self.config
        c.diaporama_delai = self.delai.value()
        c.diaporama_boucle = self.boucle.isChecked()
        c.diaporama_plein_ecran = self.dia_pe.isChecked()
        c.barre_delai_masquage = self.masquage.value()
        c.echap_ferme = self.echap.isChecked()
        c.confirmer_suppression = self.confirmer.isChecked()
        c.nouvelle_fenetre = self.nouvelle.isChecked()
        c.mosaique_mode = self.mosaique.currentData()
        c.mosaique_marge = self.marge.value()
        c.mosaique_dossier_rangees = self.rangees.value()
        c.mosaique_dossier_orientation = self.orientation.currentData()
        c.panorama_duree = self.panorama.value()
        c.mosaique_douceur = max(1, min(10, round(self.douceur.value() / 10)))
        c.mosaique_animation = self.animer.currentData()
        c.applications = [self.apps.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.apps.count())]
        c.enregistrer()
        super().accept()
