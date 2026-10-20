"""Plusieurs fenêtres dans un seul programme, et la mosaïque.

Un seul processus 36Frame tourne : quand on ouvre une autre image depuis l'Explorateur,
le nouveau lancement transmet le chemin au premier (QLocalServer) puis se termine.
Toutes les fenêtres se connaissent donc, ce qui permet de les disposer en mosaïque, et
elles partagent le même cache d'images.
"""

from __future__ import annotations

import json
import math
import os
import random

from PySide6.QtCore import QObject, QPoint, QRect, QSize, QTimer
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from .chargement import ChargeurImages, ChargeurMiniatures
from .config import Configuration

from .instance import TAILLE_MAX_MESSAGE, adresse_serveur, lire_message

MODES_MOSAIQUE = {
    "optimale": "Optimale (plus grande surface d'image)",
    "lignes": "En lignes",
    "colonnes": "En colonnes",
    "grille": "Grille régulière",
    "cascade": "Cascade",
    "pele_mele": "Pêle-mêle (original)",
}


def envoyer_a_instance(chemins: list[str]) -> bool:
    """Si 36Frame tourne déjà, lui confie les fichiers. Renvoie True si c'est fait."""
    s = QLocalSocket()
    s.connectToServer(adresse_serveur())
    if not s.waitForConnected(400):
        return False
    s.write(json.dumps([os.path.abspath(c) for c in chemins]).encode("utf-8") + b"\n")
    s.flush()
    s.waitForBytesWritten(1000)
    s.disconnectFromServer()
    return True


class Gestionnaire(QObject):
    def __init__(self, config: Configuration, parent=None):
        super().__init__(parent)
        self.config = config
        self.fenetres: list = []
        self.images = ChargeurImages(self)        # budget adapté à la RAM du PC
        self.miniatures = ChargeurMiniatures(self)
        self.serveur = QLocalServer(self)
        # seul le compte qui a lancé 36Frame peut lui envoyer des images
        self.serveur.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.serveur.newConnection.connect(self._connexion)

    def ecouter(self):
        QLocalServer.removeServer(adresse_serveur())      # reste d'un plantage éventuel
        self.serveur.listen(adresse_serveur())

    def _connexion(self):
        while self.serveur.hasPendingConnections():
            s = self.serveur.nextPendingConnection()
            tampon = bytearray()
            fait = [False]

            def lire(s=s, tampon=tampon, fait=fait):
                tampon.extend(bytes(s.readAll()))
                if len(tampon) > TAILLE_MAX_MESSAGE:          # message anormal : on coupe
                    fait[0] = True
                    tampon.clear()
                    s.abort()
                    return
                if tampon.endswith(b"\n") and not fait[0]:
                    fait[0] = True
                    chemins = lire_message(bytes(tampon))
                    # on libère tout de suite le lancement secondaire (il attend notre réponse
                    # pour se terminer), puis on ouvre l'image
                    s.disconnectFromServer()
                    QTimer.singleShot(0, lambda c=chemins: self.ouvrir_chemins(c))

            s.readyRead.connect(lire)
            s.disconnected.connect(s.deleteLater)

    # ------------------------------------------------------------------ fenêtres
    def nouvelle_fenetre(self, chemin: str | None = None, depuis=None):
        from .fenetre import Liseuse

        f = Liseuse(self.config, self)
        self.fenetres.append(f)
        f.destroyed.connect(lambda *_ , f=f: self._fermee(f))
        f.taille_initiale(chemin if chemin and os.path.isfile(chemin) else None)
        if depuis is not None:     # décalée par rapport à la fenêtre d'origine
            g = f.geometry()
            g.moveTopLeft(depuis.geometry().topLeft() + QPoint(40, 40))
            f.setGeometry(g)
        f.show()
        if chemin:
            f.ouvrir(chemin)
        self._maj_multi()
        return f

    def ouvrir_chemins(self, chemins: list[str]):
        chemins = [c for c in chemins if os.path.exists(c)]
        if not chemins:
            if self.fenetres:
                self._activer(self.fenetres[-1])
            else:
                self.nouvelle_fenetre()
            return
        for c in chemins:
            if self.config.nouvelle_fenetre or not self.fenetres:
                f = self.nouvelle_fenetre(c)
            else:
                f = self.fenetre_active() or self.fenetres[-1]
                f.ouvrir(c)
            self._activer(f)

    def _activer(self, f):
        if f.isMinimized():
            f.showNormal()
        f.raise_()
        f.activateWindow()

    def fenetre_active(self):
        for f in self.fenetres:
            if f.isActiveWindow():
                return f
        return None

    def _fermee(self, f):
        if f in self.fenetres:
            self.fenetres.remove(f)
        self._maj_multi()

    def retirer(self, f):
        """Appelé à la fermeture (avant destruction) pour mettre à jour les autres tout de suite."""
        if f in self.fenetres:
            self.fenetres.remove(f)
        QTimer.singleShot(0, self._maj_multi)

    def fichier_supprime(self, chemin: str):
        self.images.oublier(chemin)
        self.config.oublier_fichier(chemin)
        for f in list(self.fenetres):
            f.retirer_chemin(chemin)

    def _maj_multi(self):
        for f in self.fenetres:
            f.maj_multi(len(self.fenetres) > 1)

    # ------------------------------------------------------------------ mosaïque
    def mosaique(self, mode: str | None = None, depuis=None):
        fenetres = [f for f in self.fenetres if f.isVisible() or f.isMinimized()]
        if not fenetres:
            return
        mode = mode or self.config.mosaique_mode
        ref = depuis or self.fenetre_active() or fenetres[0]
        ecran = ref.screen() or QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        zone = ecran.availableGeometry()
        m = max(0, self.config.mosaique_marge)
        zone = zone.adjusted(m, m, -m, -m)
        tailles = [f.taille_native() for f in fenetres]
        calcul = {"optimale": _optimale, "lignes": _lignes, "colonnes": _colonnes, "grille": _grille,
                  "cascade": _cascade, "pele_mele": _pele_mele}.get(mode, _lignes)
        rects = calcul(tailles, zone, m)
        for f, r in zip(fenetres, rects):
            f.placer(r)
        for f in fenetres:
            f.raise_()
        ref.activateWindow()


