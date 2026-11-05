"""Impression, aperçu avant impression et mise en page.

Réglages disponibles :
- fenêtre d'impression de Windows : imprimante, nombre de copies, couleur / noir et blanc,
  recto-verso, pages (selon l'imprimante) ;
- mise en page : format du papier, orientation, marges ;
- 36Frame (mémorisés dans la configuration) : ajuster l'image à la page, taille réelle (selon la
  résolution enregistrée dans le fichier), ou remplir la page en rognant ; centrer ou non ; marges ;
  orientation automatique selon l'image (paysage si elle est plus large que haute).
"""

from __future__ import annotations

from PySide6.QtCore import QMarginsF, QRectF
from PySide6.QtGui import QImage, QPageLayout, QPageSize, QPainter
from PySide6.QtPrintSupport import (QPageSetupDialog, QPrintDialog, QPrinter, QPrintPreviewDialog,
                                    QPrintPreviewWidget)
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel, QWidget)

MODES = {
    "ajuster": "Ajuster à la page",
    "reel": "Taille réelle",
    "remplir": "Remplir la page (rogner)",
}


def _preparer(imprimante: QPrinter, image: QImage, config, titre: str = "") -> None:
    """Applique à l'imprimante les réglages mémorisés (papier, orientation, marges)."""
    if titre:
        imprimante.setDocName(titre)
    if config.impression_papier:
        try:
            imprimante.setPageSize(QPageSize(QPageSize.PageSizeId[config.impression_papier]))
        except KeyError:
            pass
    if config.impression_orientation == "auto":
        paysage = image.width() > image.height()
    else:
        paysage = config.impression_orientation == "paysage"
    imprimante.setPageOrientation(QPageLayout.Orientation.Landscape if paysage else QPageLayout.Orientation.Portrait)
    m = max(0.0, min(50.0, float(config.impression_marges_mm)))
    imprimante.setPageMargins(QMarginsF(m, m, m, m), QPageLayout.Unit.Millimeter)


def rectangle_image(image: QImage, zone: QRectF, resolution: int, mode: str, centrer: bool) -> QRectF:
    """Où dessiner l'image dans la zone imprimable (en pixels de l'imprimante)."""
    l, h = image.width(), image.height()
    if mode == "reel":
        # taille réelle : selon la résolution enregistrée dans le fichier (72 / 96 / 300 ppp…)
        ppp_x = image.dotsPerMeterX() * 0.0254
        ppp_y = image.dotsPerMeterY() * 0.0254
        ppp_x = ppp_x if ppp_x >= 30 else 96.0
        ppp_y = ppp_y if ppp_y >= 30 else 96.0
        l, h = l / ppp_x * resolution, h / ppp_y * resolution
        if l > zone.width() or h > zone.height():          # plus grande que la page : réduite
            e = min(zone.width() / l, zone.height() / h)
            l, h = l * e, h * e
    elif mode == "remplir":
        e = max(zone.width() / l, zone.height() / h)
        l, h = l * e, h * e
    else:
        e = min(zone.width() / l, zone.height() / h)
        l, h = l * e, h * e
    cible = QRectF(0, 0, l, h)
    if centrer or mode == "remplir":
        cible.moveCenter(zone.center())
    else:
        cible.moveTopLeft(zone.topLeft())
    return cible


def dessiner(imprimante: QPrinter, image: QImage, config) -> None:
    p = QPainter(imprimante)
    if not p.isActive():
        return
    zone = QRectF(imprimante.pageLayout().paintRectPixels(imprimante.resolution()))
    zone.moveTo(0, 0)
    cible = rectangle_image(image, zone, imprimante.resolution(), config.impression_mode, config.impression_centrer)
    p.setClipRect(zone)                     # « remplir » : ce qui dépasse de la page est rogné
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    p.drawImage(cible, image)
    p.end()


def _options_apercu(dlg: QPrintPreviewDialog, imprimante: QPrinter, image: QImage, config) -> None:
    """Ajoute à la barre de l'aperçu les réglages propres à 36Frame."""
    vue = dlg.findChild(QPrintPreviewWidget)
    disposition = dlg.layout()
    if vue is None or disposition is None:
        return
    boite = QWidget()                       # seconde ligne, sous la barre de Qt (toujours visible)
    l = QHBoxLayout(boite)
    l.setContentsMargins(10, 4, 10, 4)
    mode = QComboBox()
    for cle, texte in MODES.items():
        mode.addItem(texte, cle)
    mode.setCurrentIndex(max(0, mode.findData(config.impression_mode)))
    centrer = QCheckBox("Centrer")
    centrer.setChecked(config.impression_centrer)
    marges = QDoubleSpinBox()
    marges.setRange(0, 50)
    marges.setDecimals(0)
    marges.setSuffix(" mm")
    marges.setValue(config.impression_marges_mm)
    for w in (QLabel("Image :"), mode, centrer, QLabel("   Marges :"), marges):
        l.addWidget(w)
    l.addStretch(1)
    l.addWidget(QLabel("Papier, orientation : bouton « Mise en page » ci-dessus · "
                       "imprimante, copies, couleur, recto-verso : bouton « Imprimer »"))

    def changer(*_):
        config.impression_mode = mode.currentData()
        config.impression_centrer = centrer.isChecked()
        config.impression_marges_mm = marges.value()
        m = marges.value()
        imprimante.setPageMargins(QMarginsF(m, m, m, m), QPageLayout.Unit.Millimeter)
        vue.updatePreview()

    mode.currentIndexChanged.connect(changer)
    centrer.toggled.connect(changer)
    marges.valueChanged.connect(changer)
    disposition.insertWidget(1, boite)


def imprimer(image: QImage, parent, titre: str, config, apercu: bool = False) -> None:
    imprimante = QPrinter(QPrinter.PrinterMode.HighResolution)
    _preparer(imprimante, image, config, titre)
    if apercu:
        dlg = QPrintPreviewDialog(imprimante, parent)
        dlg.setWindowTitle(f"Aperçu avant impression — {titre}")
        dlg.paintRequested.connect(lambda pr: dessiner(pr, image, config))
        _options_apercu(dlg, imprimante, image, config)
        dlg.resize(1100, 820)
        dlg.exec()                     # son bouton « Imprimer » ouvre la fenêtre d'impression de Windows
    else:
        dlg = QPrintDialog(imprimante, parent)
        dlg.setWindowTitle(f"Imprimer {titre}")
        if dlg.exec() == QPrintDialog.DialogCode.Accepted:
            dessiner(imprimante, image, config)
    config.enregistrer()


def mise_en_page(parent, config) -> None:
    """Papier, orientation et marges par défaut (mémorisés)."""
    imprimante = QPrinter(QPrinter.PrinterMode.HighResolution)
    _preparer(imprimante, QImage(1, 1, QImage.Format.Format_RGB32), config)
    if config.impression_orientation == "auto":
        imprimante.setPageOrientation(QPageLayout.Orientation.Portrait)
    dlg = QPageSetupDialog(imprimante, parent)
    dlg.setWindowTitle("Mise en page — 36Frame")
    if dlg.exec() != QPageSetupDialog.DialogCode.Accepted:
        return
    page = imprimante.pageLayout()
    config.impression_papier = page.pageSize().id().name
    config.impression_orientation = "paysage" if page.orientation() == QPageLayout.Orientation.Landscape else "portrait"
    marges = page.margins(QPageLayout.Unit.Millimeter)
    config.impression_marges_mm = round(min(marges.left(), marges.top(), marges.right(), marges.bottom()), 1)
    config.enregistrer()
