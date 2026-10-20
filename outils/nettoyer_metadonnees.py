"""Copie des JPEG en retirant leurs métadonnées, SANS recompression (aucune perte de qualité).

    python outils/nettoyer_metadonnees.py <dossier source> <dossier destination>

Retirés : EXIF (appareil, date, GPS…), XMP (logiciel, historique, identifiants de documents),
blocs Photoshop (APP13), commentaires (COM) et autres blocs d'application.
Gardés : JFIF (APP0), profil de couleur ICC (APP2, sinon les couleurs changent) et bloc Adobe
(APP14, nécessaire pour décoder correctement certains JPEG), puis l'image elle-même, octet pour octet.
"""

import os
import sys

GARDES = {0xE0: b"JFIF", 0xE2: b"ICC_PROFILE", 0xEE: b"Adobe"}


def nettoyer(donnees: bytes) -> bytes:
    if donnees[:2] != b"\xff\xd8":
        raise ValueError("pas un JPEG")
    sortie = bytearray(b"\xff\xd8")
    i = 2
    while i < len(donnees):
        if donnees[i] != 0xFF:
            raise ValueError(f"marqueur attendu à l'octet {i}")
        marqueur = donnees[i + 1]
        if marqueur == 0xFF:                 # octet de remplissage
            i += 1
            continue
        if marqueur == 0xDA:                 # début des données d'image : tout le reste est gardé tel quel
            sortie += donnees[i:]
            return bytes(sortie)
        if 0xD0 <= marqueur <= 0xD9 or marqueur == 0x01:   # marqueurs sans longueur
            sortie += donnees[i:i + 2]
            i += 2
            continue
        longueur = int.from_bytes(donnees[i + 2:i + 4], "big")
        bloc = donnees[i:i + 2 + longueur]
        est_app = 0xE0 <= marqueur <= 0xEF
        if marqueur == 0xFE:                 # commentaire
            pass
        elif est_app:
            signature = GARDES.get(marqueur)
            if signature and bloc[4:4 + len(signature)] == signature:
                sortie += bloc
        else:                                # tables, en-tête de trame… : indispensables
            sortie += bloc
        i += 2 + longueur
    return bytes(sortie)


def main():
    source, destination = sys.argv[1], sys.argv[2]
    os.makedirs(destination, exist_ok=True)
    for nom in sorted(os.listdir(source)):
        if os.path.splitext(nom)[1].lower() not in (".jpg", ".jpeg"):
            print("ignoré (pas un JPEG) :", nom)
            continue
        with open(os.path.join(source, nom), "rb") as f:
            avant = f.read()
        apres = nettoyer(avant)
        with open(os.path.join(destination, nom), "wb") as f:
            f.write(apres)
        print(f"{nom} : {len(avant) - len(apres)} octets de métadonnées retirés")


if __name__ == "__main__":
    main()
