"""Fabrique assets/36frame.ico (exe, installateur) à partir de l'icône dessinée dans frame36/icones.py."""

import io
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from PIL import Image
from PySide6.QtCore import QBuffer, QIODevice, QSize
from PySide6.QtGui import QGuiApplication

app = QGuiApplication([])
from frame36.icones import icone_appli  # noqa: E402

pix = icone_appli().pixmap(QSize(256, 256))
tampon = QBuffer()
tampon.open(QIODevice.OpenModeFlag.WriteOnly)
pix.save(tampon, "PNG")
image = Image.open(io.BytesIO(bytes(tampon.data()))).convert("RGBA")

sortie = RACINE / "assets" / "36frame.ico"
sortie.parent.mkdir(exist_ok=True)
image.save(sortie, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
image.save(RACINE / "assets" / "36frame.png")      # Linux (.desktop, AppImage)
print(sortie)
