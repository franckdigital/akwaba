"""Ajoute une VIDÉO à chaque cours « Code de la route » de la banque centrale (en plus du PDF et de la fiche « À retenir »).

    python manage.py seed_courses_video                        # crée les cours s'ils manquent, puis ajoute/rafraîchit les vidéos
    python manage.py seed_courses_video --embed-urls urls.json # + une leçon « vidéo en ligne » (YouTube/Vimeo) par cours

La vidéo est un diaporama animé généré à partir du contenu du cours (titre, grandes parties, points à retenir) : aucun fichier
externe n'est nécessaire. Elle exige `ffmpeg` sur la machine ; sans ffmpeg, la commande le signale et n'ajoute que les leçons en ligne.
`urls.json` : {"Titre exact du cours": "https://www.youtube.com/watch?v=..."} (vos vraies vidéos, hébergées ailleurs).

Chaque cours est organisé en deux sections : « Vidéo » puis « Support de cours » (PDF, illustration, fiche « À retenir »).
"""
import json
import shutil
import subprocess
import tempfile
import textwrap
from math import ceil
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from apps.pedagogy.courses_code_route import COURSES
from apps.pedagogy.models import Course, CourseMaterial

W, H = 1280, 720
SECONDS_PER_SLIDE = 7
THEME_COLORS = {"regulation": ("#7F1D1D", "#DC2626"), "code": ("#1C1C1C", "#5C5C5C"), "signs": ("#1E3A8A", "#3B82F6"), "priority": ("#5B21B6", "#A78BFA"),
                "safety": ("#065F46", "#10B981"), "mechanics": ("#92400E", "#F59E0B"), "firstaid": ("#9D174D", "#F472B6")}
