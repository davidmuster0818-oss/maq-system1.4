"""

Inventory Module - Backend Routes
Handles products, serial numbers, batches, movements, suppliers, and inventory.
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
import jwt
import io
import csv
import os
import uuid
import logging
import httpx

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/inventory", tags=["inventory"])

db = None
mongo_db = None   # Native Mongo client (separate from the Supabase adapter).
                  # Used only for the `product_metadata` sidecar until the
                  # products table gains `image_url` + `product_type` columns
                  # via /app/backend/migrations/products_add_image_and_type.sql.
_jwt_secret = None
_jwt_algorithm = "HS256"
_security = HTTPBearer()

def init(database, jwt_secret, mongo=None):
    global db, _jwt_secret, mongo_db
    db = database
    _jwt_secret = jwt_secret
    mongo_db = mongo

async def _auth(credentials: HTTPAuthorizationCredentials = Depends(_security)):
    try:
        payload = jwt.decode(credentials.credentials, _jwt_secret, algorithms=[_jwt_algorithm])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    if payload.get("iss") == "mastermaq-tracking":
        raise HTTPException(status_code=401, detail="Invalid token")
    import security
    return await security.check_session(payload)

# ==================== MODELS ====================

class ProductCreate(BaseModel):
    # All fields optional — user explicitly asked: "Remova a obrigatoriedade
    # de todos os campos do produto". `code` auto-generated when missing so
    # the QR-code link always works.
    code: Optional[str] = ""
    name: Optional[str] = ""
    category: Optional[str] = ""
    brand: Optional[str] = ""
    model: Optional[str] = ""
    description: Optional[str] = ""
    unit: Optional[str] = ""
    cost: Optional[float] = 0
    sale_price: Optional[float] = 0
    default_supplier: Optional[str] = ""
    min_stock: Optional[int] = 0
    location: Optional[str] = ""
    current_stock: Optional[int] = 0
    serial_number: Optional[str] = ""
    batch: Optional[str] = ""
    # New: product_type is the user-facing category label (Geladeira, Coifa,
    # Máquina de Lavar, etc.). image_url is the public Supabase Storage URL
    # for the product's photo — used in the inventory modal preview and QR
    # labels.
    product_type: Optional[str] = ""
    image_url: Optional[str] = ""

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    description: Optional[str] = None
    unit: Optional[str] = None
    cost: Optional[float] = None
    sale_price: Optional[float] = None
    default_supplier: Optional[str] = None
    min_stock: Optional[int] = None
    location: Optional[str] = None
    serial_number: Optional[str] = None
    batch: Optional[str] = None
    product_type: Optional[str] = None
    image_url: Optional[str] = None

class SerialCreate(BaseModel):
    product_code: str
    serial_number: str
    supplier: str = ""
    status: str = "Em estoque"  # Em estoque, Instalado, Vendido, Em garantia
    os_number: str = ""

class BatchCreate(BaseModel):
    product_code: str
    batch_number: str
    quantity: int = 0
    manufacture_date: str = ""
    expiry_date: str = ""
    supplier: str = ""
    invoice_number: str = ""

class MovementCreate(BaseModel):
    product_code: str
    quantity: int
    movement_type: str  # Entrada, Saída
    reason: str = ""  # Compra, Devolução, Ajuste+, Uso em OS, Venda, Perda, Ajuste-
    document: str = ""  # NF or OS number
    notes: str = ""

class SupplierCreate(BaseModel):
    name: str
    cnpj: str = ""
    contact: str = ""
    phone: str = ""
    email: str = ""
    products_supplied: str = ""

class InventoryCountCreate(BaseModel):
    product_code: str
    system_qty: int
    counted_qty: int
    responsible: str = ""

# ==================== PRODUCTS ====================

@router.get("/products")
async def list_products(
    search: str = "",
    category: str = "",
    stock_status: str = "",
    _: dict = Depends(_auth)
):
    query = {}
    if search:
        query["$or"] = [
            {"code": {"$regex": search, "$options": "i"}},
            {"name": {"$regex": search, "$options": "i"}},
            {"brand": {"$regex": search, "$options": "i"}},
        ]
    if category:
        query["category"] = category
    
    products = await db.products.find(query, {"_id": 0}).sort("name", 1).to_list(500)

    # Merge product_metadata (image_url, product_type) from Mongo. Bulk-fetch
    # once instead of N+1 to keep the list endpoint snappy. When the SQL
    # migration is applied and these become native columns, this block can
    # be removed with no client change.
    codes = [p.get("code") for p in products if p.get("code")]
    if codes and mongo_db is not None:
        meta_docs = await mongo_db.product_metadata.find(
            {"code": {"$in": codes}}, {"_id": 0}
        ).to_list(len(codes))
        meta_by_code = {m["code"]: m for m in meta_docs if "code" in m}
        for p in products:
            m = meta_by_code.get(p.get("code"))
            if m:
                if "image_url" in m: p["image_url"] = m["image_url"]
                if "product_type" in m: p["product_type"] = m["product_type"]

    if stock_status == "low":
        products = [p for p in products if 0 < p.get("current_stock", 0) <= p.get("min_stock", 0)]
    elif stock_status == "out":
        products = [p for p in products if p.get("current_stock", 0) == 0]
    elif stock_status == "ok":
        products = [p for p in products if p.get("current_stock", 0) > p.get("min_stock", 0)]

    return products

# ==================== IMAGE UPLOAD ====================
# Product image upload → Supabase Storage bucket `product-images`.
# Returns the public URL to store in `products.image_url`.
#
# Storage bucket setup (one-time, in Supabase Dashboard):
#   - Create bucket `product-images` as PUBLIC
#   - Set policy: anyone can read, service_role can write
# Alternatively the endpoint will attempt to create the bucket on first
# upload (best-effort — silently ignores 409 if it already exists).

_BUCKET = "product-images"
_BUCKET_ENSURED = False

async def _ensure_bucket(client: httpx.AsyncClient, supa_url: str, headers: dict):
    """Idempotent: create the bucket if it doesn't exist. Best-effort.

    We do this lazily on first upload rather than at boot so the module still
    imports cleanly if SUPABASE_SERVICE_KEY is missing during local dev.
    """
    global _BUCKET_ENSURED
    if _BUCKET_ENSURED:
        return
    try:
        r = await client.post(
            f"{supa_url}/storage/v1/bucket",
            headers=headers,
            json={"id": _BUCKET, "name": _BUCKET, "public": True},
            timeout=15,
        )
        if r.status_code in (200, 201, 409):
            _BUCKET_ENSURED = True
            logger.info(f"product-images bucket ready (status={r.status_code})")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"could not verify/create product-images bucket: {e}")


@router.post("/upload-image")
async def upload_product_image(file: UploadFile = File(...), _: dict = Depends(_auth)):
    """Upload a product image to Supabase Storage and return its public URL.

    Frontend calls this from ProductFormModal after the user selects/pastes/
    drops an image. Compression is done client-side; here we just validate
    the mime type and forward to Storage.
    """
    supa_url = (os.environ.get("SUPABASE_URL") or "").rstrip("/")
    service_key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not supa_url or not service_key:
        raise HTTPException(status_code=500, detail="Supabase Storage not configured")

    content_type = file.content_type or "image/jpeg"
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Arquivo deve ser uma imagem")

    ext = content_type.split("/")[-1].split(";")[0].strip().lower()
    if ext not in {"jpeg", "jpg", "png", "webp", "gif"}:
        ext = "jpeg"
    filename = f"{uuid.uuid4().hex}.{ext}"

    data = await file.read()
    if len(data) == 0:
        raise HTTPException(status_code=400, detail="Arquivo vazio")
    if len(data) > 8 * 1024 * 1024:  # 8 MB hard cap
        raise HTTPException(status_code=400, detail="Imagem maior que 8MB")

    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
    }
    async with httpx.AsyncClient() as client:
        await _ensure_bucket(client, supa_url, headers)
        upload_headers = {
            **headers,
            "Content-Type": content_type,
            "x-upsert": "true",
        }
        r = await client.post(
            f"{supa_url}/storage/v1/object/{_BUCKET}/{filename}",
            headers=upload_headers,
            content=data,
            timeout=60,
        )
        if r.status_code not in (200, 201):
            logger.error(f"Storage upload failed: {r.status_code} {r.text[:200]}")
            raise HTTPException(status_code=500, detail=f"Storage error: {r.text[:120]}")

    public_url = f"{supa_url}/storage/v1/object/public/{_BUCKET}/{filename}"
    return {"url": public_url, "filename": filename}



@router.post("/products")
async def create_product(product: ProductCreate, _: dict = Depends(_auth)):
    doc = product.dict()
    # Auto-generate a code when the user leaves it blank — required because
    # `code` is the PRIMARY KEY in the products table and is what the QR
    # label encodes. Without a code the QR would resolve to "not found".
    code = (doc.get("code") or "").strip()
    if not code:
        code = f"PROD-{uuid.uuid4().hex[:8].upper()}"
        doc["code"] = code
    else:
        existing = await db.products.find_one({"code": code})
        if existing:
            raise HTTPException(status_code=400, detail="Código já existe")

    # Split off fields that don't exist as columns in the Supabase `products`
    # table yet. These live in a separate Mongo collection (`product_metadata`)
    # keyed by code. When someone runs the SQL migration in the Supabase
    # dashboard (see /app/backend/migrations/products_add_image_and_type.sql)
    # to add these columns natively, we can drop the split — the Mongo copy
    # will keep working as fallback until it does.
    metadata = {}
    for meta_key in ("image_url", "product_type"):
        if meta_key in doc:
            val = doc.pop(meta_key)
            if val:
                metadata[meta_key] = val

    now = datetime.now(timezone.utc).isoformat()
    doc["created_at"] = now
    doc["updated_at"] = now
    await db.products.insert_one(doc)
    doc.pop("_id", None)

    if metadata:
        metadata["code"] = code
        metadata["updated_at"] = now
        if mongo_db is not None:
            await mongo_db.product_metadata.update_one(
                {"code": code}, {"$set": metadata}, upsert=True
            )
        doc.update({k: v for k, v in metadata.items() if k in ("image_url", "product_type")})
    return doc

@router.put("/products/{code}")
async def update_product(code: str, update: ProductUpdate, _: dict = Depends(_auth)):
    update_dict = {k: v for k, v in update.dict().items() if v is not None}
    if not update_dict:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    # Split out fields stored in Mongo (see create_product for context).
    metadata_update = {}
    for meta_key in ("image_url", "product_type"):
        if meta_key in update_dict:
            metadata_update[meta_key] = update_dict.pop(meta_key)

    now = datetime.now(timezone.utc).isoformat()
    if update_dict:
        update_dict["updated_at"] = now
        result = await db.products.update_one({"code": code}, {"$set": update_dict})
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Produto não encontrado")

    if metadata_update:
        metadata_update["code"] = code
        metadata_update["updated_at"] = now
        if mongo_db is not None:
            await mongo_db.product_metadata.update_one(
                {"code": code}, {"$set": metadata_update}, upsert=True
            )

    product = await db.products.find_one({"code": code}, {"_id": 0})
    if product is None:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    # Merge metadata back into the response
    if mongo_db is not None:
        meta = await mongo_db.product_metadata.find_one({"code": code}, {"_id": 0})
        if meta:
            for k in ("image_url", "product_type"):
                if k in meta:
                    product[k] = meta[k]
    return product

@router.delete("/products/{code}")
async def delete_product(code: str, _: dict = Depends(_auth)):
    result = await db.products.delete_one({"code": code})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    # Also clean up the metadata sidecar so orphan image URLs don't linger.
    if mongo_db is not None:
        await mongo_db.product_metadata.delete_one({"code": code})
    return {"message": "Produto removido"}


# ==================== PUBLIC PRODUCT VIEW (QR code) ====================
# Note: this endpoint is registered separately (no auth) — see register_public_routes below.


# ==================== IMPORT FROM SPREADSHEET ====================

def _norm_row(row: dict) -> dict:
    """Lower-case + strip keys, normalize accents minimally so the parser is
    forgiving with column header variations (Nome / nome / NOME / Nome )."""
    out = {}
    for k, v in row.items():
        if k is None:
            continue
        key = str(k).strip().lower()
        key = (key.replace("ç", "c").replace("ã", "a").replace("á", "a")
                   .replace("é", "e").replace("ó", "o").replace("í", "i")
                   .replace("ú", "u").replace("â", "a").replace("ê", "e"))
        out[key] = "" if v is None else str(v).strip()
    return out


def _parse_price(s: str) -> float:
    """Parses Brazilian (1.234,56) or US (1,234.56) decimal formats. Returns 0
    on empty/invalid input rather than failing the whole import."""
    if not s:
        return 0.0
    s = s.replace("R$", "").replace(" ", "").strip()
    if not s:
        return 0.0
    if "," in s and "." in s:
        # ambiguous: trust the right-most separator as decimal
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


@router.post("/products/import")
async def import_products_from_spreadsheet(
    file: UploadFile = File(...),
    _: dict = Depends(_auth),
):
    """Import products from a CSV or XLSX spreadsheet.
    
    Expected columns (order matters for headerless CSV; otherwise headers are
    matched case/accent-insensitive): Nome, Categoria, Marca, Modelo,
    Preço venda, Unidade, Local estoque.
    
    Behavior:
      - Empty cells become empty strings (per user spec).
      - Auto-generates a `code` (PROD-<short uuid>) when none is provided.
      - Skips rows where Nome is empty.
      - Upserts by `code` if provided; otherwise always inserts a new product.
    """
    filename = (file.filename or "").lower()
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Arquivo vazio")
    
    rows: list[dict] = []
    try:
        if filename.endswith(".xlsx") or filename.endswith(".xls"):
            try:
                from openpyxl import load_workbook
            except ImportError as e:
                raise HTTPException(status_code=500, detail=f"openpyxl não instalado: {e}")
            wb = load_workbook(io.BytesIO(content), data_only=True, read_only=True)
            ws = wb.active
            iter_rows = ws.iter_rows(values_only=True)
            headers = next(iter_rows, None)
            if not headers:
                raise HTTPException(status_code=400, detail="Planilha vazia")
            headers = [str(h) if h is not None else "" for h in headers]
            for r in iter_rows:
                if not r or all(v in (None, "") for v in r):
                    continue
                row = {headers[i]: r[i] for i in range(min(len(headers), len(r)))}
                rows.append(_norm_row(row))
        elif filename.endswith(".csv") or filename.endswith(".txt"):
            text = content.decode("utf-8-sig", errors="replace")
            # Try sniffing the dialect to handle semicolon-separated Excel CSV
            sample = text[:2048]
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
            except csv.Error:
                dialect = csv.excel
            reader = csv.DictReader(io.StringIO(text), dialect=dialect)
            for r in reader:
                rows.append(_norm_row(r))
        else:
            raise HTTPException(status_code=400, detail="Formato não suportado. Use .xlsx ou .csv")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao ler planilha: {e}")
    
    if not rows:
        raise HTTPException(status_code=400, detail="Nenhuma linha encontrada")
    
    # Header alias mapping (normalized → product field)
    aliases = {
        "nome": "name", "produto": "name",
        "categoria": "category",
        "marca": "brand",
        "modelo": "model",
        "preco venda": "sale_price", "preco de venda": "sale_price", "preco": "sale_price",
        "valor": "sale_price", "valor venda": "sale_price",
        "unidade": "unit", "un": "unit",
        "local estoque": "location", "local": "location", "localizacao": "location",
        "codigo": "code", "code": "code", "cod": "code",
        "estoque": "current_stock", "qtd": "current_stock", "quantidade": "current_stock",
        "estoque minimo": "min_stock", "minimo": "min_stock",
        "custo": "cost",
        "descricao": "description",
    }
    
    created = 0
    updated = 0
    skipped = 0
    errors: list[str] = []
    
    for idx, row in enumerate(rows, start=2):  # +1 for header row
        product: dict = {}
        for raw_key, field in aliases.items():
            val = row.get(raw_key)
            if val is None or val == "":
                continue
            if field in ("sale_price", "cost"):
                product[field] = _parse_price(val)
            elif field in ("current_stock", "min_stock"):
                try:
                    product[field] = int(float(val))
                except ValueError:
                    product[field] = 0
            else:
                product[field] = val
        
        name = product.get("name", "").strip()
        if not name:
            skipped += 1
            continue
        
        # Defaults — keep empty strings (per user: "se alguma coluna não tiver
        # dados, fica em branco") instead of injecting placeholder values.
        product.setdefault("category", "")
        product.setdefault("brand", "")
        product.setdefault("model", "")
        product.setdefault("description", "")
        product.setdefault("unit", "")
        product.setdefault("cost", 0.0)
        product.setdefault("sale_price", 0.0)
        product.setdefault("location", "")
        product.setdefault("default_supplier", "")
        product.setdefault("min_stock", 0)
        product.setdefault("current_stock", 0)
        product.setdefault("serial_number", "")
        product.setdefault("batch", "")
        
        code = product.get("code", "").strip()
        if not code:
            code = f"PROD-{uuid.uuid4().hex[:8].upper()}"
            product["code"] = code
        
        now = datetime.now(timezone.utc).isoformat()
        product["updated_at"] = now
        
        try:
            existing = await db.products.find_one({"code": code})
            if existing:
                await db.products.update_one({"code": code}, {"$set": product})
                updated += 1
            else:
                product["created_at"] = now
                await db.products.insert_one(product)
                created += 1
        except Exception as e:
            errors.append(f"Linha {idx}: {e}")
    
    return {
        "created": created,
        "updated": updated,
        "skipped_empty_name": skipped,
        "total_rows": len(rows),
        "errors": errors[:20],
    }

# ==================== SERIAL NUMBERS ====================

@router.get("/serials")
async def list_serials(product_code: str = "", status: str = "", _: dict = Depends(_auth)):
    query = {}
    if product_code:
        query["product_code"] = product_code
    if status:
        query["status"] = status
    serials = await db.serials.find(query, {"_id": 0}).sort("entry_date", -1).to_list(500)
    return serials

@router.post("/serials")
async def create_serial(serial: SerialCreate, _: dict = Depends(_auth)):
    existing = await db.serials.find_one({"serial_number": serial.serial_number})
    if existing:
        raise HTTPException(status_code=400, detail="Número de série já cadastrado")
    
    doc = serial.dict()
    doc["entry_date"] = datetime.now(timezone.utc).isoformat()
    await db.serials.insert_one(doc)
    doc.pop("_id", None)
    return doc

@router.put("/serials/{serial_number}")
async def update_serial(serial_number: str, status: str = "", os_number: str = "", _: dict = Depends(_auth)):
    update_dict = {}
    if status:
        update_dict["status"] = status
    if os_number:
        update_dict["os_number"] = os_number
    if not update_dict:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    
    result = await db.serials.update_one({"serial_number": serial_number}, {"$set": update_dict})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Serial não encontrado")
    return {"message": "Serial atualizado"}

# ==================== BATCHES ====================

@router.get("/batches")
async def list_batches(product_code: str = "", _: dict = Depends(_auth)):
    query = {}
    if product_code:
        query["product_code"] = product_code
    batches = await db.batches.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    return batches

@router.post("/batches")
async def create_batch(batch: BatchCreate, _: dict = Depends(_auth)):
    doc = batch.dict()
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    await db.batches.insert_one(doc)
    doc.pop("_id", None)
    return doc

# ==================== MOVEMENTS ====================

@router.get("/movements")
async def list_movements(product_code: str = "", limit: int = 100, _: dict = Depends(_auth)):
    query = {}
    if product_code:
        query["product_code"] = product_code
    movements = await db.movements.find(query, {"_id": 0}).sort("date", -1).to_list(limit)
    return movements

@router.post("/movements")
async def create_movement(movement: MovementCreate, _: dict = Depends(_auth)):
    # Validate product exists
    product = await db.products.find_one({"code": movement.product_code})
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    
    # Calculate new stock
    current = product.get("current_stock", 0)
    if movement.movement_type == "Entrada":
        new_stock = current + movement.quantity
    elif movement.movement_type == "Saída":
        if current < movement.quantity:
            raise HTTPException(status_code=400, detail=f"Estoque insuficiente. Atual: {current}")
        new_stock = current - movement.quantity
    else:
        raise HTTPException(status_code=400, detail="Tipo de movimento inválido")
    
    # Save movement
    doc = movement.dict()
    doc["date"] = datetime.now(timezone.utc).isoformat()
    doc["previous_stock"] = current
    doc["new_stock"] = new_stock
    await db.movements.insert_one(doc)
    doc.pop("_id", None)
    
    # Update product stock
    await db.products.update_one(
        {"code": movement.product_code},
        {"$set": {"current_stock": new_stock, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    return doc

# ==================== SUPPLIERS ====================

@router.get("/suppliers")
async def list_suppliers(search: str = "", _: dict = Depends(_auth)):
    query = {}
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"cnpj": {"$regex": search, "$options": "i"}},
        ]
    suppliers = await db.suppliers.find(query, {"_id": 0}).sort("name", 1).to_list(500)
    return suppliers

@router.post("/suppliers")
async def create_supplier(supplier: SupplierCreate, _: dict = Depends(_auth)):
    doc = supplier.dict()
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    await db.suppliers.insert_one(doc)
    doc.pop("_id", None)
    return doc

@router.delete("/suppliers/{name}")
async def delete_supplier(name: str, _: dict = Depends(_auth)):
    result = await db.suppliers.delete_one({"name": name})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Fornecedor não encontrado")
    return {"message": "Fornecedor removido"}

# ==================== DASHBOARD / STOCK OVERVIEW ====================

@router.get("/dashboard")
async def stock_dashboard(_: dict = Depends(_auth)):
    products = await db.products.find({}, {"_id": 0}).to_list(1000)
    
    total_products = len(products)
    total_value = sum(p.get("current_stock", 0) * p.get("cost", 0) for p in products)
    out_of_stock = [p for p in products if p.get("current_stock", 0) == 0 and p.get("min_stock", 0) > 0]
    low_stock = [p for p in products if 0 < p.get("current_stock", 0) <= p.get("min_stock", 0)]
    
    # Purchase suggestions
    suggestions = []
    for p in products:
        current = p.get("current_stock", 0)
        minimum = p.get("min_stock", 0)
        if current < minimum and minimum > 0:
            suggestions.append({
                "code": p["code"],
                "name": p["name"],
                "current_stock": current,
                "min_stock": minimum,
                "to_buy": minimum - current + (minimum // 2),  # Buy enough to have 1.5x min
            })
    
    # Recent movements
    recent = await db.movements.find({}, {"_id": 0}).sort("date", -1).to_list(10)
    
    return {
        "total_products": total_products,
        "total_value": round(total_value, 2),
        "out_of_stock": len(out_of_stock),
        "low_stock": len(low_stock),
        "out_of_stock_items": out_of_stock[:10],
        "low_stock_items": low_stock[:10],
        "purchase_suggestions": suggestions[:20],
        "recent_movements": recent,
    }

# ==================== INVENTORY COUNT ====================

@router.post("/inventory-count")
async def submit_inventory_count(count: InventoryCountCreate, _: dict = Depends(_auth)):
    doc = count.dict()
    doc["difference"] = count.counted_qty - count.system_qty
    doc["date"] = datetime.now(timezone.utc).isoformat()
    await db.inventory_counts.insert_one(doc)
    doc.pop("_id", None)
    
    # If there's a difference, create an adjustment movement
    if doc["difference"] != 0:
        movement_type = "Entrada" if doc["difference"] > 0 else "Saída"
        reason = "Ajuste positivo" if doc["difference"] > 0 else "Ajuste negativo"
        
        await create_movement(MovementCreate(
            product_code=count.product_code,
            quantity=abs(doc["difference"]),
            movement_type=movement_type,
            reason=reason,
            notes=f"Inventário por {count.responsible}",
        ))
    
    return doc

@router.get("/inventory-counts")
async def list_inventory_counts(_: dict = Depends(_auth)):
    counts = await db.inventory_counts.find({}, {"_id": 0}).sort("date", -1).to_list(200)
    return counts
