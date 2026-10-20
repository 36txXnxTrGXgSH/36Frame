"""Point d'entrée sans console (double-clic, association de fichiers, futur exe PyInstaller)."""

import sys

from frame36.__main__ import principal

sys.exit(principal())
