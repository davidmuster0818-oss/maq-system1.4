"""Mi agent: memória persistente, ações (roteiros/OSs), PDFs, anexos e regiões de Sabará."""
import io
import re
import json
import uuid
import asyncio
import logging
import unicodedata
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _n(s) -> str:
    return unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower().strip()


REGIONS = {
    "Regional Sede (Centro Histórico e Entorno)": ["Adelmolândia", "Alto do Cabral", "Alto São Francisco", "Arraial Velho",
        "Centro", "Coração de Jesus", "Esplanada", "Mangabeiras", "Morro São Francisco", "Paciência", "Siderúrgica", "Vila Santa Rita"],
    "Distrito de Carvalho de Brito (Eixo General Carneiro / divisa com BH)": ["Alvorada", "Castanheiras", "General Carneiro",
        "Itacolomi", "Nações Unidas", "Novo Alvorada", "Roça Grande", "Santo Antônio de Roça Grande", "Vila Michel"],
    "Regional Ana Lúcia / Nova Vista": ["Ana Lúcia", "Bom Retiro", "Nova Vista", "Novo Santa Inês", "Rio Negro", "Vila Ribeiro"],
    "Regional Borges / Km 14": ["Borges", "Km 14", "Morada da Serra", "Pompéu"],
    "Distrito de Ravena": ["Ravena", "Centro de Ravena"],
    "Distrito de Mestre Caetano": ["Mestre Caetano", "Km 25"],
}
REGION_KEYS = {  # termos que identificam a regional na pergunta
    "Regional Sede (Centro Histórico e Entorno)": ["regional sede", "centro historico"],
    "Distrito de Carvalho de Brito (Eixo General Carneiro / divisa com BH)": ["carvalho de brito", "general carneiro"],
    "Regional Ana Lúcia / Nova Vista": ["ana lucia", "nova vista"],
    "Regional Borges / Km 14": ["borges", "km 14"],
    "Distrito de Ravena": ["ravena"],
    "Distrito de Mestre Caetano": ["mestre caetano"],
}


def regions_text() -> str:
    return "\n".join(f"- {r}: {', '.join(b)}" for r, b in REGIONS.items())


def region_context(q: str, docs: list) -> str:
    """OSs de Sabará cuja bairro pertence à regional citada na pergunta."""
    nq = _n(q)
    if "sabara" not in nq and not any(k in nq for ks in REGION_KEYS.values() for k in ks):
        return ""
    out = []
    for region, keys in REGION_KEYS.items():
        if not any(k in nq for k in keys) and "sabara" not in nq:
            continue
        bairros = {_n(b) for b in REGIONS[region]}
        hits = [d for d in docs if "sabara" in _n(d.get("city")) and _n(d.get("neighborhood")) in bairros]
        if not any(k in nq for k in keys) and not hits:
            continue
        out.append(f"{region}: {len(hits)} OSs")
        out += [f"- OS {d.get('os_number')}; status {d.get('status')}; {d.get('address') or ''} {d.get('number') or ''}, "
                f"{d.get('neighborhood')}; cliente {d.get('customer_name') or ''}; {d.get('product') or d.get('model') or ''}"
                for d in hits[:80]]
    return "\n".join(out)


# --- Memória persistente (por usuário, vale para todas as conversas) ---
async def get_memories(mongo_db, email: str):
    return await mongo_db["mi_memories"].find({"user_email": email}, {"_id": 0}).sort("created_at", -1).to_list(200)


async def remember(mongo_db, email: str, fact: str):
    fact = (fact or "").strip()
    if fact:
        await mongo_db["mi_memories"].insert_one({"id": str(uuid.uuid4()), "user_email": email, "fact": fact[:1000],
                                                  "created_at": datetime.now(timezone.utc).isoformat()})


