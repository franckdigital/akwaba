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


def _road_scene(sky=GRASS):
    img = Image.new("RGB", (W, H), sky)
    d = ImageDraw.Draw(img)
    d.rectangle([0, H // 2 - 70, W, H // 2 + 70], fill=ROAD)
    for x in range(20, W, 60):
        d.rectangle([x, H // 2 - 4, x + 30, H // 2 + 4], fill=LINE)
    return img, d


def _sign_panel(d, x, y, shape, fill, border=(200, 30, 30), text="", text_color=(20, 20, 20)):
    """Dessine un panneau routier simplifié (rond, triangle ou losange) sur un poteau."""
    d.rectangle([x + 38, y + 80, x + 46, y + 230], fill=(90, 90, 90))
    if shape == "circle":
        d.ellipse([x, y, x + 84, y + 84], fill=fill, outline=border, width=8)
    elif shape == "triangle":
        d.polygon([(x + 42, y), (x + 84, y + 80), (x, y + 80)], fill=fill, outline=border)
        d.polygon([(x + 42, y + 10), (x + 76, y + 72), (x + 8, y + 72)], fill=(255, 255, 255))
    elif shape == "diamond":
        d.polygon([(x + 42, y), (x + 84, y + 42), (x + 42, y + 84), (x, y + 42)], fill=fill, outline=border)
    if text:
        d.text((x + 42, y + 42), text, fill=text_color, anchor="mm")


def speed_sign():
    img, d = _road_scene()
    _sign_panel(d, 620, 40, "circle", (255, 255, 255), border=(210, 30, 30), text="60", text_color=(20, 20, 20))
    _car(d, 100, H // 2 - 35, 120, 70, CAR_BLUE)
    return img


def speed_sign_end():
    img, d = _road_scene()
    d2 = d
    x, y = 620, 40
    d2.rectangle([x + 38, y + 80, x + 46, y + 230], fill=(90, 90, 90))
    d2.ellipse([x, y, x + 84, y + 84], fill=(255, 255, 255), outline=(90, 90, 90), width=6)
    d2.line([x + 10, y + 74, x + 74, y + 10], fill=(90, 90, 90), width=6)
    d2.text((x + 42, y + 42), "60", fill=(20, 20, 20), anchor="mm")
    _car(d, 100, H // 2 - 35, 120, 70, CAR_RED)
    return img


def stop_sign():
    img, d = _road_scene()
    cx, cy = 650, 90
    pts = []
    import math
    for i in range(8):
        a = math.pi / 8 + i * math.pi / 4
        pts.append((cx + 55 * math.cos(a), cy + 55 * math.sin(a)))
    d.rectangle([cx - 4, cy + 55, cx + 4, cy + 200], fill=(90, 90, 90))
    d.polygon(pts, fill=(200, 30, 30), outline=(255, 255, 255))
    d.text((cx, cy), "STOP", fill=(255, 255, 255), anchor="mm")
    _car(d, 100, H // 2 - 35, 120, 70, CAR_BLUE)
    return img


def give_way_sign():
    img, d = _road_scene()
    cx, cy = 650, 90
    d.rectangle([cx - 4, cy + 60, cx + 4, cy + 200], fill=(90, 90, 90))
    d.polygon([(cx, cy - 55), (cx + 60, cy + 55), (cx - 60, cy + 55)], fill=(255, 255, 255), outline=(200, 30, 30), width=8)
    _car(d, 100, H // 2 - 35, 120, 70, CAR_RED)
    return img


def priority_road_sign():
    img, d = _road_scene()
    cx, cy = 650, 90
    d.rectangle([cx - 4, cy + 55, cx + 4, cy + 200], fill=(90, 90, 90))
    d.polygon([(cx, cy - 55), (cx + 55, cy), (cx, cy + 55), (cx - 55, cy)], fill=(255, 215, 60), outline=(255, 255, 255), width=6)
    _car(d, 100, H // 2 - 35, 120, 70, CAR_BLUE)
    return img


def emergency_vehicle():
    img, d = _base()
    d.rectangle([0, H // 2 - 70, W, H // 2 + 70], fill=ROAD)
    for x in range(20, W, 60):
        d.rectangle([x, H // 2 - 4, x + 30, H // 2 + 4], fill=LINE)
    _car(d, 100, H // 2 - 35, 130, 70, (240, 240, 240))
    d.rectangle([145, H // 2 - 50, 185, H // 2 - 35], fill=(40, 90, 200))
    d.rectangle([185, H // 2 - 50, 225, H // 2 - 35], fill=(220, 30, 30))
    _car(d, W - 260, H // 2 - 35, 120, 70, CAR_BLUE)
    return img


def narrow_crossing():
    img, d = _base()
    d.polygon([(0, H // 2 - 130), (W // 2 - 80, H // 2 - 35), (W // 2 + 80, H // 2 - 35), (W, H // 2 - 130),
               (W, H // 2 + 130), (W // 2 + 80, H // 2 + 35), (W // 2 - 80, H // 2 + 35), (0, H // 2 + 130)], fill=ROAD)
    d.line([(0, H // 2), (W // 2 - 80, H // 2), (W // 2, H // 2 - 20)], fill=LINE, width=3)
    d.line([(W // 2, H // 2 + 20), (W // 2 + 80, H // 2), (W, H // 2)], fill=LINE, width=3)
    _car(d, 120, H // 2 - 90, 100, 60, CAR_BLUE)
    _car(d, W - 240, H // 2 + 20, 100, 60, CAR_RED)
    return img


def overtaking_forbidden():
    img, d = _road_scene()
    d.line([(0, H // 2), (W, H // 2)], fill=LINE, width=5)
    _car(d, 100, H // 2 + 10, 120, 70, CAR_BLUE)
    _car(d, 420, H // 2 - 80, 120, 70, CAR_RED)
    return img


def stop_definition():
    img, d = _road_scene()
    _car(d, 380, H // 2 - 35, 120, 70, CAR_BLUE)
    d.ellipse([400, H // 2 + 40, 440, H // 2 + 80], fill=(240, 210, 150))
    return img


def parking_dangerous():
    img, d = _road_scene()
    d.rectangle([W // 2 - 90, 0, W // 2 + 90, H], fill=ROAD)
    for y in range(20, H, 60):
        d.rectangle([W // 2 - 4, y, W // 2 + 4, y + 30], fill=LINE)
    _car(d, W // 2 + 15, H // 2 - 180, 70, 110, CAR_RED)
    return img


def parking_hindering():
    img, d = _road_scene(sky=(230, 230, 230))
    d.rectangle([0, H // 2 - 90, W, H // 2 - 70], fill=(200, 200, 200))
    for x in range(0, W, 50):
        d.ellipse([x, H // 2 - 85, x + 14, H // 2 - 75], fill=(255, 255, 255))
    _car(d, 300, H // 2 - 100, 120, 30, CAR_ORANGE)
    return img


def highway_scene(label=""):
    img = Image.new("RGB", (W, H), GRASS)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 60, W, H - 60], fill=(70, 70, 75))
    d.rectangle([0, H // 2 - 6, W, H // 2 + 6], fill=(230, 180, 40))
    for i in (1,):
        pass
    for y in (160, H - 160):
        for x in range(10, W, 70):
            d.rectangle([x, y - 3, x + 35, y + 3], fill=LINE)
    _car(d, 80, 100, 110, 55, CAR_BLUE)
    _car(d, 400, H - 210, 110, 55, CAR_RED)
    return img


def highway_entry():
    img = highway_scene()
    d = ImageDraw.Draw(img)
    d.polygon([(0, H - 40), (260, H - 220), (420, H - 220), (420, H - 40)], fill=(70, 70, 75))
    _car(d, 60, H - 110, 110, 55, CAR_ORANGE)
    return img


def toll_scene():
    img, d = _road_scene(sky=(235, 235, 235))
    for x in (260, 520, 780):
        d.rectangle([x, H // 2 - 110, x + 14, H // 2 + 110], fill=(60, 60, 65))
    d.rectangle([150, H // 2 - 115, 850, H // 2 - 100], fill=(200, 200, 60))
    _car(d, 60, H // 2 - 35, 110, 70, CAR_BLUE)
    return img


def highway_exit():
    img = highway_scene()
    d = ImageDraw.Draw(img)
    d.polygon([(W, H - 40), (W - 260, H - 220), (W - 420, H - 220), (W - 420, H - 40)], fill=(70, 70, 75))
    _car(d, W - 200, H - 110, 110, 55, CAR_RED)
    return img


def bifurcation_scene():
    img = Image.new("RGB", (W, H), GRASS)
    d = ImageDraw.Draw(img)
    d.polygon([(0, H - 40), (W, 180), (W, 260), (W // 2 + 40, H - 40)], fill=(70, 70, 75))
    d.polygon([(0, H - 40), (W, H - 340), (W, H - 260), (W // 2 - 40, H - 40)], fill=(70, 70, 75))
    _car(d, 120, H - 120, 110, 55, CAR_BLUE)
    return img


def mountain_scene():
    img = Image.new("RGB", (W, H), (210, 230, 245))
    d = ImageDraw.Draw(img)
    d.polygon([(0, H), (200, 120), (420, H)], fill=(120, 140, 110))
    d.polygon([(260, H), (520, 60), (780, H)], fill=(100, 120, 95))
    d.polygon([(40, H), (W // 2, H - 200), (W, H - 40), (W, H), (0, H)], fill=ROAD)
    for x in range(20, W, 60):
        d.rectangle([x, H - 120, x + 30, H - 112], fill=LINE)
    _car(d, W // 2 - 60, H - 170, 100, 55, CAR_BLUE)
    return img


def weather_scene(kind):
    sky = {"rain": (150, 160, 175), "fog": (205, 205, 205), "wind": (190, 210, 225),
           "snow": (235, 240, 245), "ice": (210, 225, 235)}[kind]
    img = Image.new("RGB", (W, H), sky)
    d = ImageDraw.Draw(img)
    d.rectangle([0, H // 2 - 70, W, H // 2 + 70], fill=ROAD)
    for x in range(20, W, 60):
        d.rectangle([x, H // 2 - 4, x + 30, H // 2 + 4], fill=LINE)
    _car(d, 120, H // 2 - 35, 120, 70, CAR_BLUE)
    if kind == "rain":
        for x in range(0, W, 40):
            d.line([(x, 0), (x - 20, 100)], fill=(120, 140, 170), width=3)
    elif kind == "fog":
        for y in range(40, H - 40, 70):
            d.rectangle([0, y, W, y + 35], fill=(225, 225, 225))
    elif kind == "wind":
        for y in (80, 140, 400, 460):
            d.arc([600, y, 780, y + 60], 200, 340, fill=(255, 255, 255), width=4)
    elif kind == "snow":
        import random
        random.seed(3)
        for _ in range(60):
            x, y = random.randint(0, W), random.randint(0, H)
            d.ellipse([x, y, x + 6, y + 6], fill=(255, 255, 255))
    elif kind == "ice":
        d.polygon([(500, H // 2 - 68), (700, H // 2 - 68), (650, H // 2 + 68), (520, H // 2 + 68)], fill=(200, 230, 245))
    return img


BY_LESSON_TITLE = {
    "Les règles de circulation": lane_discipline,
    "Jeunes conducteurs": speed_sign,
    "Réduction de la vitesse": speed_sign_end,
    "Temps de réaction": stop_definition,
    "Distance de sécurité, de freinage et d'arrêt": lane_discipline,
    "Véhicules équipés de pneus à crampons": lambda: weather_scene("snow"),
    "La vitesse": speed_sign,
    "Signalisation": speed_sign,
    "Non-respect des limitations de vitesse": speed_sign,
    "Les routes prioritaires": priority_road_sign,
    "L'intersection": priority_right,
    "La signalisation de priorité": priority_road_sign,
    "La priorité à droite": priority_right,
    "La priorité ponctuelle": give_way_sign,
    "Le stop": stop_sign,
    "Cédez le passage": give_way_sign,
    "Carrefour à sens giratoire": roundabout,
    "Les feux tricolores": traffic_lights,
    "Les feux avec signalisation": traffic_lights,
    "Véhicules d'urgence et véhicules prioritaires": emergency_vehicle,
    "Autres cas": narrow_crossing,
    "Croisements": narrow_crossing,
    "Sur une chaussée en pente": slope_crossing,
    "Dépassements": overtaking,
    "Dépassements interdits": overtaking_forbidden,
    "Dépassements autorisés": overtaking,
    "Définition de l'arrêt": stop_definition,
    "Définition du stationnement": parking_modes,
    "Stationnement et arrêt dangereux": parking_dangerous,
    "Stationnement et arrêt gênants": parking_hindering,
    "Les manœuvres": parking_modes,
    "Se diriger vers l'autoroute": highway_scene,
    "Entrer sur l'autoroute": highway_entry,
    "Le péage": toll_scene,
    "Bretelle de raccordement autoroutière": highway_entry,
    "Caractéristiques de l'autoroute": highway_scene,
    "Marche normale": lane_discipline,
    "Manœuvres interdites": highway_scene,
    "Bifurcation": bifurcation_scene,
    "Jonction": highway_entry,
    "Sorties": highway_exit,
    "Routes pour automobiles": highway_scene,
    "Généralités": night_lights,
    "Quelques conseils": night_lights,
    "La pluie": lambda: weather_scene("rain"),
    "Le brouillard": lambda: weather_scene("fog"),
    "Le vent": lambda: weather_scene("wind"),
    "La neige": lambda: weather_scene("snow"),
    "Le verglas": lambda: weather_scene("ice"),
    "La conduite en montagne": mountain_scene,
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
