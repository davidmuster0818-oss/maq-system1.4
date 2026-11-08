"""Módulo Financeiro (base: projeto finance-maq) integrado às OSs reais (Supabase) e usuários/técnicos reais (Mongo)."""
import os
import time
import hmac
import uuid
import asyncio
import logging
import calendar
from datetime import datetime, timezone, date, timedelta
from zoneinfo import ZoneInfo
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

log = logging.getLogger("finance")
router = APIRouter()
M = None  # Mongo (lançamentos, categorias, usuários)
S = None  # Supabase (ordens de serviço)
_verify = None
_bearer = HTTPBearer()
TZ = ZoneInfo("America/Sao_Paulo")
NO_ID = {"_id": 0}
METHODS = ("cartao", "pix", "dinheiro")
STATUSES = ("previsto", "pago", "atrasado")
GROUPS = {"entrada": ("servico", "peca", "taxa", "outros"), "saida": ("fixa", "variavel", "outra")}
DONE_STATUSES = ("Finalizada", "Visita Realizada")
OS_FIELDS = {"_id": 0, "os_number": 1, "customer_name": 1, "technician": 1, "status": 1, "visit_fee": 1,
             "visit_fee_paid": 1, "source": 1, "updated_at": 1, "product": 1}
DEFAULT_CATEGORIES = [
    ("entrada", "servico", "Serviço", "#2563EB", "servico"),
    ("entrada", "peca", "Peças", "#16A34A", "peca"),
    ("entrada", "taxa", "Taxa de visita", "#D97706", "taxa"),
    ("entrada", "outros", "Outras entradas", "#9333EA", None),
    ("saida", "fixa", "Aluguel", "#E11D48", None),
    ("saida", "fixa", "Salários e comissões", "#4F46E5", "comissao"),
    ("saida", "variavel", "Combustível", "#0891B2", None),
    ("saida", "variavel", "Peças compradas", "#059669", None),
    ("saida", "outra", "Outras saídas", "#64748B", None),
]


def new_id() -> str:
    return str(uuid.uuid4())


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def today() -> str:
    return datetime.now(TZ).date().isoformat()


def parse_date(s: str) -> date:
    return date.fromisoformat(s[:10])


def month_day(year: int, month: int, day: int) -> str:
    return date(year, month, min(day, calendar.monthrange(year, month)[1])).isoformat()


def with_status(t: dict) -> dict:
    if t.get("status") == "previsto" and t["date"] < today():
        t["status"] = "atrasado"
    return t


def status_filter(status: str) -> dict:
    if status == "atrasado":
        return {"$or": [{"status": "atrasado"}, {"status": "previsto", "date": {"$lt": today()}}]}
    if status == "previsto":
        return {"status": "previsto", "date": {"$gte": today()}}
    return {"status": status}


# ---------- Autenticação (login real do sistema) ----------
async def current_user(credentials: HTTPAuthorizationCredentials = Depends(_bearer)) -> dict:
    p = await _verify(credentials)
    email = (p.get("email") or "").strip().lower()
    u = await M.users.find_one({"email": email}, {"_id": 0, "password_hash": 0, "password_enc": 0}) or {}
    return {"id": u.get("id") or p.get("user_id") or email, "email": email, "name": u.get("name") or p.get("name") or "",
            "role": "admin" if p.get("role") == "admin" else "tecnico",
            "finance_access": u.get("finance_access") or "own", "commission_pct": u.get("commission_pct", 0)}