FONTS = {
    "regular": ["arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"],
    "bold": ["arialbd.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
}


def _font(kind, size):
    from PIL import ImageFont
    for name in FONTS[kind]:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _short(text, limit=170):
    """Première(s) phrase(s) du paragraphe, tronquée(s) proprement pour tenir sur une diapositive."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("; "))
    return (cut[:end + 1] if end > 60 else cut.rsplit(" ", 1)[0] + "…")


def _flatten(paragraphs):
    """Paragraphes (texte, liste à puces ou tableau) -> lignes courtes pour une diapositive."""
    out = []
    for p in paragraphs:
        if isinstance(p, str):
            out.append(_short(p))
        elif isinstance(p, (list, tuple)):
            out.extend(_short(x, 120) for x in p[:3])
        elif isinstance(p, dict):   # tableau : « colonne 1 : colonne 2 » (en-tête ignorée)
            out.extend(_short(f"{row[0]} : {row[1]}", 130) for row in p["table"][1:4] if len(row) > 1)
    return out


def _slide(theme, kicker, title, lines, footer, number, total):
    from PIL import Image, ImageDraw
    dark, accent = THEME_COLORS.get(theme, THEME_COLORS["regulation"])
    img = Image.new("RGB", (W, H), dark)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 18, H], fill=accent)
    d.ellipse([W - 320, -160, W + 120, 280], fill=accent)
    d.text((70, 52), kicker.upper(), font=_font("bold", 26), fill="#FCA5A5" if theme == "regulation" else "#E5E7EB")
    y = 100
    for line in textwrap.wrap(title, 34)[:3]:
        d.text((70, y), line, font=_font("bold", 54), fill="white")
        y += 66
    y += 26
    for line in lines:
        wrapped = textwrap.wrap(line, 54)
        d.ellipse([74, y + 12, 88, y + 26], fill=accent)
        for k, part in enumerate(wrapped[:3]):
            d.text((108, y), part, font=_font("regular", 34), fill="#F9FAFB")
            y += 44
        y += 14
    d.text((70, H - 54), footer, font=_font("regular", 22), fill="#D1D5DB")
    d.text((W - 150, H - 54), f"{number} / {total}", font=_font("regular", 22), fill="#D1D5DB")
    return img


def build_slides(data):
    theme, title = data["theme"], data["title"]
    slides = [dict(kicker="Auto-Ecole Akwaba Treich · Code de la route", title=title, lines=[data["summary"]])]
    for heading, paragraphs in data["sections"][:5]:
        lines = _flatten(paragraphs)
        for i in range(0, min(len(lines), 6), 3):   # 2 diapositives au plus par grande partie
            slides.append(dict(kicker="À comprendre", title=heading, lines=lines[i:i + 3]))
    points = data["key_points"]
    for i in range(0, len(points), 3):
        slides.append(dict(kicker="À retenir", title="Les points essentiels", lines=[_short(p, 150) for p in points[i:i + 3]]))
    slides.append(dict(kicker="Et maintenant ?", title="Passez au support PDF puis au QCM", lines=["Lisez le support de cours.", "Entraînez-vous avec les QCM du code.", "Passez l'examen blanc quand vous êtes prêt(e)."]))
    footer = "Auto-Ecole Akwaba Treich"
    return [_slide(theme, s["kicker"], s["title"], s["lines"], footer, n, len(slides)) for n, s in enumerate(slides, 1)], len(slides)


def build_video(data, ffmpeg):
    """Diaporama -> MP4 (H.264) ; renvoie (octets, extension, durée en secondes)."""
    images, count = build_slides(data)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for i, im in enumerate(images):
            im.save(tmp / f"s{i:03d}.png")
        out = tmp / "out.mp4"
        cmd = [ffmpeg, "-y", "-loglevel", "error", "-framerate", f"1/{SECONDS_PER_SLIDE}", "-i", str(tmp / "s%03d.png"),
               "-vf", "fps=25,format=yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-movflags", "+faststart", str(out)]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise CommandError(f"ffmpeg a échoué : {res.stderr.strip()[:300]}")
        return out.read_bytes(), "mp4", count * SECONDS_PER_SLIDE


class Command(BaseCommand):
    help = "Ajoute une vidéo (diaporama généré) à chaque cours « Code de la route », en plus du PDF."

    def add_arguments(self, parser):
        parser.add_argument("--embed-urls", help="Fichier JSON {titre du cours: URL YouTube/Vimeo} : ajoute une leçon « vidéo en ligne ».")
        parser.add_argument("--no-generate", action="store_true", help="Ne génère pas les vidéos (uniquement --embed-urls).")

    def handle(self, *args, **opts):
        if not Course.objects.filter(school=None, title=COURSES[0]["title"]).exists():
            self.stdout.write("Cours absents : création via seed_courses_code_route…")
            call_command("seed_courses_code_route")
        embeds = json.loads(Path(opts["embed_urls"]).read_text(encoding="utf8")) if opts["embed_urls"] else {}
        ffmpeg = None if opts["no_generate"] else shutil.which("ffmpeg")
        if not opts["no_generate"] and not ffmpeg:
            self.stderr.write(self.style.WARNING("ffmpeg introuvable : vidéos générées ignorées (installez ffmpeg ou utilisez --embed-urls)."))

        done = 0
        for data in COURSES:
            course = Course.objects.filter(school=None, title=data["title"]).first()
            if course is None:
                continue
            # organisation en sections : Vidéo, puis Support de cours
            CourseMaterial.objects.filter(course=course, material_type__in=["pdf", "image", "text"]).update(section="Support de cours")
            CourseMaterial.objects.filter(course=course, material_type__in=["video", "embed"]).delete()
            order = 0
            if ffmpeg:
                content, ext, seconds = build_video(data, ffmpeg)
                m = CourseMaterial(course=course, material_type="video", section="Vidéo", order=order, title=f"Vidéo : {data['title']}", is_required=True,
                                   description="Les grandes idées du cours en images. Regardez la vidéo puis lisez le support PDF.",
                                   duration_minutes=max(1, ceil(seconds / 60)), download_allowed=False)
                m.file.save(f"cours-{data['theme']}-{course.id}.{ext}", ContentFile(content), save=False)
                m.save()
                m.file_size = m.file.size
                m.save(update_fields=["file_size"])
                order += 1
            if data["title"] in embeds:
                CourseMaterial.objects.create(course=course, material_type="embed", section="Vidéo", order=order, title=f"Vidéo complète : {data['title']}",
                                              url=embeds[data["title"]], is_required=False, duration_minutes=10, description="Vidéo d'approfondissement.")
                order += 1
            # PDF, illustration, fiche : passent après la vidéo en conservant leur ordre relatif
            for j, mat in enumerate(course.materials.exclude(material_type__in=["video", "embed"]).order_by("order", "id")):
                mat.order = order + j
                mat.save(update_fields=["order"])
            course.duration_minutes = sum(x.duration_minutes for x in course.materials.all()) or course.duration_minutes
            course.save(update_fields=["duration_minutes"])
            done += 1
        self.stdout.write(self.style.SUCCESS(f"{done} cours mis à jour (vidéo{' + lien en ligne' if embeds else ''} + PDF)."))