# ---------------------------------------------------------------------- dispositions
# Chaque fenêtre est décrite par la taille de son image à 100 % (pixels logiques) :
# on ne l'agrandit jamais au-delà, une petite image resterait sinon entourée de gris.
Taille = tuple[float, float]


def _rangees(tailles: list[Taille], ordre: list[int], h_cible: float, W: float, m: int):
    """Range les fenêtres en lignes, toutes à la hauteur h_cible (ou moins si l'image est petite)."""
    lignes, ligne, x = [], [], 0.0
    for i in ordre:
        w, h = tailles[i]
        hh = min(h, h_cible)
        ww = hh * w / h
        if ww > W:
            ww, hh = W, W * h / w
        if ligne and x + m + ww > W:
            lignes.append(ligne)
            ligne, x = [], 0.0
        x += (m if ligne else 0) + ww
        ligne.append((i, ww, hh))
    lignes.append(ligne)
    hauteur = sum(max(e[2] for e in l) for l in lignes) + m * (len(lignes) - 1)
    return lignes, hauteur


def _lignes(tailles: list[Taille], zone: QRect, m: int) -> list[QRect]:
    """Disposition optimale : la plus grande hauteur commune qui fait tout tenir à l'écran."""
    W, H = zone.width(), zone.height()
    n = len(tailles)
    meilleur, surface_max = None, -1.0
    for ordre in (list(range(n)), sorted(range(n), key=lambda i: -tailles[i][0] / tailles[i][1])):
        bas, haut = 1.0, max(h for _, h in tailles)
        for _ in range(40):                      # recherche dichotomique de la hauteur
            milieu = (bas + haut) / 2
            if _rangees(tailles, ordre, milieu, W, m)[1] <= H:
                bas = milieu
            else:
                haut = milieu
        lignes, hauteur = _rangees(tailles, ordre, bas, W, m)
        surface = sum(ww * hh for l in lignes for _, ww, hh in l)
        if surface > surface_max:
            surface_max, meilleur = surface, (lignes, hauteur)
    lignes, hauteur = meilleur
    rects = [QRect()] * n
    y = zone.top() + (H - hauteur) / 2
    for l in lignes:
        hl = max(e[2] for e in l)
        largeur = sum(e[1] for e in l) + m * (len(l) - 1)
        x = zone.left() + (W - largeur) / 2
        for i, ww, hh in l:
            rects[i] = QRect(round(x), round(y + (hl - hh) / 2), round(ww), round(hh))
            x += ww + m
        y += hl + m
    return rects


