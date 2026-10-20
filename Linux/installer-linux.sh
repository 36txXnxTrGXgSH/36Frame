#!/bin/sh
# Installe 36Frame pour l'utilisateur courant (sans sudo), depuis l'archive tar.gz decompressee :
#
#   sh installer-linux.sh            installe et ajoute 36Frame au menu des applications
#   sh installer-linux.sh --defaut   idem + 36Frame devient la visionneuse d'images par defaut
#   sh installer-linux.sh --retirer  desinstalle
set -e
ICI="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/.local/opt/36Frame"
APPS="$HOME/.local/share/applications"
ICONES="$HOME/.local/share/icons/hicolor/256x256/apps"
BIN="$HOME/.local/bin"
TYPES="image/jpeg image/png image/gif image/webp image/bmp image/tiff image/avif"

if [ "$1" = "--retirer" ]; then
    rm -rf "$DEST" "$APPS/36frame.desktop" "$ICONES/36frame.png" "$BIN/36frame"
    command -v update-desktop-database >/dev/null && update-desktop-database "$APPS" || true
    echo "36Frame a ete retire."
    exit 0
fi

mkdir -p "$DEST" "$APPS" "$ICONES" "$BIN"
rm -rf "$DEST"
cp -r "$ICI/programme" "$DEST"
chmod +x "$DEST/36Frame"
cp "$ICI/36frame.png" "$ICONES/36frame.png"
sed "s|36FRAME_EXEC|$DEST/36Frame|" "$ICI/36frame.desktop" > "$APPS/36frame.desktop"
ln -sf "$DEST/36Frame" "$BIN/36frame"
command -v update-desktop-database >/dev/null && update-desktop-database "$APPS" || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q "$HOME/.local/share/icons/hicolor" || true

if [ "$1" = "--defaut" ]; then
    for t in $TYPES; do xdg-mime default 36frame.desktop "$t"; done
    echo "36Frame est maintenant la visionneuse d'images par defaut."
fi
echo "36Frame installe dans $DEST"
echo "Lancement : menu des applications > 36Frame, ou la commande « 36frame »."
