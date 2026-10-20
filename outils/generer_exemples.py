"""Génère les images d'exemple de 36Frame (dossier exemples/), entièrement dessinées par programme.

    python outils/generer_exemples.py

Aucune photo ni œuvre de tiers : tout est calculé ici (dégradés, montagnes fractales, fractale de
Mandelbrot, formes géométriques), avec une graine fixe — le résultat est identique à chaque fois.
Ces images sont dédiées au domaine public (CC0) : utilisez-les librement.

Chaque image montre une fonction de 36Frame : navigation et Mosaïque Dossier (paysages), zoom à
100 % (grand panorama détaillé), images détourées (planète à fond transparent), animations GIF et
WebP, orientation portrait.
"""

from __future__ import annotations

import math
import os
import random
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

SORTIE = Path(__file__).resolve().parent.parent / "exemples"


# ---------------------------------------------------------------------------- outils de dessin
def melange(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def degrade_vertical(l, h, arrets):
    """arrets : [(position 0..1, (r, g, b)), …]"""
    im = Image.new("RGB", (l, h))
    d = ImageDraw.Draw(im)
    for y in range(h):
        t = y / max(1, h - 1)
        for (p0, c0), (p1, c1) in zip(arrets, arrets[1:]):
            if p0 <= t <= p1:
                d.line([(0, y), (l, y)], fill=melange(c0, c1, (t - p0) / max(1e-9, p1 - p0)))
                break
    return im


def ligne_de_crete(l, base, amplitude, rugosite, rng):
    """Montagnes par déplacement du point milieu : liste de hauteurs, une par colonne."""
    n = 1
    while n < l:
        n *= 2
    pts = [0.0] * (n + 1)
    pts[0], pts[n] = rng.uniform(-1, 1), rng.uniform(-1, 1)
    pas, echelle = n, 1.0
    while pas > 1:
        demi = pas // 2
        for i in range(demi, n, pas):
            pts[i] = (pts[i - demi] + pts[i + demi]) / 2 + rng.uniform(-1, 1) * echelle
        echelle *= rugosite
        pas = demi
    return [base - pts[round(x * n / l)] * amplitude for x in range(l)]


def montagnes(im, couches, rng, flou_lointain=True):
    l, h = im.size
    for k, (base, amplitude, couleur, rugosite) in enumerate(couches):
        crete = ligne_de_crete(l, base * h, amplitude * h, rugosite, rng)
        calque = Image.new("RGBA", (l, h), (0, 0, 0, 0))
        ImageDraw.Draw(calque).polygon([(0, h)] + [(x, y) for x, y in enumerate(crete)] + [(l, h)], fill=couleur)
        if flou_lointain and k == 0:
            calque = calque.filter(ImageFilter.GaussianBlur(1.2))
        im.paste(calque, (0, 0), calque)
    return im


def halo(im, centre, rayon, couleur, intensite=1.0):
    l, h = im.size
    masque = Image.new("L", (l, h), 0)
    d = ImageDraw.Draw(masque)
    for i in range(12, 0, -1):
        r = rayon * (1 + i * 0.35)
        d.ellipse([centre[0] - r, centre[1] - r, centre[0] + r, centre[1] + r], fill=round(255 * intensite * (1 - i / 13) ** 2.2))
    masque = masque.filter(ImageFilter.GaussianBlur(rayon * 0.6))
    im.paste(Image.new("RGB", (l, h), couleur), (0, 0), masque)
    ImageDraw.Draw(im).ellipse([centre[0] - rayon, centre[1] - rayon, centre[0] + rayon, centre[1] + rayon], fill=couleur)


def etoiles(im, nombre, rng, hauteur_max=0.6):
    l, h = im.size
    d = ImageDraw.Draw(im)
    for _ in range(nombre):
        x, y = rng.randrange(l), rng.randrange(int(h * hauteur_max))
        v = rng.randint(150, 255)
        r = rng.choice((0, 0, 0, 1, 1, 2))
        d.ellipse([x - r, y - r, x + r, y + r], fill=(v, v, min(255, v + 20)))


def sauver(im, nom, **options):
    chemin = SORTIE / nom
    im.save(chemin, **options)
    print(f"  {nom:32s} {im.size[0]}x{im.size[1]}  {chemin.stat().st_size / 1024:7.0f} Ko")


# ---------------------------------------------------------------------------- les images
def paysage(nom, l, h, ciel, soleil, couches, graine, nuit=False, mer=None):
    rng = random.Random(graine)
    im = degrade_vertical(l, h, ciel)
    if nuit:
        etoiles(im, l * h // 2500, rng)
    if soleil:
        (sx, sy, sr, sc) = soleil
        halo(im, (sx * l, sy * h), sr * h, sc, 0.9)
    montagnes(im, couches, rng)
    if mer:
        # mer : reflet du ciel, vaguelettes horizontales
        y0 = int(mer * h)
        reflet = ImageOps.flip(im.crop((0, 0, l, y0))).resize((l, h - y0)).filter(ImageFilter.GaussianBlur(3))
        reflet = Image.blend(reflet, Image.new("RGB", reflet.size, (10, 30, 60)), 0.45)
        d = ImageDraw.Draw(reflet)
        for _ in range(l * (h - y0) // 900):
            x, y = rng.randrange(l), rng.randrange(h - y0)
            d.line([(x, y), (x + rng.randint(10, 60), y)], fill=melange((255, 230, 190), (40, 60, 90), y / (h - y0)), width=1)
        im.paste(reflet, (0, y0))
    sauver(im, nom, quality=92, optimize=True, progressive=True)


def fractale(nom, l, h):
    gris = Image.effect_mandelbrot((l, h), (-2.2, -1.2, 1.0, 1.2), 255)
    gris = ImageOps.autocontrast(ImageOps.equalize(gris))
    couleur = ImageOps.colorize(gris, black=(8, 10, 40), mid=(220, 70, 120), white=(255, 230, 140), midpoint=110)
    sauver(couleur, nom, optimize=True)


def mosaique_hexagones(nom, l, h, graine):
    rng = random.Random(graine)
    im = Image.new("RGB", (l, h), (20, 22, 30))
    d = ImageDraw.Draw(im)
    r = 46
    dx, dy = r * math.sqrt(3), r * 1.5
    palette = [(255, 170, 40), (61, 109, 181), (90, 160, 230), (240, 90, 110), (110, 200, 150), (250, 220, 120)]
    for j in range(int(h / dy) + 2):
        for i in range(int(l / dx) + 2):
            cx, cy = i * dx + (dx / 2 if j % 2 else 0), j * dy
            dist = math.hypot(cx - l / 2, cy - h / 2) / math.hypot(l / 2, h / 2)
            base = palette[(i * 3 + j * 5 + rng.randrange(2)) % len(palette)]
            c = melange(base, (20, 22, 30), min(0.85, dist * 0.9 + rng.uniform(0, 0.2)))
            pts = [(cx + (r - 3) * math.cos(math.radians(60 * k + 30)), cy + (r - 3) * math.sin(math.radians(60 * k + 30)))
                   for k in range(6)]
            d.polygon(pts, fill=c)
    sauver(im, nom, optimize=True)


def vagues(nom, l, h):
    im = degrade_vertical(l, h, [(0, (12, 18, 48)), (1, (40, 12, 70))])
    calque = Image.new("RGBA", (l, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(calque)
    for k in range(14):
        t = k / 13
        couleur = melange((90, 160, 230), (255, 120, 170), t) + (150,)
        amp, freq, phase, y0 = 40 + 50 * t, 2 + 3 * t, k * 0.7, h * (0.2 + 0.6 * t)
        pts = [(x, y0 + amp * math.sin(freq * 2 * math.pi * x / l + phase) + 0.4 * amp * math.sin(3.1 * 2 * math.pi * x / l))
               for x in range(0, l + 8, 8)]
        d.line(pts, fill=couleur, width=4)
    calque = calque.filter(ImageFilter.GaussianBlur(1.5))
    im.paste(calque, (0, 0), calque)
    sauver(im, nom, quality=90, method=6)


def planete_detouree(nom, cote):
    """Planète à anneaux sur fond TRANSPARENT (mode « voir derrière la fenêtre »)."""
    ech = 2
    t = cote * ech
    im = Image.new("RGBA", (t, t), (0, 0, 0, 0))
    centre, r = t / 2, t * 0.2
    # globe : dégradé radial et bandes
    globe = Image.new("RGBA", (t, t), (0, 0, 0, 0))
    g = ImageDraw.Draw(globe)
    for i in range(120, 0, -1):
        f = i / 120
        c = melange((255, 214, 150), (150, 70, 40), f ** 0.8)
        rr = r * f
        g.ellipse([centre - rr - r * 0.25 * (1 - f), centre - rr - r * 0.25 * (1 - f), centre + rr - r * 0.25 * (1 - f),
                   centre + rr - r * 0.25 * (1 - f)], fill=c + (255,))
    masque = Image.new("L", (t, t), 0)
    ImageDraw.Draw(masque).ellipse([centre - r, centre - r, centre + r, centre + r], fill=255)
    bandes = Image.new("RGBA", (t, t), (0, 0, 0, 0))
    b = ImageDraw.Draw(bandes)
    for k in range(9):
        y = centre - r + (k + 0.5) * 2 * r / 9
        b.rectangle([0, y - r * 0.05, t, y + r * 0.05], fill=(120, 50, 30, 70))
    globe = Image.alpha_composite(globe, bandes)
    globe.putalpha(ImageChops.multiply(globe.getchannel("A"), masque))
    # anneau : ellipse aplatie, partie arrière puis avant
    anneau = Image.new("RGBA", (t, t), (0, 0, 0, 0))
    a = ImageDraw.Draw(anneau)
    for k in range(26):
        e = r * (1.28 + k * 0.022)
        if k in (9, 10, 18):            # divisions sombres entre les anneaux
            continue
        a.ellipse([centre - e * 1.33, centre - e * 0.36, centre + e * 1.33, centre + e * 0.36],
                  outline=melange((255, 238, 205), (190, 140, 100), k / 25) + (235,), width=max(3, t // 380))
    arriere = anneau.crop((0, 0, t, round(centre)))
    im.paste(arriere, (0, 0), arriere)
    im = Image.alpha_composite(im, globe)
    avant = anneau.crop((0, round(centre), t, t))
    im.paste(avant, (0, round(centre)), avant)
    # ombre douce au sol (reste semi-transparente)
    ombre = Image.new("RGBA", (t, t), (0, 0, 0, 0))
    ImageDraw.Draw(ombre).ellipse([centre - r * 1.2, t * 0.86, centre + r * 1.2, t * 0.92], fill=(0, 0, 0, 90))
    ombre = ombre.filter(ImageFilter.GaussianBlur(t * 0.015))
    im = Image.alpha_composite(ombre, im)
    im = im.resize((cote, cote), Image.LANCZOS)
    sauver(im, nom, optimize=True)


def animation(nom, cote, images=36, format_="WEBP"):
    """Petites planètes en orbite autour d'un soleil (animation en boucle)."""
    trames = []
    for n in range(images):
        im = degrade_vertical(cote, cote, [(0, (10, 12, 35)), (1, (30, 16, 60))])
        rng = random.Random(7)
        etoiles(im, cote * cote // 900, rng, 1.0)
        halo(im, (cote / 2, cote / 2), cote * 0.08, (255, 190, 80), 0.8)
        d = ImageDraw.Draw(im)
        for k, (rayon, taille, couleur, vitesse) in enumerate(((0.2, 0.03, (90, 160, 230), 2), (0.31, 0.045, (240, 90, 110), 1),
                                                               (0.42, 0.035, (110, 200, 150), -1))):
            d.ellipse([cote / 2 - rayon * cote, cote / 2 - rayon * cote * 0.55, cote / 2 + rayon * cote,
                       cote / 2 + rayon * cote * 0.55], outline=(80, 80, 120), width=1)
            ang = 2 * math.pi * (n / images) * vitesse + k
            x = cote / 2 + rayon * cote * math.cos(ang)
            y = cote / 2 + rayon * cote * 0.55 * math.sin(ang)
            s = taille * cote
            d.ellipse([x - s, y - s, x + s, y + s], fill=couleur)
        trames.append(im)
    if format_ == "GIF":
        trames = [t.convert("P", palette=Image.ADAPTIVE, colors=96) for t in trames]
        trames[0].save(SORTIE / nom, save_all=True, append_images=trames[1:], duration=60, loop=0, optimize=True)
    else:
        trames[0].save(SORTIE / nom, save_all=True, append_images=trames[1:], duration=50, loop=0, quality=80, method=4)
    print(f"  {nom:32s} {cote}x{cote}  {(SORTIE / nom).stat().st_size / 1024:7.0f} Ko  ({images} images)")


def panorama_ville(nom, l, h, graine):
    """Très grand panorama nocturne rempli de petits détails : pour essayer le zoom à 100 % et au-delà."""
    rng = random.Random(graine)
    im = degrade_vertical(l, h, [(0, (6, 8, 30)), (0.55, (40, 30, 90)), (0.75, (190, 90, 110)), (1, (240, 160, 110))])
    etoiles(im, l * h // 1800, rng, 0.5)
    halo(im, (l * 0.8, h * 0.18), h * 0.05, (245, 240, 220), 0.6)
    d = ImageDraw.Draw(im)
    for plan, (haut_max, couleur_mur, eclairage, largeur) in enumerate(((0.45, (35, 30, 70), 0.25, (60, 160)),
                                                                     (0.62, (22, 20, 45), 0.4, (80, 220)),
                                                                     (0.8, (12, 12, 24), 0.55, (100, 300)))):
        x = -rng.randint(0, 80)
        while x < l:
            lb = rng.randint(*largeur)
            hb = rng.uniform(0.15, haut_max) * h
            y0 = h - hb
            d.rectangle([x, y0, x + lb, h], fill=couleur_mur)
            if rng.random() < 0.3:      # antenne
                d.line([(x + lb / 2, y0), (x + lb / 2, y0 - rng.randint(20, 90))], fill=couleur_mur, width=3)
                d.ellipse([x + lb / 2 - 3, y0 - 95, x + lb / 2 + 3, y0 - 89], fill=(255, 60, 60))
            # fenêtres : beaucoup de petits rectangles allumés ou éteints
            for wy in range(int(y0) + 10, h - 10, 14):
                for wx in range(x + 6, x + lb - 8, 11):
                    if rng.random() < eclairage:
                        d.rectangle([wx, wy, wx + 5, wy + 7], fill=rng.choice(((255, 210, 120), (255, 240, 200), (150, 200, 255))))
            x += lb + rng.randint(2, 18)
    sauver(im, nom, quality=90, optimize=True, progressive=True)


def main():
    SORTIE.mkdir(exist_ok=True)
    print("Images d'exemple :", SORTIE)
    paysage("paysage-aube.jpg", 2400, 1350, [(0, (40, 60, 120)), (0.5, (250, 170, 120)), (1, (255, 220, 170))],
            (0.68, 0.55, 0.05, (255, 240, 200)),
            [(0.62, 0.10, (150, 120, 150), 0.55), (0.72, 0.12, (90, 70, 110), 0.58), (0.86, 0.10, (40, 30, 60), 0.6)], 1)
    paysage("paysage-crepuscule.jpg", 2400, 1350, [(0, (20, 20, 60)), (0.55, (210, 80, 90)), (1, (255, 170, 80))],
            (0.3, 0.6, 0.06, (255, 200, 120)),
            [(0.6, 0.12, (120, 50, 80), 0.55), (0.7, 0.14, (70, 30, 60), 0.57), (0.84, 0.12, (25, 12, 30), 0.6)], 2)
    paysage("paysage-nuit-portrait.jpg", 1200, 1800, [(0, (4, 6, 22)), (0.7, (20, 30, 70)), (1, (40, 60, 110))],
            (0.72, 0.18, 0.04, (235, 235, 245)),
            [(0.66, 0.10, (40, 50, 90), 0.55), (0.76, 0.10, (25, 30, 60), 0.57), (0.88, 0.08, (10, 12, 25), 0.6)], 3, nuit=True)
    paysage("paysage-desert.jpg", 2400, 1200, [(0, (90, 150, 220)), (0.6, (230, 200, 160)), (1, (250, 220, 170))],
            (0.5, 0.3, 0.05, (255, 250, 230)),
            [(0.7, 0.05, (220, 160, 110), 0.45), (0.8, 0.06, (200, 130, 80), 0.45), (0.9, 0.05, (170, 100, 60), 0.45)], 4)
    paysage("paysage-ocean.jpg", 2400, 1350, [(0, (30, 60, 120)), (0.6, (240, 150, 110)), (1, (250, 200, 150))],
            (0.55, 0.58, 0.05, (255, 230, 180)),
            [(0.6, 0.08, (110, 80, 120), 0.55)], 5, mer=0.62)
    fractale("fractale.png", 2000, 1400)
    mosaique_hexagones("mosaique-hexagones.png", 1800, 1800, 6)
    vagues("vagues.webp", 2000, 1125)
    planete_detouree("planete-detouree.png", 1400)
    animation("orbites-animees.webp", 600, 48, "WEBP")
    animation("orbites-animees.gif", 420, 36, "GIF")
    panorama_ville("panorama-ville-tres-grand.jpg", 8000, 2600, 8)
    total = sum(p.stat().st_size for p in SORTIE.iterdir() if p.is_file())
    print(f"Total : {total / 2**20:.1f} Mo")


if __name__ == "__main__":
    main()
