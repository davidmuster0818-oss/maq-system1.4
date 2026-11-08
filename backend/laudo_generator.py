"""
Laudo Generator - Template-based approach
Opens the real DOCX template and replaces text fields and photo images
while preserving the original formatting, frames, logos, and decorative images.
"""
import io
import base64
import zipfile
import logging
from pathlib import Path
from docx import Document
from docx.oxml.ns import qn
from PIL import Image

logger = logging.getLogger(__name__)

TEMPLATE_PATH = Path(__file__).parent / "laudo_template.docx"

# Map: user image index -> image filename in ZIP
# Mapping determined by XML position analysis (anchor offsets + paragraph grouping):
#   rId7  (image1) -> H=41pt left, V=87pt top (margin) = FOTO 1 (left, page 1)
#   rId8  (image2) -> H=125pt left, V=106pt top (margin) = FOTO 2 (right, page 1)
#   rId9  (image3) -> H=67pt left, V=627pt top (margin) = FOTO 3 (left, bottom page 1)
#   rId10 (image4) -> H=349pt left, V=627pt top (margin) = FOTO 4 (right, bottom page 1)
#   rId12 (image6) -> H=72pt left (column-relative) = FOTO 5 (left, page 2)
#   rId13 (image7) -> H=356pt left (margin) = FOTO 6 (right, page 2)
#   rId15 (image9) -> H=58pt left (column-relative) = FOTO 7 (left, page 2/3)
#   rId14 (image8) -> H=325pt left (margin) = FOTO 8 (right, page 2/3)
#   rId11 (image5) -> extra image in P[38] group, blanked out
#   rId16 (image10.png) -> decorative voltage diagram, not touched
PHOTO_SLOTS = {
    0: 'word/media/image1.jpeg',   # FOTO 1 (rId7)
    1: 'word/media/image2.jpeg',   # FOTO 2 (rId8)
    2: 'word/media/image3.jpeg',   # FOTO 3 (rId9)
    3: 'word/media/image4.jpeg',   # FOTO 4 (rId10)
    4: 'word/media/image6.jpeg',   # FOTO 5 (rId12)
    5: 'word/media/image7.jpeg',   # FOTO 6 (rId13)
    6: 'word/media/image9.jpeg',   # FOTO 7 (rId15)
    7: 'word/media/image8.jpeg',   # FOTO 8 (rId14)
}

# Extra image that should be blanked when user provides photos
EXTRA_IMAGE_SLOT = 'word/media/image5.jpeg'  # rId11 - extra anchor in FOTO 3/4 group

VML_NS = 'urn:schemas-microsoft-com:vml'
W_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'


def _make_blank_jpeg():
    """Create a 1x1 white JPEG for blank photo slots."""
    img = Image.new('RGB', (1, 1), (255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format='JPEG')
    return buf.getvalue()

BLANK_JPEG = _make_blank_jpeg()


def _to_jpeg_bytes(image_bytes):
    """Convert any image bytes to JPEG format for compatibility with template slots."""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        if img.mode in ('RGBA', 'P', 'LA'):
            bg = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            bg.paste(img, mask=img.split()[-1] if 'A' in img.mode else None)
            img = bg
        elif img.mode != 'RGB':
            img = img.convert('RGB')
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=90)
        return buf.getvalue()
    except Exception:
        return image_bytes


def _replace_cell_text(cell, new_text):
    """Replace text in a table cell while preserving formatting of the first run.
    Preserves any drawing elements (anchored images like FOTO 2) by moving them
    out of runs before text replacement."""
    if not cell.paragraphs:
        return
    p = cell.paragraphs[0]

    # Preserve any drawing elements that may be inside runs
    W_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    saved_drawings = []
    for run_elem in p._element.findall(f'{{{W_NS}}}r'):
        for drawing in run_elem.findall(f'{{{W_NS}}}drawing'):
            saved_drawings.append(drawing)
            run_elem.remove(drawing)

    if p.runs:
        p.runs[0].text = str(new_text)
        for run in p.runs[1:]:
            run.text = ""
    else:
        p.text = str(new_text)
    for extra_p in cell.paragraphs[1:]:
        for run in extra_p.runs:
            run.text = ""

    # Re-insert preserved drawings at the paragraph level
    for drawing in saved_drawings:
        # Insert drawing in its own run to preserve formatting
        new_run = p._element.makeelement(f'{{{W_NS}}}r', {})
        new_run.append(drawing)
        p._element.append(new_run)


