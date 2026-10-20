"""Icônes dessinées au pinceau (aucun fichier image à embarquer, nettes à toute échelle)."""

from __future__ import annotations

import math
from functools import lru_cache

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

CLAIR = QColor(235, 235, 235)
OR = QColor(255, 200, 40)


def _fleche_arc(p: QPainter, sens: int):
    """Flèche circulaire de rotation ; sens = -1 gauche (↺), +1 droite (↻)."""
    cx, cy, r = 16.0, 17.0, 9.0
    debut, etendue = (60, -300) if sens > 0 else (120, 300)
    p.drawArc(QRectF(cx - r, cy - r, 2 * r, 2 * r), debut * 16, etendue * 16)
    fin = math.radians(debut + etendue)
    px, py = cx + r * math.cos(fin), cy - r * math.sin(fin)
    # tangente dans le sens du parcours (repère écran, y vers le bas)
    dx, dy = (math.sin(fin), math.cos(fin)) if sens > 0 else (-math.sin(fin), -math.cos(fin))
    nx, ny = -dy, dx
    pointe = QPointF(px + dx * 4.5, py + dy * 4.5)
    a = QPointF(px - dx * 2 + nx * 4.5, py - dy * 2 + ny * 4.5)
    b = QPointF(px - dx * 2 - nx * 4.5, py - dy * 2 - ny * 4.5)
    couleur = p.pen().color()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(couleur)
    p.drawPolygon(QPolygonF([pointe, a, b]))