# --- Ações ---
ACTIONS_PROMPT = (
    "AÇÕES: você pode agir no sistema. Quando o usuário pedir (ou quando for claramente útil), inclua no FINAL da resposta "
    "um bloco <acoes>[...]</acoes> com um array JSON. Tipos:\n"
    '- {"type":"remember","fact":"..."} → guarda na memória permanente (use sempre que o usuário pedir para lembrar, '
    "ou contar preferência/fato duradouro).\n"
    '- {"type":"create_route","name":"...","technician":"...","date":"AAAA-MM-DD","os_numbers":["..."]} (máx. 9 OSs)\n'
    '- {"type":"update_route","route":"nome ou id","fields":{"date":"AAAA-MM-DD","technician":"...","status":"Pendente|Em andamento|Concluído|Cancelado","name":"..."},'
    '"add_os":["..."],"remove_os":["..."]}\n'
    '- {"type":"update_os","os_number":"...","fields":{"status":"...","technician":"...","observations":"...","attendance_date":"AAAA-MM-DD", ...}}\n'
    '- {"type":"create_os","fields":{"customer_name":"...","phone1":"...","cep":"...","address":"...","number":"...","complement":"...",'
    '"neighborhood":"...","city":"...","product":"...","brand":"...","model":"...","reported_defect":"...","service_type":"..."}} '
    "(número da OS é gerado automaticamente se não informado)\n"
    '- {"type":"edit_docx","replacements":[{"find":"texto exato do documento","replace":"novo texto"}],"pdf":false} → edita o '
    "DOCX anexado mantendo layout e todo o resto do conteúdo igual (só troca os trechos indicados; use pdf=true para entregar em PDF).\n"
    '- {"type":"send_whatsapp","os_number":"... (ou \"phone\":\"31999999999\")","text":"mensagem"} → envia WhatsApp pelo número oficial '
    "da Mastermaq (o cliente precisa ter falado com a empresa nas últimas 24h, senão a Meta recusa).\n"
    '- {"type":"delete_os","os_number":"..."} → exclui a OS definitivamente.\n'
    '- {"type":"sync_orders"} → puxa as ordens do Telecontrol (Hisense e HQ ao mesmo tempo, do último mês até hoje).\n'
    '- {"type":"generate_laudo","os_number":"...","technical_diagnosis":"...","installation_correct":"SIM|NÃO","required_parts":"...",'
    '"technical_notes":"...","final_status":"..."} → gera o laudo com as fotos enviadas na conversa (na ordem FOTO 1..8; '
    "as que faltarem vêm da OS). Escreva technical_diagnosis ESTENDIDO, técnico e profissional, a partir do que o usuário "
    "informou, sem inventar fatos. OS do Telecontrol Hisense usa o modelo Hisense; OS da loja gera o laudo Mastermaq digital. "
    "Se o usuário não disser o número da OS, pergunte antes.\n"
    '- {"type":"simulate_route","os_numbers":["..."],"optimize":true,"origin":"base | lat,lng | endereço","return_to_base":true} '
    "→ calcula NA HORA a rota real (Google, com trânsito): ordem otimizada, km e minutos por trecho e total, link do Maps. "
    "Não grava nada. Use sempre que pedirem para calcular/simular rota ou roteiro; nunca invente distâncias.\n"
    '- {"type":"generate_pdf","title":"...","content":"texto completo do documento"} → gera PDF novo do zero e devolve link.\n'
    "Ações create_route/update_route/update_os/create_os/send_whatsapp/delete_os/sync_orders/generate_laudo ficam aguardando o usuário clicar em Confirmar; diga isso em uma frase. "
    "Nunca escreva o JSON fora do bloco <acoes>."
)
OS_EDITABLE = {"status", "technician", "observations", "attendance_date", "priority", "reported_defect", "technical_diagnosis",
               "required_parts", "customer_name", "phone1", "address", "number", "neighborhood", "city", "model",
               "serial_number", "product", "service_type"}
CONFIRM_TYPES = {"create_route", "update_route", "update_os", "create_os", "send_whatsapp", "delete_os", "sync_orders", "generate_laudo"}
CREATE_OS = None  # injetado pelo server.py (cria OS reutilizando o endpoint)
SYNC_ORDERS = None  # injetado pelo server.py (sync Hisense + HQ)
BASE = (-19.8881334, -43.9420748)


