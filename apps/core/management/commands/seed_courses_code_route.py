"""Crée les cours « Code de la route » de la banque centrale Akwaba : supports PDF générés, fiches « À retenir » (texte), image illustrée.

    python manage.py seed_courses_code_route            # crée/met à jour les cours
    python manage.py seed_courses_code_route --wipe     # supprime d'abord TOUS les cours (et leurs contenus)

Les cours sont créés dans la banque centrale (school = NULL) : visibles par toutes les auto-écoles, modifiables par l'administrateur Akwaba.
Le contenu source est dans apps/pedagogy/courses_code_route.py.
"""
import io
import os

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.pedagogy.courses_code_route import COURSES
from apps.pedagogy.models import Course, CourseMaterial

RED, INK = "#E02027", "#2B2B2B"
THEME_COLORS = {"regulation": ("#B9161D", "#E02027"), "code": ("#2B2B2B", "#5C5C5C"), "signs": ("#1D4ED8", "#3B82F6"), "priority": ("#7C3AED", "#A78BFA"),
                "safety": ("#059669", "#34D399"), "mechanics": ("#D97706", "#FBBF24"), "firstaid": ("#DB2777", "#F472B6")}


# ---------------------------------------------------------------------------------------------------- PDF
def build_pdf(course, number, total):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import KeepTogether, ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    red, ink = colors.HexColor(RED), colors.HexColor(INK)
    body = ParagraphStyle("body", fontName="Helvetica", fontSize=10.5, leading=15, textColor=colors.HexColor("#1F2937"), alignment=TA_LEFT, spaceAfter=6)
    h1 = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=22, leading=26, textColor=ink, spaceAfter=4)
    sub = ParagraphStyle("sub", fontName="Helvetica", fontSize=11.5, leading=16, textColor=colors.HexColor("#6B7280"), spaceAfter=14)
    h2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=13.5, leading=18, textColor=red, spaceBefore=12, spaceAfter=6)
    cell = ParagraphStyle("cell", parent=body, fontSize=9.5, leading=13, spaceAfter=0)
    cell_b = ParagraphStyle("cell_b", parent=cell, fontName="Helvetica-Bold", textColor=colors.white)
    key = ParagraphStyle("key", parent=body, fontSize=10.5, textColor=ink)

    def esc(t):
        return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#E5E7EB"))
        canvas.line(20 * mm, 15 * mm, A4[0] - 20 * mm, 15 * mm)
        canvas.setFont("Helvetica", 8.5)
        canvas.setFillColor(colors.HexColor("#6B7280"))
        canvas.drawString(20 * mm, 10 * mm, "Auto-Ecole Akwaba Treich - Cours de code de la route")
        canvas.drawRightString(A4[0] - 20 * mm, 10 * mm, f"Page {doc.page}")
        canvas.setFillColor(red)
        canvas.rect(0, A4[1] - 6 * mm, A4[0], 6 * mm, stroke=0, fill=1)
        canvas.restoreState()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=20 * mm, bottomMargin=22 * mm,
                            title=course["title"], author="Auto-Ecole Akwaba Treich", subject="Code de la route")
    W = A4[0] - 40 * mm
    story = [Paragraph(f"COURS {number} / {total}", ParagraphStyle("kicker", fontName="Helvetica-Bold", fontSize=9, textColor=red, spaceAfter=6)),
             Paragraph(esc(course["title"]), h1), Paragraph(esc(course["summary"]) + f" &nbsp;·&nbsp; Durée indicative : {course['minutes']} min", sub)]

    def render(item):
        if isinstance(item, str):
            return [Paragraph(esc(item), body)]
        if isinstance(item, list):
            return [ListFlowable([ListItem(Paragraph(esc(t), body), leftIndent=14) for t in item], bulletType="bullet", start="•", leftIndent=14, bulletColor=red), Spacer(1, 4)]
        rows = [[Paragraph(esc(c), cell_b if i == 0 else cell) for c in r] for i, r in enumerate(item["table"])]
        widths = item.get("widths")
        scale = W / sum(widths) if widths else None
        t = Table(rows, colWidths=[w * scale for w in widths] if widths else None, repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), red), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FEF3F3")]),
                               ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#F9C4C6")), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
        return [t, Spacer(1, 8)]

    for heading, items in course["sections"]:
        block = [Paragraph(esc(heading), h2)]
        first = render(items[0])
        story.append(KeepTogether(block + first))
        for it in items[1:]:
            story.extend(render(it))

    pts = [[Paragraph("<b>À RETENIR</b>", ParagraphStyle("kh", parent=key, textColor=red))]] + [[Paragraph("• " + esc(p), key)] for p in course["key_points"]]
    box = Table(pts, colWidths=[W])
    box.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FEF3F3")), ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#F9C4C6")),
                             ("LEFTPADDING", (0, 0), (-1, -1), 12), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story += [Spacer(1, 12), KeepTogether([box])]
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()


