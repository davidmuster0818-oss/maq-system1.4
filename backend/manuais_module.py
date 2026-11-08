"""
Manuais Module - File management for technical manuals
Upload, organize by brand/category, serve PDF/DOCX/PPTX files
"""
import os
import uuid
import requests
import logging
import subprocess
import shutil
import tempfile
import asyncio
from datetime import datetime, timezone
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Response, Header, Query, Depends
from typing import Optional, List

logger = logging.getLogger(__name__)

STORAGE_URL = "https://integrations.emergentagent.com/objstore/api/v1/storage"
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY")
APP_NAME = "mastermaq-manuais"
storage_key = None

ALLOWED_EXTENSIONS = {"pdf", "docx", "pptx", "ppt"}
ALLOWED_CONTENT_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "ppt": "application/vnd.ms-powerpoint",
}
MAX_FILE_SIZE = 80 * 1024 * 1024  # 80MB (pptx with images can be large)

# SOFFICE_BIN is resolved lazily inside _find_soffice() to survive container restarts.


def init_storage():
    global storage_key
    if storage_key:
        return storage_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_KEY}, timeout=30)
    resp.raise_for_status()
    storage_key = resp.json()["storage_key"]
    logger.info("Object storage initialized for manuais")
    return storage_key


# Arquivos ficam no Supabase Storage (bucket privado "manuais"): não dependem da Universal Key,
# que muda entre preview/produção e fazia os downloads darem 500 no site publicado.
SB_BUCKET_URL = f"{os.environ.get('SUPABASE_URL')}/storage/v1/object/manuais"


def _sb_headers(extra=None):
    k = os.environ["SUPABASE_SERVICE_KEY"]
    return {"Authorization": f"Bearer {k}", "apikey": k, **(extra or {})}


def put_object(path: str, data: bytes, content_type: str) -> dict:
    resp = requests.post(
        f"{SB_BUCKET_URL}/{path}",
        headers=_sb_headers({"Content-Type": content_type, "x-upsert": "true"}),
        data=data, timeout=300
    )
    resp.raise_for_status()
    return {"path": path, "size": len(data)}


def _legacy_get_object(path: str):
    """Storage antigo (Emergent). Só leitura, para arquivos não migrados."""
    global storage_key
    key = init_storage()
    resp = requests.get(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key}, timeout=60
    )
    if resp.status_code in (401, 403):
        # storage_key em cache expirou (processo longo em produção): renova e tenta 1x.
        storage_key = None
        resp = requests.get(
            f"{STORAGE_URL}/objects/{path}",
            headers={"X-Storage-Key": init_storage()}, timeout=60
        )
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")


def get_object(path: str):
    resp = requests.get(f"{SB_BUCKET_URL}/{path}", headers=_sb_headers(), timeout=120)
    if resp.status_code in (400, 404):
        return _legacy_get_object(path)
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")


def _find_soffice() -> str:
    """Locate soffice/libreoffice binary at call time (re-resolved each call
    to survive container restarts that may wipe /usr/bin links)."""
    for p in (shutil.which("soffice"), shutil.which("libreoffice"),
              "/usr/bin/soffice", "/usr/bin/libreoffice"):
        if p and os.path.exists(p):
            return p
    raise RuntimeError("LibreOffice (soffice) not available on host")


def _convert_pptx_to_pdf(pptx_bytes: bytes) -> bytes:
    """Convert PPTX/PPT to PDF using LibreOffice headless. Returns PDF bytes."""
    bin_path = _find_soffice()
    with tempfile.TemporaryDirectory() as tmp:
        in_path = os.path.join(tmp, "in.pptx")
        with open(in_path, "wb") as f:
            f.write(pptx_bytes)
        out_dir = os.path.join(tmp, "out")
        os.makedirs(out_dir, exist_ok=True)
        # Use separate user profile per conversion to avoid concurrent-instance lock
        user_dir = os.path.join(tmp, "userdir")
        try:
            subprocess.run(
                [bin_path, "--headless", "--norestore", "--nologo", "--nofirststartwizard",
                 f"-env:UserInstallation=file://{user_dir}",
                 "--convert-to", "pdf", "--outdir", out_dir, in_path],
                check=True, capture_output=True, timeout=180
            )
        except subprocess.CalledProcessError as e:
            logger.error(f"LibreOffice convert-to PDF failed: {e.stderr.decode(errors='ignore')[:500]}")
            raise RuntimeError("LibreOffice failed to convert PPTX to PDF")
        except subprocess.TimeoutExpired:
            raise RuntimeError("LibreOffice timeout converting PPTX")

        pdf_files = [f for f in os.listdir(out_dir) if f.endswith(".pdf")]
        if not pdf_files:
            raise RuntimeError("No PDF produced by LibreOffice")
        with open(os.path.join(out_dir, pdf_files[0]), "rb") as f:
            return f.read()


