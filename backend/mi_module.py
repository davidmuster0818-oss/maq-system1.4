"""Mi — assistente IA com contexto de todas as OSs (Supabase) e do texto dos manuais (indexado no Mongo)."""
import os
import re
import time
import uuid
import asyncio
import logging
import subprocess
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from pydantic import BaseModel

import mi_agent
from manuais_module import get_object, _convert_pptx_to_pdf

logger = logging.getLogger(__name__)
MODEL = "gpt-5.4"

OS_FIELDS = [
    "os_number", "customer_name", "status", "source", "brand", "model", "product", "service_type",
    "reported_defect", "technical_diagnosis", "required_parts", "address", "number", "complement", "city", "neighborhood",
    "reference_point", "cep", "phone2", "email", "visit_fee_paid", "lat", "lng", "serial_number",
    "registration_date", "attendance_date", "technician", "phone1", "observations", "updated_at",
]
STOP = set("""a o as os um uma de da do das dos em no na nos nas e ou que qual quais quanto quantos quantas
como para por com sem se ser sao tem ter foi esta estao isso esse essa este me meu minha voce mi
qual sobre mais menos muito todas todos tudo pelo pela ate ja nao sim ola oi cliente clientes ordem ordens
servico roteiro roteiros rota rotas onde quem liste listar lista mostre mostrar encontre encontrar informe favor
pode poderia preciso quero saber dados informacao informacoes""".split())
_llm_state = {"openai_off_until": 0.0}
_routes_cache = {"ts": 0.0, "docs": []}

_os_cache = {"ts": 0.0, "docs": [], "blobs": [], "stats": ""}
_os_lock = asyncio.Lock()
_index_state = {"running": False, "last_check": 0.0}


def _norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return s.lower()


def _tokens(q: str):
    return [t for t in re.findall(r"[a-z0-9][a-z0-9./-]*", _norm(q)) if len(t) >= 3 and t not in STOP]


async def _load_os(db):
    async with _os_lock:
        if time.time() - _os_cache["ts"] < 600 and _os_cache["docs"]:
            return
        proj = {f: 1 for f in OS_FIELDS}
        docs, skip = [], 0
        while True:
            batch = await db.service_orders.find({}, proj).skip(skip).limit(1000).to_list(1000)
            docs += batch
            if len(batch) < 1000:
                break
            skip += 1000
        by_src_status = Counter((d.get("source") or "-", d.get("status") or "-") for d in docs)
        by_brand = Counter((d.get("brand") or "-").upper() for d in docs)
        lines = [f"Total de OSs no sistema: {len(docs)}", "Contagem por origem/status:"]
        lines += [f"- {s} | {st}: {n}" for (s, st), n in sorted(by_src_status.items())]
        lines.append("Top marcas: " + ", ".join(f"{b}: {n}" for b, n in by_brand.most_common(20)))
        _os_cache.update(ts=time.time(), docs=docs, stats="\n".join(lines),
                         blobs=[_norm(" ".join(str(v) for v in d.values() if v)) for d in docs])


def _search_os(q: str, limit: int = 25):
    toks = _tokens(q)
    nums = set(re.findall(r"\d{4,}", q))
    scored = []
    for d, blob in zip(_os_cache["docs"], _os_cache["blobs"]):
        s = (100 if str(d.get("os_number")) in nums else 0) + sum(
            1 for t in toks if t in blob or (len(t) >= 5 and t[:-2] in blob))
        if s > 0:
            scored.append((s, d.get("updated_at") or "", d))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [d for _, _, d in scored[:limit]]


def _pdf_pages(pdf: bytes):
    out = subprocess.run(["pdftotext", "-layout", "-", "-"], input=pdf, capture_output=True, timeout=180)
    return out.stdout.decode(errors="ignore").split("\f")


def _extract_pages(data: bytes, ext: str, cached_pdf: Optional[bytes]):
    if ext == "pdf":
        return _pdf_pages(data)
    if ext in ("pptx", "ppt"):
        return _pdf_pages(cached_pdf or _convert_pptx_to_pdf(data))
    if ext == "docx":
        import io
        import docx
        return ["\n".join(p.text for p in docx.Document(io.BytesIO(data)).paragraphs)]
    return []