def _replace_status_cell(cell, status_text):
    """Replace status cell text with clean formatting (white background, black text).
    Only the checkbox symbol (✅/❌) keeps its color."""
    if not cell.paragraphs:
        return
    p = cell.paragraphs[0]
    # Clear ALL existing runs
    for run in p.runs:
        run.text = ""
        # Remove highlight and color from run properties
        rPr = run._element.find(qn('w:rPr'))
        if rPr is not None:
            for highlight in rPr.findall(qn('w:highlight')):
                rPr.remove(highlight)
            for color in rPr.findall(qn('w:color')):
                rPr.remove(color)

    # Set text in first run with clean formatting
    if p.runs:
        p.runs[0].text = str(status_text)
        # Ensure black text, no highlight
        rPr = p.runs[0]._element.find(qn('w:rPr'))
        if rPr is None:
            rPr = p.runs[0]._element.makeelement(qn('w:rPr'), {})
            p.runs[0]._element.insert(0, rPr)
        # Set color to black
        color_elem = rPr.makeelement(qn('w:color'), {qn('w:val'): '000000'})
        rPr.append(color_elem)
    else:
        p.text = str(status_text)

    for extra_p in cell.paragraphs[1:]:
        for run in extra_p.runs:
            run.text = ""


def _replace_serial_number(cell, new_text):
    """Replace serial number in cell, targeting the bold run at the end."""
    if not cell.paragraphs:
        return
    p = cell.paragraphs[0]
    if not p.runs:
        p.text = str(new_text)
        return
    bold_run = None
    for run in reversed(p.runs):
        if run.bold or (run.text and run.text.strip()):
            bold_run = run
            break
    if bold_run:
        bold_run.text = str(new_text)
    else:
        p.runs[-1].text = str(new_text)


def _replace_image_in_docx(doc, rid, new_jpeg_bytes):
    """Replace image blob AND update content type to ensure JPEG compatibility."""
    rel = doc.part.rels.get(rid)
    if not rel or not rel.target_part:
        return False
    rel.target_part._blob = new_jpeg_bytes
    # Ensure content type is JPEG
    if hasattr(rel.target_part, '_content_type'):
        rel.target_part._content_type = 'image/jpeg'
    return True


def _decode_base64_image(img_data):
    """Decode a base64 image string or download from URL. Returns None on failure."""
    if not img_data:
        return None
    try:
        # Handle URL-based images (e.g., from Supabase storage)
        if img_data.startswith(('http://', 'https://')):
            import httpx
            try:
                resp = httpx.get(img_data, timeout=15, follow_redirects=True)
                if resp.status_code == 200 and len(resp.content) > 100:
                    logger.info(f"Downloaded image from URL: {len(resp.content)} bytes")
                    return resp.content
            except Exception as e:
                logger.warning(f"Failed to download image URL: {e}")
            return None
        # Handle base64
        if "," in img_data:
            img_data = img_data.split(",", 1)[1]
        return base64.b64decode(img_data)
    except Exception:
        return None


def _get_month_name(month_num):
    months = {
        "01": "Janeiro", "02": "Fevereiro", "03": "Março",
        "04": "Abril", "05": "Maio", "06": "Junho",
        "07": "Julho", "08": "Agosto", "09": "Setembro",
        "10": "Outubro", "11": "Novembro", "12": "Dezembro"
    }
    return months.get(month_num, "")