def _pdf_page_count(pdf_bytes: bytes) -> int:
    """Best-effort: parse /Count from PDF or count /Type /Page objects."""
    import re
    # pdfinfo via subprocess (most reliable when poppler-utils present)
    try:
        out = subprocess.run(["pdfinfo", "-"], input=pdf_bytes, capture_output=True, timeout=20)
        m = re.search(rb"Pages:\s+(\d+)", out.stdout)
        if m:
            return int(m.group(1))
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.debug(f"pdfinfo failed: {e}")
    # Fallback: count /Type /Page (not perfect for compressed PDFs but works for our case)
    return max(1, len(re.findall(rb"/Type\s*/Page[^s]", pdf_bytes)))


def _render_pdf_page_to_png(pdf_bytes: bytes, page_num: int, dpi: int = 100) -> bytes:
    """Render a single PDF page (1-indexed) to PNG using pdftoppm (poppler-utils)."""
    with tempfile.TemporaryDirectory() as tmp:
        in_pdf = os.path.join(tmp, "in.pdf")
        with open(in_pdf, "wb") as f:
            f.write(pdf_bytes)
        prefix = os.path.join(tmp, "page")
        try:
            subprocess.run(
                ["pdftoppm", "-png", "-r", str(dpi), "-f", str(page_num), "-l", str(page_num),
                 "-singlefile", in_pdf, prefix],
                check=True, capture_output=True, timeout=30
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"pdftoppm failed: {e.stderr.decode(errors='ignore')[:200]}")
        png_path = f"{prefix}.png"
        if not os.path.exists(png_path):
            raise RuntimeError("pdftoppm did not produce PNG")
        with open(png_path, "rb") as f:
            return f.read()