def parse_actions(answer: str):
    m = re.search(r"<acoes>(.*?)</acoes>", answer or "", re.S)
    if not m:
        return answer, []
    try:
        acts = json.loads(m.group(1).strip())
        acts = acts if isinstance(acts, list) else [acts]
    except Exception:
        acts = []
    return (answer[:m.start()] + answer[m.end():]).strip(), [a for a in acts if isinstance(a, dict) and a.get("type")]


def summarize(a: dict) -> str:
    t = a.get("type")
    if t == "create_route":
        return f"Criar roteiro \"{a.get('name') or 'Roteiro'}\" — {a.get('technician')}, {a.get('date')}, OSs {', '.join(map(str, a.get('os_numbers') or []))}"
    if t == "update_route":
        extra = [f"{k}={v}" for k, v in (a.get("fields") or {}).items()]
        if a.get("add_os"):
            extra.append("+OS " + ", ".join(map(str, a["add_os"])))
        if a.get("remove_os"):
            extra.append("-OS " + ", ".join(map(str, a["remove_os"])))
        return f"Alterar roteiro \"{a.get('route')}\": {'; '.join(extra)}"
    if t == "update_os":
        return f"Alterar OS {a.get('os_number')}: " + "; ".join(f"{k}={v}" for k, v in (a.get("fields") or {}).items())
    if t == "delete_os":
        return f"EXCLUIR OS {a.get('os_number')} (definitivo)"
    if t == "sync_orders":
        return "Puxar ordens do Telecontrol (Hisense + HQ, último mês)"
    if t == "generate_laudo":
        n = len(a.get("photos") or [])
        return f"Gerar laudo da OS {a.get('os_number')} com {n} foto(s) enviada(s) — diagnóstico: {(a.get('technical_diagnosis') or '')[:300]}"
    if t == "send_whatsapp":
        return f"Enviar WhatsApp para {a.get('os_number') and 'OS ' + str(a['os_number']) or a.get('phone')}: \"{a.get('text')}\""
    if t == "create_os":
        return "Criar OS: " + "; ".join(f"{k}={v}" for k, v in (a.get("fields") or {}).items() if v)
    return t


async def _route_orders(db, os_numbers):
    orders = []
    for i, num in enumerate(os_numbers, 1):
        d = await db.service_orders.find_one({"os_number": str(num)}, {"_id": 0})
        if not d:
            raise ValueError(f"OS {num} não encontrada")
        orders.append({k: d.get(k) for k in ("os_number", "customer_name", "neighborhood", "city", "address", "number",
                                             "phone1", "lat", "lng", "attendance_date", "status")} | {"sequence": i})
    return orders


