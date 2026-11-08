"""Laudo Mastermaq digital (PDF) — layout moderno: fundo branco, texto preto, acentos azul/vermelho."""
import asyncio
import io
import os
import uuid
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from laudo_generator import _decode_base64_image, _to_jpeg_bytes

BLUE = colors.HexColor("#1a3a8f")
RED = colors.HexColor("#c8102e")
LINE = colors.HexColor("#d9dde6")
SOFT = colors.HexColor("#f6f7fa")
LOGO = Path(__file__).parent / "assets" / "mastermaq-logo.png"
PHOTO_LABELS = [
    "Instalação do Produto", "Instalação do Produto", "Local onde o Produto está Instalado", "Instalação Elétrica",
    "Nº de Série", "Peça Avariada", "Defeito/Erro Encontrado", "Defeito/Erro Encontrado",
]
COMPANY = ("<b>MASTERMAQ ASSISTÊNCIA TÉCNICA</b><br/>Conserto de Geladeiras e Eletrodomésticos Belo Horizonte – MG<br/>"
           "CNPJ: 19955560/0001-28<br/>Telefone: 31 3422-5293 / 31 2526-8420")


def _s(size=9, bold=False, align=0, leading=None):
    return ParagraphStyle("x", fontName="Helvetica-Bold" if bold else "Helvetica", fontSize=size,
                          leading=leading or size * 1.35, textColor=colors.black, alignment=align)


def _p(text, **kw):
    return Paragraph(escape(str(text or "—")).replace("\n", "<br/>"), _s(**kw))


def _field(label, value):
    return [Paragraph(label.upper(), _s(6.5, bold=True)), Spacer(1, 1.2 * mm), _p(value, size=9.5)]


def _card(rows, widths, pad=3.2 * mm):
    t = Table(rows, colWidths=widths)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), SOFT), ("ROUNDEDCORNERS", [2.5 * mm] * 4),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), pad), ("RIGHTPADDING", (0, 0), (-1, -1), pad),
        ("TOPPADDING", (0, 0), (-1, -1), 2.6 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.6 * mm),
    ]))
    return t


def _section(title, W):
    t = Table([["", Paragraph(title.upper(), _s(8.5, bold=True))]], colWidths=[1.4 * mm, W - 1.4 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, 0), BLUE), ("LEFTPADDING", (1, 0), (1, 0), 2.5 * mm),
                           ("TOPPADDING", (0, 0), (-1, -1), 0.6 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 0.6 * mm),
                           ("LEFTPADDING", (0, 0), (0, 0), 0), ("RIGHTPADDING", (0, 0), (0, 0), 0)]))
    return [Spacer(1, 4.5 * mm), t, Spacer(1, 2.2 * mm)]


def _photo(raw, w, h):
    data = _decode_base64_image(raw) if raw else None
    if not data:
        return Paragraph("Sem foto", _s(8, align=1))
    img = Image(io.BytesIO(_to_jpeg_bytes(data)))
    r = min(w / img.imageWidth, h / img.imageHeight)
    img.drawWidth, img.drawHeight = img.imageWidth * r, img.imageHeight * r
    return img


def _photo_card(i, raw, w):
    num = Table([[Paragraph(f"<font color='white'><b>{i + 1}</b></font>", _s(7.5, align=1))]], colWidths=[5 * mm], rowHeights=[5 * mm])
    num.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), RED), ("ROUNDEDCORNERS", [2.5 * mm] * 4),
                             ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    head = Table([[num, Paragraph(PHOTO_LABELS[i], _s(8, bold=True))]], colWidths=[7 * mm, w - 13 * mm])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    t = Table([[head], [_photo(raw, w - 8 * mm, 41 * mm)]], colWidths=[w], rowHeights=[8 * mm, 45 * mm])
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, LINE), ("ROUNDEDCORNERS", [2.5 * mm] * 4),
                           ("ALIGN", (0, 1), (0, 1), "CENTER"), ("VALIGN", (0, 1), (0, 1), "MIDDLE"),
                           ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm)]))
    return t