def _replace_voltage_textbox(doc, v_f1f2, v_f1_terra, v_f2_terra):
    """Replace voltage values in the VML textbox (Shape 8).
    
    Structure:
      Para 0: 'Leitura de Tensão na Tomada'
      Para 1: 'F1 + F2'
      Para 2: '219V' (Run0=number, Run1='V')
      Para 3: 'F1 + Terra'
      Para 4: '0,0V'
      Para 5: 'F2 + Terra'
      Para 6: '0,0V'
    """
    body = doc.element.body
    shapes = body.findall('.//' + f'{{{VML_NS}}}shape')

    for shape in shapes:
        txbx = shape.find(f'{{{VML_NS}}}textbox')
        if txbx is None:
            continue
        paragraphs = txbx.findall(f'.//{{{W_NS}}}p')
        if len(paragraphs) < 7:
            continue
        # Check if this is the voltage textbox
        first_runs = paragraphs[0].findall(f'.//{{{W_NS}}}r')
        first_text = ''
        for r in first_runs:
            t = r.find(f'{{{W_NS}}}t')
            if t is not None and t.text:
                first_text += t.text
        if 'Tens' not in first_text:
            continue

        # Found the voltage textbox - replace values
        # Para 2: F1+F2 value
        runs_p2 = paragraphs[2].findall(f'.//{{{W_NS}}}r')
        if runs_p2:
            t = runs_p2[0].find(f'{{{W_NS}}}t')
            if t is not None:
                t.text = str(v_f1f2) if v_f1f2 else '0,0'
            if len(runs_p2) > 1:
                t2 = runs_p2[1].find(f'{{{W_NS}}}t')
                if t2 is not None:
                    t2.text = 'V'
            else:
                if t is not None:
                    t.text = f'{v_f1f2 or "0,0"}V'

        # Para 4: F1+Terra value
        runs_p4 = paragraphs[4].findall(f'.//{{{W_NS}}}r')
        if runs_p4:
            t = runs_p4[0].find(f'{{{W_NS}}}t')
            if t is not None:
                t.text = f'{v_f1_terra or "0,0"}V'
            for extra in runs_p4[1:]:
                et = extra.find(f'{{{W_NS}}}t')
                if et is not None:
                    et.text = ''

        # Para 6: F2+Terra value
        runs_p6 = paragraphs[6].findall(f'.//{{{W_NS}}}r')
        if runs_p6:
            t = runs_p6[0].find(f'{{{W_NS}}}t')
            if t is not None:
                t.text = f'{v_f2_terra or "0,0"}V'
            for extra in runs_p6[1:]:
                et = extra.find(f'{{{W_NS}}}t')
                if et is not None:
                    et.text = ''
        return True
    return False