async def index_manuals(db, mongo_db):
    """Sincroniza o índice com os manuais ativos: indexa novos/substituídos, remove apagados."""
    if _index_state["running"]:
        _index_state["again"] = True  # upload durante indexação: roda de novo ao terminar
        return
    _index_state.update(running=True, last_check=time.time())
    try:
        while True:
            _index_state["again"] = False
            await _index_pass(db, mongo_db)
            if not _index_state["again"]:
                break
    finally:
        _index_state["running"] = False


async def _index_pass(db, mongo_db):
    chunks_col, idx_col = mongo_db["mi_manual_chunks"], mongo_db["mi_manual_index"]
    await chunks_col.create_index([("text", "text"), ("title", "text")], default_language="portuguese")
    done = {d["manual_id"]: d.get("storage_path") async for d in idx_col.find({}, {"manual_id": 1, "storage_path": 1})}
    manuals = await db.manuais.find({"is_deleted": False}, {"_id": 0}).to_list(1000)
    gone = list(set(done) - {m["id"] for m in manuals})
    if gone:
        await chunks_col.delete_many({"manual_id": {"$in": gone}})
        await idx_col.delete_many({"manual_id": {"$in": gone}})
    for m in manuals:
        # Já indexado e arquivo não substituído (índices antigos sem storage_path contam como atuais).
        if m["id"] in done and done[m["id"]] in (None, m["storage_path"]):
            continue
        await chunks_col.delete_many({"manual_id": m["id"]})
        await idx_col.delete_many({"manual_id": m["id"]})
        extra = " ".join(x for x in (m.get("brand"), m.get("category")) if x)
        title = f"{m.get('original_filename', '')}" + (f" ({extra})" if extra else "")
        try:
            data, _ = await asyncio.to_thread(get_object, m["storage_path"])
            meta = await mongo_db["manuais_preview"].find_one({"manual_id": m["id"]}) or {}
            cached = None
            if meta.get("pdf_cache_path"):
                cached, _ = await asyncio.to_thread(get_object, meta["pdf_cache_path"])
            pages = await asyncio.to_thread(_extract_pages, data, (m.get("extension") or "").lower(), cached)
            docs = []
            for pnum, txt in enumerate(pages, 1):
                txt = re.sub(r"[ \t]+", " ", txt).strip()
                for i in range(0, len(txt), 1500):
                    docs.append({"manual_id": m["id"], "title": title, "page": pnum, "text": txt[i:i + 1600]})
            if docs:
                await chunks_col.insert_many(docs)
            await idx_col.insert_one({"manual_id": m["id"], "title": title, "chunks": len(docs),
                                      "storage_path": m["storage_path"], "indexed_at": datetime.now(timezone.utc)})
            logger.info(f"[Mi] manual indexado: {title} ({len(docs)} trechos)")
        except Exception as e:
            logger.error(f"[Mi] falha ao indexar {title}: {e!r}")


def _km(a_lat, a_lng, b_lat, b_lng):
    import math
    p = math.pi / 180
    h = math.sin((b_lat - a_lat) * p / 2) ** 2 + math.cos(a_lat * p) * math.cos(b_lat * p) * math.sin((b_lng - a_lng) * p / 2) ** 2
    return 12742 * math.asin(math.sqrt(h))


GEO_WORDS = ("proxim", "perto", "redor", "raio", "regiao", "vizinh", "bairro", "distancia", "localiza")