def setup_manuais_routes(api_router: APIRouter, db, verify_token):
    """Register manuais routes on the main API router"""

    # Auxiliary MongoDB collection for PPTX metadata (slide_count, pdf_cache_path).
    # We can't add columns to the Supabase `manuais` table on the fly, so we keep
    # rendering metadata locally and merge at read time.
    import os as _os
    from motor.motor_asyncio import AsyncIOMotorClient as _AsyncMongo
    _mongo_url = _os.environ.get('MONGO_URL')
    _db_name = _os.environ.get('DB_NAME')
    _mongo_client = _AsyncMongo(_mongo_url) if _mongo_url else None
    _meta_col = _mongo_client[_db_name]["manuais_preview"] if _mongo_client else None

    async def _get_meta(manual_id: str) -> dict:
        if _meta_col is None:
            return {}
        m = await _meta_col.find_one({"manual_id": manual_id}, {"_id": 0})
        return m or {}

    async def _set_meta(manual_id: str, slide_count: int, pdf_cache_path: str):
        if _meta_col is None:
            return
        await _meta_col.update_one(
            {"manual_id": manual_id},
            {"$set": {"manual_id": manual_id, "slide_count": slide_count, "pdf_cache_path": pdf_cache_path}},
            upsert=True,
        )

    @api_router.post("/manuais/upload")
    async def upload_manual(
        file: UploadFile = File(...),
        brand: str = Form(""),
        category: str = Form(""),
        _: dict = Depends(verify_token)
    ):
        ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"Formato não permitido. Use: {', '.join(ALLOWED_EXTENSIONS)}")

        data = await file.read()
        if len(data) > MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail="Arquivo muito grande (máx 80MB)")

        content_type = ALLOWED_CONTENT_TYPES.get(ext, "application/octet-stream")
        storage_path = f"{APP_NAME}/uploads/{uuid.uuid4()}.{ext}"

        try:
            result = put_object(storage_path, data, content_type)
        except Exception as e:
            logger.error(f"Storage upload failed: {e}")
            if not EMERGENT_KEY:
                raise HTTPException(status_code=500, detail="EMERGENT_LLM_KEY não configurada no servidor")
            raise HTTPException(status_code=500, detail=f"Erro ao enviar arquivo: {str(e)}")

        # For PPTX/PPT: convert to PDF in background and cache - used for slide preview.
        slide_count = None
        pdf_cache_path = None
        if ext in ("pptx", "ppt"):
            try:
                pdf_bytes = await asyncio.to_thread(_convert_pptx_to_pdf, data)
                slide_count = _pdf_page_count(pdf_bytes)
                pdf_cache_path = f"{APP_NAME}/cache/{uuid.uuid4()}.pdf"
                put_object(pdf_cache_path, pdf_bytes, "application/pdf")
                logger.info(f"PPTX converted: {file.filename} → {slide_count} slides cached at {pdf_cache_path}")
            except Exception as conv_err:
                logger.warning(f"PPTX preview conversion failed for {file.filename}: {conv_err}. Upload succeeded but preview will be unavailable.")

        manual_id = str(uuid.uuid4())
        doc = {
            "id": manual_id,
            "storage_path": result["path"],
            "original_filename": file.filename,
            "content_type": content_type,
            "size": result.get("size", len(data)),
            "extension": ext,
            "brand": brand.strip(),
            "category": category.strip(),
            "is_deleted": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.manuais.insert_one(doc)

        # Persist preview metadata to local Mongo (not in Supabase schema)
        if slide_count and pdf_cache_path:
            await _set_meta(manual_id, slide_count, pdf_cache_path)

        # Mi: indexa o texto do novo manual já (background).
        if _meta_col is not None:
            from mi_module import index_manuals
            asyncio.create_task(index_manuals(db, _meta_col.database))

        return {
            "id": manual_id,
            "filename": file.filename,
            "brand": doc["brand"],
            "category": doc["category"],
            "size": doc["size"],
            "extension": ext,
            "slide_count": slide_count,
        }

    @api_router.get("/manuais")
    async def list_manuais(
        brand: Optional[str] = None,
        category: Optional[str] = None,
        search: Optional[str] = None,
        _: dict = Depends(verify_token)
    ):
        query = {"is_deleted": False}
        if brand:
            query["brand"] = brand
        if category:
            query["category"] = category
        if search:
            query["original_filename"] = {"$regex": search, "$options": "i"}

        docs = await db.manuais.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
        # Merge slide preview metadata (slide_count, pdf_cache_path) from local Mongo
        if _meta_col is not None:
            try:
                ids = [d.get("id") for d in docs if d.get("id")]
                meta_map = {}
                async for m in _meta_col.find({"manual_id": {"$in": ids}}, {"_id": 0}):
                    meta_map[m["manual_id"]] = m
                for d in docs:
                    m = meta_map.get(d.get("id"))
                    if m:
                        d["slide_count"] = m.get("slide_count")
                        # Don't expose pdf_cache_path to frontend
            except Exception as e:
                logger.debug(f"meta merge skipped: {e}")
        brands = await db.manuais.distinct("brand", {"is_deleted": False})
        categories = await db.manuais.distinct("category", {"is_deleted": False})

        return {
            "manuais": docs,
            "brands": sorted([b for b in brands if b]),
            "categories": sorted([c for c in categories if c])
        }

    @api_router.get("/manuais/{manual_id}/download")
    async def download_manual(
        manual_id: str,
        authorization: Optional[str] = Header(None),
        auth: Optional[str] = Query(None)
    ):
        # Support both header and query param auth
        if not authorization and auth:
            authorization = f"Bearer {auth}"
        if not authorization:
            raise HTTPException(status_code=401, detail="Not authenticated")

        doc = await db.manuais.find_one({"id": manual_id, "is_deleted": False}, {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail="Manual não encontrado")

        try:
            data, _ = get_object(doc["storage_path"])
        except Exception as e:
            logger.error(f"Storage download failed for {doc['storage_path']}: {e!r}")
            raise HTTPException(status_code=500, detail="Erro ao baixar arquivo")

        # RFC 5987: Content-Disposition não suporta latin-1. Nome com
        # cedilha/acento (comum em PT-BR) quebrava com UnicodeEncodeError.
        # Enviamos filename ASCII-safe + filename* com encoding UTF-8.
        from urllib.parse import quote
        raw_name = doc.get("original_filename") or f"manual-{manual_id}"
        ascii_name = raw_name.encode('ascii', 'ignore').decode('ascii') or 'manual.bin'
        utf8_name = quote(raw_name)
        return Response(
            content=data,
            media_type=doc.get("content_type", "application/octet-stream"),
            headers={"Content-Disposition": f'inline; filename="{ascii_name}"; filename*=UTF-8\'\'{utf8_name}'}
        )

    @api_router.get("/manuais/{manual_id}/slide/{slide_num}")
    async def get_manual_slide(
        manual_id: str,
        slide_num: int,
        authorization: Optional[str] = Header(None),
        auth: Optional[str] = Query(None)
    ):
        """Render a single slide of a PPTX manual as PNG. 1-indexed."""
        if not authorization and auth:
            authorization = f"Bearer {auth}"
        if not authorization:
            raise HTTPException(status_code=401, detail="Not authenticated")

        doc = await db.manuais.find_one({"id": manual_id, "is_deleted": False}, {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail="Manual não encontrado")
        if doc.get("extension") not in ("pptx", "ppt"):
            raise HTTPException(status_code=400, detail="Preview de slides disponível apenas para PPTX/PPT")

        meta = await _get_meta(manual_id)
        slide_count = meta.get("slide_count") or 0
        if slide_num < 1 or (slide_count and slide_num > slide_count):
            raise HTTPException(status_code=400, detail=f"Slide inválido (1-{slide_count})")

        # Use cached PDF if available; otherwise convert on-the-fly
        pdf_path = meta.get("pdf_cache_path")
        try:
            pdf_bytes = None
            if pdf_path:
                try:
                    pdf_bytes, _ = await asyncio.to_thread(get_object, pdf_path)
                except Exception:
                    pdf_bytes = None  # cache inacessível (ex: storage antigo) → reconverte
            if pdf_bytes is None:
                pptx_bytes, _ = await asyncio.to_thread(get_object, doc["storage_path"])
                pdf_bytes = await asyncio.to_thread(_convert_pptx_to_pdf, pptx_bytes)
                # Persist for next time
                new_path = f"{APP_NAME}/cache/{uuid.uuid4()}.pdf"
                put_object(new_path, pdf_bytes, "application/pdf")
                await _set_meta(manual_id, _pdf_page_count(pdf_bytes), new_path)
            png_bytes = await asyncio.to_thread(_render_pdf_page_to_png, pdf_bytes, slide_num, 100)
        except Exception as e:
            logger.error(f"Slide render failed for {manual_id} slide {slide_num}: {e}")
            raise HTTPException(status_code=500, detail=f"Erro ao gerar preview do slide: {str(e)[:120]}")

        return Response(
            content=png_bytes,
            media_type="image/png",
            headers={
                "Cache-Control": "public, max-age=86400",
                "Content-Disposition": f'inline; filename="slide_{slide_num}.png"'
            }
        )

    @api_router.post("/manuais/{manual_id}/regenerate-preview")
    async def regenerate_preview(manual_id: str, _: dict = Depends(verify_token)):
        """Re-trigger PPTX → PDF conversion for slide preview, for manuals where upload failed."""
        doc = await db.manuais.find_one({"id": manual_id, "is_deleted": False}, {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail="Manual não encontrado")
        if doc.get("extension") not in ("pptx", "ppt"):
            raise HTTPException(status_code=400, detail="Apenas PPTX/PPT")
        try:
            pptx_bytes, _ = await asyncio.to_thread(get_object, doc["storage_path"])
            pdf_bytes = await asyncio.to_thread(_convert_pptx_to_pdf, pptx_bytes)
            slide_count = _pdf_page_count(pdf_bytes)
            pdf_cache_path = f"{APP_NAME}/cache/{uuid.uuid4()}.pdf"
            put_object(pdf_cache_path, pdf_bytes, "application/pdf")
            await _set_meta(manual_id, slide_count, pdf_cache_path)
            return {"id": manual_id, "slide_count": slide_count}
        except Exception as e:
            logger.error(f"regenerate_preview failed: {e}")
            raise HTTPException(status_code=500, detail=str(e)[:200])

    # Action routes MUST be registered before parametric {manual_id} routes
    @api_router.put("/manuais/actions/rename-group")
    async def rename_group(body: dict, _: dict = Depends(verify_token)):
        """Rename a brand or category across all manuals"""
        group_type = body.get("type")  # 'brand' or 'category'
        old_name = body.get("old_name", "").strip()
        new_name = body.get("new_name", "").strip()

        if group_type not in ("brand", "category"):
            raise HTTPException(status_code=400, detail="type deve ser 'brand' ou 'category'")
        if not old_name or not new_name:
            raise HTTPException(status_code=400, detail="old_name e new_name são obrigatórios")

        result = await db.manuais.update_many(
            {group_type: old_name, "is_deleted": False},
            {"$set": {group_type: new_name}}
        )
        return {"message": f"{result.modified_count} manual(is) atualizado(s)", "modified": result.modified_count}

    @api_router.delete("/manuais/actions/delete-group")
    async def delete_group(body: dict, _: dict = Depends(verify_token)):
        """Soft-delete all manuals in a brand/category group"""
        group_type = body.get("type")
        name = body.get("name", "").strip()

        if group_type not in ("brand", "category"):
            raise HTTPException(status_code=400, detail="type deve ser 'brand' ou 'category'")
        if not name:
            raise HTTPException(status_code=400, detail="name é obrigatório")

        result = await db.manuais.update_many(
            {group_type: name, "is_deleted": False},
            {"$set": {"is_deleted": True}}
        )
        return {"message": f"{result.modified_count} manual(is) removido(s)", "deleted": result.modified_count}

    @api_router.put("/manuais/actions/move")
    async def move_manual(body: dict, _: dict = Depends(verify_token)):
        """Move a manual to a different brand/category"""
        manual_id = body.get("manual_id")
        if not manual_id:
            raise HTTPException(status_code=400, detail="manual_id é obrigatório")

        update = {}
        if "brand" in body:
            update["brand"] = body["brand"].strip()
        if "category" in body:
            update["category"] = body["category"].strip()
        if not update:
            raise HTTPException(status_code=400, detail="Informe brand ou category para mover")

        result = await db.manuais.update_one(
            {"id": manual_id, "is_deleted": False},
            {"$set": update}
        )
        if result.modified_count == 0:
            raise HTTPException(status_code=404, detail="Manual não encontrado")
        return {"message": "Manual movido"}

    @api_router.delete("/manuais/{manual_id}")
    async def delete_manual(manual_id: str, _: dict = Depends(verify_token)):
        result = await db.manuais.update_one(
            {"id": manual_id, "is_deleted": False},
            {"$set": {"is_deleted": True}}
        )
        if result.modified_count == 0:
            raise HTTPException(status_code=404, detail="Manual não encontrado")
        if _meta_col is not None:
            from mi_module import index_manuals
            asyncio.create_task(index_manuals(db, _meta_col.database))
        return {"message": "Manual removido"}

    @api_router.put("/manuais/{manual_id}")
    async def update_manual(manual_id: str, body: dict, _: dict = Depends(verify_token)):
        update = {}
        if "brand" in body:
            update["brand"] = body["brand"].strip()
        if "category" in body:
            update["category"] = body["category"].strip()
        if "original_filename" in body:
            update["original_filename"] = body["original_filename"].strip()
        if not update:
            raise HTTPException(status_code=400, detail="Nada para atualizar")

        result = await db.manuais.update_one(
            {"id": manual_id, "is_deleted": False},
            {"$set": update}
        )
        if result.modified_count == 0:
            raise HTTPException(status_code=404, detail="Manual não encontrado")
        return {"message": "Manual atualizado"}
