"""
Mastermaq Laudo Generator — separate template for non-Hisense/HQ brands.

Distinguishing features vs. the Hisense generator (`laudo_generator.py`):
  * No serial_number, batch, installation_correct
  * No voltage (F1F2, F1_Terra, F2_Terra)
  * No technical_notes, final_status

Photo mapping (empirically derived from XML analysis, 21/07/2026):
  The template ships with FOUR labeled photo slots but only THREE unique image
  files — rId7 (image1) is embedded TWICE, so "FOTO 1" and "FOTO 2" of the
  template rendered the same image. To place four DISTINCT photos, this
  generator patches the document.xml at generation time so the second
  occurrence of rId7 becomes rId200, then injects a new relationship pointing
  to a new "image_foto2.jpeg" file.

  Mapping from the LaudoModal 8-photo grid → Mastermaq template slots:
    Template FOTO 1 (Instalação do Produto)     ← images[0]  (modal FOTO 1)
    Template FOTO 2 (Instalação do Produto)     ← images[1]  (modal FOTO 2)
    Template FOTO 3 (Defeito/Erro Encontrado)   ← images[6]  (modal FOTO 7, "Defeito/Erro")
    Template FOTO 4 (Instalação Elétrica)       ← images[3]  (modal FOTO 4, "Instalação Elétrica")

  Labels of modal and template are aligned semantically so techs upload once
  and both laudos (Hisense + Mastermaq) render correctly without rearranging.

Replacement is done at the run level of python-docx so the template's
paragraph alignment, font family, font size, bold/italic and color are
preserved on every cell we touch — nothing is rebuilt from scratch.
"""
from pathlib import Path
import io
import logging
import zipfile

from docx import Document
from docx.oxml.ns import qn  # noqa: F401  (kept for future needs)

from laudo_generator import (
    _decode_base64_image,
    _to_jpeg_bytes,
)

logger = logging.getLogger(__name__)

TEMPLATE_PATH = Path(__file__).parent / "templates" / "laudo_mastermaq_template.docx"

# LaudoModal grid index → template slot mapping. Indices reference `images`
# in the LaudoModal payload (0-based: images[0] is modal "FOTO 1").
#
# Ordered so the SAME order is used both by the media-file writer AND by the
# XML/rels patcher below — index 0 goes to image1.jpeg (via rId7), index 1
# goes to the NEW image_foto2.jpeg (via rId200), etc.
SLOT_MAP = [
    # (modal_photo_index, target_filename_in_zip, target_rid)
    # NOTE: In the template document.xml the FIRST occurrence of
    # `r:embed="rId7"` renders in the RIGHT column (visual "FOTO 2"),
    # and the SECOND occurrence renders in the LEFT column
    # (visual "FOTO 1"). We patch the SECOND occurrence to rId200, so:
    #   rId7   -> right slot (FOTO 2) -> images[1]  (modal FOTO 2)
    #   rId200 -> left slot  (FOTO 1) -> images[0]  (modal FOTO 1)
    (1, "word/media/image1.jpeg",       "rId7"),    # Template FOTO 2 (right)
    (0, "word/media/image_foto2.jpeg",  "rId200"),  # Template FOTO 1 (left)  [NEW rId]
    (6, "word/media/image2.jpeg",       "rId8"),    # Template FOTO 3 (Defeito/Erro ← modal FOTO 7)
    (3, "word/media/image3.jpeg",       "rId9"),    # Template FOTO 4 (Elétrica ← modal FOTO 4)
]

# Legacy alias kept for any external caller that still references the previous
# single-slot behaviour. Not used inside this module anymore.
DEFECT_PHOTO_INDEX = 6

PHOTO_SLOTS = [entry[1] for entry in SLOT_MAP]  # noqa: F841 (external readers)