async def require_finance(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "admin" and user.get("finance_access") != "own":
        raise HTTPException(403, "Sem acesso ao financeiro")
    return user


async def require_admin(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(403, "Apenas administradores")
    return user


def scope(user: dict) -> dict:
    return {} if user["role"] == "admin" else {"technician_id": user["id"]}


# ---------- Técnicos reais ----------
def _tech_public(u: dict) -> dict:
    return {"id": u["id"], "name": u.get("name", ""), "email": u.get("email"), "role": "tecnico",
            "commission_pct": u.get("commission_pct", 0), "finance_access": u.get("finance_access") or "own"}


async def technicians() -> list:
    rows = await M.users.find({"role": "technician"}, {"_id": 0, "password_hash": 0, "password_enc": 0}).sort("name", 1).to_list(500)
    return [_tech_public(u) for u in rows if u.get("id")]


def match_tech(name: Optional[str], techs: list) -> Optional[str]:
    n = (name or "").strip().lower()
    if not n:
        return None
    exact = next((t["id"] for t in techs if (t["name"] or "").strip().lower() == n), None)
    if exact:
        return exact
    first = n.split()[0]
    return next((t["id"] for t in techs if (t["name"] or "").strip().lower().split()[:1] == [first]), None)


# ---------- Ordens de serviço reais ----------
def parts_total(parts: list) -> float:
    return sum(float(p.get("qty") or 0) * float(p.get("unit_price") or 0) for p in parts or [])


def values_total(v: dict) -> float:
    return float(v.get("service_value") or 0) + float(v.get("fee_value") or 0) + parts_total(v.get("parts"))


async def os_rows(q: Optional[str] = None, ids: Optional[List[str]] = None, limit: int = 30) -> list:
    if ids is not None:
        if not ids:
            return []
        query = {"os_number": {"$in": ids}}
        limit = max(limit, len(ids))
    elif q:
        query = {"$or": [{"os_number": {"$regex": q}}, {"customer_name": {"$regex": q}}]}
    else:
        query = {}
    rows = await S.service_orders.find(query, OS_FIELDS).sort("updated_at", -1).limit(limit).to_list(limit)
    techs = await technicians()
    nums = [r["os_number"] for r in rows]
    vals = {v["os_number"]: v async for v in M.fin_os_values.find({"os_number": {"$in": nums}}, NO_ID)}
    out = []
    for r in rows:
        v = vals.get(r["os_number"])
        out.append({"id": r["os_number"], "number": str(r["os_number"]).strip(), "client": r.get("customer_name") or "",
                    "technician": r.get("technician") or "", "technician_id": match_tech(r.get("technician"), techs),
                    "status": r.get("status") or "", "source": r.get("source") or "", "product": r.get("product") or "",
                    "visit_fee": float(r.get("visit_fee") or 0), "visit_fee_paid": bool(r.get("visit_fee_paid")),
                    "values": v, "total": round(values_total(v) if v else float(r.get("visit_fee") or 0), 2)})
    return out


async def check_os_ids(ids: List[str]):
    ids = list(dict.fromkeys(ids))
    if ids and len(await os_rows(ids=ids)) != len(ids):
        raise HTTPException(400, "OS inválida")
    return ids


async def system_cats() -> dict:
    return {c["system_key"]: c["id"] async for c in M.fin_categories.find({"system_key": {"$ne": None}}, NO_ID)}


async def os_entries(o: dict, vals: dict, method: str, status: str, when: str):
    cats = await system_cats()
    parts = vals.get("parts") or []
    rows = [("servico", float(vals.get("service_value") or 0), f"Serviço OS #{o['number']} - {o['client']}", None),
            ("taxa", float(vals.get("fee_value") or 0), f"Taxa OS #{o['number']}", None),
            ("peca", parts_total(parts), f"Peças OS #{o['number']}", ", ".join(p["name"] for p in parts if p.get("name")) or None)]
    docs = [{"id": new_id(), "type": "entrada", "date": when, "amount": round(v, 2), "description": desc,
             "category_id": cats.get(key), "payment_method": method, "status": status, "os_ids": [o["id"]],
             "technician_id": o.get("technician_id"), "part_name": part, "reconciled": False, "source": "os",
             "os_key": key, "recurring_id": None, "created_at": now_iso()} for key, v, desc, part in rows if v > 0]
    if docs:
        await M.fin_transactions.insert_many(docs)
    return len(docs)


async def on_os_updated(order: dict):
    """Chamado após editar uma OS: OS finalizada com taxa de visita gera/atualiza a entrada da taxa."""
    try:
        fee = float(order.get("visit_fee") or 0)
        num = order.get("os_number")
        if not num or fee <= 0 or order.get("status") not in DONE_STATUSES:
            return
        existing = await M.fin_transactions.find_one({"os_ids": num, "source": "os", "os_key": "taxa"}, NO_ID)
        status = "pago" if order.get("visit_fee_paid") else "previsto"
        if existing:
            if not existing.get("reconciled") and existing.get("auto") and (existing["amount"] != fee or existing["status"] != status):
                await M.fin_transactions.update_one({"id": existing["id"]}, {"$set": {"amount": round(fee, 2), "status": status}})
            return
        if await M.fin_transactions.find_one({"os_ids": num, "source": "os"}):
            return
        cats = await system_cats()
        tech = match_tech(order.get("technician"), await technicians())
        await M.fin_transactions.insert_one({
            "id": new_id(), "type": "entrada", "date": today(), "amount": round(fee, 2),
            "description": f"Taxa OS #{str(num).strip()} - {order.get('customer_name') or ''}", "category_id": cats.get("taxa"),
            "payment_method": "pix", "status": status, "os_ids": [num], "technician_id": tech, "part_name": None,
            "reconciled": False, "source": "os", "os_key": "taxa", "auto": True, "recurring_id": None, "created_at": now_iso()})
    except Exception as exc:
        log.error("on_os_updated %s: %s", order.get("os_number"), exc)


async def os_finance(o: dict) -> dict:
    txs = await M.fin_transactions.find({"os_ids": o["id"]}, NO_ID).to_list(500)
    cobrado = recebido = custo_saidas = 0.0
    for t in txs:
        share = t["amount"] / max(len(t["os_ids"]), 1)
        if t["type"] == "entrada":
            cobrado += share
            if t["status"] == "pago":
                recebido += share
        else:
            custo_saidas += share
    vals = o.get("values") or {}
    custo_pecas = sum(float(p.get("qty") or 0) * float(p.get("unit_cost") or 0) for p in vals.get("parts") or [])
    custo = custo_saidas + custo_pecas
    return {"os": o, "valor_os": o["total"], "cobrado": round(cobrado, 2), "recebido": round(recebido, 2),
            "a_receber": round(cobrado - recebido, 2), "custo": round(custo, 2), "custo_pecas": round(custo_pecas, 2),
            "custo_saidas": round(custo_saidas, 2), "lucro": round(cobrado - custo, 2),
            "lancamentos": [with_status(t) for t in txs]}


class PartIn(BaseModel):
    name: str
    qty: float = Field(gt=0)
    unit_price: float = Field(ge=0)
    unit_cost: float = Field(0, ge=0)


class LaunchIn(BaseModel):
    service_value: float = Field(0, ge=0)
    fee_value: float = Field(0, ge=0)
    parts: List[PartIn] = []
    payment_method: str = "pix"
    status: str = "previsto"
    date: Optional[str] = None


class ImportIn(BaseModel):
    start: str
    end: str


async def get_os(os_number: str, user: dict) -> dict:
    rows = await os_rows(ids=[os_number])
    if not rows or (user["role"] != "admin" and rows[0]["technician_id"] != user["id"]):
        raise HTTPException(404, "OS não encontrada")
    return rows[0]


@router.get("/finance/os")
async def list_os(q: Optional[str] = None, ids: Optional[str] = None, user: dict = Depends(require_finance)):
    rows = await os_rows(q=(q or "").strip() or None, ids=[i for i in ids.split("|") if i] if ids is not None else None)
    return rows if user["role"] == "admin" else [r for r in rows if r["technician_id"] == user["id"]]


@router.get("/finance/os/{os_number}/finance")
async def get_os_finance(os_number: str, user: dict = Depends(require_finance)):
    return await os_finance(await get_os(os_number, user))


@router.post("/finance/os/{os_number}/launch")
async def launch_os(os_number: str, body: LaunchIn, user: dict = Depends(require_admin)):
    if body.payment_method not in METHODS or body.status not in ("previsto", "pago"):
        raise HTTPException(400, "Forma de pagamento ou status inválido")
    o = await get_os(os_number, user)
    if await M.fin_transactions.find_one({"os_ids": os_number, "source": "os", "reconciled": True}):
        raise HTTPException(409, "Esta OS já tem lançamentos conferidos com o extrato")
    vals = {"os_number": os_number, "service_value": body.service_value, "fee_value": body.fee_value,
            "parts": [p.model_dump() for p in body.parts], "date": body.date or today(), "updated_at": now_iso()}
    if values_total(vals) <= 0:
        raise HTTPException(400, "Informe ao menos um valor")
    await M.fin_os_values.update_one({"os_number": os_number}, {"$set": vals}, upsert=True)
    await M.fin_transactions.delete_many({"os_ids": os_number, "source": "os"})
    n = await os_entries(o, vals, body.payment_method, body.status, vals["date"])
    return {"ok": True, "created": n}


@router.post("/finance/os/import-done")
async def import_done(body: ImportIn, _: dict = Depends(require_admin)):
    rows = await S.service_orders.find({"status": {"$in": list(DONE_STATUSES)}, "visit_fee": {"$gte": 0.01},
                                        "updated_at": {"$gte": body.start, "$lte": body.end + "T23:59:59"}},
                                       OS_FIELDS).limit(3000).to_list(3000)
    before = await M.fin_transactions.count_documents({"source": "os"})
    for r in rows:
        await on_os_updated(r)
    return {"ok": True, "checked": len(rows), "created": await M.fin_transactions.count_documents({"source": "os"}) - before}


# ---------- Categorias ----------
class CategoryIn(BaseModel):
    name: str
    type: str
    group: str
    color: str = "#2563EB"


class MoveIn(BaseModel):
    direction: str


def validate_category(body: CategoryIn):
    if body.type not in GROUPS or body.group not in GROUPS[body.type]:
        raise HTTPException(400, "Tipo ou grupo inválido")


@router.get("/finance/me")
async def me(user: dict = Depends(current_user)):
    return {**user, "is_admin": user["role"] == "admin", "has_finance": user["role"] == "admin" or user["finance_access"] == "own"}


@router.get("/finance/techs")
async def list_techs(_: dict = Depends(require_admin)):
    return await technicians()


@router.get("/finance/categories")
async def list_categories(_: dict = Depends(require_finance)):
    return await M.fin_categories.find({}, NO_ID).sort("order", 1).to_list(500)


@router.post("/finance/categories")
async def create_category(body: CategoryIn, _: dict = Depends(require_admin)):
    validate_category(body)
    doc = {"id": new_id(), **body.model_dump(), "system_key": None, "order": await M.fin_categories.count_documents({})}
    await M.fin_categories.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/finance/categories/{cat_id}")
async def update_category(cat_id: str, body: CategoryIn, _: dict = Depends(require_admin)):
    validate_category(body)
    cat = await M.fin_categories.find_one({"id": cat_id}, NO_ID)
    if not cat:
        raise HTTPException(404, "Categoria não encontrada")
    if cat.get("system_key") and body.type != cat["type"]:
        raise HTTPException(400, "Categoria do sistema não pode mudar de tipo")
    await M.fin_categories.update_one({"id": cat_id}, {"$set": body.model_dump()})
    return await M.fin_categories.find_one({"id": cat_id}, NO_ID)


@router.post("/finance/categories/{cat_id}/move")
async def move_category(cat_id: str, body: MoveIn, _: dict = Depends(require_admin)):
    cats = await M.fin_categories.find({}, NO_ID).sort("order", 1).to_list(500)
    idx = next((i for i, c in enumerate(cats) if c["id"] == cat_id), None)
    if idx is None:
        raise HTTPException(404, "Categoria não encontrada")
    j = idx - 1 if body.direction == "up" else idx + 1
    if 0 <= j < len(cats):
        cats[idx], cats[j] = cats[j], cats[idx]
        for i, c in enumerate(cats):
            await M.fin_categories.update_one({"id": c["id"]}, {"$set": {"order": i}})
    return {"ok": True}


@router.delete("/finance/categories/{cat_id}")
async def delete_category(cat_id: str, _: dict = Depends(require_admin)):
    cat = await M.fin_categories.find_one({"id": cat_id}, NO_ID)
    if not cat:
        raise HTTPException(404, "Categoria não encontrada")
    if cat.get("system_key"):
        raise HTTPException(400, "Categoria usada pelo sistema não pode ser excluída")
    if await M.fin_transactions.count_documents({"category_id": cat_id}) or await M.fin_recurring.count_documents({"category_id": cat_id}):
        raise HTTPException(409, "Categoria em uso por lançamentos")
    await M.fin_categories.delete_one({"id": cat_id})
    await M.fin_budgets.delete_many({"category_id": cat_id})
    return {"ok": True}


# ---------- Lançamentos ----------
class TxIn(BaseModel):
    type: str
    date: str
    amount: float = Field(gt=0)
    description: str
    category_id: str
    payment_method: str
    status: str
    os_ids: List[str] = []
    technician_id: Optional[str] = None
    part_name: Optional[str] = None


class LinksIn(BaseModel):
    os_ids: List[str]


class ReconcileIn(BaseModel):
    reconciled: bool


async def validate_tx(body: TxIn) -> dict:
    if body.type not in GROUPS or body.payment_method not in METHODS or body.status not in STATUSES:
        raise HTTPException(400, "Tipo, forma de pagamento ou status inválido")
    try:
        parse_date(body.date)
    except ValueError:
        raise HTTPException(400, "Data inválida")
    cat = await M.fin_categories.find_one({"id": body.category_id}, NO_ID)
    if not cat or cat["type"] != body.type:
        raise HTTPException(400, "Categoria inválida para este tipo")
    data = body.model_dump()
    data["os_ids"] = await check_os_ids(body.os_ids)
    return data


async def generate_recurring() -> int:
    t = datetime.now(TZ).date()
    ym = t.strftime("%Y-%m")
    created = 0
    async for r in M.fin_recurring.find({"active": True}, NO_ID):
        if await M.fin_transactions.find_one({"recurring_id": r["id"], "date": {"$regex": f"^{ym}"}}):
            continue
        await M.fin_transactions.insert_one({
            "id": new_id(), "type": "saida", "date": month_day(t.year, t.month, r["day_of_month"]),
            "amount": r["amount"], "description": r["description"], "category_id": r["category_id"],
            "payment_method": r.get("payment_method", "pix"), "status": "previsto", "os_ids": [],
            "technician_id": None, "part_name": None, "reconciled": False, "source": "recorrente",
            "recurring_id": r["id"], "created_at": now_iso()})
        created += 1
    return created


@router.get("/finance/transactions")
async def list_transactions(
    user: dict = Depends(require_finance),
    type: Optional[str] = None, start: Optional[str] = None, end: Optional[str] = None,
    category_id: Optional[str] = None, technician_id: Optional[str] = None, status: Optional[str] = None,
    payment_method: Optional[str] = None, os_id: Optional[str] = None, limit: int = Query(2000, le=5000),
):
    await generate_recurring()
    q = {**scope(user)}
    if type:
        q["type"] = type
    if start or end:
        q["date"] = {**({"$gte": start} if start else {}), **({"$lte": end} if end else {})}
    if category_id:
        q["category_id"] = category_id
    if technician_id and user["role"] == "admin":
        q["technician_id"] = None if technician_id == "none" else technician_id
    if payment_method:
        q["payment_method"] = payment_method
    if os_id:
        q["os_ids"] = os_id
    if status:
        q = {"$and": [q, status_filter(status)]}
    txs = await M.fin_transactions.find(q, NO_ID).sort("date", -1).to_list(limit)
    return [with_status(t) for t in txs]


@router.post("/finance/transactions")
async def create_transaction(body: TxIn, _: dict = Depends(require_admin)):
    doc = {"id": new_id(), **(await validate_tx(body)), "reconciled": False, "source": "manual", "recurring_id": None,
           "created_at": now_iso()}
    await M.fin_transactions.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/finance/transactions/{tx_id}")
async def update_transaction(tx_id: str, body: TxIn, _: dict = Depends(require_admin)):
    data = await validate_tx(body)
    data["auto"] = False
    if (await M.fin_transactions.update_one({"id": tx_id}, {"$set": data})).matched_count == 0:
        raise HTTPException(404, "Lançamento não encontrado")
    return with_status(await M.fin_transactions.find_one({"id": tx_id}, NO_ID))


@router.delete("/finance/transactions/{tx_id}")
async def delete_transaction(tx_id: str, _: dict = Depends(require_admin)):
    if (await M.fin_transactions.delete_one({"id": tx_id})).deleted_count == 0:
        raise HTTPException(404, "Lançamento não encontrado")
    await M.fin_bank_transactions.update_many({"linked_tx_id": tx_id}, {"$set": {"handled": None, "linked_tx_id": None}})
    return {"ok": True}


@router.put("/finance/transactions/{tx_id}/links")
async def set_links(tx_id: str, body: LinksIn, _: dict = Depends(require_admin)):
    ids = await check_os_ids(body.os_ids)
    if (await M.fin_transactions.update_one({"id": tx_id}, {"$set": {"os_ids": ids}})).matched_count == 0:
        raise HTTPException(404, "Lançamento não encontrado")
    return {"ok": True, "os_ids": ids}


@router.patch("/finance/transactions/{tx_id}/reconcile")
async def reconcile(tx_id: str, body: ReconcileIn, _: dict = Depends(require_admin)):
    if (await M.fin_transactions.update_one({"id": tx_id}, {"$set": {"reconciled": body.reconciled}})).matched_count == 0:
        raise HTTPException(404, "Lançamento não encontrado")
    return {"ok": True}


# ---------- Visão geral ----------
def summarize(txs: list) -> dict:
    s = {"entradas_pagas": 0.0, "saidas_pagas": 0.0, "entradas_total": 0.0, "saidas_total": 0.0,
         "a_receber": 0.0, "a_pagar": 0.0, "atrasado_receber": 0.0}
    for t in txs:
        e = t["type"] == "entrada"
        s["entradas_total" if e else "saidas_total"] += t["amount"]
        if t["status"] == "pago":
            s["entradas_pagas" if e else "saidas_pagas"] += t["amount"]
        else:
            s["a_receber" if e else "a_pagar"] += t["amount"]
            if e and t["status"] == "atrasado":
                s["atrasado_receber"] += t["amount"]
    s["saldo"] = s["entradas_pagas"] - s["saidas_pagas"]
    s["saldo_previsto"] = s["entradas_total"] - s["saidas_total"]
    return {k: round(v, 2) for k, v in s.items()}


@router.get("/finance/overview")
async def overview(start: str, end: str, technician_id: Optional[str] = None, user: dict = Depends(require_finance)):
    await generate_recurring()
    q = {**scope(user)}
    if technician_id and user["role"] == "admin":
        q["technician_id"] = technician_id
    s, e = parse_date(start), parse_date(end)
    days = (e - s).days + 1
    ps, pe = (s - timedelta(days=days)).isoformat(), (s - timedelta(days=1)).isoformat()
    cur = [with_status(t) for t in await M.fin_transactions.find({**q, "date": {"$gte": start, "$lte": end}}, NO_ID).to_list(20000)]
    prev = [with_status(t) for t in await M.fin_transactions.find({**q, "date": {"$gte": ps, "$lte": pe}}, NO_ID).to_list(20000)]
    cats = {c["id"]: c async for c in M.fin_categories.find({}, NO_ID)}
    names = {t["id"]: t["name"] for t in await technicians()}
    by_cat, ranking, series = {}, {}, {}
    for t in cur:
        c = cats.get(t["category_id"], {"name": "Sem categoria", "color": "#94A3B8"})
        key = (t["type"], t["category_id"])
        by_cat.setdefault(key, {"type": t["type"], "category_id": t["category_id"], "name": c["name"], "color": c["color"], "total": 0})
        by_cat[key]["total"] += t["amount"]
        if t["type"] == "entrada" and t.get("technician_id"):
            r = ranking.setdefault(t["technician_id"], {"technician_id": t["technician_id"],
                                                        "name": names.get(t["technician_id"], "?"), "total": 0, "recebido": 0, "os": set()})
            r["total"] += t["amount"]
            if t["status"] == "pago":
                r["recebido"] += t["amount"]
            r["os"].update(t.get("os_ids", []))
        day = series.setdefault(t["date"], {"date": t["date"], "entradas": 0, "saidas": 0})
        day["entradas" if t["type"] == "entrada" else "saidas"] += t["amount"]
    rank = sorted(({**r, "os": len(r["os"]), "total": round(r["total"], 2), "recebido": round(r["recebido"], 2)}
                   for r in ranking.values()), key=lambda r: -r["total"])
    if user["role"] != "admin":
        rank = [r for r in rank if r["technician_id"] == user["id"]]
    alerts, due = [], []
    if user["role"] == "admin":
        alerts = [b for b in await budget_status() if b["pct"] >= 80]
        limit_day = (parse_date(today()) + timedelta(days=7)).isoformat()
        due = [with_status(t) for t in await M.fin_transactions.find(
            {"type": "saida", "status": {"$ne": "pago"}, "date": {"$lte": limit_day}}, NO_ID).sort("date", 1).to_list(50)]
    return {"current": summarize(cur), "previous": summarize(prev), "previous_range": {"start": ps, "end": pe},
            "by_category": sorted(by_cat.values(), key=lambda x: -x["total"]), "ranking": rank,
            "series": sorted(series.values(), key=lambda x: x["date"]), "budget_alerts": alerts, "due_soon": due}


# ---------- Despesas fixas ----------
class RecurringIn(BaseModel):
    description: str
    amount: float = Field(gt=0)
    category_id: str
    day_of_month: int = Field(ge=1, le=31)
    payment_method: str = "pix"
    active: bool = True


class BudgetIn(BaseModel):
    category_id: str
    monthly_limit: float = Field(gt=0)


class PayoutIn(BaseModel):
    technician_id: str
    amount: float = Field(gt=0)
    period_start: str
    period_end: str
    payment_method: str = "pix"
    note: Optional[str] = None


class TechSettingsIn(BaseModel):
    commission_pct: Optional[float] = Field(None, ge=0, le=100)
    finance_access: Optional[str] = None


async def check_expense_category(cat_id: str):
    cat = await M.fin_categories.find_one({"id": cat_id}, NO_ID)
    if not cat or cat["type"] != "saida":
        raise HTTPException(400, "Escolha uma categoria de saída")


@router.get("/finance/recurring")
async def list_recurring(_: dict = Depends(require_admin)):
    await generate_recurring()
    items = await M.fin_recurring.find({}, NO_ID).sort("day_of_month", 1).to_list(500)
    ym = datetime.now(TZ).strftime("%Y-%m")
    for r in items:
        t = await M.fin_transactions.find_one({"recurring_id": r["id"], "date": {"$regex": f"^{ym}"}}, NO_ID)
        r["current"] = with_status(t) if t else None
    return items


@router.post("/finance/recurring")
async def create_recurring(body: RecurringIn, _: dict = Depends(require_admin)):
    await check_expense_category(body.category_id)
    doc = {"id": new_id(), **body.model_dump(), "created_at": now_iso()}
    await M.fin_recurring.insert_one(doc)
    doc.pop("_id", None)
    await generate_recurring()
    return doc


@router.put("/finance/recurring/{rid}")
async def update_recurring(rid: str, body: RecurringIn, _: dict = Depends(require_admin)):
    await check_expense_category(body.category_id)
    if (await M.fin_recurring.update_one({"id": rid}, {"$set": body.model_dump()})).matched_count == 0:
        raise HTTPException(404, "Despesa fixa não encontrada")
    await generate_recurring()
    return {"ok": True}


@router.delete("/finance/recurring/{rid}")
async def delete_recurring(rid: str, _: dict = Depends(require_admin)):
    if (await M.fin_recurring.delete_one({"id": rid})).deleted_count == 0:
        raise HTTPException(404, "Despesa fixa não encontrada")
    await M.fin_transactions.delete_many({"recurring_id": rid, "status": {"$ne": "pago"}, "date": {"$gte": today()}})
    return {"ok": True}


# ---------- Metas e limites ----------
async def budget_status() -> list:
    ym = datetime.now(TZ).strftime("%Y-%m")
    cats = {c["id"]: c async for c in M.fin_categories.find({}, NO_ID)}
    out = []
    async for b in M.fin_budgets.find({}, NO_ID):
        spent = 0.0
        async for t in M.fin_transactions.find({"category_id": b["category_id"], "type": "saida", "date": {"$regex": f"^{ym}"}}, {"_id": 0, "amount": 1}):
            spent += t["amount"]
        c = cats.get(b["category_id"], {})
        pct = round(spent / b["monthly_limit"] * 100, 1)
        out.append({**b, "category_name": c.get("name", "?"), "color": c.get("color", "#64748B"), "spent": round(spent, 2),
                    "pct": pct, "level": "estourado" if pct >= 100 else "alerta" if pct >= 80 else "ok", "month": ym})
    return sorted(out, key=lambda x: -x["pct"])


@router.get("/finance/budgets")
async def list_budgets(_: dict = Depends(require_admin)):
    return await budget_status()


@router.post("/finance/budgets")
async def upsert_budget(body: BudgetIn, _: dict = Depends(require_admin)):
    await check_expense_category(body.category_id)
    await M.fin_budgets.update_one({"category_id": body.category_id},
                                   {"$set": {"monthly_limit": body.monthly_limit}, "$setOnInsert": {"id": new_id()}}, upsert=True)
    return {"ok": True}


@router.delete("/finance/budgets/{bid}")
async def delete_budget(bid: str, _: dict = Depends(require_admin)):
    if (await M.fin_budgets.delete_one({"id": bid})).deleted_count == 0:
        raise HTTPException(404, "Limite não encontrado")
    return {"ok": True}


# ---------- Técnicos: fechamento ----------
@router.get("/finance/technicians")
async def technicians_closing(start: str, end: str, user: dict = Depends(require_finance)):
    techs = await technicians()
    if user["role"] != "admin":
        techs = [t for t in techs if t["id"] == user["id"]]
    service_cats = [c["id"] async for c in M.fin_categories.find({"type": "entrada", "group": "servico"}, {"_id": 0, "id": 1})]
    out = []
    for tech in techs:
        txs = await M.fin_transactions.find({"technician_id": tech["id"], "type": "entrada",
                                             "date": {"$gte": start, "$lte": end}}, NO_ID).to_list(5000)
        txs = [with_status(t) for t in txs]
        servico_pago = sum(t["amount"] for t in txs if t["status"] == "pago" and t["category_id"] in service_cats)
        commission = servico_pago * (tech.get("commission_pct") or 0) / 100
        payouts = await M.fin_payouts.find({"technician_id": tech["id"], "period_start": {"$lte": end},
                                            "period_end": {"$gte": start}}, NO_ID).to_list(500)
        repassado = sum(p["amount"] for p in payouts)
        out.append({"technician_id": tech["id"], "name": tech["name"], "commission_pct": tech.get("commission_pct", 0),
                    "finance_access": tech.get("finance_access"), "os_count": len({o for t in txs for o in t.get("os_ids", [])}),
                    "gerado": round(sum(t["amount"] for t in txs), 2),
                    "recebido": round(sum(t["amount"] for t in txs if t["status"] == "pago"), 2),
                    "servico_total": round(sum(t["amount"] for t in txs if t["category_id"] in service_cats), 2),
                    "servico_pago": round(servico_pago, 2), "comissao": round(commission, 2),
                    "repassado": round(repassado, 2), "a_repassar": round(max(commission - repassado, 0), 2)})
    return sorted(out, key=lambda x: -x["gerado"])


@router.put("/finance/technicians/{tech_id}/settings")
async def tech_settings(tech_id: str, body: TechSettingsIn, _: dict = Depends(require_admin)):
    data = body.model_dump(exclude_none=True)
    if "finance_access" in data and data["finance_access"] not in ("own", "none"):
        raise HTTPException(400, "Acesso inválido")
    if (await M.users.update_one({"id": tech_id, "role": "technician"}, {"$set": data})).matched_count == 0:
        raise HTTPException(404, "Técnico não encontrado")
    return {"ok": True}


@router.get("/finance/payouts")
async def list_payouts(technician_id: Optional[str] = None, user: dict = Depends(require_finance)):
    q = {}
    if user["role"] != "admin":
        q["technician_id"] = user["id"]
    elif technician_id:
        q["technician_id"] = technician_id
    return await M.fin_payouts.find(q, NO_ID).sort("paid_at", -1).to_list(500)


@router.post("/finance/payouts")
async def create_payout(body: PayoutIn, _: dict = Depends(require_admin)):
    if body.payment_method not in METHODS:
        raise HTTPException(400, "Forma de pagamento inválida")
    tech = next((t for t in await technicians() if t["id"] == body.technician_id), None)
    if not tech:
        raise HTTPException(404, "Técnico não encontrado")
    cats = await system_cats()
    tx_id = new_id()
    await M.fin_transactions.insert_one({
        "id": tx_id, "type": "saida", "date": today(), "amount": body.amount,
        "description": f"Repasse de comissão - {tech['name']} ({body.period_start} a {body.period_end})",
        "category_id": cats.get("comissao"), "payment_method": body.payment_method, "status": "pago", "os_ids": [],
        "technician_id": tech["id"], "part_name": None, "reconciled": False, "source": "repasse",
        "recurring_id": None, "created_at": now_iso()})
    doc = {"id": new_id(), **body.model_dump(), "technician_name": tech["name"], "transaction_id": tx_id, "paid_at": today()}
    await M.fin_payouts.insert_one(doc)
    doc.pop("_id", None)
    return doc


# ---------- Bancos (Pluggy) ----------
PLUGGY_BASE = "https://api.pluggy.ai"
_pluggy_cache = {"key": None, "exp": 0}


async def pluggy_key() -> str:
    if _pluggy_cache["key"] and _pluggy_cache["exp"] > time.time():
        return _pluggy_cache["key"]
    cid, secret = os.environ.get("PLUGGY_ID"), os.environ.get("PLUGGY_SECRET")
    if not cid or not secret:
        raise HTTPException(503, "Pluggy não configurado (PLUGGY_ID / PLUGGY_SECRET)")
    async with httpx.AsyncClient(base_url=PLUGGY_BASE, timeout=20) as c:
        r = await c.post("/auth", json={"clientId": cid, "clientSecret": secret})
    if r.is_error:
        raise HTTPException(424, f"Pluggy recusou as credenciais ({r.status_code})")
    _pluggy_cache.update(key=r.json()["apiKey"], exp=time.time() + 100 * 60)
    return _pluggy_cache["key"]


async def pluggy(method: str, path: str, **kw) -> dict:
    key = await pluggy_key()
    async with httpx.AsyncClient(base_url=PLUGGY_BASE, timeout=30) as c:
        r = await c.request(method, path, headers={"X-API-KEY": key}, **kw)
    if r.is_error:
        log.error("Pluggy %s %s -> %s %s", method, path, r.status_code, r.text[:200])
        raise HTTPException(424, f"Erro no Pluggy ({r.status_code})")
    return r.json()


class ItemIn(BaseModel):
    item_id: str


class LinkBankIn(BaseModel):
    transaction_id: str


class CreateFromBankIn(BaseModel):
    category_id: str
    description: Optional[str] = None
    os_ids: List[str] = []
    payment_method: str = "pix"


async def import_item(item_id: str) -> dict:
    accounts = (await pluggy("GET", "/accounts", params={"itemId": item_id})).get("results", [])
    count = 0
    for acc in accounts:
        await M.fin_bank_accounts.update_one({"id": acc["id"]}, {"$set": {
            "id": acc["id"], "item_id": item_id, "name": acc.get("name"), "number": acc.get("number"),
            "type": acc.get("type"), "balance": acc.get("balance"), "currency": acc.get("currencyCode")}}, upsert=True)
        params = {"accountId": acc["id"], "pageSize": 500}
        while True:
            page = await pluggy("GET", "/v2/transactions", params=params)
            for tx in page.get("results", []):
                amount = float(tx.get("amount") or 0)
                kind = "entrada" if (tx.get("type") == "CREDIT" or (tx.get("type") is None and amount > 0)) else "saida"
                await M.fin_bank_transactions.update_one({"id": tx["id"]}, {
                    "$set": {"id": tx["id"], "item_id": item_id, "account_id": acc["id"], "account_name": acc.get("name"),
                             "date": (tx.get("date") or "")[:10], "amount": round(abs(amount), 2), "type": kind,
                             "description": tx.get("description") or ""},
                    "$setOnInsert": {"handled": None, "linked_tx_id": None, "imported_at": now_iso()}}, upsert=True)
                count += 1
            nxt = page.get("next")
            if not nxt or "after=" not in nxt:
                break
            params = {"accountId": acc["id"], "pageSize": 500, "after": nxt.split("after=", 1)[1].split("&")[0]}
    await M.fin_bank_items.update_one({"id": item_id}, {"$set": {"last_sync": now_iso()}})
    return {"accounts": len(accounts), "transactions": count}


@router.get("/banks/status")
async def banks_status(_: dict = Depends(require_admin)):
    return {"configured": bool(os.environ.get("PLUGGY_ID") and os.environ.get("PLUGGY_SECRET"))}


@router.post("/banks/connect-token")
async def connect_token(user: dict = Depends(require_admin)):
    data = await pluggy("POST", "/connect_token", json={"options": {"clientUserId": user["id"], "avoidDuplicates": True}})
    return {"accessToken": data["accessToken"]}


@router.post("/banks/items")
async def save_item(body: ItemIn, _: dict = Depends(require_admin)):
    item = await pluggy("GET", f"/items/{body.item_id}")
    await M.fin_bank_items.update_one({"id": body.item_id}, {"$set": {
        "id": body.item_id, "connector": (item.get("connector") or {}).get("name", "Banco"),
        "status": item.get("status"), "connected_at": now_iso()}}, upsert=True)
    return await import_item(body.item_id)


@router.post("/banks/items/{item_id}/sync")
async def sync_item(item_id: str, _: dict = Depends(require_admin)):
    if not await M.fin_bank_items.find_one({"id": item_id}):
        raise HTTPException(404, "Conexão não encontrada")
    return await import_item(item_id)


@router.delete("/banks/items/{item_id}")
async def remove_item(item_id: str, _: dict = Depends(require_admin)):
    await M.fin_bank_items.delete_one({"id": item_id})
    await M.fin_bank_accounts.delete_many({"item_id": item_id})
    await M.fin_bank_transactions.delete_many({"item_id": item_id, "handled": None})
    return {"ok": True}


@router.get("/banks/items")
async def list_items(_: dict = Depends(require_admin)):
    items = await M.fin_bank_items.find({}, NO_ID).to_list(50)
    for it in items:
        it["accounts"] = await M.fin_bank_accounts.find({"item_id": it["id"]}, NO_ID).to_list(50)
    return items


async def suggestions(bt: dict) -> list:
    lo, hi = bt["amount"] - 0.01, bt["amount"] + 0.01
    try:
        d = parse_date(bt["date"])
    except ValueError:
        return []
    rng = {"$gte": (d - timedelta(days=5)).isoformat(), "$lte": (d + timedelta(days=5)).isoformat()}
    out = []
    async for t in M.fin_transactions.find({"type": bt["type"], "amount": {"$gte": lo, "$lte": hi}, "date": rng,
                                            "bank_tx_id": {"$in": [None]}}, NO_ID).limit(3):
        out.append({"kind": "lancamento", "transaction_id": t["id"], "label": t["description"], "date": t["date"],
                    "amount": t["amount"], "os_ids": t.get("os_ids", [])})
    if bt["type"] == "entrada":
        async for v in M.fin_os_values.find({"date": rng}, NO_ID):
            if abs(values_total(v) - bt["amount"]) <= 0.01:
                out.append({"kind": "os", "os_id": v["os_number"], "label": f"OS #{str(v['os_number']).strip()}",
                            "date": v["date"], "amount": round(values_total(v), 2)})
    return out


@router.get("/banks/transactions")
async def bank_transactions(pending_only: bool = False, _: dict = Depends(require_admin)):
    txs = await M.fin_bank_transactions.find({"handled": None} if pending_only else {}, NO_ID).sort("date", -1).to_list(1000)
    for t in txs:
        t["suggestions"] = await suggestions(t) if not t.get("handled") else []
    return txs


async def get_bank_tx(bid: str) -> dict:
    bt = await M.fin_bank_transactions.find_one({"id": bid}, NO_ID)
    if not bt:
        raise HTTPException(404, "Movimento não encontrado")
    if bt.get("handled"):
        raise HTTPException(409, "Movimento já tratado")
    return bt


@router.post("/banks/transactions/{bid}/link")
async def link_bank(bid: str, body: LinkBankIn, _: dict = Depends(require_admin)):
    await get_bank_tx(bid)
    res = await M.fin_transactions.update_one({"id": body.transaction_id},
                                              {"$set": {"bank_tx_id": bid, "reconciled": True, "status": "pago"}})
    if res.matched_count == 0:
        raise HTTPException(404, "Lançamento não encontrado")
    await M.fin_bank_transactions.update_one({"id": bid}, {"$set": {"handled": "vinculado", "linked_tx_id": body.transaction_id}})
    return {"ok": True}


@router.post("/banks/transactions/{bid}/create")
async def create_from_bank(bid: str, body: CreateFromBankIn, _: dict = Depends(require_admin)):
    bt = await get_bank_tx(bid)
    cat = await M.fin_categories.find_one({"id": body.category_id}, NO_ID)
    if not cat or cat["type"] != bt["type"]:
        raise HTTPException(400, "Categoria inválida para este movimento")
    ids = await check_os_ids(body.os_ids)
    tech = (await os_rows(ids=ids[:1]))[0]["technician_id"] if ids else None
    tx_id = new_id()
    await M.fin_transactions.insert_one({
        "id": tx_id, "type": bt["type"], "date": bt["date"], "amount": bt["amount"],
        "description": body.description or bt["description"], "category_id": body.category_id,
        "payment_method": body.payment_method, "status": "pago", "os_ids": ids, "technician_id": tech,
        "part_name": None, "reconciled": True, "source": "banco", "recurring_id": None, "bank_tx_id": bid,
        "created_at": now_iso()})
    await M.fin_bank_transactions.update_one({"id": bid}, {"$set": {"handled": "criado", "linked_tx_id": tx_id}})
    return {"ok": True, "transaction_id": tx_id}


@router.post("/banks/transactions/{bid}/ignore")
async def ignore_bank(bid: str, _: dict = Depends(require_admin)):
    await get_bank_tx(bid)
    await M.fin_bank_transactions.update_one({"id": bid}, {"$set": {"handled": "ignorado"}})
    return {"ok": True}


_tasks = set()


def spawn(coro):
    t = asyncio.create_task(coro)
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)


async def sync_all(trigger: str):
    results = []
    async for it in M.fin_bank_items.find({}, {"_id": 0, "id": 1}):
        try:
            results.append({"item_id": it["id"], **(await import_item(it["id"]))})
        except Exception as exc:
            log.error("sync item %s falhou: %s", it["id"], exc)
            results.append({"item_id": it["id"], "error": str(getattr(exc, "detail", exc))})
    await M.fin_sync_runs.insert_one({"trigger": trigger, "finished_at": now_iso(), "results": results})


@router.post("/finance/cron/bank-sync")
async def cron_bank_sync(request: Request):
    secret = os.environ.get("WEBHOOK_CRON_SECRET", "")
    auth = request.headers.get("authorization", "")
    if not secret or not auth.startswith("Bearer ") or not hmac.compare_digest(auth[7:], secret):
        raise HTTPException(401, "Unauthorized")
    try:
        body = await request.json()
    except Exception:
        body = {}
    run_id = request.headers.get("x-webhook-id") or (body.get("run_id") if isinstance(body, dict) else None)
    if run_id:
        res = await M.fin_cron_runs.update_one({"run_id": run_id}, {"$setOnInsert": {"run_id": run_id, "at": now_iso()}}, upsert=True)
        if res.upserted_id is None:
            return {"ok": True, "duplicate": True}
    spawn(sync_all("cron"))
    return {"ok": True}


async def handle_event(evt: dict):
    event, item_id = evt.get("event", ""), evt.get("itemId")
    if not item_id or not await M.fin_bank_items.find_one({"id": item_id}):
        return
    if event == "item/deleted":
        await M.fin_bank_items.delete_one({"id": item_id})
        await M.fin_bank_accounts.delete_many({"item_id": item_id})
        await M.fin_bank_transactions.delete_many({"item_id": item_id, "handled": None})
    elif event == "transactions/deleted":
        await M.fin_bank_transactions.delete_many({"id": {"$in": evt.get("transactionIds") or []}, "handled": None})
    elif event in ("item/updated", "transactions/created", "transactions/updated"):
        await import_item(item_id)
    if event.startswith("item/") and event != "item/deleted":
        try:
            item = await pluggy("GET", f"/items/{item_id}")
            await M.fin_bank_items.update_one({"id": item_id}, {"$set": {"status": item.get("status")}})
        except Exception as exc:
            log.warning("item status %s: %s", item_id, exc)


@router.post("/banks/pluggy-webhook")
async def pluggy_webhook(request: Request, token: str = ""):
    secret = os.environ.get("PLUGGY_WEBHOOK_SECRET", "")
    if not secret or not hmac.compare_digest(token, secret):
        raise HTTPException(401, "Unauthorized")
    try:
        evt = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid body")
    if not isinstance(evt, dict):
        raise HTTPException(400, "Invalid body")
    if evt.get("clientId") and evt["clientId"] != os.environ.get("PLUGGY_ID"):
        return JSONResponse({"ok": True, "ignored": True})
    event_id = evt.get("eventId")
    if event_id:
        res = await M.fin_webhook_events.update_one({"event_id": event_id}, {"$setOnInsert": {
            "event_id": event_id, "event": evt.get("event"), "item_id": evt.get("itemId"), "received_at": now_iso()}}, upsert=True)
        if res.upserted_id is None:
            return {"ok": True, "duplicate": True}
    spawn(handle_event(evt))
    return {"ok": True}


def webhook_url(request: Request) -> str:
    host = (request.headers.get("x-forwarded-host") or request.headers.get("host", "")).split(",")[0].strip()
    return f"https://{host}/api/banks/pluggy-webhook?token={os.environ.get('PLUGGY_WEBHOOK_SECRET', '')}"


@router.get("/banks/webhook")
async def webhook_info(request: Request, _: dict = Depends(require_admin)):
    url = webhook_url(request)
    registered = False
    try:
        registered = any(h.get("url") == url for h in (await pluggy("GET", "/webhooks")).get("results", []))
    except HTTPException:
        pass
    last_events = await M.fin_webhook_events.find({}, NO_ID).sort("received_at", -1).limit(5).to_list(5)
    last_sync = await M.fin_sync_runs.find_one({}, NO_ID, sort=[("finished_at", -1)])
    return {"url": url, "registered": registered, "last_events": last_events, "last_sync": last_sync}


@router.post("/banks/webhook/register")
async def register_webhook(request: Request, _: dict = Depends(require_admin)):
    url = webhook_url(request)
    if any(h.get("url") == url for h in (await pluggy("GET", "/webhooks")).get("results", [])):
        return {"ok": True, "already": True}
    await pluggy("POST", "/webhooks", json={"event": "all", "url": url})
    return {"ok": True}


@router.post("/banks/sync-all")
async def sync_all_now(_: dict = Depends(require_admin)):
    spawn(sync_all("manual"))
    return {"ok": True}


# ---------- Assistentes de IA ----------
FUNCTIONS = {"resumo_semanal": "Resumo semanal"}
SYSTEM = ("Você é um assistente financeiro de uma empresa de assistência técnica. Escreva em português do Brasil, "
          "em markdown simples, com: um parágrafo de resumo, 3 a 5 destaques em tópicos, alertas que exigem ação "
          "e uma recomendação para a próxima semana. Use apenas os números fornecidos, nunca invente dados.")


class AssistantIn(BaseModel):
    name: str
    function: str = "resumo_semanal"
    instructions: Optional[str] = ""
    active: bool = True


async def week_context() -> str:
    end = parse_date(today())
    start = end - timedelta(days=6)
    pstart, pend = start - timedelta(days=7), start - timedelta(days=1)
    cats = {c["id"]: c["name"] async for c in M.fin_categories.find({}, NO_ID)}
    names = {t["id"]: t["name"] for t in await technicians()}

    async def load(a, b):
        return [with_status(t) for t in await M.fin_transactions.find(
            {"date": {"$gte": a.isoformat(), "$lte": b.isoformat()}}, NO_ID).to_list(10000)]
    cur, prev = await load(start, end), await load(pstart, pend)

    def tot(txs, typ, paid=None):
        return round(sum(t["amount"] for t in txs if t["type"] == typ and (paid is None or (t["status"] == "pago") == paid)), 2)
    lines = [f"Período: {start} a {end}. Semana anterior: {pstart} a {pend}.",
             f"Entradas recebidas: R$ {tot(cur, 'entrada', True)} (anterior R$ {tot(prev, 'entrada', True)})",
             f"Entradas a receber: R$ {tot(cur, 'entrada', False)}",
             f"Saídas pagas: R$ {tot(cur, 'saida', True)} (anterior R$ {tot(prev, 'saida', True)})",
             f"Saídas previstas/em atraso: R$ {tot(cur, 'saida', False)}", "Por categoria:"]
    bycat = {}
    for t in cur:
        k = (t["type"], cats.get(t["category_id"], "Sem categoria"))
        bycat[k] = bycat.get(k, 0) + t["amount"]
    lines += [f"- {k[0]} / {k[1]}: R$ {round(v, 2)}" for k, v in sorted(bycat.items(), key=lambda x: -x[1])]
    tech = {}
    for t in cur:
        if t["type"] == "entrada" and t.get("technician_id"):
            tech[t["technician_id"]] = tech.get(t["technician_id"], 0) + t["amount"]
    lines.append("Técnicos (valor gerado): " + (", ".join(f"{names.get(k, '?')} R$ {round(v, 2)}" for k, v in tech.items()) or "nenhum"))
    late = await M.fin_transactions.find({"status": {"$ne": "pago"}, "date": {"$lt": today()}}, NO_ID).to_list(200)
    lines.append(f"Lançamentos em atraso (total geral): {len(late)}, somando R$ {round(sum(t['amount'] for t in late), 2)}")
    lines += [f"- {t['type']} {t['date']} {t['description']} R$ {t['amount']}" for t in late[:10]]
    return "\n".join(lines)


async def generate_text(prompt: str, instructions: str) -> tuple:
    system = SYSTEM + (f"\nInstruções do administrador: {instructions}" if instructions else "")
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(api_key=os.environ["EMERGENT_LLM_KEY"], session_id=new_id(), system_message=system) \
            .with_model("openai", "gpt-6-luna")
        text = await chat.send_message(UserMessage(text=prompt))
        if text and str(text).strip():
            return str(text), "gpt-6-luna"
    except Exception as exc:
        log.warning("GPT-6 Luna falhou, usando Ollama: %s", exc)
    key, base = os.environ.get("OLLAMA_API_KEY"), os.environ.get("OLLAMA_BASE_URL")
    if not key or not base:
        raise HTTPException(424, "GPT-6 Luna indisponível e Ollama não configurado")
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(f"{base.rstrip('/')}/api/chat", headers={"Authorization": f"Bearer {key}"}, json={
            "model": os.environ.get("OLLAMA_MODEL", "gpt-oss:120b"), "stream": False,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]})
    if r.is_error:
        raise HTTPException(424, f"Ollama falhou ({r.status_code})")
    return r.json()["message"]["content"], "ollama/" + os.environ.get("OLLAMA_MODEL", "gpt-oss:120b")