def generate_laudo_from_template(data: dict) -> bytes:
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Template not found at {TEMPLATE_PATH}")

    doc = Document(str(TEMPLATE_PATH))

    def up(val):
        """Uppercase text (all text except technical_diagnosis)."""
        return str(val).upper() if val else ""

    # === TABLE 0: Header Info ===
    table0 = doc.tables[0]
    _replace_cell_text(table0.rows[0].cells[1], up(data.get("os_number", "")))
    _replace_cell_text(table0.rows[1].cells[1], up(data.get("customer_name", "")))
    _replace_cell_text(table0.rows[2].cells[1], up(data.get("model", "")))

    _replace_serial_number(table0.rows[2].cells[3], up(data.get("serial_number", "")))
    _replace_cell_text(table0.rows[3].cells[1], up(data.get("batch", "")))

    brand = data.get("brand", "")
    if brand and "gorenje" in brand.lower():
        _replace_cell_text(table0.rows[3].cells[2], "Produto Gorenje ✓")
        _replace_cell_text(table0.rows[3].cells[5], "Produto Hisense")
    elif brand:
        _replace_cell_text(table0.rows[3].cells[2], "Produto Gorenje")
        _replace_cell_text(table0.rows[3].cells[5], "Produto Hisense ✓")

    # === TABLE 1: Defect info ===
    table1 = doc.tables[1]
    _replace_cell_text(table1.rows[0].cells[1], up(data.get("reported_defect", "")))
    # technical_diagnosis keeps original case
    _replace_cell_text(table1.rows[1].cells[1], data.get("technical_diagnosis", ""))
    _replace_cell_text(table1.rows[2].cells[1], up(data.get("installation_correct", "")))
    _replace_cell_text(table1.rows[3].cells[1], up(data.get("required_parts", "")))

    # === PHOTO AREA: Prepare photo replacements for ZIP-level injection ===
    # Remove brightness/contrast effects from photo blips (they're calibrated for original template images)
    R_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    photo_rids = {'rId7', 'rId8', 'rId9', 'rId10', 'rId11', 'rId12', 'rId13', 'rId14', 'rId15'}
    for blip in doc.element.body.iter(qn('a:blip')):
        rid = blip.get(f'{{{R_NS}}}embed', '')
        if rid in photo_rids:
            for lum in blip.findall(qn('a:lum')):
                blip.remove(lum)

    images_raw = data.get("images", [])
    logger.info(f"LAUDO PHOTOS: Received {len(images_raw)} images")
    for i, img_data in enumerate(images_raw):
        prefix = img_data[:40] if img_data else 'EMPTY'
        length = len(img_data) if img_data else 0
        logger.info(f"  FOTO {i+1}: len={length}, prefix={prefix}")
    
    photo_replacements = {}  # filename -> jpeg_bytes
    for i, zip_filename in PHOTO_SLOTS.items():
        img_data = images_raw[i] if i < len(images_raw) else ""
        decoded = _decode_base64_image(img_data)
        if decoded:
            jpeg_bytes = _to_jpeg_bytes(decoded)
            photo_replacements[zip_filename] = jpeg_bytes
            logger.info(f"  FOTO {i+1} -> {zip_filename}: DECODED {len(jpeg_bytes)} bytes")
        else:
            photo_replacements[zip_filename] = BLANK_JPEG
            logger.info(f"  FOTO {i+1} -> {zip_filename}: BLANK (decode failed or empty)")

    # Blank out the extra image slot so it doesn't show the original template photo
    if any(v != BLANK_JPEG for v in photo_replacements.values()):
        photo_replacements[EXTRA_IMAGE_SLOT] = BLANK_JPEG
        logger.info(f"  EXTRA -> {EXTRA_IMAGE_SLOT}: BLANKED")

    # === VOLTAGE: Replace values in VML textbox ===
    _replace_voltage_textbox(
        doc,
        data.get("voltage_f1f2", ""),
        data.get("voltage_f1_terra", ""),
        data.get("voltage_f2_terra", "")
    )

    # === TABLE 2: Notes ===
    table2 = doc.tables[2]

    # Row 0: "Diagnóstico técnico:" prefix must always appear
    cell_notes = table2.rows[0].cells[0]
    if cell_notes.paragraphs and cell_notes.paragraphs[0].runs:
        runs = cell_notes.paragraphs[0].runs
        technical_notes = data.get("technical_notes", "")
        if len(runs) >= 3:
            runs[0].text = "Diagnóstico técnico"
            runs[1].text = ":"
            runs[2].text = f"  {technical_notes}"
            for run in runs[3:]:
                run.text = ""
        elif len(runs) >= 1:
            runs[0].text = f"Diagnóstico técnico:  {technical_notes}"
            for run in runs[1:]:
                run.text = ""
    else:
        _replace_cell_text(cell_notes, f"Diagnóstico técnico:  {data.get('technical_notes', '')}")

    # Row 1: Status - clean formatting (white bg, black text)
    final_status = data.get("final_status", "")
    _replace_status_cell(table2.rows[1].cells[0], final_status)

    # === FOOTER ===
    location = up(data.get("location", ""))
    date_str = data.get("date", "")
    technician = up(data.get("technician", ""))

    day, month_num, year = "", "", ""
    if "/" in date_str:
        parts = date_str.split("/")
        if len(parts) >= 3:
            day, month_num, year = parts[0], parts[1], parts[2]
    month_name = _get_month_name(month_num)

    p16 = doc.paragraphs[16]
    if day and month_num and year and location:
        for run in p16.runs:
            if "BELO HORIZONTE" in run.text:
                run.text = run.text.replace("BELO HORIZONTE", location)
            if ", 25 " in run.text:
                run.text = run.text.replace("25 ", f"{day} ")
            if "Agosto" in run.text:
                run.text = run.text.replace("Agosto", month_name)
            if "de 20" in run.text:
                run.text = f"de {year[:2]}"
            if run.text == "25":
                run.text = year[2:] if len(year) > 2 else year
            if "Data de emissão do Laudo: 27" in run.text:
                run.text = run.text.replace("27", day)
            if "/08" in run.text:
                run.text = f"/{month_num}"
            if "/2025" in run.text:
                run.text = f"/{year}"

    p17 = doc.paragraphs[17]
    for run in p17.runs:
        if "Nelson Rodrigues" in run.text:
            run.text = run.text.replace("Nelson Rodrigues", technician)
            break

    # Save document to buffer first (text/voltage/status changes)
    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    # Now replace photo images at ZIP level (most reliable approach)
    if any(v != BLANK_JPEG for v in photo_replacements.values()):
        src_zip = zipfile.ZipFile(buffer, 'r')
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as zout:
            for item in src_zip.namelist():
                file_data = src_zip.read(item)
                if item in photo_replacements:
                    file_data = photo_replacements[item]
                zout.writestr(item, file_data)
        src_zip.close()
        output.seek(0)
        return output.getvalue()

    buffer.seek(0)
    return buffer.getvalue()