def _set_cell_text_preserving_runs(cell, new_text: str) -> None:
    """
    Replace the visible text of a table cell while keeping every run's
    formatting intact.

    Strategy:
      * Pick the most representative run (longest non-whitespace text) as the
        "carrier" — its font/color/size/bold/italic properties are what the
        user actually sees for the field.
      * Write the new text into that carrier run.
      * Empty every other run's text (so their formatting still lives on the
        paragraph but they contribute nothing visible).
      * Drop extra paragraphs beyond the first inside the cell (Word often
        adds a trailing empty paragraph that inflates row height).

    Drawings (anchored images) that live inside runs are preserved by moving
    them out before we touch text and re-attaching them afterwards.
    """
    if not cell.paragraphs:
        return

    W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    new_text = "" if new_text is None else str(new_text)

    first_p = cell.paragraphs[0]

    # Preserve any drawings living inside the runs of the first paragraph.
    saved_drawings = []
    for r_elem in first_p._element.findall(f"{{{W}}}r"):
        for drawing in list(r_elem.findall(f"{{{W}}}drawing")):
            saved_drawings.append(drawing)
            r_elem.remove(drawing)

    runs = first_p.runs
    if not runs:
        # No runs to work with — fall back to a plain text assignment which
        # will create a single default-styled run.
        first_p.text = new_text
    else:
        # Pick the run with the longest stripped text as the carrier — it's
        # the visible one the user cares about. Whitespace-only leading runs
        # (very common in Word templates) are ignored.
        carrier = max(runs, key=lambda r: len(r.text.strip()))
        if not carrier.text.strip():
            # Every run is whitespace-only — just use the first run.
            carrier = runs[0]

        for r in runs:
            r.text = "" if r is not carrier else new_text

    # Clear text of every subsequent paragraph inside the cell — the cell
    # keeps its structure but only the first paragraph shows the new value.
    for extra_p in cell.paragraphs[1:]:
        for r in extra_p.runs:
            r.text = ""

    # Re-attach any drawings we pulled off.
    for drawing in saved_drawings:
        new_r = first_p._element.makeelement(f"{{{W}}}r", {})
        new_r.append(drawing)
        first_p._element.append(new_r)


def _up(v) -> str:
    return str(v).upper() if v else ""


