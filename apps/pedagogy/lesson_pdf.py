"""Mise en page des leçons en PDF, dans le style du livre : fil d'Ariane (chapitre > section), pastille
numérotée (ex. « 3.1 »), encadré violet pour un texte réglementaire mis en avant, puces orange, image
d'illustration (photo extraite du livre source quand elle existe, sinon schéma généré). Réutilisé par
`seed_course_conduite` (une leçon = un PDF, comme dans le livre).
"""
import io
import re

from django.core.files.base import ContentFile

PURPLE, ORANGE, INK, RED = "#6D3FA0", "#E8702A", "#2B2B2B", "#C62828"


def _sharpen_for_print(raw, img_w_pt):
    """Les photos extraites du livre sont petites (souvent <250px de large) : les agrandir
    directement (via reportlab/le lecteur PDF) donne un rendu flou. On les ré-échantillonne
    nous-mêmes en LANCZOS à une densité d'impression correcte (~200 dpi) puis on accentue
    légèrement la netteté, ce qui donne un rendu bien plus net qu'un agrandissement brut.
    Retourne (BytesIO jpeg, ratio hauteur/largeur) ou None si l'image est illisible.
    """
    from PIL import Image as PILImage, ImageFilter

    pil = PILImage.open(io.BytesIO(raw))
    if pil.mode in ("RGBA", "LA", "P"):
        # Composite sur fond blanc (et non noir, le défaut de convert("RGB")) pour les PNG
        # transparents (icônes générées, logos) avant de les aplatir en JPEG.
        base = PILImage.new("RGB", pil.size, (255, 255, 255))
        rgba = pil.convert("RGBA")
        base.paste(rgba, mask=rgba.split()[-1])
        pil = base
    else:
        pil = pil.convert("RGB")
    ratio = pil.height / pil.width
    target_w = max(int(img_w_pt * 200 / 72), pil.width)
    target_h = int(target_w * ratio)
    if (target_w, target_h) != pil.size:
        pil = pil.resize((target_w, target_h), PILImage.LANCZOS)
    pil = pil.filter(ImageFilter.UnsharpMask(radius=1.4, percent=140, threshold=2))
    out = io.BytesIO()
    pil.save(out, format="JPEG", quality=92)
    out.seek(0)
    return out, ratio


def _fit_box(w, h, max_w, max_h):
    """Réduit (w, h) pour tenir dans (max_w, max_h) en conservant le ratio ; évite qu'une image
    à l'aspect inhabituel (très haute/étroite) ne dépasse la page (LayoutError)."""
    if w <= 0 or h <= 0:
        return max_w, max_h
    scale = min(max_w / w, max_h / h, 1.0)
    return w * scale, h * scale


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
            from PIL import Image as PILImage
            pil = PILImage.open(io.BytesIO(image_bytes))
            ratio = pil.height / pil.width
            img_w = min(W * 0.62, 320)
            img = Image(io.BytesIO(image_bytes), width=img_w, height=img_w * ratio)
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