async def execute(db, a: dict, payload: dict = None):
    """Executa ação confirmada. Retorna texto de resultado."""
    from routes_module import create_route, update_route, RouteCreate, RouteUpdate
    t = a["type"]
    if t == "delete_os":
        num = str(a.get("os_number") or "")
        res = await db.service_orders.delete_one({"os_number": num})
        if not res.deleted_count:
            raise ValueError(f"OS {num} não encontrada")
        return f"OS {num} excluída."
    if t == "sync_orders":
        return await SYNC_ORDERS()
    if t == "generate_laudo":
        return await _generate_laudo(db, a)
    if t == "send_whatsapp":
        from whatsapp_module import send_text
        phone = a.get("phone")
        if a.get("os_number"):
            d = await db.service_orders.find_one({"os_number": str(a["os_number"])}, {"phone1": 1}) or {}
            phone = d.get("phone1")
            if not phone:
                raise ValueError(f"OS {a['os_number']} sem telefone")
        sent_to = await send_text(db, phone, a.get("text") or "")
        return f"WhatsApp enviado para {sent_to}."
    if t == "create_os":
        r = await CREATE_OS(dict(a.get("fields") or {}), payload or {})
        num = r.get("os_number") if isinstance(r, dict) else getattr(r, "os_number", None)
        return f"OS {num} criada."
    if t == "create_route":
        nums = list(a.get("os_numbers") or [])[:9]
        r = await create_route(RouteCreate(name=a.get("name"), technician=a.get("technician") or "", date=a.get("date") or "",
                                           orders=await _route_orders(db, nums)), payload or {})
        return f"Roteiro \"{r.get('name')}\" criado com {len(nums)} OSs."
    if t == "update_route":
        ref = str(a.get("route") or "")
        route = await db.routes.find_one({"id": ref}, {"_id": 0}) or await db.routes.find_one({"name": ref}, {"_id": 0})
        if not route:
            raise ValueError(f"Roteiro \"{ref}\" não encontrado")
        fields = {k: v for k, v in (a.get("fields") or {}).items() if k in {"date", "technician", "status", "name"}}
        if a.get("add_os") or a.get("remove_os"):
            remove = {str(x) for x in a.get("remove_os") or []}
            keep = [str(o["os_number"]) for o in route.get("orders") or [] if str(o.get("os_number")) not in remove]
            fields["orders"] = await _route_orders(db, (keep + [str(x) for x in a.get("add_os") or [] if str(x) not in keep])[:9])
        await update_route(route["id"], RouteUpdate(**fields), payload or {})
        return f"Roteiro \"{route.get('name')}\" atualizado."
    if t == "update_os":
        fields = {k: v for k, v in (a.get("fields") or {}).items() if k in OS_EDITABLE}
        if not fields:
            raise ValueError("Nenhum campo permitido para alterar")
        fields["updated_at"] = datetime.now(timezone.utc).isoformat()
        if "observations" in fields:  # acrescenta, não apaga (ex: "[SITE] Taxa de visita PAGA")
            cur = await db.service_orders.find_one({"os_number": str(a.get("os_number"))}, {"observations": 1}) or {}
            if cur.get("observations"):
                fields["observations"] = f"{cur['observations']}\n{fields['observations']}"
        res = await db.service_orders.update_one({"os_number": str(a.get("os_number"))}, {"$set": fields})
        if not res.matched_count:
            raise ValueError(f"OS {a.get('os_number')} não encontrada")
        return f"OS {a.get('os_number')} atualizada."
    raise ValueError(f"Ação desconhecida: {t}")


# --- Laudo ---
LAUDO_FIELDS = ("os_number", "customer_name", "model", "serial_number", "batch", "brand", "service_type", "reported_defect",
                "technical_diagnosis", "installation_correct", "required_parts", "technician",
                "voltage_f1f2", "voltage_f1_terra", "voltage_f2_terra")


