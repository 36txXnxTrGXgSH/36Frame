#!/bin/sh
# Fabrique la version Linux de 36Frame, A LANCER SUR UN LINUX (Ubuntu, Debian, Mint, Fedora…) :
#
#   sh Linux/construire-linux.sh
#
# Resultat dans Linux/sortie/ :
#   - 36Frame-<version>-x86_64.AppImage   un seul fichier, aucune installation (equivalent du portable)
#   - 36Frame-<version>-linux-x86_64.tar.gz  le dossier du programme + installer-linux.sh
#
# Prerequis (une seule fois) :
#   Ubuntu / Debian / Mint : sudo apt install python3-venv python3-pip binutils libxcb-cursor0 file
#   Fedora                 : sudo dnf install python3 python3-pip binutils xcb-util-cursor file
set -e
cd "$(dirname "$0")/.."
RACINE="$(pwd)"
SORTIE="$RACINE/Linux/sortie"

# --- environnement Python dedie (separe du .venv Windows)
if [ ! -x .venv-linux/bin/python ]; then
    python3 -m venv .venv-linux
fi
PY="$RACINE/.venv-linux/bin/python"
"$PY" -m pip install -q --upgrade pip
"$PY" -m pip install -q -r requirements-compilation.txt

VERSION="$("$PY" -c 'import frame36; print(frame36.__version__)')"
echo "== 36Frame $VERSION (Linux) =="

echo "== Icone =="
QT_QPA_PLATFORM=offscreen "$PY" outils/fabriquer_icone.py

echo "== Compilation (PyInstaller) =="
# 36frame.spec : même recette allégée que sous Windows (OpenGL logiciel, chiffrement réseau… retirés)
MODE=dossier NOM=36Frame "$PY" -m PyInstaller --noconfirm --clean \
    --distpath build/linux/dist --workpath build/linux/travail 36frame.spec

mkdir -p "$SORTIE"

echo "== Archive tar.gz =="
PAQUET="build/linux/36Frame-$VERSION"
rm -rf "$PAQUET"
mkdir -p "$PAQUET"
cp -r build/linux/dist/36Frame "$PAQUET/programme"
cp assets/36frame.png "$PAQUET/"
cp Linux/installer-linux.sh Linux/36frame.desktop Linux/LISEZ-MOI.txt THIRD_PARTY_NOTICES.md "$PAQUET/"
tar -czf "$SORTIE/36Frame-$VERSION-linux-x86_64.tar.gz" -C build/linux "36Frame-$VERSION"

echo "== AppImage =="
APPDIR="build/linux/36Frame.AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/lib"
cp -r build/linux/dist/36Frame "$APPDIR/usr/lib/36Frame"
cp assets/36frame.png "$APPDIR/36frame.png"
sed 's|^Exec=.*|Exec=36Frame %F|' Linux/36frame.desktop > "$APPDIR/36frame.desktop"
cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/lib/36Frame/36Frame" "$@"
EOF
chmod +x "$APPDIR/AppRun"
OUTIL="build/linux/appimagetool-x86_64.AppImage"
if [ ! -x "$OUTIL" ]; then
    echo "Telechargement d'appimagetool (outil officiel AppImage)..."
    curl -L -o "$OUTIL" https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
    # Outil téléchargé : vérifiez son empreinte si vous la connaissez (APPIMAGETOOL_SHA256=...)
    if [ -n "$APPIMAGETOOL_SHA256" ]; then
        echo "$APPIMAGETOOL_SHA256  $OUTIL" | sha256sum -c - || { echo "Empreinte incorrecte : abandon."; rm -f "$OUTIL"; exit 1; }
    fi
    chmod +x "$OUTIL"
fi
# --appimage-extract-and-run : fonctionne meme sans FUSE
ARCH=x86_64 "$OUTIL" --appimage-extract-and-run "$APPDIR" "$SORTIE/36Frame-$VERSION-x86_64.AppImage"

echo "== Termine : $SORTIE =="
ls -lh "$SORTIE"
