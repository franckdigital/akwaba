"""Mise en page des leçons en PDF, dans le style du livre : fil d'Ariane (chapitre > section), pastille
numérotée (ex. « 3.1 »), encadré violet pour un texte réglementaire mis en avant, puces orange, image
d'illustration. Réutilisé par `seed_course_conduite` (une leçon = un PDF, comme dans le livre).

Important : les illustrations du livre (photographies de situations de circulation) sont protégées par le
droit d'auteur de l'éditeur et ne sont pas reproduites ici. Les images utilisées sont des illustrations
génériques déjà présentes dans le projet (voir `apps/pedagogy/courses_code_route.py` pour le même principe).
"""
import io
import re

from django.core.files.base import ContentFile

PURPLE, ORANGE, INK = "#6D3FA0", "#E8702A", "#2B2B2B"


def _paragraphs(html):
    """Découpe un petit HTML (<p>...</p>) en paragraphes, en gardant <b> (gras) pour ReportLab."""
    parts = re.split(r"</p>\s*<p>", html.strip().removeprefix("<p>").removesuffix("</p>"))
    return [p.strip() for p in parts if p.strip()]


def build_lesson_pdf(chapter, section, number, title, html_text, image_bytes=None):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    purple, orange, ink = colors.HexColor(PURPLE), colors.HexColor(ORANGE), colors.HexColor(INK)
    crumb = ParagraphStyle("crumb", fontName="Helvetica-Bold", fontSize=9, textColor=colors.white, leading=12)
    h1 = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=18, leading=22, textColor=purple, spaceAfter=4)
    body = ParagraphStyle("body", fontName="Helvetica", fontSize=10.5, leading=16, textColor=colors.HexColor("#1F2937"), spaceAfter=10)
    callout = ParagraphStyle("callout", fontName="Helvetica-Oblique", fontSize=10, leading=14, textColor=colors.white)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=18 * mm,
                            title=title, author="Auto-Ecole Akwaba Treich", subject="Code de la route")
    W = A4[0] - 36 * mm

    # Fil d'Ariane façon onglets
    crumb_tbl = Table([[Paragraph(chapter.upper(), crumb), Paragraph(section.upper(), crumb)]],
                      colWidths=[W * 0.35, W * 0.65])
    crumb_tbl.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, 0), purple), ("BACKGROUND", (1, 0), (1, 0), orange),
                                   ("LEFTPADDING", (0, 0), (-1, -1), 10), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))

    # Pastille numérotée + titre
    badge = Table([[Paragraph(f"<b>{number}</b>", ParagraphStyle("num", fontName="Helvetica-Bold", fontSize=13, textColor=colors.white, alignment=1))]],
                  colWidths=[13 * mm], rowHeights=[13 * mm])
    badge.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), orange), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (0, 0), (-1, -1), "CENTER")]))
    head = Table([[badge, Paragraph(title, h1)]], colWidths=[16 * mm, W - 16 * mm])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))

    story = [crumb_tbl, Spacer(1, 14), head, Spacer(1, 10)]

    paras = _paragraphs(html_text)
    if paras:
        # Le premier paragraphe est mis en exergue (encadré violet), comme les citations de loi du livre.
        quote_tbl = Table([[Paragraph(paras[0], callout)]], colWidths=[W])
        quote_tbl.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), purple), ("LEFTPADDING", (0, 0), (-1, -1), 12),
                                       ("RIGHTPADDING", (0, 0), (-1, -1), 12), ("TOPPADDING", (0, 0), (-1, -1), 10),
                                       ("BOTTOMPADDING", (0, 0), (-1, -1), 10)]))
        story += [quote_tbl, Spacer(1, 12)]
        for p in paras[1:]:
            story.append(Paragraph(p, body))

    if image_bytes:
        try:
            img = Image(io.BytesIO(image_bytes), width=W * 0.6, height=W * 0.6 * (560 / 900))
            story += [Spacer(1, 10), img]
        except Exception:  # pragma: no cover - image optionnelle
            pass

    def footer(canvas, pdf):
        canvas.saveState()
        canvas.setFillColor(purple)
        canvas.rect(0, A4[1] - 5 * mm, A4[0], 5 * mm, stroke=0, fill=1)
        canvas.setFont("Helvetica", 8.5)
        canvas.setFillColor(colors.HexColor("#6B7280"))
        canvas.drawString(18 * mm, 10 * mm, "Auto-Ecole Akwaba Treich - Code de la route")
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"{chapter} — {section}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return ContentFile(buf.getvalue())