@router.get("/assistants")
async def list_assistants(_: dict = Depends(require_admin)):
    items = await M.fin_assistants.find({}, NO_ID).sort("created_at", 1).to_list(100)
    for a in items:
        a["last_run"] = await M.fin_assistant_runs.find_one({"assistant_id": a["id"]}, NO_ID, sort=[("created_at", -1)])
    return {"assistants": items, "functions": FUNCTIONS}


@router.post("/assistants")
async def create_assistant(body: AssistantIn, _: dict = Depends(require_admin)):
    if body.function not in FUNCTIONS:
        raise HTTPException(400, "Função não disponível")
    doc = {"id": new_id(), **body.model_dump(), "created_at": now_iso()}
    await M.fin_assistants.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/assistants/{aid}")
async def update_assistant(aid: str, body: AssistantIn, _: dict = Depends(require_admin)):
    if body.function not in FUNCTIONS:
        raise HTTPException(400, "Função não disponível")
    if (await M.fin_assistants.update_one({"id": aid}, {"$set": body.model_dump()})).matched_count == 0:
        raise HTTPException(404, "Assistente não encontrado")
    return {"ok": True}


@router.delete("/assistants/{aid}")
async def delete_assistant(aid: str, _: dict = Depends(require_admin)):
    if (await M.fin_assistants.delete_one({"id": aid})).deleted_count == 0:
        raise HTTPException(404, "Assistente não encontrado")
    await M.fin_assistant_runs.delete_many({"assistant_id": aid})
    return {"ok": True}