def build_lesson_pdf_v2(chapter, section, number, title, blocks, images=None):
    """Variante fidèle au livre : rend une suite de blocs (quote/p/ul/h) dans l'ordre réel du
    document, avec les photos réelles du livre insérées juste après le sous-titre auquel elles
    se rapportent (comme dans la mise en page originale à deux colonnes).

    blocks : liste de dict {"t": "quote"|"p"|"ul"|"h", "text": str} ou {"t": "ul", "items": [...]}.
    images : liste d'octets JPEG/PNG, dans l'ordre de lecture du livre.
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Image, KeepTogether, ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    purple, orange, ink, red = colors.HexColor(PURPLE), colors.HexColor(ORANGE), colors.HexColor(INK), colors.HexColor(RED)
    crumb = ParagraphStyle("crumb", fontName="Helvetica-Bold", fontSize=9, textColor=colors.white, leading=12)
    h1 = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=18, leading=22, textColor=red, spaceAfter=4)
    h4 = ParagraphStyle("h4", fontName="Helvetica-Bold", fontSize=12, leading=16, textColor=orange, spaceBefore=12, spaceAfter=6, keepWithNext=True)
    body = ParagraphStyle("body", fontName="Helvetica", fontSize=10.5, leading=15.5, textColor=colors.HexColor("#1F2937"), spaceAfter=8)
    li_style = ParagraphStyle("li", fontName="Helvetica", fontSize=10.5, leading=15, textColor=colors.HexColor("#1F2937"))
    callout = ParagraphStyle("callout", fontName="Helvetica-Oblique", fontSize=10, leading=14, textColor=colors.white)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=18 * mm,
                            title=title, author="Auto-Ecole Akwaba Treich", subject="Code de la route")
    W = A4[0] - 36 * mm

    crumb_tbl = Table([[Paragraph(chapter.upper(), crumb), Paragraph(section.upper(), crumb)]],
                      colWidths=[W * 0.35, W * 0.65])
    crumb_tbl.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, 0), red), ("BACKGROUND", (1, 0), (1, 0), orange),
                                   ("LEFTPADDING", (0, 0), (-1, -1), 10), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))

    badge = Table([[Paragraph(f"<b>{number}</b>", ParagraphStyle("num", fontName="Helvetica-Bold", fontSize=13, textColor=colors.white, alignment=1))]],
                  colWidths=[13 * mm], rowHeights=[13 * mm])
    badge.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), red), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (0, 0), (-1, -1), "CENTER")]))
    head = Table([[badge, Paragraph(title, h1)]], colWidths=[16 * mm, W - 16 * mm])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))

    story = [crumb_tbl, Spacer(1, 14), head, Spacer(1, 10)]

    images = list(images or [])
    img_idx = 0

    def next_image_flowable(raw=None):
        nonlocal img_idx
        if raw is None:
            if img_idx >= len(images):
                return None
            raw = images[img_idx]
            img_idx += 1
        try:
            img_w = min(W * 0.55, 280)
            sharp = _sharpen_for_print(raw, img_w)
            if sharp is None:
                return None
            data, ratio = sharp
            img_w, img_h = _fit_box(img_w, img_w * ratio, img_w, 260)
            return [Spacer(1, 6), Image(data, width=img_w, height=img_h), Spacer(1, 8)]
        except Exception:
            return None

    quoted = False

    def flow_for(b):
        nonlocal quoted
        if b["t"] == "quote" and not quoted:
            quoted = True
            quote_tbl = Table([[Paragraph(b["text"], callout)]], colWidths=[W])
            quote_tbl.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), purple), ("LEFTPADDING", (0, 0), (-1, -1), 12),
                                           ("RIGHTPADDING", (0, 0), (-1, -1), 12), ("TOPPADDING", (0, 0), (-1, -1), 10),
                                           ("BOTTOMPADDING", (0, 0), (-1, -1), 10)]))
            return [quote_tbl, Spacer(1, 12)]
        elif b["t"] in ("quote", "p"):
            return [Paragraph(b["text"], body)]
        elif b["t"] == "ul":
            items = [ListItem(Paragraph(it, li_style), bulletColor=orange) for it in b["items"]]
            return [ListFlowable(items, bulletType="bullet", bulletColor=orange, leftIndent=14, spaceBefore=2, spaceAfter=8)]
        elif b["t"] == "note":
            # Encadré secondaire à bordure rouge (ex. peines complémentaires), fond blanc,
            # distinct de la citation principale (encadré violet plein).
            note_body = ParagraphStyle("noteBody", fontName="Helvetica-Bold", fontSize=9.5, leading=13, textColor=colors.HexColor("#1F2937"))
            note_li = ParagraphStyle("noteLi", fontName="Helvetica-Bold", fontSize=9.5, leading=12.5, textColor=colors.HexColor("#1F2937"))
            inner = [Paragraph(b["text"], note_body)]
            if b.get("items"):
                items = [ListItem(Paragraph(it, note_li), bulletColor=red) for it in b["items"]]
                inner.append(ListFlowable(items, bulletType="bullet", bulletColor=red, leftIndent=12, spaceBefore=4))
            note_tbl = Table([[inner]], colWidths=[W])
            note_tbl.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 1.2, red), ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                                          ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                                          ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 10)]))
            return [note_tbl, Spacer(1, 10)]
        elif b["t"] == "img":
            img_w = min(W * 0.55, 280)
            sharp = _sharpen_for_print(b["data"], img_w)
            if not sharp:
                return []
            data, ratio = sharp
            img_w, img_h = _fit_box(img_w, img_w * ratio, img_w, 260)
            return [Spacer(1, 6), Image(data, width=img_w, height=img_h), Spacer(1, 8)]
        elif b["t"] == "img_row":
            cells, cw = [], W / len(b["data"])
            for raw in b["data"]:
                sharp = _sharpen_for_print(raw, cw * 0.85)
                if not sharp:
                    continue
                data, ratio = sharp
                iw = cw * 0.85
                iw, ih = _fit_box(iw, iw * ratio, iw, 180)
                cells.append(Image(data, width=iw, height=ih))
            if not cells:
                return []
            row_tbl = Table([cells], colWidths=[cw] * len(cells))
            row_tbl.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
            return [Spacer(1, 6), row_tbl, Spacer(1, 8)]
        elif b["t"] == "table":
            cell_style = ParagraphStyle("cell", fontName="Helvetica", fontSize=8.5, leading=11, textColor=colors.HexColor("#1F2937"))
            head_style = ParagraphStyle("thead", fontName="Helvetica-Bold", fontSize=8.5, leading=11, textColor=colors.white, alignment=1)
            val_style = ParagraphStyle("tval", fontName="Helvetica-Bold", fontSize=10, leading=12, textColor=red, alignment=1)
            header_row = [Paragraph(c, head_style) for c in b["header"]]
            data_rows = [[Paragraph(row[0], cell_style)] + [Paragraph(v, val_style) for v in row[1:]] for row in b["rows"]]
            n_cols = len(b["header"])
            col_w = [W * 0.28] + [W * 0.72 / (n_cols - 1)] * (n_cols - 1)
            tbl = Table([header_row] + data_rows, colWidths=col_w)
            style = [("BACKGROUND", (0, 0), (-1, 0), orange), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                     ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("GRID", (0, 0), (-1, -1), 0.6, colors.HexColor("#E5E7EB")),
                     ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                     ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6)]
            for r in range(1, len(data_rows) + 1):
                if r % 2 == 0:
                    style.append(("BACKGROUND", (0, r), (-1, r), colors.HexColor("#F9FAFB")))
            tbl.setStyle(TableStyle(style))
            return [tbl, Spacer(1, 10)]
        return []

    caption_style = ParagraphStyle("caption", fontName="Helvetica-Bold", fontSize=9, leading=12,
                                   textColor=colors.HexColor("#1F2937"), alignment=1, spaceBefore=4)

    def next_thumb_flowable(raw=None):
        nonlocal img_idx
        if raw is None:
            if img_idx >= len(images):
                return None
            raw = images[img_idx]
            img_idx += 1
        try:
            thumb_w = min(W * 0.22, 110)
            sharp = _sharpen_for_print(raw, thumb_w)
            if sharp is None:
                return None
            data, ratio = sharp
            thumb_w, thumb_h = _fit_box(thumb_w, thumb_w * ratio, thumb_w, 140)
            return Image(data, width=thumb_w, height=thumb_h)
        except Exception:
            return None

    def caption_cell(text, raw=None):
        thumb = next_thumb_flowable(raw)
        cell = [thumb] if thumb else []
        cell.append(Paragraph(text, caption_style))
        return cell

    ncols = 3
    col_w = W / ncols

    def grid_row(cells):
        row = list(cells) + [[]] * (ncols - len(cells))
        grid = Table([row], colWidths=[col_w] * ncols)
        grid.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                  ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 10)]))
        return grid

    first_h_seen = False
    i = 0
    while i < len(blocks):
        b = blocks[i]
        if b["t"] == "caption":
            # Légendes courtes d'un panneau (ex. « Virage à gauche ») : regroupées par 3 avec
            # leur vignette, façon planche de panneaux comme dans le livre. Chaque légende porte
            # déjà (si extraite avec appariement spatial) l'image exacte qui lui correspond.
            run = []
            while i < len(blocks) and blocks[i]["t"] == "caption":
                run.append(caption_cell(blocks[i]["text"], blocks[i].get("img_data")))
                i += 1
            for r0 in range(0, len(run), ncols):
                story.append(grid_row(run[r0:r0 + ncols]))
            continue
        cur_i = i
        i += 1
        if b["t"] == "h":
            if not first_h_seen and cur_i > 0:
                # Une image sans sous-titre associé (photo de l'intro, avant le premier
                # sous-titre du sujet) est insérée ici plutôt que rattachée au 1er sous-titre.
                img_flow = next_image_flowable()
                if img_flow:
                    story += img_flow
            first_h_seen = True
            # Le sous-titre est maintenu avec son image et le début de son texte, pour ne
            # jamais le laisser seul en bas de page (titre détaché de son contenu).
            group = [Paragraph(f'<font color="{ORANGE}">●</font>&nbsp;&nbsp;{b["text"]}', h4)]
            img_flow = next_image_flowable(b.get("img_data")) if b.get("img_data") else next_image_flowable()
            if img_flow:
                group += img_flow
            else:
                nxt = blocks[cur_i + 1] if cur_i + 1 < len(blocks) else None
                if nxt and nxt["t"] == "caption":
                    # Le sous-titre est immédiatement suivi d'une planche de légendes : on
                    # rattache la 1re rangée (jusqu'à 3) au sous-titre pour ne jamais le laisser
                    # seul en bas de page, et on consomme ces légendes ici (pas de double rendu).
                    row_cells = []
                    j = cur_i + 1
                    while j < len(blocks) and blocks[j]["t"] == "caption" and len(row_cells) < ncols:
                        row_cells.append(caption_cell(blocks[j]["text"], blocks[j].get("img_data")))
                        blocks[j] = {"t": "_consumed"}
                        j += 1
                    if row_cells:
                        group.append(grid_row(row_cells))
                elif nxt and nxt["t"] != "h":
                    group += flow_for(nxt)
                    blocks[cur_i + 1] = {"t": "_consumed"}
            story.append(KeepTogether(group))
        elif b["t"] == "_consumed":
            continue
        else:
            story += flow_for(b)

    # Image(s) restantes (pas de sous-titre dans le livre, ou illustration générale de la leçon).
    while img_idx < len(images):
        img_flow = next_image_flowable()
        if not img_flow:
            break
        story += img_flow

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