def generate_mastermaq_laudo(data: dict) -> bytes:
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Mastermaq template not found at {TEMPLATE_PATH}")

    doc = Document(str(TEMPLATE_PATH))

    # === TABLE 0: Header ================================================
    # Row layout of the template:
    #   [NÚMERO DA OS] [<os_number>] [ASSISTÊNCIA TÉC.] [ASSISTÊNCIA TÉC.] [MASTERMAQ ...]
    #   [NOME DO CLIENTE] [<customer_name>] [...] [...] [...]
    #   [PRODUTO] [<product>] [MARCA] [<brand>] [<brand>]
    table0 = doc.tables[0]
    _set_cell_text_preserving_runs(table0.rows[0].cells[1], _up(data.get("os_number", "")))
    _set_cell_text_preserving_runs(table0.rows[1].cells[1], _up(data.get("customer_name", "")))

    product_val = data.get("product") or data.get("model") or ""
    _set_cell_text_preserving_runs(table0.rows[2].cells[1], _up(product_val))

    brand_val = _up(data.get("brand", ""))
    # Fill both brand cells (col 3 and 4) so the layout stays symmetric.
    _set_cell_text_preserving_runs(table0.rows[2].cells[3], brand_val)
    _set_cell_text_preserving_runs(table0.rows[2].cells[4], brand_val)

    # === TABLE 1: Defect + Diagnosis + Required parts ===================
    # ONLY these three fields — no serial_number, batch, installation_correct,
    # voltage or technical_notes (those are Hisense-only concepts).
    table1 = doc.tables[1]
    _set_cell_text_preserving_runs(table1.rows[0].cells[1], _up(data.get("reported_defect", "")))
    # technical_diagnosis keeps original case (long-form text).
    _set_cell_text_preserving_runs(table1.rows[1].cells[1], data.get("technical_diagnosis", ""))
    _set_cell_text_preserving_runs(table1.rows[2].cells[1], _up(data.get("required_parts", "")))

    # === Photos — 4 distinct slots =====================================
    # See SLOT_MAP at the top of this file. The template ships with rId7
    # embedded twice (image1 duplicated), so before we swap bytes we also
    # need to patch document.xml so the second rId7 becomes rId200 and
    # add a new relationship rId200 -> media/image_foto2.jpeg. Without
    # that patch, template FOTO 1 and FOTO 2 would keep rendering the
    # same image no matter what we do at the ZIP level.
    images_raw = data.get("images") or []
    photo_replacements: dict = {}  # zip filename -> jpeg bytes to inject
    new_rels: list = []            # (rId, target) tuples to append to rels
    filled_slots = 0
    for modal_idx, target_fname, target_rid in SLOT_MAP:
        raw = images_raw[modal_idx] if modal_idx < len(images_raw) else ""
        decoded = _decode_base64_image(raw)
        if not decoded:
            continue
        processed = _to_jpeg_bytes(decoded)
        photo_replacements[target_fname] = processed
        # For the NEW rId (rId200, mapped to image_foto2.jpeg), we also
        # need a relationship pointing to it — the template doesn't have
        # one yet.
        if target_rid == "rId200":
            new_rels.append((target_rid, "media/image_foto2.jpeg"))
        filled_slots += 1
    logger.info(
        "MASTERMAQ LAUDO: %d/%d photo slots filled from modal grid",
        filled_slots, len(SLOT_MAP),
    )

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)

    if not photo_replacements:
        return buf.getvalue()

    # Rewrite the DOCX zip:
    #  1. Patch document.xml: turn the SECOND occurrence of `r:embed="rId7"`
    #     into `r:embed="rId200"` (only if we're actually providing a distinct
    #     FOTO 2). The FIRST occurrence stays as rId7 -> image1.jpeg.
    #  2. Patch word/_rels/document.xml.rels: append the new relationship
    #     for rId200 (if used).
    #  3. Swap the media/imageN.jpeg files in `photo_replacements`.
    #  4. Add media/image_foto2.jpeg as a new file (if used).
    need_rid200 = any(rid == "rId200" for rid, _ in new_rels)
    src = zipfile.ZipFile(buf, "r")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in src.namelist():
            data_bytes = src.read(item)

            if item == "word/document.xml" and need_rid200:
                # Only rewrite the SECOND occurrence of r:embed="rId7".
                xml = data_bytes.decode("utf-8")
                first = xml.find('r:embed="rId7"')
                if first != -1:
                    second = xml.find('r:embed="rId7"', first + 1)
                    if second != -1:
                        xml = (
                            xml[:second]
                            + 'r:embed="rId200"'
                            + xml[second + len('r:embed="rId7"'):]
                        )
                        logger.info(
                            "MASTERMAQ LAUDO: patched 2nd rId7 -> rId200 (offset %d)",
                            second,
                        )
                data_bytes = xml.encode("utf-8")

            elif item == "word/_rels/document.xml.rels" and new_rels:
                rels_xml = data_bytes.decode("utf-8")
                # Insert new <Relationship .../> before the closing tag.
                additions = "".join(
                    f'<Relationship Id="{rid}" '
                    f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
                    f'Target="{target}"/>'
                    for rid, target in new_rels
                )
                rels_xml = rels_xml.replace("</Relationships>", additions + "</Relationships>")
                data_bytes = rels_xml.encode("utf-8")

            elif item in photo_replacements:
                data_bytes = photo_replacements[item]

            zout.writestr(item, data_bytes)

        # Add brand-new media file (image_foto2.jpeg) if the template
        # didn't already have it. This only fires when SLOT_MAP entry for
        # modal FOTO 2 actually had bytes.
        new_media = "word/media/image_foto2.jpeg"
        if new_media in photo_replacements and new_media not in src.namelist():
            zout.writestr(new_media, photo_replacements[new_media])

    src.close()
    out.seek(0)
    return out.getvalue()
