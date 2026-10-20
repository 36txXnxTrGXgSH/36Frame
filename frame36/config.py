"""Configuration persistante (JSON dans le dossier de configuration de l'utilisateur).

Windows : %APPDATA%\\36Frame\\config.json
Linux   : ~/.config/36Frame/config.json
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path


def est_portable() -> bool:
    """Version portable (exe nommé « …Portable… ») : tout est rangé à côté de l'exe."""
    return getattr(sys, "frozen", False) and "portable" in Path(sys.executable).stem.lower()


def _dossier_portable() -> Path:
    return Path(sys.executable).resolve().parent / "36Frame-donnees"


def dossier_config() -> Path:
    if est_portable():
        return _dossier_portable()
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "36Frame"


def dossier_cache() -> Path:
    if est_portable():
        return _dossier_portable() / "miniatures"
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "36Frame" / "miniatures"


def _valider(defaut: "Configuration", donnees: dict) -> dict:
    """Ne garde que les réglages connus ET du bon type : un config.json abîmé, modifié à la main
    ou venant d'une autre version ne peut pas faire planter 36Frame (la valeur par défaut reste)."""
    propre = {}
    for f in fields(defaut):
        if f.name not in donnees:
            continue
        v, ref = donnees[f.name], getattr(defaut, f.name)
        if isinstance(ref, bool):
            ok = isinstance(v, bool)
        elif isinstance(ref, float):
            ok = isinstance(v, (int, float)) and not isinstance(v, bool)
            v = float(v) if ok else v
        elif isinstance(ref, int):
            ok = isinstance(v, int) and not isinstance(v, bool)
        elif isinstance(ref, str):
            ok = isinstance(v, str)
        elif isinstance(ref, list):
            ok = isinstance(v, list)
            if ok and f.name == "applications":
                v = [a for a in v if isinstance(a, dict) and isinstance(a.get("nom"), str)
                     and isinstance(a.get("chemin"), str)]
            elif ok and f.name == "geometrie":
                v = [int(x) for x in v if isinstance(x, int)] if len(v) == 4 else []
            elif ok:
                v = [x for x in v if isinstance(x, str)]
        elif isinstance(ref, dict):
            ok = isinstance(v, dict)
            if ok:
                v = {k: [x for x in l if isinstance(x, str)] for k, l in v.items()
                     if isinstance(k, str) and isinstance(l, list)}
        else:
            ok = False
        if ok:
            propre[f.name] = v
    return propre


