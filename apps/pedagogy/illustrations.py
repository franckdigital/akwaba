"""Illustrations schématiques originales (générées, pas copiées du livre) pour quelques leçons clés du
cours « La conduite ». Simples vues de dessus en formes géométriques : aucune photographie n'est reprise
d'une source tierce, évitant tout problème de droit d'auteur sur les images du livre.
"""
import io

from PIL import Image, ImageDraw

ROAD = (90, 90, 95)
LINE = (255, 255, 255)
GRASS = (210, 230, 200)
CAR_RED, CAR_BLUE, CAR_ORANGE = (224, 32, 39), (31, 85, 183), (232, 112, 42)
W, H = 900, 560


def _base():
    img = Image.new("RGB", (W, H), GRASS)
    return img, ImageDraw.Draw(img)


def _car(d, x, y, w, h, color, angle=0):
    """Petit rectangle arrondi représentant une voiture vue de dessus, avec un pare-brise plus clair."""
    if angle == 90:
        w, h = h, w
    d.rounded_rectangle([x, y, x + w, y + h], radius=8, fill=color, outline=(30, 30, 30), width=2)
    if angle == 0:
        d.rectangle([x + w * 0.15, y + h * 0.15, x + w * 0.85, y + h * 0.4], fill=(210, 230, 245))
    else:
        d.rectangle([x + w * 0.6, y + h * 0.15, x + w * 0.85, y + h * 0.85], fill=(210, 230, 245))