@router.post("/assistants/{aid}/run")
async def run_assistant(aid: str, _: dict = Depends(require_admin)):
    a = await M.fin_assistants.find_one({"id": aid}, NO_ID)
    if not a:
        raise HTTPException(404, "Assistente não encontrado")
    context = await week_context()
    text, model = await generate_text(f"Dados da semana:\n{context}\n\nEscreva o resumo semanal.", a.get("instructions", ""))
    run = {"id": new_id(), "assistant_id": aid, "content": text, "model": model, "created_at": now_iso()}
    await M.fin_assistant_runs.insert_one(run)
    run.pop("_id", None)
    return run


@router.get("/assistants/{aid}/runs")
async def list_runs(aid: str, _: dict = Depends(require_admin)):
    return await M.fin_assistant_runs.find({"assistant_id": aid}, NO_ID).sort("created_at", -1).to_list(50)


# ---------- Inicialização ----------
async def startup():
    if await M.fin_categories.count_documents({}) == 0:
        await M.fin_categories.insert_many([{"id": new_id(), "type": t, "group": g, "name": n, "color": c, "system_key": k, "order": i}
                                            for i, (t, g, n, c, k) in enumerate(DEFAULT_CATEGORIES)])
    if await M.fin_assistants.count_documents({}) == 0:
        await M.fin_assistants.insert_one({"id": new_id(), "name": "Resumo da semana", "function": "resumo_semanal",
                                           "instructions": "Seja direto, destaque o que exige ação.", "active": True,
                                           "created_at": now_iso()})
    for col, keys in {"fin_transactions": ["id", "date", "technician_id", "os_ids", "recurring_id"],
                      "fin_categories": ["id"], "fin_os_values": ["os_number"], "fin_bank_transactions": ["id"]}.items():
        for k in keys:
            try:
                await M[col].create_index(k, unique=k in ("id", "os_number"))
            except Exception as exc:
                log.error("index %s.%s: %s", col, k, exc)
    await generate_recurring()


def setup_finance(api_router, mongo_db, supa_db, verify_token):
    global M, S, _verify
    M, S, _verify = mongo_db, supa_db, verify_token
    api_router.include_router(router)