async def _generate_laudo(db, a: dict) -> dict:
    import base64
    from manuais_module import get_object, put_object
    num = str(a.get("os_number") or "")
    o = await db.service_orders.find_one({"os_number": num}, {"_id": 0})
    if not o:
        raise ValueError(f"OS {num} não encontrada")
    sent = []
    for pid in a.get("photos") or []:
        data, _ = await asyncio.to_thread(get_object, f"{FILE_PREFIX}/{pid}.jpg")
        sent.append("data:image/jpeg;base64," + base64.b64encode(data).decode())
    images = [sent[i] if i < len(sent) else (o.get(f"photo_{i + 1}") or "") for i in range(8)]
    fields = {k: str(a[k]) for k in ("technical_diagnosis", "installation_correct", "required_parts", "technical_notes", "final_status") if a.get(k)}
    d = {**{k: str(o.get(k) or "") for k in LAUDO_FIELDS}, **fields, "images": images,
         "location": "BELO HORIZONTE", "date": datetime.now().strftime("%d/%m/%Y"), "photo_labels": []}
    upd = {k: v for k, v in fields.items() if k in ("technical_diagnosis", "installation_correct", "required_parts")}
    if upd:
        await db.service_orders.update_one({"os_number": num}, {"$set": {**upd, "updated_at": datetime.now(timezone.utc).isoformat()}})
    if o.get("source") == "telecontrol_hisense":
        from laudo_generator import generate_laudo_from_template
        docx = await asyncio.to_thread(generate_laudo_from_template, d)
        tok = uuid.uuid4().hex
        await asyncio.to_thread(put_object, f"{FILE_PREFIX}/{tok}.docx", docx,
                                "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        res = {"text": f"Laudo Hisense da OS {num} gerado.", "url2": f"/api/mi/files/{tok}.docx"}
        try:
            pdf = await asyncio.to_thread(_docx_to_pdf, docx)
            await asyncio.to_thread(put_object, f"{FILE_PREFIX}/{tok}.pdf", pdf, "application/pdf")
            res["url"] = f"/api/mi/files/{tok}.pdf"
        except Exception as e:
            logger.warning(f"[Mi] laudo PDF falhou (DOCX ok): {e!r}")
        return res
    import laudo_digital
    r = await laudo_digital.create(d)
    return {"text": f"Laudo Mastermaq digital da OS {num} gerado.", "url": r["path"]}


# --- Rota ---
async def simulate_route(db, a: dict) -> str:
    from routes_module import compute_route, ComputeRouteRequest, Waypoint
    from urllib.parse import quote
    orders = []
    for n in [str(x) for x in (a.get("os_numbers") or [])][:25]:
        d = await db.service_orders.find_one({"os_number": n}, {"_id": 0, "os_number": 1, "customer_name": 1, "lat": 1, "lng": 1,
                                                              "address": 1, "number": 1, "neighborhood": 1, "city": 1})
        if d:
            orders.append(d)
    if not orders:
        raise ValueError("nenhuma das OSs foi encontrada")

    def wp(o):
        try:
            return Waypoint(lat=float(o["lat"]), lng=float(o["lng"]))
        except (KeyError, TypeError, ValueError):
            return Waypoint(address=", ".join(str(o.get(k)) for k in ("address", "number", "neighborhood", "city") if o.get(k)) + ", MG")

    base = Waypoint(lat=BASE[0], lng=BASE[1])
    org = str(a.get("origin") or "base").strip()
    m = re.fullmatch(r"(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)", org)
    origin = base if org.lower() == "base" else (Waypoint(lat=float(m[1]), lng=float(m[2])) if m else Waypoint(address=org))
    ret = a.get("return_to_base", True) is not False
    inter = orders if ret else orders[:-1]
    data = await compute_route(ComputeRouteRequest(origin=origin, destination=base if ret else wp(orders[-1]),
                                                   intermediates=[wp(o) for o in inter], round_trip=ret,
                                                   optimize_waypoint_order=a.get("optimize", True) is not False))
    route = data["routes"][0]
    idx = route.get("optimizedIntermediateWaypointIndex") or list(range(len(inter)))
    seq = [inter[i] for i in idx] + ([] if ret else [orders[-1]])
    legs = route.get("legs") or []
    km = lambda lg: (lg.get("distanceMeters") or 0) / 1000  # noqa: E731
    mins = lambda lg: round(int(str(lg.get("duration") or "0s").rstrip("s") or 0) / 60)  # noqa: E731
    lines = ["**Rota calculada (Google, com trânsito agora)**"]
    for i, o in enumerate(seq):
        lg = legs[i] if i < len(legs) else {}
        lines.append(f"{i + 1}. OS {o['os_number']} — {o.get('customer_name') or ''} ({o.get('neighborhood') or ''}) — {km(lg):.1f} km, {mins(lg)} min")
    if ret and len(legs) > len(seq):
        lines.append(f"Retorno à base — {km(legs[-1]):.1f} km, {mins(legs[-1])} min")
    lines.append(f"**Total: {sum(km(lg) for lg in legs):.1f} km, {sum(mins(lg) for lg in legs)} min** (sem tempo de atendimento)")
    pts = [f"{origin.lat},{origin.lng}" if origin.lat is not None else origin.address]
    pts += [f"{w.lat},{w.lng}" if w.lat is not None else w.address for w in (wp(o) for o in seq)]
    if ret:
        pts.append(f"{BASE[0]},{BASE[1]}")
    lines.append("Abrir no Maps: https://www.google.com/maps/dir/" + "/".join(quote(p) for p in pts))
    return "\n".join(lines)


# --- PDF ---
def _build_pdf(title: str, content: str) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from xml.sax.saxutils import escape
    buf = io.BytesIO()
    st = getSampleStyleSheet()
    story = [Paragraph(escape(title or "Documento"), st["Title"]), Spacer(1, 12)]
    for line in (content or "").split("\n"):
        txt = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escape(line.strip()))
        story.append(Paragraph(txt, st["Normal"]) if txt else Spacer(1, 8))
    SimpleDocTemplate(buf, pagesize=A4, title=title or "Documento").build(story)
    return buf.getvalue()