def build_pdf(d: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=12 * mm, bottomMargin=12 * mm,
                            title=f"Laudo Mastermaq OS {d.get('os_number', '')}")
    W = doc.width
    logo = Image(str(LOGO), width=40 * mm, height=40 * mm * 329 / 669)
    head = Table([[logo, Paragraph(COMPANY, _s(8.5, align=2, leading=12))]], colWidths=[50 * mm, W - 50 * mm])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    accent = Table([["", ""]], colWidths=[W * 0.72, W * 0.28], rowHeights=[1.6 * mm])
    accent.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, 0), BLUE), ("BACKGROUND", (1, 0), (1, 0), RED)]))
    chip = Table([[Paragraph(f"<font color='white'><b>OS {escape(str(d.get('os_number') or ''))}</b></font>", _s(10, align=1))]],
                 colWidths=[42 * mm])
    chip.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), BLUE), ("ROUNDEDCORNERS", [3 * mm] * 4),
                              ("TOPPADDING", (0, 0), (-1, -1), 2 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 2 * mm)]))
    title = Table([[Paragraph("Relatório de Atendimento ao Cliente", _s(15, bold=True, leading=18)), chip]],
                  colWidths=[W - 44 * mm, 44 * mm])
    title.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                               ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    h = W / 2
    info = _card([
        [_field("Cliente", d.get("customer_name")), _field("Assistência técnica", "Mastermaq")],
        [_field("Modelo do produto", d.get("model")), _field("Nº de série", d.get("serial_number"))],
        [_field("Marca", d.get("brand")), _field("Tipo de atendimento", d.get("service_type"))],
    ], [h, h])
    diag = _card([
        [_field("Defeito relatado pelo cliente", d.get("reported_defect"))],
        [_field("Diagnóstico técnico", d.get("technical_diagnosis"))],
        [_field("Instalação correta?", d.get("installation_correct"))],
        [_field("Peças necessárias para reparo", d.get("required_parts"))],
    ], [W])
    imgs = list(d.get("images") or []) + [""] * 8
    cw = (W - 4 * mm) / 2
    rows = [[_photo_card(i, imgs[i], cw), _photo_card(i + 1, imgs[i + 1], cw)] for i in range(0, 8, 2)]
    photos = Table(rows, colWidths=[cw + 2 * mm, cw + 2 * mm])
    photos.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 3 * mm),
                                ("ALIGN", (1, 0), (1, -1), "RIGHT")]))
    v = lambda k: f"{d.get(k)} V" if d.get(k) else "—"  # noqa: E731
    third = W / 3
    volt = _card([[_field("F1 + F2", v("voltage_f1f2")), _field("F1 + Terra", v("voltage_f1_terra")), _field("F2 + Terra", v("voltage_f2_terra"))]],
                 [third, third, third])
    obs_txt = "\n".join(x for x in (d.get("technical_notes"), d.get("final_status")) if x)
    obs = _card([[[Paragraph("Observações técnicas", _s(9.5, bold=True)), Spacer(1, 1.5 * mm), _p(obs_txt or "—", size=9.5)]]], [W])
    when = d.get("date") or datetime.now().strftime("%d/%m/%Y")
    sig = Table([[_p(f"{d.get('location') or 'BELO HORIZONTE'}, {when}", size=9, align=1)], [Spacer(1, 14 * mm)],
                 [_p(d.get("technician"), size=9.5, bold=True, align=1)], [_p("Técnico responsável", size=8, align=1)]],
                colWidths=[80 * mm])
    sig.setStyle(TableStyle([("LINEABOVE", (0, 2), (0, 2), 0.8, colors.black), ("ALIGN", (0, 0), (-1, -1), "CENTER")]))
    foot = Table([[sig]], colWidths=[W])
    foot.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER")]))
    issued = _p(f"Laudo emitido digitalmente em {datetime.now().strftime('%d/%m/%Y')} · Mastermaq Assistência Técnica", size=7, align=1)
    story = [head, Spacer(1, 3 * mm), accent, Spacer(1, 5 * mm), title,
             *_section("Dados do atendimento", W), info,
             *_section("Diagnóstico", W), diag,
             *_section("Registro fotográfico", W), photos,
             KeepTogether([*_section("Tensão de alimentação do produto", W), volt]),
             Spacer(1, 4.5 * mm), obs,
             KeepTogether([Spacer(1, 8 * mm), foot, Spacer(1, 5 * mm), issued])]
    doc.build(story)
    return buf.getvalue()


async def create(d: dict) -> dict:
    """Gera o PDF e guarda no storage permanente. Devolve link público."""
    from manuais_module import put_object
    token = uuid.uuid4().hex
    pdf = await asyncio.to_thread(build_pdf, d)
    await asyncio.to_thread(put_object, f"mastermaq-manuais/shared-pdfs/{token}.pdf", pdf, "application/pdf")
    path = f"/api/files/temp-pdf/{token}"
    return {"path": path, "url": f"{os.environ.get('PUBLIC_BACKEND_URL') or ''}{path}"}