def priority_right():
    """Priorité à droite : deux routes qui se croisent, flèche indiquant qui passe."""
    img, d = _base()
    d.rectangle([0, H // 2 - 70, W, H // 2 + 70], fill=ROAD)
    d.rectangle([W // 2 - 70, 0, W // 2 + 70, H], fill=ROAD)
    for x in range(20, W, 60):
        if x < W // 2 - 90 or x > W // 2 + 90:
            d.rectangle([x, H // 2 - 4, x + 30, H // 2 + 4], fill=LINE)
    for y in range(20, H, 60):
        if y < H // 2 - 90 or y > H // 2 + 90:
            d.rectangle([W // 2 - 4, y, W // 2 + 4, y + 30], fill=LINE)
    _car(d, W // 2 + 110, H // 2 - 130, 70, 110, CAR_BLUE)  # arrive du haut
    _car(d, W // 2 - 220, H // 2 - 35, 110, 70, CAR_RED)    # vient de la droite du bleu -> prioritaire
    d.polygon([(W // 2 - 110, H // 2 - 10), (W // 2 - 60, H // 2 - 10), (W // 2 - 85, H // 2 + 40)], fill=CAR_ORANGE)
    return img


def roundabout():
    """Rond-point : anneau de circulation avec terre-plein central."""
    img, d = _base()
    cx, cy, r_out, r_in = W // 2, H // 2, 200, 90
    d.ellipse([cx - r_out, cy - r_out, cx + r_out, cy + r_out], fill=ROAD)
    d.ellipse([cx - r_in, cy - r_in, cx + r_in, cy + r_in], fill=GRASS, outline=(60, 100, 60), width=4)
    for w, is_h in [(90, True), (90, False)]:
        if is_h:
            d.rectangle([0, cy - 45, cx - r_out, cy + 45], fill=ROAD)
            d.rectangle([cx + r_out, cy - 45, W, cy + 45], fill=ROAD)
        else:
            d.rectangle([cx - 45, 0, cx + 45, cy - r_out], fill=ROAD)
            d.rectangle([cx - 45, cy + r_out, cx + 45, H], fill=ROAD)
    _car(d, cx - 230, cy - 25, 70, 50, CAR_BLUE)
    _car(d, cx + 60, cy - r_out + 30, 70, 50, CAR_RED)
    return img


def slope_crossing():
    """Croisement en pente : un véhicule qui monte, un qui descend, celui qui descend s'arrête."""
    img, d = _base()
    d.polygon([(0, H), (W, H), (W, H - 260), (0, H - 60)], fill=ROAD)
    d.line([(0, H - 155), (W, H - 160)], fill=LINE, width=4)
    _car(d, 120, H - 230, 110, 60, CAR_RED)
    _car(d, W - 260, H - 110, 110, 60, CAR_BLUE)
    return img


def overtaking():
    """Dépassement : véhicule qui déboîte à gauche pour doubler, puis revient à droite."""
    img, d = _base()
    d.rectangle([0, 120, W, H - 120], fill=ROAD)
    d.line([(0, H // 2), (W, H // 2)], fill=LINE, width=4)
    for x in range(20, W, 70):
        d.rectangle([x, 160, x + 35, 168], fill=LINE)
    _car(d, 60, H // 2 + 10, 120, 70, CAR_BLUE)
    _car(d, W // 2 - 30, 160, 120, 70, CAR_RED)
    d.polygon([(W // 2 + 120, H // 2 + 10), (W // 2 + 120, 195), (W // 2 + 200, 195), (W // 2 + 160, 150)], fill=(40, 40, 40))
    return img


def traffic_lights():
    """Feu tricolore avec les trois couleurs, posé au bord d'une intersection."""
    img, d = _base()
    d.rectangle([0, H // 2 - 70, W, H // 2 + 70], fill=ROAD)
    for x in range(20, W, 60):
        d.rectangle([x, H // 2 - 4, x + 30, H // 2 + 4], fill=LINE)
    bx, by = W - 220, 60
    d.rectangle([bx, by, bx + 90, by + 230], fill=(35, 35, 35), outline=(10, 10, 10), width=3)
    for i, col in enumerate([(220, 40, 40), (235, 185, 30), (40, 180, 70)]):
        d.ellipse([bx + 15, by + 15 + i * 70, bx + 75, by + 75 + i * 70], fill=col)
    _car(d, 120, H // 2 - 120, 90, 60, CAR_BLUE, angle=90)
    return img


def parking_modes():
    """Trois façons de se garer : en épi, en bataille, en créneau."""
    img, d = _base()
    d.rectangle([0, 0, W, H], fill=(235, 235, 235))
    d.rectangle([0, H - 40, W, H], fill=ROAD)
    labels_y = H - 190
    # épi
    for i in range(3):
        x = 40 + i * 90
        d.polygon([(x, labels_y + 150), (x + 60, labels_y + 110), (x + 60, labels_y + 10), (x, labels_y + 50)], fill=CAR_BLUE, outline=(20, 20, 20))
    # bataille
    for i in range(3):
        x = 360 + i * 80
        d.rectangle([x, labels_y + 10, x + 55, labels_y + 150], fill=CAR_RED, outline=(20, 20, 20))
    # créneau
    d.rectangle([640, labels_y + 90, 860, labels_y + 150], fill=CAR_ORANGE, outline=(20, 20, 20))
    return img


def lane_discipline():
    """Autoroute à trois voies : circulation normale à droite, dépassement à gauche."""
    img, d = _base()
    d.rectangle([0, 0, W, H], fill=ROAD)
    d.rectangle([0, 0, W, H], fill=(70, 70, 75))
    for i in range(1, 3):
        y = i * H // 3
        for x in range(10, W, 70):
            d.rectangle([x, y - 3, x + 35, y + 3], fill=LINE)
    _car(d, 80, H - H // 6 - 35, 120, 60, CAR_BLUE)
    _car(d, 400, H // 6 - 30, 120, 60, CAR_RED)
    return img


def night_lights():
    """Conduite de nuit : feux de croisement (courts) contre feux de route (longs) sur la chaussée."""
    img = Image.new("RGB", (W, H), (20, 24, 40))
    d = ImageDraw.Draw(img)
    d.rectangle([0, H // 2 - 70, W, H // 2 + 70], fill=(45, 45, 50))
    for x in range(20, W, 60):
        d.rectangle([x, H // 2 - 4, x + 30, H // 2 + 4], fill=LINE)
    _car(d, 80, H // 2 - 35, 120, 70, CAR_BLUE)
    d.polygon([(200, H // 2 - 20), (420, H // 2 - 60), (420, H // 2 + 20), (200, H // 2 + 10)], fill=(255, 245, 190))
    _car(d, W - 220, H // 2 - 35, 120, 70, CAR_RED)
    d.polygon([(W - 220, H // 2 - 20), (W - 480, H // 2 - 110), (W - 480, H // 2 + 90), (W - 220, H // 2 + 10)], fill=(255, 250, 220))
    return img


BY_LESSON_TITLE = {
    "La priorité à droite": priority_right,
    "Carrefour à sens giratoire": roundabout,
    "Sur une chaussée en pente": slope_crossing,
    "Dépassements": overtaking,
    "Les feux tricolores": traffic_lights,
    "Les manœuvres": parking_modes,
    "Marche normale": lane_discipline,
    "Généralités": night_lights,
}


def illustration_for(title):
    """Retourne les octets PNG de l'illustration associée à une leçon, ou None si aucune n'est prévue."""
    fn = BY_LESSON_TITLE.get(title)
    if not fn:
        return None
    img = fn()
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