async def generate_pdf(title: str, content: str) -> str:
    from manuais_module import put_object
    token = uuid.uuid4().hex
    data = await asyncio.to_thread(_build_pdf, title, content)
    await asyncio.to_thread(put_object, f"mastermaq-manuais/shared-pdfs/{token}.pdf", data, "application/pdf")
    return f"/api/files/temp-pdf/{token}"


# --- Anexos ---
FILE_PREFIX = "mastermaq-manuais/mi-files"


def _replace_in_paragraph(p, find: str, repl: str) -> bool:
    """Troca texto preservando a formatação do primeiro run do trecho."""
    if find not in p.text:
        return False
    if any(find in r.text for r in p.runs):
        for r in p.runs:
            if find in r.text:
                r.text = r.text.replace(find, repl)
        return True
    full = p.text.replace(find, repl)
    for i, r in enumerate(p.runs):
        r.text = full if i == 0 else ""
    return True


def _edit_docx(data: bytes, replacements: list) -> tuple:
    import docx
    doc = docx.Document(io.BytesIO(data))
    paras = list(doc.paragraphs)
    for tbl in doc.tables:
        for row in tbl.rows:
            for cell in row.cells:
                paras += cell.paragraphs
    for sec in doc.sections:
        paras += sec.header.paragraphs + sec.footer.paragraphs
    done = 0
    for rp in replacements:
        f, r = str(rp.get("find") or ""), str(rp.get("replace") or "")
        if f:
            done += sum(_replace_in_paragraph(p, f, r) for p in paras)
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue(), done


def _docx_to_pdf(data: bytes) -> bytes:
    import os
    import subprocess
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "doc.docx")
        open(src, "wb").write(data)
        subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", d, src], capture_output=True, timeout=180)
        return open(os.path.join(d, "doc.pdf"), "rb").read()


async def edit_docx(file_id: str, replacements: list, as_pdf: bool) -> tuple:
    from manuais_module import get_object, put_object
    src, _ = await asyncio.to_thread(get_object, f"{FILE_PREFIX}/{file_id}.docx")
    out, done = await asyncio.to_thread(_edit_docx, src, replacements)
    ext, ctype = "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if as_pdf:
        out, ext, ctype = await asyncio.to_thread(_docx_to_pdf, out), "pdf", "application/pdf"
    token = uuid.uuid4().hex
    await asyncio.to_thread(put_object, f"{FILE_PREFIX}/{token}.{ext}", out, ctype)
    return f"/api/mi/files/{token}.{ext}", done


async def store_upload(data: bytes) -> str:
    from manuais_module import put_object
    fid = uuid.uuid4().hex
    await asyncio.to_thread(put_object, f"{FILE_PREFIX}/{fid}.docx", data,
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    return fid


def extract_upload(data: bytes, filename: str) -> str:
    import subprocess
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext == "pdf":
        return subprocess.run(["pdftotext", "-layout", "-", "-"], input=data, capture_output=True, timeout=120).stdout.decode(errors="ignore")
    if ext == "docx":
        import docx
        return "\n".join(p.text for p in docx.Document(io.BytesIO(data)).paragraphs)
    if ext in ("txt", "md", "csv", "json"):
        return data.decode(errors="ignore")
    raise ValueError("Formato não suportado (use PDF, DOCX, TXT ou CSV)")