def generate_recall_laudo(data: dict) -> bytes:
    """Generate a Recall inspection laudo DOCX programmatically."""
    from docx.shared import Inches, Pt, Cm, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT
    import httpx

    doc = Document()
    
    # Set margins
    for section in doc.sections:
        section.top_margin = Cm(1.5)
        section.bottom_margin = Cm(1.5)
        section.left_margin = Cm(2)
        section.right_margin = Cm(2)

    # Title
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run("Laudo Técnico de Inspeção - Recall")
    run.bold = True
    run.font.size = Pt(16)
    run.font.color.rgb = RGBColor(0x1a, 0x27, 0x44)

    # Subtitle
    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run2 = sub.add_run("ASSISTÊNCIA TÉC. MASTERMAQ")
    run2.bold = True
    run2.font.size = Pt(10)
    run2.font.color.rgb = RGBColor(0x66, 0x66, 0x66)

    # Info table
    table = doc.add_table(rows=4, cols=4)
    table.style = 'Table Grid'
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    cells_data = [
        ("NÚMERO OS", data.get("os_number", ""), "ASSISTÊNCIA TÉCNICA", "MASTERMAQ"),
        ("NOME DO CLIENTE", data.get("customer_name", ""), "", ""),
        ("MODELO DO PROD.", data.get("model", ""), "Nº DE SERIE", data.get("serial_number", "")),
        ("ART ou Batch", data.get("batch", ""), "", ""),
    ]

    for row_idx, (l1, v1, l2, v2) in enumerate(cells_data):
        row = table.rows[row_idx]
        c0 = row.cells[0]
        c0.text = l1
        for p in c0.paragraphs:
            for r in p.runs:
                r.bold = True
                r.font.size = Pt(9)
        c1 = row.cells[1]
        c1.text = v1
        for p in c1.paragraphs:
            for r in p.runs:
                r.font.size = Pt(9)
        if l2:
            c2 = row.cells[2]
            c2.text = l2
            for p in c2.paragraphs:
                for r in p.runs:
                    r.bold = True
                    r.font.size = Pt(9)
            c3 = row.cells[3]
            c3.text = v2
            for p in c3.paragraphs:
                for r in p.runs:
                    r.font.size = Pt(9)
        else:
            row.cells[1].merge(row.cells[2]).merge(row.cells[3])

    doc.add_paragraph()  # spacing

    # Photo labels for recall
    recall_labels = data.get("photo_labels", [
        "FOTO 1 – Imagem geral do local onde o produto foi instalado",
        "FOTO 2 – Lateral esquerda do produto",
        "FOTO 3 – Lateral direita do produto",
        "FOTO 4 – Topo do produto",
        "FOTO 5 – Etiqueta do produto com Batch e nº de série",
        "FOTO 6 – Foto geral do interior do produto",
        "FOTO 7 – Foto do cordão de solda do cesto",
    ])

    images = data.get("images", [])

    # Add photos in pairs
    for i in range(0, len(recall_labels), 2):
        # Add label for left photo
        p = doc.add_paragraph()
        run = p.add_run(recall_labels[i])
        run.bold = True
        run.font.size = Pt(9)
        run.font.color.rgb = RGBColor(0xC0, 0x39, 0x2B)

        # Add image
        if i < len(images) and images[i]:
            try:
                img_data = images[i]
                if img_data.startswith('data:'):
                    img_data = img_data.split(',', 1)[1]
                    img_bytes = base64.b64decode(img_data)
                elif img_data.startswith('http'):
                    resp = httpx.get(img_data, timeout=15)
                    img_bytes = resp.content
                else:
                    img_bytes = base64.b64decode(img_data)
                img_io = io.BytesIO(img_bytes)
                doc.add_picture(img_io, width=Inches(3.5))
                last_p = doc.paragraphs[-1]
                last_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            except Exception as e:
                logger.warning(f"Failed to add recall photo {i}: {e}")
                doc.add_paragraph("[Foto não disponível]")

        # Add right photo if exists
        if i + 1 < len(recall_labels):
            p2 = doc.add_paragraph()
            run2 = p2.add_run(recall_labels[i + 1])
            run2.bold = True
            run2.font.size = Pt(9)
            run2.font.color.rgb = RGBColor(0xC0, 0x39, 0x2B)

            if i + 1 < len(images) and images[i + 1]:
                try:
                    img_data = images[i + 1]
                    if img_data.startswith('data:'):
                        img_data = img_data.split(',', 1)[1]
                        img_bytes = base64.b64decode(img_data)
                    elif img_data.startswith('http'):
                        resp = httpx.get(img_data, timeout=15)
                        img_bytes = resp.content
                    else:
                        img_bytes = base64.b64decode(img_data)
                    img_io = io.BytesIO(img_bytes)
                    doc.add_picture(img_io, width=Inches(3.5))
                    last_p = doc.paragraphs[-1]
                    last_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                except Exception as e:
                    logger.warning(f"Failed to add recall photo {i+1}: {e}")
                    doc.add_paragraph("[Foto não disponível]")

    doc.add_paragraph()  # spacing

    # Technical notes section
    notes_header = doc.add_paragraph()
    run = notes_header.add_run("Anotações Técnicas:")
    run.bold = True
    run.font.size = Pt(11)

    notes_p = doc.add_paragraph()
    run = notes_p.add_run("Diagnóstico técnico: ")
    run.bold = True
    run.font.size = Pt(10)
    run2 = notes_p.add_run(data.get("technical_notes", ""))
    run2.font.size = Pt(10)

    # Status
    status = data.get("final_status", "")
    if status:
        status_p = doc.add_paragraph()
        status_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = status_p.add_run(status)
        run.bold = True
        run.font.size = Pt(11)

    doc.add_paragraph()  # spacing

    # Location and date
    location = data.get("location", "BELO HORIZONTE")
    date_str = data.get("date", "")
    
    loc_p = doc.add_paragraph()
    loc_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = loc_p.add_run(f"{location}, {date_str}")
    run.font.size = Pt(10)

    emission_p = doc.add_paragraph()
    emission_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    from datetime import datetime as dt
    now = dt.now()
    run = emission_p.add_run(f"Data de emissão do Laudo: {now.strftime('%d/%m/%Y')}")
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)

    doc.add_paragraph()  # spacing

    # Technician signature
    tech_p = doc.add_paragraph()
    tech_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = tech_p.add_run("_" * 40)
    run.font.size = Pt(10)

    name_p = doc.add_paragraph()
    name_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = name_p.add_run(data.get("technician", ""))
    run.bold = True
    run.font.size = Pt(11)

    role_p = doc.add_paragraph()
    role_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = role_p.add_run("Técnico Responsável")
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)

    # Save to buffer
    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()