# ---------------------------------------------------------------------------------------------------- images
def _font(size, bold=False):
    from PIL import ImageFont
    for path in ("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                 "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"):
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


def cover_png(course):
    from PIL import Image, ImageDraw
    c1, c2 = THEME_COLORS.get(course["theme"], THEME_COLORS["regulation"])
    w, h = 960, 540
    img = Image.new("RGB", (w, h), c1)
    px = img.load()
    a, b = tuple(int(c1[i:i + 2], 16) for i in (1, 3, 5)), tuple(int(c2[i:i + 2], 16) for i in (1, 3, 5))
    for y in range(h):
        for x in range(w):
            t = (x / w + y / h) / 2
            px[x, y] = tuple(int(a[k] + (b[k] - a[k]) * t) for k in range(3))
    d = ImageDraw.Draw(img, "RGBA")
    d.ellipse((w - 420, -160, w + 120, 380), fill=(255, 255, 255, 40))
    d.ellipse((-120, h - 220, 300, h + 160), fill=(255, 255, 255, 30))
    d.text((60, 60), "CODE DE LA ROUTE", font=_font(28, True), fill=(255, 255, 255, 210))
    words, lines, cur = course["title"].split(), [], ""
    for wd in words:
        if len(cur + " " + wd) > 24 and cur:
            lines.append(cur)
            cur = wd
        else:
            cur = (cur + " " + wd).strip()
    lines.append(cur)
    y = 150
    for ln in lines[:4]:
        d.text((60, y), ln, font=_font(58, True), fill=(255, 255, 255, 255))
        y += 70
    d.text((60, h - 80), "Auto-Ecole Akwaba Treich", font=_font(26), fill=(255, 255, 255, 220))
    out = io.BytesIO()
    img.save(out, "PNG", optimize=True)
    return out.getvalue()


def panneaux_png():
    """Illustration : formes et couleurs des panneaux (cours « La signalisation routière »)."""
    from PIL import Image, ImageDraw
    w, h = 1200, 700
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)
    d.text((40, 24), "Reconnaître un panneau : forme, couleur, symbole", font=_font(38, True), fill=INK)
    cols = 3
    items = [("tri", "Danger", "Triangle rouge et blanc"), ("rond_r", "Interdiction / ordre", "Rond rouge et blanc"), ("rond_b", "Obligation", "Rond bleu foncé et blanc"),
             ("carre", "Indication", "Carré bleu foncé et blanc"), ("rect", "Localisation", "Rectangle blanc"), ("fleche", "Direction", "Flèche verte ou bleue")]
    for i, (kind, title, sub) in enumerate(items):
        cx, cy = 200 + (i % cols) * 400, 210 + (i // cols) * 250
        if kind == "tri":
            d.polygon([(cx, cy - 75), (cx - 85, cy + 65), (cx + 85, cy + 65)], fill="#DC2626")
            d.polygon([(cx, cy - 45), (cx - 55, cy + 50), (cx + 55, cy + 50)], fill="white")
        elif kind == "rond_r":
            d.ellipse((cx - 75, cy - 75, cx + 75, cy + 75), fill="#DC2626")
            d.ellipse((cx - 52, cy - 52, cx + 52, cy + 52), fill="white")
        elif kind == "rond_b":
            d.ellipse((cx - 75, cy - 75, cx + 75, cy + 75), fill="#1D4ED8")
            d.ellipse((cx - 58, cy - 58, cx + 58, cy + 58), fill="#1D4ED8", outline="white", width=6)
        elif kind == "carre":
            d.rounded_rectangle((cx - 70, cy - 70, cx + 70, cy + 70), 12, fill="#1D4ED8", outline="white", width=6)
        elif kind == "rect":
            d.rounded_rectangle((cx - 90, cy - 50, cx + 90, cy + 50), 12, fill="white", outline="#9CA3AF", width=5)
        else:
            d.polygon([(cx - 95, cy - 45), (cx + 40, cy - 45), (cx + 95, cy), (cx + 40, cy + 45), (cx - 95, cy + 45)], fill="#059669")
        d.text((cx - 150, cy + 90), title, font=_font(30, True), fill=INK)
        d.text((cx - 150, cy + 128), sub, font=_font(22), fill="#6B7280")
    d.text((40, h - 46), "Danger : annoncé à 50 m en agglomération, 150 m en dehors.", font=_font(24), fill="#B9161D")
    out = io.BytesIO()
    img.save(out, "PNG", optimize=True)
    return out.getvalue()


class Command(BaseCommand):
    help = "Crée les cours Code de la route (PDF, texte, image) dans la banque centrale."

    def add_arguments(self, parser):
        parser.add_argument("--wipe", action="store_true", help="Supprime d'abord tous les cours existants.")

    @transaction.atomic
    def handle(self, *args, **opts):
        if opts["wipe"]:
            n = Course.objects.count()
            Course.objects.all().delete()
            self.stdout.write(f"{n} cours supprimé(s).")
        total = len(COURSES)
        created = 0
        for i, data in enumerate(COURSES, start=1):
            course, was_new = Course.objects.update_or_create(
                school=None, title=data["title"],
                defaults=dict(kind="theory", theme=data["theme"], summary=data["summary"], duration_minutes=data["minutes"], order=i, is_published=True, sequential=True,
                              content=data["summary"]))
            created += was_new
            slug = f"cours-{i:02d}"
            course.cover.save(f"{slug}.png", ContentFile(cover_png(data)), save=True)
            course.materials.all().delete()
            mats = []
            pdf = build_pdf(data, i, total)
            m = CourseMaterial(course=course, material_type="pdf", title=f"Cours complet (PDF) — {data['title']}", order=1,
                               description="Support de cours à lire en ligne ou à télécharger.", duration_minutes=data["minutes"], is_required=True, download_allowed=True)
            m.file.save(f"{slug}-{i}.pdf", ContentFile(pdf), save=False)
            m.save()
            m.file_size = m.file.size
            m.save(update_fields=["file_size"])
            mats.append(m)
            if data.get("image") == "panneaux":
                im = CourseMaterial(course=course, material_type="image", title="Illustration : formes et couleurs des panneaux", order=2, is_required=False,
                                    description="Schéma récapitulatif à mémoriser.")
                im.file.save("panneaux-formes-couleurs.png", ContentFile(panneaux_png()), save=False)
                im.save()
                im.file_size = im.file.size
                im.save(update_fields=["file_size"])
            CourseMaterial.objects.create(course=course, material_type="text", title="À retenir", order=3, is_required=True, duration_minutes=3,
                                          text="\n".join("• " + p for p in data["key_points"]),
                                          description="Les points essentiels avant de passer le QCM.")
        self.stdout.write(self.style.SUCCESS(f"{total} cours prêts ({created} créés)."))