def _geo_context(q: str):
    """OSs perto de um bairro/cidade (centro = média das OSs desse bairro) ou de uma OS citada."""
    nq = _norm(q)
    if not any(w in nq for w in GEO_WORDS):
        return ""
    docs = [d for d in _os_cache["docs"] if isinstance(d.get("lat"), (int, float)) and isinstance(d.get("lng"), (int, float))]
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*km", nq)
    radius = float(m.group(1).replace(",", ".")) if m else 2.0
    label, pts = None, []
    nums = set(re.findall(r"\d{5,}", q))
    ref = next((d for d in docs if str(d.get("os_number")) in nums), None)
    if ref:
        label, pts = f"OS {ref['os_number']}", [(ref["lat"], ref["lng"])]
    else:
        for field, name in (("neighborhood", "bairro"), ("city", "cidade")):
            names = {_norm(d.get(field)).strip() for d in docs if d.get(field)}
            found = sorted((n for n in names if len(n) >= 4 and re.search(rf"\b{re.escape(n)}\b", nq)), key=len, reverse=True)
            if found:
                label = f"{name} {found[0]}"
                pts = [(d["lat"], d["lng"]) for d in docs if _norm(d.get(field)).strip() == found[0]]
                break
    if not pts:
        return ""
    c_lat, c_lng = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
    near = sorted(((round(_km(c_lat, c_lng, d["lat"], d["lng"]), 2), d) for d in docs), key=lambda x: x[0])
    near = [(k, d) for k, d in near if k <= radius]
    lines = [f"Centro: {label}; raio {radius} km; {len(near)} OSs encontradas (ordenadas por distância)."]
    lines += [f"- OS {d.get('os_number')}; {k} km; status {d.get('status')}; {d.get('address') or ''} {d.get('number') or ''}, "
              f"{d.get('neighborhood') or ''}, {d.get('city') or ''}; cliente {d.get('customer_name') or ''}; "
              f"{d.get('product') or d.get('model') or ''}" for k, d in near[:150]]
    return "\n".join(lines)


async def _routes_context(db, q: str = ""):
    """Roteiros que batem com a pergunta (nome/técnico/data/OS/cliente, mesmo parcial) com detalhe + 15 recentes."""
    if time.time() - _routes_cache["ts"] > 120:
        _routes_cache.update(ts=time.time(), docs=await db.routes.find({}, {"_id": 0}).sort("created_at", -1).to_list(2000))
    routes = _routes_cache["docs"]
    toks = _tokens(q)
    nums = set(re.findall(r"\d{4,}", q))

    def orders_of(r):
        return [o for o in (r.get("orders") if isinstance(r.get("orders"), list) else []) if isinstance(o, dict)]

    def head(r):
        return (f"{r.get('name')}; id {r.get('id')}; técnico {r.get('technician') or '-'}; data {r.get('date')}; "
                f"status {r.get('status')}; {r.get('total_distance') or ''} {r.get('total_duration') or ''}")

    scored = []
    for r in routes:
        blob = _norm(" ".join(str(v) for v in (r.get("name"), r.get("technician"), r.get("date"), r.get("status")))
                     + " " + " ".join(f"{o.get('os_number')} {o.get('customer_name')} {o.get('neighborhood')}" for o in orders_of(r)))
        s = sum(1 for t in toks if t in blob) + sum(50 for n in nums if n in blob)
        if s:
            scored.append((s, r))
    scored.sort(key=lambda x: x[0], reverse=True)
    lines = []
    for _, r in scored[:8]:
        lines.append("- " + head(r))
        lines += [f"    {o.get('sequence')}. OS {o.get('os_number')}; {o.get('customer_name') or ''}; {o.get('address') or ''} "
                  f"{o.get('number') or ''} {o.get('complement') or ''}, {o.get('neighborhood') or ''}, {o.get('city') or ''}; "
                  f"status {o.get('status') or ''}" for o in orders_of(r)]
    lines.append("Recentes:")
    lines += ["- " + head(r) + "; OSs: " + ", ".join(str(o.get("os_number")) for o in orders_of(r)) for r in routes[:15]]
    return "\n".join(lines)


async def _search_manuals(mongo_db, q: str, limit: int = 8):
    toks = _tokens(q)
    if not toks:
        return []
    cur = mongo_db["mi_manual_chunks"].find(
        {"$text": {"$search": " ".join(toks)}},
        {"_id": 0, "title": 1, "page": 1, "text": 1, "score": {"$meta": "textScore"}},
    ).sort([("score", {"$meta": "textScore"})]).limit(limit)
    return await cur.to_list(limit)