def _etoile(p: QPainter, pleine: bool):
    pts = []
    for i in range(10):
        a = math.radians(-90 + i * 36)
        r = 11 if i % 2 == 0 else 4.6
        pts.append(QPointF(16 + r * math.cos(a), 17 + r * math.sin(a)))
    if pleine:
        p.setPen(QPen(OR, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.setBrush(OR)
    p.drawPolygon(QPolygonF(pts))


@lru_cache(maxsize=None)
def icone(nom: str, couleur: str = "#ebebeb") -> QIcon:
    pix = QPixmap(64, 64)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(2, 2)
    c = QColor(couleur)
    p.setPen(QPen(c, 2.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.setBrush(Qt.BrushStyle.NoBrush)

    if nom == "plus":
        p.drawLine(QPointF(9, 16), QPointF(23, 16)); p.drawLine(QPointF(16, 9), QPointF(16, 23))
    elif nom == "moins":
        p.drawLine(QPointF(9, 16), QPointF(23, 16))
    elif nom == "un_un":
        f = QFont("Segoe UI"); f.setPixelSize(19); f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(0, 0, 32, 32), Qt.AlignmentFlag.AlignCenter, "1:1")
    elif nom in ("precedent", "suivant"):
        s = -1 if nom == "precedent" else 1
        p.setBrush(c)
        p.drawPolygon(QPolygonF([QPointF(16 - 6 * s, 8), QPointF(16 + 7 * s, 16), QPointF(16 - 6 * s, 24)]))
    elif nom == "lecture":
        p.setBrush(c)
        p.drawPolygon(QPolygonF([QPointF(11, 7), QPointF(25, 16), QPointF(11, 25)]))
    elif nom == "pause":
        p.setBrush(c); p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(9, 8, 5, 16), 1.5, 1.5); p.drawRoundedRect(QRectF(18, 8, 5, 16), 1.5, 1.5)
    elif nom == "partager":
        # boîte ouverte + flèche sortante
        chemin = QPainterPath()
        chemin.moveTo(11, 13); chemin.lineTo(7, 13); chemin.lineTo(7, 26); chemin.lineTo(25, 26)
        chemin.lineTo(25, 13); chemin.lineTo(21, 13)
        p.drawPath(chemin)
        p.drawLine(QPointF(16, 5), QPointF(16, 19))
        p.drawLine(QPointF(11, 10), QPointF(16, 5)); p.drawLine(QPointF(21, 10), QPointF(16, 5))
    elif nom == "rot_gauche":
        _fleche_arc(p, -1)
    elif nom == "rot_droite":
        _fleche_arc(p, +1)
    elif nom == "etoile":
        _etoile(p, False)
    elif nom == "etoile_pleine":
        _etoile(p, True)
    elif nom == "menu":
        p.drawPolyline(QPolygonF([QPointF(9, 13), QPointF(16, 20), QPointF(23, 13)]))
    elif nom == "fermer":
        p.drawLine(QPointF(10, 10), QPointF(22, 22)); p.drawLine(QPointF(22, 10), QPointF(10, 22))
    elif nom == "reduire":
        p.drawLine(QPointF(10, 20), QPointF(22, 20))
    elif nom == "plein_ecran":
        for (x, y, dx, dy) in ((8, 8, 1, 1), (24, 8, -1, 1), (8, 24, 1, -1), (24, 24, -1, -1)):
            p.drawPolyline(QPolygonF([QPointF(x, y + 5 * dy), QPointF(x, y), QPointF(x + 5 * dx, y)]))
    elif nom == "fenetre":
        for (x, y, dx, dy) in ((13, 13, -1, -1), (19, 13, 1, -1), (13, 19, -1, 1), (19, 19, 1, 1)):
            p.drawPolyline(QPolygonF([QPointF(x, y + 5 * dy), QPointF(x, y), QPointF(x + 5 * dx, y)]))
    elif nom in ("epingle", "epingle_active"):
        coul = OR if nom == "epingle_active" else c
        p.save()
        p.translate(16, 16)
        p.rotate(45)
        p.setPen(QPen(coul, 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        if nom == "epingle_active":
            p.setBrush(coul)
        p.drawRoundedRect(QRectF(-4.5, -12, 9, 4), 1.2, 1.2)          # tête
        corps = QPainterPath()
        corps.moveTo(-3, -8); corps.lineTo(3, -8); corps.lineTo(5, 1); corps.lineTo(-5, 1); corps.closeSubpath()
        p.drawPath(corps)                                                # corps
        p.drawLine(QPointF(0, 1), QPointF(0, 12))                        # pointe
        p.restore()
    elif nom == "recadrer":
        # l'image au centre, et les quatre coins de la fenêtre qui viennent l'entourer
        p.drawRect(QRectF(11, 11, 10, 10))
        for (x, y, dx, dy) in ((5, 5, 1, 1), (27, 5, -1, 1), (5, 27, 1, -1), (27, 27, -1, -1)):
            p.drawPolyline(QPolygonF([QPointF(x, y + 5 * dy), QPointF(x, y), QPointF(x + 5 * dx, y)]))
    elif nom == "mosaique":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(c)
        for r in (QRectF(6, 7, 11, 8), QRectF(19, 7, 7, 8), QRectF(6, 17, 7, 8), QRectF(15, 17, 11, 8)):
            p.drawRoundedRect(r, 1.5, 1.5)
    elif nom == "dossier":
        chemin = QPainterPath()
        chemin.moveTo(6, 10); chemin.lineTo(13, 10); chemin.lineTo(15, 12); chemin.lineTo(26, 12)
        chemin.lineTo(26, 24); chemin.lineTo(6, 24); chemin.closeSubpath()
        p.drawPath(chemin)
    p.end()
    return QIcon(pix)


@lru_cache(maxsize=None)
def icone_appli() -> QIcon:
    """Icône de la fenêtre : un cadre photo stylisé « 36 »."""
    icon = QIcon()
    for taille in (16, 24, 32, 48, 64, 128, 256):
        pix = QPixmap(taille, taille)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.scale(taille / 64, taille / 64)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(30, 30, 34))
        p.drawRoundedRect(QRectF(2, 2, 60, 60), 12, 12)
        p.setBrush(QColor(255, 170, 40))
        p.drawRoundedRect(QRectF(9, 9, 46, 46), 6, 6)
        p.setBrush(QColor(30, 30, 34))
        p.drawRoundedRect(QRectF(14, 14, 36, 36), 3, 3)
        chemin = QPainterPath()
        chemin.moveTo(14, 50); chemin.lineTo(27, 32); chemin.lineTo(35, 42); chemin.lineTo(41, 35)
        chemin.lineTo(50, 50); chemin.closeSubpath()
        p.setBrush(QColor(90, 160, 230))
        p.drawPath(chemin)
        p.setBrush(QColor(255, 220, 120))
        p.drawEllipse(QPointF(40, 23), 4.5, 4.5)
        p.end()
        icon.addPixmap(pix)
    return icon