@dataclass
class Configuration:
    # « adaptatif » : la fenêtre épouse l'image (Ctrl+molette = fenêtre + image) ;
    # « picasa » : fenêtre de taille fixe, fond gris autour de l'image (ancien comportement)
    mode_affichage: str = "adaptatif"
    fenetre_max_ecran: int = 90                # % de l'écran au maximum pour une grande image (adaptatif)

    # Fond en mode fenêtré (mode PICASA) : "couleur" ou "transparent"
    fenetre_fond: str = "couleur"
    fenetre_couleur: str = "#7f7f7f"          # gris Picasa
    fenetre_opacite: int = 100                 # % (utilisé si fond = couleur)
    transparence: str = "derriere"             # images détourées : derriere | fond | damier

    # Fond en mode plein écran : couleur assombrissant le bureau
    plein_ecran_couleur: str = "#000000"
    plein_ecran_opacite: int = 60              # % ; 0 = totalement transparent

    # Image
    lissage: bool = True                       # interpolation de qualité
    ombre_image: bool = True                   # ombre portée autour de l'image

    # Diaporama
    diaporama_delai: float = 4.0               # secondes
    diaporama_boucle: bool = True
    diaporama_plein_ecran: bool = True

    # Barre d'outils
    barre_delai_masquage: int = 600            # ms
    barre_fond: bool = False                   # bandeau sombre derrière la barre (sinon : boutons seuls)

    # Plusieurs fenêtres
    nouvelle_fenetre: bool = True              # une image ouverte depuis l'Explorateur = une nouvelle fenêtre
    mosaique_mode: str = "optimale"            # optimale | grille | colonnes | cascade | pele_mele
    mosaique_marge: int = 6                    # px entre les fenêtres (et entre les images de la Mosaïque Dossier)
    mosaique_dossier_rangees: float = 4.0      # rangées d'images visibles à l'écran (Ctrl+molette)
    mosaique_dossier_orientation: str = "verticale"   # verticale | horizontale (sens du défilement)
    panorama_duree: float = 15.0               # secondes pour faire défiler un écran (Panorama)
    mosaique_douceur: int = 5                  # 1 = vif … 10 = très doux (défilement à la molette)
    mosaique_animation: str = "toujours"       # GIF / WebP dans la Mosaïque Dossier : toujours | survol | jamais
    echap_ferme: bool = True                   # Échap en fenêtré ferme la liseuse
    confirmer_suppression: bool = True         # demander avant de mettre une image à la corbeille

    # Données
    favoris: list[str] = field(default_factory=list)                       # dossier « Favoris »
    dossiers_favoris: dict[str, list[str]] = field(default_factory=dict)   # dossiers créés par l'utilisateur
    applications: list[dict] = field(default_factory=list)   # [{"nom":..., "chemin":...}]
    geometrie: list[int] = field(default_factory=list)       # x, y, l, h
    dernier_dossier: str = ""
    derniers_dossiers: list[str] = field(default_factory=list)   # dernière sélection « Ouvrir des dossiers »

    # ------------------------------------------------------------------
    @classmethod
    def charger(cls) -> "Configuration":
        chemin = dossier_config() / "config.json"
        try:
            donnees = json.loads(chemin.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        if not isinstance(donnees, dict):
            return cls()
        if "mosaique_animer" in donnees and "mosaique_animation" not in donnees:   # ancien réglage (0.6)
            donnees["mosaique_animation"] = "toujours" if donnees["mosaique_animer"] else "jamais"
        return cls(**_valider(cls(), donnees))

    def enregistrer(self) -> None:
        dossier = dossier_config()
        try:
            dossier.mkdir(parents=True, exist_ok=True)
            tmp = dossier / "config.json.tmp"
            tmp.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")
            tmp.replace(dossier / "config.json")
        except OSError:
            pass

    # ------------------------------------------------------------------
    def est_favori(self, chemin: str) -> bool:
        return os.path.normcase(chemin) in {os.path.normcase(f) for f in self.favoris}

    def basculer_favori(self, chemin: str) -> bool:
        """Ajoute ou retire le favori ; renvoie le nouvel état."""
        cle = os.path.normcase(chemin)
        avant = len(self.favoris)
        self.favoris = [f for f in self.favoris if os.path.normcase(f) != cle]
        if len(self.favoris) == avant:
            self.favoris.append(chemin)
            etat = True
        else:
            etat = False
        self.enregistrer()
        return etat

    def oublier_fichier(self, chemin: str) -> None:
        """Fichier supprimé : on le retire de tous les dossiers de favoris."""
        cle = os.path.normcase(chemin)
        self.favoris = [f for f in self.favoris if os.path.normcase(f) != cle]
        for nom, liste in self.dossiers_favoris.items():
            self.dossiers_favoris[nom] = [f for f in liste if os.path.normcase(f) != cle]
        self.enregistrer()

    # ------------------------------------------------------------------ dossiers de favoris
    def liste_favoris(self, dossier: str | None) -> list[str]:
        """dossier None = le dossier « Favoris » par défaut."""
        return self.favoris if dossier is None else self.dossiers_favoris.setdefault(dossier, [])

    def dans_dossier(self, dossier: str | None, chemin: str) -> bool:
        cle = os.path.normcase(chemin)
        return any(os.path.normcase(f) == cle for f in self.liste_favoris(dossier))

    def ajouter_au_dossier(self, dossier: str | None, chemin: str) -> bool:
        """Renvoie False si l'image y était déjà."""
        if self.dans_dossier(dossier, chemin):
            return False
        self.liste_favoris(dossier).append(chemin)
        self.enregistrer()
        return True

    def retirer_du_dossier(self, dossier: str | None, chemin: str) -> None:
        cle = os.path.normcase(chemin)
        liste = [f for f in self.liste_favoris(dossier) if os.path.normcase(f) != cle]
        if dossier is None:
            self.favoris = liste
        else:
            self.dossiers_favoris[dossier] = liste
        self.enregistrer()