SYSTEM = (
    "Você é a Mi, assistente da Mastermaq (assistência técnica de eletrodomésticos em Belo Horizonte). "
    "Responda sempre em português do Brasil. Use SOMENTE os dados de contexto fornecidos (OSs, roteiros, "
    "localização das OSs e trechos de manuais). Ao usar um manual, cite o nome do manual e a página. "
    "Para ajudar a montar roteiros, agrupe OSs próximas pela distância informada (máximo 9 OSs por roteiro). "
    "Se a informação não estiver no contexto, diga que não encontrou — nunca invente números, códigos, peças ou procedimentos.\n"
    "FORMATO (obrigatório): responda como o ChatGPT numa conversa normal — vá direto ao ponto, sem repetir a "
    "pergunta e sem frases de enchimento. Parágrafos curtos; listas com '-' ou '1.' quando houver vários itens. "
    "NUNCA use tabelas, barras verticais '|', linhas '---', citações '>' ou blocos de código. "
    "Use **negrito** só para destacar o essencial. Em listas de OSs, uma OS por linha: número, distância, endereço e status."
)


async def _ollama_chat(prompt: str) -> str:
    """Fallback: Ollama Cloud quando a Universal Key falha (ex: saldo esgotado)."""
    import httpx
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(
            f"{os.environ['OLLAMA_BASE_URL']}/api/chat",
            headers={"Authorization": f"Bearer {os.environ['OLLAMA_API_KEY']}"},
            json={"model": os.environ["OLLAMA_MODEL"], "stream": False,
                  "messages": [{"role": "system", "content": SYSTEM_FULL}, {"role": "user", "content": prompt}]},
        )
        r.raise_for_status()
        return (r.json().get("message", {}).get("content") or "").strip()