def _colonnes(tailles: list[Taille], zone: QRect, m: int) -> list[QRect]:
    transpose = QRect(zone.top(), zone.left(), zone.height(), zone.width())
    rects = _lignes([(h, w) for w, h in tailles], transpose, m)
    return [QRect(r.top(), r.left(), r.height(), r.width()) for r in rects]


def _optimale(tailles: list[Taille], zone: QRect, m: int) -> list[QRect]:
    """Le meilleur des rangements en lignes et en colonnes (plus grande surface d'image affichée)."""
    candidats = [_lignes(tailles, zone, m), _colonnes(tailles, zone, m)]
    return max(candidats, key=lambda rs: sum(r.width() * r.height() for r in rs))


def _ajuster_dans(taille: Taille, cellule: QRect) -> QRect:
    w, h = taille
    e = min(1.0, cellule.width() / w, cellule.height() / h)
    r = QRect(0, 0, round(w * e), round(h * e))
    r.moveCenter(cellule.center())
    return r


def _grille(tailles: list[Taille], zone: QRect, m: int) -> list[QRect]:
    n = len(tailles)
    meilleur, surface_max = None, -1.0
    for cols in range(1, n + 1):
        lignes = math.ceil(n / cols)
        cl = (zone.width() - m * (cols - 1)) / cols
        ch = (zone.height() - m * (lignes - 1)) / lignes
        rects = []
        for i, t in enumerate(tailles):
            c, l = i % cols, i // cols
            cellule = QRect(round(zone.left() + c * (cl + m)), round(zone.top() + l * (ch + m)), round(cl), round(ch))
            rects.append(_ajuster_dans(t, cellule))
        surface = sum(r.width() * r.height() for r in rects)
        if surface > surface_max:
            surface_max, meilleur = surface, rects
    return meilleur


def _cascade(tailles: list[Taille], zone: QRect, m: int) -> list[QRect]:
    n = len(tailles)
    pas = 36
    dispo = QRect(zone.left(), zone.top(), int(zone.width() * 0.65), int(zone.height() * 0.65))
    if n > 1:
        pas = max(8, min(48, (zone.width() - dispo.width()) // (n - 1), (zone.height() - dispo.height()) // (n - 1)))
    rects = []
    for i, t in enumerate(tailles):
        cellule = QRect(dispo.left() + i * pas, dispo.top() + i * pas, dispo.width(), dispo.height())
        a = _ajuster_dans(t, cellule)
        a.moveTopLeft(cellule.topLeft())
        rects.append(a)
    return rects


def _pele_mele(tailles: list[Taille], zone: QRect, m: int) -> list[QRect]:
    """Comme des photos posées sur une table : tailles variées, chevauchements légers."""
    rng = random.Random()
    rects = []
    for r in _lignes(tailles, zone, m):
        f = rng.uniform(0.85, 1.0)
        l, h = max(80, round(r.width() * f)), max(60, round(r.height() * f))
        cx = r.center().x() + rng.uniform(-0.2, 0.2) * r.width()
        cy = r.center().y() + rng.uniform(-0.2, 0.2) * r.height()
        x = min(max(zone.left(), round(cx - l / 2)), zone.right() - l)
        y = min(max(zone.top(), round(cy - h / 2)), zone.bottom() - h)
        rects.append(QRect(x, y, l, h))
    return rects