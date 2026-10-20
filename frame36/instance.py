"""Instance unique, côté « lancement secondaire », SANS charger Qt.

Quand on ouvre une autre image depuis l'Explorateur, Windows lance un nouveau 36Frame. Celui-ci
doit seulement transmettre le chemin à la fenêtre déjà ouverte puis se terminer : charger Qt pour
ça coûtait la majeure partie du temps (plusieurs secondes sur un portable avec antivirus). On écrit
donc directement dans le canal du QLocalServer de la première instance :
  Windows : tube nommé \\\\.\\pipe\\<nom>     Linux : socket Unix <tmp>/<nom>
"""

from __future__ import annotations

import getpass
import json
import os
import sys

NOM_SERVEUR = "36Frame-" + "".join(c for c in getpass.getuser() if c.isalnum())
TAILLE_MAX_MESSAGE = 1024 * 1024        # 1 Mo : des milliers de chemins ; au-delà, message ignoré


def adresse_serveur() -> str:
    """Windows : nom du tube (réservé à l'utilisateur, voir gestion.py).
    Linux : chemin complet du socket dans XDG_RUNTIME_DIR (dossier privé de l'utilisateur, 0700),
    plutôt que /tmp où un autre compte pourrait créer le socket avant nous et recevoir nos chemins."""
    if sys.platform == "win32":
        return NOM_SERVEUR
    prive = os.environ.get("XDG_RUNTIME_DIR")
    if prive and os.path.isdir(prive):
        return os.path.join(prive, NOM_SERVEUR)
    return os.path.join(os.environ.get("TMPDIR") or "/tmp", NOM_SERVEUR)     # = QDir::tempPath()


def lire_message(donnees: bytes) -> list[str]:
    """Décode un message reçu d'un autre lancement : uniquement une liste de chemins (texte)."""
    try:
        valeur = json.loads(donnees.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return []
    if not isinstance(valeur, list):
        return []
    return [c for c in valeur if isinstance(c, str) and c and len(c) < 32768]


def _message(chemins: list[str]) -> bytes:
    return json.dumps([os.path.abspath(c) for c in chemins]).encode("utf-8") + b"\n"


def envoyer_rapide(chemins: list[str]) -> bool:
    """Confie les fichiers à l'instance déjà lancée. Renvoie False s'il n'y en a pas."""
    donnees = _message(chemins)
    if sys.platform == "win32":
        try:
            with open("\\\\.\\pipe\\" + adresse_serveur(), "r+b", buffering=0) as tube:
                tube.write(donnees)
                try:
                    tube.read(1)          # attend que l'instance ait tout lu et ferme le tube
                except OSError:
                    pass
            return True
        except OSError:
            return False
    import socket
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(2)
            s.connect(adresse_serveur())
            s.sendall(donnees)
            try:
                s.recv(1)
            except OSError:
                pass
        return True
    except OSError:
        return False
