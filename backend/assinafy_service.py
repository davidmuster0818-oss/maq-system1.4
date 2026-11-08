"""
Assinafy Digital Signature Service
Handles PDF generation and Assinafy API integration for OS signing
"""
import os
import io
import base64
import logging
import httpx
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.lib.utils import ImageReader

logger = logging.getLogger(__name__)

ASSINAFY_API_URL = os.environ.get("ASSINAFY_API_URL", "https://api.assinafy.com.br/v1")
ASSINAFY_API_KEY = os.environ.get("ASSINAFY_API_KEY", "")
ASSINAFY_WORKSPACE_ID = os.environ.get("ASSINAFY_WORKSPACE_ID", "")


def generate_os_pdf(order: dict, sig_tech_b64: str = None, sig_client_b64: str = None) -> bytes:
    """Generate a PDF of the OS with optional signatures"""
    buf = io.BytesIO()
    c = pdf_canvas.Canvas(buf, pagesize=A4)
    w, h = A4

    # Header
    c.setFont("Helvetica-Bold", 16)
    c.drawString(20 * mm, h - 20 * mm, f"Ordem de Servico - {order.get('os_number', '')}")

    c.setFont("Helvetica", 10)
    y = h - 35 * mm

    fields = [
        ("Cliente", order.get("customer_name", "")),
        ("Data Cadastro", order.get("registration_date", "")),
        ("Data Atendimento", order.get("attendance_date", "")),
        ("Endereco", f"{order.get('address', '')}, {order.get('number', '')} - {order.get('neighborhood', '')}"),
        ("Cidade/UF", f"{order.get('city', '')} / {order.get('state', '')}"),
        ("Telefone", order.get("phone1", "")),
        ("Tipo Atendimento", order.get("service_type", "")),
        ("Produto", order.get("product", "")),
        ("Marca", order.get("brand", "")),
        ("Modelo", order.get("model", "")),
        ("N. Serie", order.get("serial_number", "")),
        ("Defeito Relatado", order.get("reported_defect", "")),
        ("Diagnostico Tecnico", order.get("technical_diagnosis", "")),
        ("Pecas Necessarias", order.get("required_parts", "")),
        ("Instalacao Correta", order.get("installation_correct", "")),
        ("Tecnico", order.get("technician", "")),
        ("Observacoes", order.get("observations", "")),
        ("Status", order.get("status", "")),
    ]

    for label, value in fields:
        if y < 60 * mm:
            c.showPage()
            c.setFont("Helvetica", 10)
            y = h - 20 * mm
        c.setFont("Helvetica-Bold", 9)
        c.drawString(20 * mm, y, f"{label}:")
        c.setFont("Helvetica", 9)
        text = str(value or "")[:80]
        c.drawString(65 * mm, y, text)
        y -= 6 * mm

    # Signatures section
    y -= 10 * mm
    if y < 80 * mm:
        c.showPage()
        y = h - 20 * mm

    c.setFont("Helvetica-Bold", 12)
    c.drawString(20 * mm, y, "Assinaturas")
    y -= 8 * mm

    # Technician signature
    c.setFont("Helvetica-Bold", 10)
    c.drawString(20 * mm, y, "Tecnico:")
    y -= 2 * mm
    if sig_tech_b64:
        try:
            img_data = base64.b64decode(sig_tech_b64.split(",")[-1] if "," in sig_tech_b64 else sig_tech_b64)
            img = ImageReader(io.BytesIO(img_data))
            c.drawImage(img, 20 * mm, y - 25 * mm, width=70 * mm, height=25 * mm, preserveAspectRatio=True)
        except Exception as e:
            logger.error(f"Error drawing tech signature: {e}")
    y -= 30 * mm

    c.line(20 * mm, y, 100 * mm, y)
    c.setFont("Helvetica", 8)
    c.drawString(20 * mm, y - 4 * mm, order.get("technician", "Tecnico Responsavel"))

    # Client signature
    y -= 15 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(20 * mm, y, "Cliente:")
    y -= 2 * mm
    if sig_client_b64:
        try:
            img_data = base64.b64decode(sig_client_b64.split(",")[-1] if "," in sig_client_b64 else sig_client_b64)
            img = ImageReader(io.BytesIO(img_data))
            c.drawImage(img, 20 * mm, y - 25 * mm, width=70 * mm, height=25 * mm, preserveAspectRatio=True)
        except Exception as e:
            logger.error(f"Error drawing client signature: {e}")
    y -= 30 * mm

    c.line(20 * mm, y, 100 * mm, y)
    c.setFont("Helvetica", 8)
    c.drawString(20 * mm, y - 4 * mm, order.get("customer_name", "Cliente"))

    c.save()
    return buf.getvalue()


async def upload_document_to_assinafy(pdf_bytes: bytes, filename: str) -> dict:
    """Upload a PDF document to Assinafy and return the document data"""
    url = f"{ASSINAFY_API_URL}/accounts/{ASSINAFY_WORKSPACE_ID}/documents"
    headers = {"X-Api-Key": ASSINAFY_API_KEY}

    async with httpx.AsyncClient(timeout=30) as client:
        files = {"file": (filename, pdf_bytes, "application/pdf")}
        resp = await client.post(url, headers=headers, files=files)
        data = resp.json()
        logger.info(f"Assinafy upload response status: {data.get('status')}")
        if resp.status_code != 200 and data.get("status") != 200:
            raise Exception(f"Assinafy upload failed: {data.get('message', resp.text)}")
        return data.get("data", data)


async def create_signer(full_name: str, email: str = None) -> dict:
    """Create a signer in Assinafy"""
    url = f"{ASSINAFY_API_URL}/accounts/{ASSINAFY_WORKSPACE_ID}/signers"
    headers = {"X-Api-Key": ASSINAFY_API_KEY, "Content-Type": "application/json"}
    body = {"full_name": full_name}
    if email:
        body["email"] = email

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, headers=headers, json=body)
        data = resp.json()
        logger.info(f"Assinafy create signer response: {data.get('status')}")
        if resp.status_code != 200 and data.get("status") != 200:
            raise Exception(f"Assinafy create signer failed: {data.get('message', resp.text)}")
        return data.get("data", data)


async def create_assignment(document_id: str, signer_ids: list) -> dict:
    """Create a virtual assignment for the document"""
    url = f"{ASSINAFY_API_URL}/documents/{document_id}/assignments"
    headers = {"X-Api-Key": ASSINAFY_API_KEY, "Content-Type": "application/json"}
    body = {
        "method": "virtual",
        "signers": [{"id": sid} for sid in signer_ids]
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, headers=headers, json=body)
        data = resp.json()
        logger.info(f"Assinafy assignment response: {data.get('status')}")
        if resp.status_code != 200 and data.get("status") != 200:
            raise Exception(f"Assinafy assignment failed: {data.get('message', resp.text)}")
        return data.get("data", data)


async def get_document_status(document_id: str) -> dict:
    """Get document status from Assinafy"""
    url = f"{ASSINAFY_API_URL}/documents/{document_id}"
    headers = {"X-Api-Key": ASSINAFY_API_KEY}

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers=headers)
        data = resp.json()
        return data.get("data", data)