class ChatBody(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    attachment_name: Optional[str] = None
    attachment_text: Optional[str] = None
    attachment_file_id: Optional[str] = None
    photo_ids: List[str] = []


SYSTEM_FULL = (SYSTEM + "\nREGIONAIS DE SABARÁ (use para localizar OSs e montar roteiros):\n" + mi_agent.regions_text()
               + "\n\n" + mi_agent.ACTIONS_PROMPT)


def setup_mi_routes(api_router: APIRouter, db, mongo_db, require_admin):
    convs, msgs = mongo_db["mi_conversations"], mongo_db["mi_messages"]

    async def _own_conv(cid: str, email: str):
        c = await convs.find_one({"id": cid, "user_email": email}, {"_id": 0})
        if not c:
            raise HTTPException(status_code=404, detail="Conversa não encontrada")
        return c

    @api_router.get("/mi/conversations")
    async def list_convs(payload: dict = Depends(require_admin)):
        return await convs.find({"user_email": payload["email"]}, {"_id": 0}).sort("updated_at", -1).to_list(200)

    @api_router.get("/mi/conversations/{cid}/messages")
    async def list_msgs(cid: str, payload: dict = Depends(require_admin)):
        await _own_conv(cid, payload["email"])
        return await msgs.find({"conversation_id": cid}, {"_id": 0}).sort("created_at", 1).to_list(1000)

    @api_router.delete("/mi/conversations/{cid}")
    async def delete_conv(cid: str, payload: dict = Depends(require_admin)):
        await _own_conv(cid, payload["email"])
        await convs.delete_one({"id": cid})
        await msgs.delete_many({"conversation_id": cid})
        return {"ok": True}

    @api_router.get("/mi/status")
    async def mi_status(_: dict = Depends(require_admin)):
        return {
            "manuais_indexados": await mongo_db["mi_manual_index"].count_documents({}),
            "trechos": await mongo_db["mi_manual_chunks"].count_documents({}),
            "indexando": _index_state["running"],
        }

    @api_router.post("/mi/upload")
    async def mi_upload(file: UploadFile = File(...), _: dict = Depends(require_admin)):
        data = await file.read()
        if (file.content_type or "").startswith("image/") or re.search(r"\.(jpe?g|png|webp|heic)$", file.filename or "", re.I):
            from laudo_generator import _to_jpeg_bytes
            from manuais_module import put_object
            pid = uuid.uuid4().hex
            jpg = await asyncio.to_thread(_to_jpeg_bytes, data)
            await asyncio.to_thread(put_object, f"{mi_agent.FILE_PREFIX}/{pid}.jpg", jpg, "image/jpeg")
            return {"name": file.filename, "photo_id": pid}
        try:
            text = await asyncio.to_thread(mi_agent.extract_upload, data, file.filename or "")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        # DOCX: guarda o original para a Mi editar sem perder layout.
        fid = await mi_agent.store_upload(data) if (file.filename or "").lower().endswith(".docx") else None
        return {"name": file.filename, "text": text[:60000], "chars": len(text), "file_id": fid}

    @api_router.get("/mi/files/{name}")
    async def mi_file(name: str):
        """Download público (token aleatório) dos arquivos gerados pela Mi."""
        m = re.fullmatch(r"([0-9a-f]{32})\.(pdf|docx|jpg)", name)
        if not m:
            raise HTTPException(status_code=404, detail="Arquivo inexistente")
        try:
            data, ctype = await asyncio.to_thread(get_object, f"{mi_agent.FILE_PREFIX}/{name}")
        except Exception:
            raise HTTPException(status_code=404, detail="Arquivo inexistente")
        from fastapi.responses import Response
        disp = "attachment" if m.group(2) == "docx" else "inline"
        return Response(content=data, media_type=ctype,
                        headers={"Content-Disposition": f'{disp}; filename="documento_mi.{m.group(2)}"'})

    @api_router.get("/mi/memories")
    async def list_memories(payload: dict = Depends(require_admin)):
        return await mi_agent.get_memories(mongo_db, payload["email"])

    @api_router.delete("/mi/memories/{mid}")
    async def delete_memory(mid: str, payload: dict = Depends(require_admin)):
        await mongo_db["mi_memories"].delete_one({"id": mid, "user_email": payload["email"]})
        return {"ok": True}

    async def _set_action_status(aid, status, result, urls=None):
        extra = {f"actions.$.{k}": v for k, v in (urls or {}).items()}
        await mongo_db["mi_actions"].update_one({"id": aid}, {"$set": {"status": status, "result": result}})
        await msgs.update_one({"actions.id": aid}, {"$set": {"actions.$.status": status, "actions.$.result": result, **extra}})

    @api_router.post("/mi/actions/{aid}/{decision}")
    async def decide_action(aid: str, decision: str, payload: dict = Depends(require_admin)):
        act = await mongo_db["mi_actions"].find_one({"id": aid, "user_email": payload["email"]}, {"_id": 0})
        if not act or act["status"] != "pending":
            raise HTTPException(status_code=404, detail="Ação não encontrada ou já decidida")
        if decision == "cancel":
            await _set_action_status(aid, "canceled", "Cancelada")
            return {"status": "canceled", "result": "Cancelada"}
        urls = {}
        try:
            result = await mi_agent.execute(db, act["action"], payload)
            if isinstance(result, dict):
                urls = {k: result[k] for k in ("url", "url2") if result.get(k)}
                result = result.get("text") or "Feito"
            status = "done"
        except Exception as e:
            result, status = f"Erro: {e}", "error"
        await _set_action_status(aid, status, result, urls)
        return {"status": status, "result": result, **urls}

    @api_router.post("/mi/chat")
    async def mi_chat(body: ChatBody, payload: dict = Depends(require_admin)):
        text = (body.message or "").strip()
        if not text:
            raise HTTPException(status_code=400, detail="Mensagem vazia")
        email = payload["email"]
        now = datetime.now(timezone.utc).isoformat()
        if body.conversation_id:
            conv = await _own_conv(body.conversation_id, email)
        else:
            conv = {"id": str(uuid.uuid4()), "user_email": email, "title": text[:60], "created_at": now, "updated_at": now}
            await convs.insert_one(dict(conv))
        cid = conv["id"]

        # Novos manuais já entram no upload; isto é só rede de segurança (10 min).
        if time.time() - _index_state["last_check"] > 600:
            asyncio.create_task(index_manuals(db, mongo_db))

        history = await msgs.find({"conversation_id": cid}, {"_id": 0}).sort("created_at", -1).to_list(10)
        await msgs.insert_one({"id": str(uuid.uuid4()), "conversation_id": cid, "role": "user", "content": text,
                               "attachment_name": body.attachment_name, "attachment_text": body.attachment_text,
                               "attachment_file_id": body.attachment_file_id, "photo_ids": body.photo_ids, "created_at": now})
        conv_photos = [p async for m in msgs.find({"conversation_id": cid, "role": "user"}, {"photo_ids": 1}).sort("created_at", 1)
                       for p in (m.get("photo_ids") or [])][-8:]
        attach = body.attachment_text and (body.attachment_name, body.attachment_text)
        file_id = body.attachment_file_id
        if not attach:
            prev = await msgs.find_one({"conversation_id": cid, "attachment_text": {"$nin": [None, ""]}}, {"_id": 0}, sort=[("created_at", -1)])
            attach = prev and (prev["attachment_name"], prev["attachment_text"])
            file_id = prev and prev.get("attachment_file_id")
        memories = await mi_agent.get_memories(mongo_db, email)

        await _load_os(db)
        hist_q = " ".join(m["content"] for m in history if m["role"] == "user")[-400:]
        os_hits = _search_os(f"{text} {hist_q}")
        man_hits = await _search_manuals(mongo_db, f"{text} {hist_q[-150:]}", limit=10)
        geo_txt = _geo_context(text) or _geo_context(f"{text} {hist_q}")
        region_txt = mi_agent.region_context(text, _os_cache["docs"])
        routes_txt = await _routes_context(db, f"{text} {hist_q[-200:]}")
        titles = [d["title"] async for d in mongo_db["mi_manual_index"].find({}, {"title": 1})]
        wa_txt = ""
        if re.search(r"whats|zap|wpp|mensag", text, re.I):
            wa = (await db.whatsapp_messages.find({"direction": "inbound"}, {"_id": 0}).sort("received_at", -1).to_list(20)
                  + await db.whatsapp_messages.find({"direction": "outbound"}, {"_id": 0}).sort("sent_at", -1).to_list(20))
            wa_txt = "\n".join(f"{'←' if m.get('direction') == 'inbound' else '→'} {m.get('from') or m.get('to')} "
                               f"{m.get('contact_name') or ''} [{m.get('status') or ''}] {(m.get('body') or '')[:200]}" for m in wa)

        os_txt = "\n".join("; ".join(f"{k}={v}" for k, v in d.items() if v) for d in os_hits) or "(nenhuma OS relacionada)"
        man_txt = "\n\n".join(f"[{h['title']} — pág. {h['page']}]\n{h['text']}" for h in man_hits) or "(nenhum trecho encontrado)"
        hist_txt = "\n".join(f"{'Usuário' if m['role'] == 'user' else 'Mi'}: {m['content'][:1500]}" for m in reversed(history))
        prompt = (
            f"Data de hoje: {datetime.now().strftime('%d/%m/%Y')}\n\n"
            + ("## Memória permanente (fatos que o usuário pediu para lembrar)\n" + "\n".join(f"- {m['fact']}" for m in memories) + "\n\n" if memories else "")
            + (f"## Documento anexado: {attach[0]}\n{attach[1][:40000]}\n\n" if attach else "")
            + f"## Resumo do banco de OSs\n{_os_cache['stats']}\n\n"
            f"## OSs relacionadas à pergunta\n{os_txt}\n\n"
            + (f"## Localização (OSs próximas, calculado pelas coordenadas)\n{geo_txt}\n\n" if geo_txt else "")
            + (f"## OSs por regional de Sabará\n{region_txt}\n\n" if region_txt else "")
            + (f"## WhatsApp — últimas mensagens (← recebida, → enviada)\n{wa_txt or '(nenhuma)'}\n\n" if wa_txt or re.search(r"whats|zap|wpp|mensag", text, re.I) else "")
            + f"## Roteiros (os que batem com a pergunta em detalhe + recentes)\n{routes_txt}\n\n"
            f"## Manuais disponíveis\n" + "\n".join(f"- {t}" for t in titles) + "\n\n"
            f"## Trechos de manuais relevantes\n{man_txt}\n\n"
            + (f"## Fotos enviadas nesta conversa: {len(conv_photos)} (serão FOTO 1..{len(conv_photos)} do laudo)\n\n" if conv_photos else "")
            + f"## Conversa anterior\n{hist_txt or '(início)'}\n\n"
            f"## Pergunta\n{text}"
        )
        try:
            # Universal Key sem saldo: pula direto p/ Ollama por 10 min (evita esperar o erro a cada pergunta).
            if time.time() < _llm_state["openai_off_until"]:
                raise RuntimeError("openai em pausa")
            from emergentintegrations.llm.chat import LlmChat, UserMessage
            chat = LlmChat(api_key=os.environ["EMERGENT_LLM_KEY"], session_id=f"mi-{cid}", system_message=SYSTEM_FULL).with_model("openai", MODEL)
            answer = (await chat.send_message(UserMessage(text=prompt)) or "").strip()
        except Exception as e:
            if "pausa" not in str(e):
                _llm_state["openai_off_until"] = time.time() + 600
                logger.warning(f"[Mi] Universal Key falhou, usando Ollama: {e!r}")
            try:
                answer = await _ollama_chat(prompt)
            except Exception as e2:
                logger.error(f"[Mi] Ollama falhou: {e2!r}")
                raise HTTPException(status_code=424, detail="Falha ao consultar a IA (Universal Key e Ollama).")

        answer, acts = mi_agent.parse_actions(answer)
        actions = []
        for a in acts:
            aid = str(uuid.uuid4())
            if a["type"] == "remember":
                await mi_agent.remember(mongo_db, email, a.get("fact"))
                actions.append({"id": aid, "type": "remember", "summary": f"Memorizado: {a.get('fact')}", "status": "done"})
            elif a["type"] == "generate_pdf":
                try:
                    url = await mi_agent.generate_pdf(a.get("title"), a.get("content"))
                    actions.append({"id": aid, "type": "pdf", "summary": a.get("title") or "Documento", "status": "done", "url": url})
                except Exception as e:
                    logger.error(f"[Mi] PDF falhou: {e!r}")
                    actions.append({"id": aid, "type": "pdf", "summary": "Falha ao gerar PDF", "status": "error"})
            elif a["type"] == "edit_docx":
                try:
                    if not file_id:
                        raise ValueError("nenhum DOCX anexado nesta conversa")
                    url, n = await mi_agent.edit_docx(file_id, a.get("replacements") or [], bool(a.get("pdf")))
                    actions.append({"id": aid, "type": "pdf", "summary": f"Documento editado ({n} trecho(s) alterado(s))", "status": "done", "url": url})
                except Exception as e:
                    logger.error(f"[Mi] edit_docx falhou: {e!r}")
                    actions.append({"id": aid, "type": "pdf", "summary": f"Falha ao editar documento: {e}", "status": "error"})
            elif a["type"] == "simulate_route":
                try:
                    txt = await mi_agent.simulate_route(db, a)
                    answer = f"{answer}\n\n{txt}".strip()
                    actions.append({"id": aid, "type": "route", "summary": "Rota simulada (nada foi gravado)", "status": "done"})
                except Exception as e:
                    logger.error(f"[Mi] simulate_route falhou: {e!r}")
                    actions.append({"id": aid, "type": "route", "summary": f"Não consegui calcular a rota: {getattr(e, 'detail', e)}", "status": "error"})
            elif a["type"] in mi_agent.CONFIRM_TYPES:
                if a["type"] == "generate_laudo" and not a.get("photos"):
                    a["photos"] = conv_photos
                await mongo_db["mi_actions"].insert_one({"id": aid, "user_email": email, "conversation_id": cid, "action": a,
                                                         "status": "pending", "created_at": now})
                actions.append({"id": aid, "type": a["type"], "summary": mi_agent.summarize(a), "status": "pending"})

        done = datetime.now(timezone.utc).isoformat()
        reply = {"id": str(uuid.uuid4()), "conversation_id": cid, "role": "assistant", "content": answer,
                 "actions": actions, "created_at": done}
        await msgs.insert_one(dict(reply))
        await convs.update_one({"id": cid}, {"$set": {"updated_at": done}})
        return {"conversation_id": cid, "title": conv["title"], "message": reply}
