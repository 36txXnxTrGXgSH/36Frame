# Composants tiers inclus dans 36Frame

Les exécutables de 36Frame (installateur, versions portables, AppImage) contiennent les composants
suivants. Ils restent sous leur propre licence.

| Composant | Rôle | Licence | Source |
|---|---|---|---|
| **Python** 3.14 | interpréteur | PSF License | https://www.python.org |
| **Qt 6** (Core, Gui, Widgets, Network, Svg) | interface, décodage d'images | **LGPL v3** | https://www.qt.io / https://code.qt.io |
| **PySide6 / Shiboken6** 6.12 | liaison Python ↔ Qt | **LGPL v3** | https://pypi.org/project/PySide6-Essentials |
| Modules d'images de Qt (qjpeg, qpng, qwebp, qtiff, qgif, qsvg…) | JPEG, WebP, TIFF… | LGPL v3 + bibliothèques libjpeg-turbo (BSD/IJG), libwebp (BSD), libtiff (libtiff), libpng (libpng), zlib (zlib) | https://code.qt.io/qt/qtimageformats |
| **Pillow** 12.3 | AVIF, PSD, DDS, JPEG 2000 | MIT-CMU (HPND) ; libavif (BSD-2), dav1d (BSD-2), aom (BSD-2) | https://python-pillow.org |
| **PyInstaller** 6.22 (chargeur) | fabrication de l'exe | GPL v2 avec exception pour le chargeur (sans effet sur la licence de 36Frame) | https://pyinstaller.org |
| **Inno Setup** | installateur Windows | licence Inno Setup | https://jrsoftware.org/isinfo.php |

## Qt et PySide6 (LGPL v3)

Qt et PySide6 sont utilisés sans modification, sous forme de **bibliothèques séparées** (fichiers
`Qt6*.dll`, `PySide6\*.pyd` dans le dossier du programme installé). Conformément à la LGPL v3 :

- le texte de la licence est disponible sur https://www.gnu.org/licenses/lgpl-3.0.html ;
- le code source de Qt et de PySide6 est disponible aux adresses ci-dessus ;
- vous pouvez remplacer ces bibliothèques par une autre version compatible : la version installée
  (et la version portable « rapide ») les contient en fichiers séparés ; le code de 36Frame est
  publié dans ce dépôt, et `compiler.ps1` / `Linux/construire-linux.sh` permettent de refabriquer le
  programme avec la version de votre choix (`requirements.txt`).
