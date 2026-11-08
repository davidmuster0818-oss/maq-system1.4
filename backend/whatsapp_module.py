"""
WhatsApp Business API Module
Handles configuration, message sending, interactive menus, and webhook management
with Meta webhook signature validation (X-Hub-Signature-256).

Optimizations:
- Webhook returns 200 OK immediately, processes async via asyncio.create_task
- In-memory config cache (refreshed every 5min) to avoid DB queries per webhook
- Bot self-response prevention (ignores messages from own number)
- Shared httpx client for connection reuse
- Reduced logging (DEBUG for routine, INFO/ERROR for important events)
"""
import os
import hmac
import hashlib
import httpx
import json
import logging
import asyncio
import time
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import PlainTextResponse

logger = logging.getLogger(__name__)

GRAPH_API_URL = "https://graph.facebook.com"
GRAPH_API_VERSION = "v21.0"
WA_APP_SECRET = os.environ.get("WA_APP_SECRET", "")
WA_APP_ID = os.environ.get("WA_APP_ID", "")
WA_PERMANENT_TOKEN = os.environ.get("WA_APP_PERMANENT_TOKEN") or os.environ.get("WA_PERMANENT_TOKEN", "")
WA_PHONE_NUMBER_ID = os.environ.get("WA_PHONE_NUMBER_ID", "")
WA_WABA_ID = os.environ.get("WA_WABA_ID", "")
SCHEDULE_TEMPLATE = "agendamento_os"
SCHEDULE_TEXT = ("Olá, {{1}}! Aqui é da Mastermaq Assistência Técnica. Referente à OS {{2}} ({{3}}), "
                 "podemos confirmar o agendamento para {{4}}?")

# --- In-memory caches to avoid DB queries on every webhook ---
_wa_config_cache = {"data": None, "ts": 0}
_menu_config_cache = {"data": None, "ts": 0}
_CONFIG_TTL = 300  # 5 minutes

# Shared httpx client (reused across requests)
_shared_client: httpx.AsyncClient = None

async def _get_shared_client() -> httpx.AsyncClient:
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.AsyncClient(timeout=30)
    return _shared_client


def get_saudacao():
    """Dynamic greeting based on time of day (Brasilia timezone UTC-3)"""
    hour = (datetime.now(timezone.utc).hour - 3) % 24
    if hour < 12:
        return "Bom dia"
    elif hour < 18:
        return "Boa tarde"
    return "Boa noite"


def _schedule_when(route_date: str) -> str:
    """'hoje' se o roteiro é do dia (horário de Brasília), senão dd/mm/aaaa."""
    from datetime import timedelta
    today = (datetime.now(timezone.utc) - timedelta(hours=3)).date()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            d = datetime.strptime((route_date or "")[:10], fmt).date()
            return "hoje" if d == today else d.strftime("%d/%m/%Y")
        except ValueError:
            continue
    return route_date or "a data combinada"


async def send_text(db, phone_raw: str, text: str) -> str:
    """Envia texto livre (usado pela Mi). Fora da janela de 24h a Meta recusa — devolve o erro."""
    if not (WA_PHONE_NUMBER_ID and WA_PERMANENT_TOKEN):
        raise ValueError("WhatsApp não configurado (WA_PHONE_NUMBER_ID/token)")
    digits = "".join(c for c in (phone_raw or "") if c.isdigit())
    if len(digits) < 10:
        raise ValueError("Telefone inválido")
    phone = digits if digits.startswith("55") and len(digits) >= 12 else f"55{digits}"
    client = await _get_shared_client()
    resp = await client.post(f"{GRAPH_API_URL}/{GRAPH_API_VERSION}/{WA_PHONE_NUMBER_ID}/messages",
                             json={"messaging_product": "whatsapp", "to": phone, "type": "text", "text": {"body": text}},
                             headers={"Authorization": f"Bearer {WA_PERMANENT_TOKEN}"})
    ok = resp.status_code < 400
    await db.whatsapp_messages.insert_one({
        "direction": "outbound", "to": phone, "type": "text", "body": text,
        "wa_message_id": (resp.json().get("messages") or [{}])[0].get("id") if ok else None,
        "status": "sent" if ok else "failed", "sent_at": datetime.now(timezone.utc).isoformat(),
    })
    if not ok:
        err = (resp.json().get("error") or {}) if resp.headers.get("content-type", "").startswith("application/json") else {}
        raise ValueError(f"Meta recusou: {err.get('message') or resp.text[:200]}")
    return phone


async def send_route_schedule(db, route: dict):
    """Envia o template agendamento_os para o cliente de cada OS do roteiro recém-criado."""
    if not (WA_PHONE_NUMBER_ID and WA_PERMANENT_TOKEN):
        logger.warning("[WA] agendamento não enviado: WA_PHONE_NUMBER_ID/token ausentes")
        return
    when = _schedule_when(route.get("date"))
    url = f"{GRAPH_API_URL}/{GRAPH_API_VERSION}/{WA_PHONE_NUMBER_ID}/messages"
    client = await _get_shared_client()
    for o in route.get("orders") or []:
        os_doc = await db.service_orders.find_one({"os_number": o.get("os_number")}, {"phone1": 1, "product": 1, "model": 1, "customer_name": 1}) or {}
        digits = "".join(c for c in (o.get("phone1") or os_doc.get("phone1") or "") if c.isdigit())
        if len(digits) < 10:
            logger.warning(f"[WA] OS {o.get('os_number')}: sem telefone válido, agendamento não enviado")
            continue
        phone = digits if digits.startswith("55") and len(digits) >= 12 else f"55{digits}"
        name = (o.get("customer_name") or os_doc.get("customer_name") or "cliente").split()[0].title()
        product = os_doc.get("product") or os_doc.get("model") or "seu equipamento"
        params = [name, str(o.get("os_number")), product, when]
        text = SCHEDULE_TEXT
        for i, p in enumerate(params, 1):
            text = text.replace("{{" + str(i) + "}}", p)
        # Direct Send (utility, sem template pré-aprovado); se a conta não for elegível, cai no template.
        direct = {
            "messaging_product": "whatsapp", "recipient_type": "individual", "to": phone, "type": "text",
            "text": {"body": text}, "category": "utility",
            "direct_send_config": {"template_name": SCHEDULE_TEMPLATE + "_ds"},
        }
        payload = {
            "messaging_product": "whatsapp", "to": phone, "type": "template",
            "template": {"name": SCHEDULE_TEMPLATE, "language": {"code": "pt_BR"},
                         "components": [{"type": "body", "parameters": [{"type": "text", "text": p} for p in params]}]},
        }
        try:
            headers = {"Authorization": f"Bearer {WA_PERMANENT_TOKEN}"}
            resp = await client.post(url, json=direct, headers=headers)
            if resp.status_code >= 400 and "Direct Send" in resp.text:
                resp = await client.post(url, json=payload, headers=headers)
            ok = resp.status_code < 400
            if not ok:
                logger.error(f"[WA] agendamento OS {o.get('os_number')} falhou: {resp.text[:300]}")
            await db.whatsapp_messages.insert_one({
                "direction": "outbound", "to": phone, "type": "text",
                "body": text,
                "wa_message_id": (resp.json().get("messages") or [{}])[0].get("id") if ok else None,
                "status": "sent" if ok else "failed",
                "sent_at": datetime.now(timezone.utc).isoformat(),
            })
        except Exception as e:
            logger.error(f"[WA] agendamento OS {o.get('os_number')} erro: {e!r}")



def setup_whatsapp_routes(api_router: APIRouter, db, verify_token):
    """Register WhatsApp Business API routes"""

    async def get_wa_config(force_refresh=False):
        """Get WhatsApp config from DB (cached in memory for 5 min)"""
        now = time.time()
        if not force_refresh and _wa_config_cache["data"] is not None and (now - _wa_config_cache["ts"]) < _CONFIG_TTL:
            return _wa_config_cache["data"]
        config = await db.whatsapp_config.find_one({}, {"_id": 0})
        # IDs do .env têm prioridade sobre a config salva no banco.
        if WA_PHONE_NUMBER_ID:
            config = {**(config or {}), "phone_number_id": WA_PHONE_NUMBER_ID}
        if WA_WABA_ID:
            config = {**(config or {}), "waba_id": WA_WABA_ID}
        _wa_config_cache["data"] = config
        _wa_config_cache["ts"] = now
        return config

    async def get_menu_config_cached():
        """Get menu config from DB (cached in memory for 5 min)"""
        now = time.time()
        if _menu_config_cache["data"] is not None and (now - _menu_config_cache["ts"]) < _CONFIG_TTL:
            return _menu_config_cache["data"]
        config = await db.whatsapp_menu_config.find_one({}, {"_id": 0})
        _menu_config_cache["data"] = config
        _menu_config_cache["ts"] = now
        return config

    def get_access_token(config):
        """Get access token: permanent env token > DB config token"""
        if WA_PERMANENT_TOKEN:
            return WA_PERMANENT_TOKEN
        return config.get("access_token", "") if config else ""

    def validate_signature(payload: bytes, signature_header: str) -> bool:
        """
        Validate webhook payload signature from Meta (X-Hub-Signature-256).
        Uses WA_APP_SECRET from environment (primary) or DB config (fallback).
        """
        secret = WA_APP_SECRET
        if not signature_header or not secret:
            return False
        try:
            if not signature_header.startswith("sha256="):
                return False
            expected_sig = signature_header[7:]
            computed_sig = hmac.new(
                secret.encode("utf-8"),
                payload,
                hashlib.sha256
            ).hexdigest()
            return hmac.compare_digest(computed_sig, expected_sig)
        except Exception as e:
            logger.error(f"Signature validation error: {e}")
            return False

    # --- Config CRUD ---
    @api_router.get("/whatsapp/config")
    async def get_config(_: dict = Depends(verify_token)):
        config = await get_wa_config()
        if not config:
            return {"configured": False}
        masked = {**config, "configured": True}
        if masked.get("access_token"):
            token = masked["access_token"]
            masked["access_token_masked"] = f"{token[:12]}...{token[-8:]}" if len(token) > 20 else "***"
        if masked.get("app_secret"):
            secret = masked["app_secret"]
            masked["app_secret_masked"] = f"{secret[:6]}...{secret[-4:]}" if len(secret) > 10 else "***"
        return masked

    @api_router.post("/whatsapp/config")
    async def save_config(body: dict, _: dict = Depends(verify_token)):
        access_token = body.get("access_token", "").strip()
        phone_number_id = body.get("phone_number_id", "").strip()
        waba_id = body.get("waba_id", "").strip()
        app_secret = body.get("app_secret", "").strip()
        webhook_verify_token = body.get("webhook_verify_token", "mastermaq_wh_verify_2024").strip()
        display_phone = body.get("display_phone", "").strip()

        if not access_token or not phone_number_id:
            raise HTTPException(status_code=400, detail="access_token e phone_number_id sao obrigatorios")

        config = {
            "access_token": access_token,
            "phone_number_id": phone_number_id,
            "waba_id": waba_id,
            "app_secret": app_secret,
            "webhook_verify_token": webhook_verify_token,
            "display_phone": display_phone,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        await db.whatsapp_config.update_one({}, {"$set": config}, upsert=True)
        _wa_config_cache["data"] = None  # Invalidate cache
        _wa_config_cache["ts"] = 0
        return {"message": "Configuracao salva com sucesso"}

    # --- Send Message ---
    @api_router.post("/whatsapp/send")
    async def send_message(body: dict, _: dict = Depends(verify_token)):
        config = await get_wa_config()
        token = get_access_token(config)
        if not token or not config or not config.get("phone_number_id"):
            raise HTTPException(status_code=400, detail="WhatsApp nao configurado")

        to = body.get("to", "").strip()
        msg_type = body.get("type", "text")
        text_body = body.get("text", "")
        template_name = body.get("template_name")
        template_lang = body.get("template_lang", "pt_BR")
        template_components = body.get("template_components", [])
        interactive = body.get("interactive")

        if not to:
            raise HTTPException(status_code=400, detail="Numero do destinatario e obrigatorio")

        phone = to.replace("+", "").replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        if not phone.startswith("55"):
            phone = f"55{phone}"

        url = f"{GRAPH_API_URL}/{GRAPH_API_VERSION}/{config['phone_number_id']}/messages"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        if msg_type == "interactive" and interactive:
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": phone,
                "type": "interactive",
                "interactive": interactive,
            }
        elif msg_type == "template" and template_name:
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": phone,
                "type": "template",
                "template": {
                    "name": template_name,
                    "language": {"code": template_lang},
                    "components": template_components,
                },
            }
        else:
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": phone,
                "type": "text",
                "text": {"preview_url": True, "body": text_body},
            }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=payload, headers=headers)

        if resp.status_code >= 400:
            detail = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text
            raise HTTPException(status_code=resp.status_code, detail=detail)

        result = resp.json()
        await db.whatsapp_messages.insert_one({
            "direction": "outbound",
            "to": phone,
            "type": msg_type,
            "body": text_body or template_name or "[interactive]",
            "wa_message_id": result.get("messages", [{}])[0].get("id"),
            "status": "sent",
            "sent_at": datetime.now(timezone.utc).isoformat(),
        })
        return result

    # --- Interactive Menu ---
    @api_router.get("/whatsapp/menu-config")
    async def get_menu_config(_: dict = Depends(verify_token)):
        config = await db.whatsapp_menu_config.find_one({}, {"_id": 0})
        if not config:
            return {
                "representative_name": "Thamires",
                "default_brand": "Posto Autorizado",
                "greeting_enabled": True,
                "buttons": [
                    {"id": "enviar_dados", "title": "Enviar dados"},
                    {"id": "duvidas", "title": "Tirar duvidas"},
                    {"id": "atendente", "title": "Falar com atendente"}
                ],
                "data_collection_message": "",
                "duvidas_message": "Fique a vontade para enviar sua duvida que responderemos o mais breve possivel.",
                "atendente_message": "Aguarde um momento, vamos transferir voce para um atendente.",
            }
        return config

    @api_router.post("/whatsapp/menu-config")
    async def save_menu_config(body: dict, _: dict = Depends(verify_token)):
        body["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.whatsapp_menu_config.update_one({}, {"$set": body}, upsert=True)
        _menu_config_cache["data"] = None  # Invalidate cache
        _menu_config_cache["ts"] = 0
        return {"message": "Configuracao do menu salva"}

    @api_router.post("/whatsapp/send-menu")
    async def send_interactive_menu(body: dict, _: dict = Depends(verify_token)):
        """Send interactive greeting menu with buttons to a phone number"""
        config = await get_wa_config()
        token = get_access_token(config)
        if not token or not config or not config.get("phone_number_id"):
            raise HTTPException(status_code=400, detail="WhatsApp nao configurado")

        to = body.get("to", "").strip()
        brand = body.get("brand", "Posto Autorizado")
        if not to:
            raise HTTPException(status_code=400, detail="Numero do destinatario e obrigatorio")

        phone = to.replace("+", "").replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        if not phone.startswith("55"):
            phone = f"55{phone}"

        menu_config = await db.whatsapp_menu_config.find_one({}, {"_id": 0})
        rep_name = (menu_config or {}).get("representative_name", "Thamires")
        saudacao = get_saudacao()

        greeting_text = (
            f"*{saudacao},*\n\n"
            f"Meu nome e *{rep_name}*, represento o *{brand}*, e estou entrando em contato para dar continuidade ao seu atendimento.\n\n"
            f"Como deseja prosseguir?"
        )

        buttons = (menu_config or {}).get("buttons", [
            {"id": "enviar_dados", "title": "Enviar dados"},
            {"id": "duvidas", "title": "Tirar duvidas"},
            {"id": "atendente", "title": "Falar com atendente"}
        ])

        interactive = {
            "type": "button",
            "body": {"text": greeting_text},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": b["id"], "title": b["title"]}}
                    for b in buttons[:3]
                ]
            }
        }

        url = f"{GRAPH_API_URL}/{GRAPH_API_VERSION}/{config['phone_number_id']}/messages"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": phone,
            "type": "interactive",
            "interactive": interactive,
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=payload, headers=headers)

        if resp.status_code >= 400:
            detail = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text
            raise HTTPException(status_code=resp.status_code, detail=detail)

        result = resp.json()
        await db.whatsapp_messages.insert_one({
            "direction": "outbound",
            "to": phone,
            "type": "interactive",
            "body": f"[Menu] {greeting_text[:80]}...",
            "wa_message_id": result.get("messages", [{}])[0].get("id"),
            "status": "sent",
            "sent_at": datetime.now(timezone.utc).isoformat(),
        })
        return result

    async def _find_customer_brand(phone: str):
        """Try to find the customer's OS brand by phone number"""
        try:
            clean = phone.replace("+", "").replace(" ", "").replace("-", "")
            if clean.startswith("55"):
                clean = clean[2:]
            # Search by phone1 containing the digits
            os_record = await db.service_orders.find_one(
                {"phone1": {"$regex": clean[-8:]}},
                {"_id": 0, "brand": 1}
            )
            if os_record and os_record.get("brand"):
                return os_record["brand"]
        except Exception as e:
            logger.error(f"Error finding customer brand: {e}")
        return None

    async def send_auto_menu(from_phone: str):
        """Auto-send interactive menu only on FIRST contact of the day"""
        config = await get_wa_config()
        token = get_access_token(config)
        if not token or not config or not config.get("phone_number_id"):
            return

        # Check if we already sent a menu to this phone TODAY
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        existing = await db.whatsapp_messages.find_one({
            "to": from_phone,
            "body": {"$regex": "^\\[Auto-Menu\\]"},
            "sent_at": {"$regex": f"^{today_str}"}
        })
        if existing:
            return

        menu_config = await get_menu_config_cached() or {}
        rep_name = menu_config.get("representative_name", "Thamires")
        brand = menu_config.get("default_brand", "Posto Autorizado")

        # Try to find brand from customer's OS
        customer_brand = await _find_customer_brand(from_phone)
        if customer_brand:
            brand = customer_brand

        saudacao = get_saudacao()
        buttons = menu_config.get("buttons", [
            {"id": "enviar_dados", "title": "Enviar dados"},
            {"id": "duvidas", "title": "Tirar duvidas"},
            {"id": "atendente", "title": "Falar com atendente"}
        ])

        greeting_text = (
            f"*{saudacao},*\n\n"
            f"Meu nome e *{rep_name}*, represento o *{brand}*, e estou entrando em contato para dar continuidade ao seu atendimento.\n\n"
            f"Como deseja prosseguir?"
        )

        interactive = {
            "type": "button",
            "body": {"text": greeting_text},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": b["id"], "title": b["title"]}}
                    for b in buttons[:3]
                ]
            }
        }

        url = f"{GRAPH_API_URL}/{GRAPH_API_VERSION}/{config['phone_number_id']}/messages"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": from_phone,
            "type": "interactive",
            "interactive": interactive,
        }

        try:
            client = await _get_shared_client()
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code < 400:
                result = resp.json()
                await db.whatsapp_messages.insert_one({
                    "direction": "outbound",
                    "to": from_phone,
                    "type": "interactive",
                    "body": f"[Auto-Menu] {greeting_text[:80]}...",
                    "wa_message_id": result.get("messages", [{}])[0].get("id"),
                    "status": "sent",
                    "sent_at": datetime.now(timezone.utc).isoformat(),
                })
                logger.info(f"Auto-menu sent to {from_phone} (brand={brand})")
            else:
                logger.error(f"Auto-menu failed: {resp.status_code} {resp.text[:200]}")
        except Exception as e:
            logger.error(f"Auto-menu error: {e}")

    async def handle_interactive_reply(from_phone: str, reply_id: str, reply_title: str):
        """Handle interactive button/list replies and send follow-up messages"""
        config = await get_wa_config()
        token = get_access_token(config)
        if not token or not config or not config.get("phone_number_id"):
            return

        menu_config = await get_menu_config_cached() or {}
        rep_name = menu_config.get("representative_name", "Thamires")
        brand = menu_config.get("default_brand", "Posto Autorizado")
        saudacao = get_saudacao()

        # Try to find brand from customer's OS by phone number
        customer_brand = await _find_customer_brand(from_phone)
        if customer_brand:
            brand = customer_brand

        if reply_id == "enviar_dados":
            msg = (
                f"*{saudacao},*\n\n"
                f"Meu nome e *{rep_name}*, represento o *{brand}*, e estou entrando em contato para dar continuidade ao seu atendimento.\n\n"
                f"Para isso, solicito, por gentileza, o envio dos seguintes dados e informacoes:\n\n"
                f"*Dados para cadastro:*\n"
                f"- Nome completo:\n"
                f"- Endereco completo:\n"
                f"- CEP:\n"
                f"- Ponto de referencia:\n"
                f"- Telefones para contato (preferencialmente dois):\n"
                f"- E-mail:\n\n"
                f"*Informacoes do produto:*\n"
                f"- Produto:\n"
                f"- Marca:\n"
                f"- Modelo:\n"
                f"- Defeito apresentado:\n"
                f"- O produto esta dentro do prazo de garantia?\n\n"
                f"*Se estiver, por favor, envie:*\n"
                f"- Nota Fiscal (NF)\n"
                f"- Foto da etiqueta do produto\n\n"
                f"*_Caso o produto nao esteja na garantia:_*\n"
                f"Cobramos uma *taxa de diagnostico e deslocamento tecnico*, que pode variar conforme sua localizacao.\n\n"
                f"Se possivel, envie tambem uma foto ou video que evidencie o defeito e o local de instalacao do produto.\n\n"
                f"Essas informacoes sao essenciais para agilizar o processo e garantir um atendimento eficiente e preciso.\n\n"
                f"Agradeco pela atencao e colaboracao.\n\n"
                f"*Atenciosamente,*\n"
                f"*{rep_name}*\n"
                f"*{brand}*"
            )
        elif reply_id == "duvidas":
            msg = menu_config.get("duvidas_message",
                "Fique a vontade para enviar sua duvida que responderemos o mais breve possivel.")
        elif reply_id == "atendente":
            msg = menu_config.get("atendente_message",
                "Aguarde um momento, vamos transferir voce para um atendente.")
        else:
            return

        url = f"{GRAPH_API_URL}/{GRAPH_API_VERSION}/{config['phone_number_id']}/messages"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": from_phone,
            "type": "text",
            "text": {"preview_url": False, "body": msg},
        }

        try:
            client = await _get_shared_client()
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code < 400:
                result = resp.json()
                await db.whatsapp_messages.insert_one({
                    "direction": "outbound",
                    "to": from_phone,
                    "type": "text",
                    "body": f"[Auto-Reply:{reply_id}] {msg[:150]}",
                    "wa_message_id": result.get("messages", [{}])[0].get("id"),
                    "status": "sent",
                    "sent_at": datetime.now(timezone.utc).isoformat(),
                })
            else:
                logger.error(f"Auto-reply failed: {resp.status_code} {resp.text[:200]}")
        except Exception as e:
            logger.error(f"Auto-reply error: {e}")

    # --- Get Templates ---
    @api_router.post("/whatsapp/templates/agendamento")
    async def create_schedule_template(_: dict = Depends(verify_token)):
        """Cria e envia para aprovação da Meta o template agendamento_os (pt_BR, UTILITY)."""
        if not WA_WABA_ID:
            raise HTTPException(status_code=400, detail="WA_WABA_ID não configurado")
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{GRAPH_API_URL}/{GRAPH_API_VERSION}/{WA_WABA_ID}/message_templates",
                headers={"Authorization": f"Bearer {WA_PERMANENT_TOKEN}"},
                json={"name": SCHEDULE_TEMPLATE, "language": "pt_BR", "category": "UTILITY",
                      "components": [{"type": "BODY", "text": SCHEDULE_TEXT,
                                      "example": {"body_text": [["Maria", "73069831", "Lavadora", "hoje"]]}}]},
            )
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=resp.json())
        return resp.json()

    @api_router.get("/whatsapp/templates")
    async def get_templates(_: dict = Depends(verify_token)):
        config = await get_wa_config()
        if not config or not config.get("waba_id"):
            raise HTTPException(status_code=400, detail="WABA ID nao configurado")

        token = get_access_token(config)
        url = f"{GRAPH_API_URL}/{GRAPH_API_VERSION}/{config['waba_id']}/message_templates"
        headers = {"Authorization": f"Bearer {token}"}

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers=headers)

        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail="Erro ao buscar templates")
        return resp.json()

    # --- Get Phone Number Info ---
    @api_router.get("/whatsapp/phone-info")
    async def get_phone_info(_: dict = Depends(verify_token)):
        config = await get_wa_config()
        if not config or not config.get("phone_number_id"):
            raise HTTPException(status_code=400, detail="Phone Number ID nao configurado")

        token = get_access_token(config)
        url = f"{GRAPH_API_URL}/{GRAPH_API_VERSION}/{config['phone_number_id']}"
        headers = {"Authorization": f"Bearer {token}"}
        params = {"fields": "verified_name,code_verification_status,display_phone_number,quality_rating,platform_type,throughput"}

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers=headers, params=params)

        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail="Erro ao buscar informacoes do telefone")
        return resp.json()

    # --- Webhook Verification (GET) ---
    @api_router.get("/whatsapp/webhook")
    async def webhook_verify(request: Request):
        """
        WhatsApp webhook verification endpoint.
        Meta sends: hub.mode=subscribe, hub.challenge=<int>, hub.verify_token=<string>
        Must respond with hub.challenge value if verify_token matches.
        """
        params = dict(request.query_params)
        mode = params.get("hub.mode")
        token = params.get("hub.verify_token")
        challenge = params.get("hub.challenge")

        logger.debug(f"Webhook verify: mode={mode}, challenge={challenge}")

        config = await get_wa_config()
        verify = config.get("webhook_verify_token", "mastermaq_wh_verify_2024") if config else "mastermaq_wh_verify_2024"

        if mode == "subscribe" and token == verify:
            return PlainTextResponse(content=str(challenge), status_code=200)

        logger.warning("Webhook verification FAILED: token mismatch")
        raise HTTPException(status_code=403, detail="Verification failed")

    # --- Webhook Receive (POST) ---
    @api_router.post("/whatsapp/webhook")
    async def webhook_receive(request: Request):
        """
        Receive WhatsApp webhook events from Meta.
        OPTIMIZED: Returns 200 OK immediately, processes async in background.
        Validates X-Hub-Signature-256 using WA_APP_SECRET.
        """
        raw_body = await request.body()

        # Validate signature if app_secret is configured
        if WA_APP_SECRET:
            signature = request.headers.get("X-Hub-Signature-256", "")
            if not validate_signature(raw_body, signature):
                logger.warning("Webhook signature validation FAILED")
                return {"status": "signature_invalid"}

        try:
            body = json.loads(raw_body)
        except Exception:
            return {"status": "ok"}

        # Fire-and-forget: process in background, respond 200 OK immediately
        asyncio.create_task(_process_webhook_async(body))
        return {"status": "ok"}

    async def _process_webhook_async(body: dict):
        """Process webhook events in background (after 200 OK already sent)"""
        try:
            config = await get_wa_config()
            own_phone = config.get("display_phone", "").replace("+", "").replace(" ", "").replace("-", "") if config else ""

            for entry in body.get("entry", []):
                for change in entry.get("changes", []):
                    value = change.get("value", {})

                    # Incoming messages
                    for msg in value.get("messages", []):
                        from_phone = msg.get("from", "")

                        # LOOP PREVENTION: ignore messages from our own number
                        if own_phone and from_phone.endswith(own_phone[-8:]):
                            logger.debug(f"Ignoring message from own number: {from_phone}")
                            continue

                        msg_type = msg.get("type")
                        msg_body = ""
                        interactive_reply_id = None
                        interactive_reply_title = None

                        if msg_type == "text":
                            msg_body = msg.get("text", {}).get("body", "")
                        elif msg_type == "interactive":
                            interactive = msg.get("interactive", {})
                            int_type = interactive.get("type", "")
                            if int_type == "button_reply":
                                reply = interactive.get("button_reply", {})
                                interactive_reply_id = reply.get("id", "")
                                interactive_reply_title = reply.get("title", "")
                                msg_body = f"[Botao] {interactive_reply_title}"
                            elif int_type == "list_reply":
                                reply = interactive.get("list_reply", {})
                                interactive_reply_id = reply.get("id", "")
                                interactive_reply_title = reply.get("title", "")
                                msg_body = f"[Lista] {interactive_reply_title}"

                        await db.whatsapp_messages.insert_one({
                            "direction": "inbound",
                            "from": from_phone,
                            "type": msg_type,
                            "body": msg_body,
                            "wa_message_id": msg.get("id"),
                            "timestamp": msg.get("timestamp"),
                            "contact_name": (value.get("contacts", [{}])[0].get("profile", {}).get("name")),
                            "received_at": datetime.now(timezone.utc).isoformat(),
                        })
                        logger.debug(f"Received: {from_phone} {msg_type} {msg_body[:50]}")

                        # Auto-respond to interactive replies
                        if interactive_reply_id and from_phone:
                            await handle_interactive_reply(from_phone, interactive_reply_id, interactive_reply_title or "")
                        # Auto-send menu when customer sends a text message
                        elif msg_type == "text" and from_phone:
                            await send_auto_menu(from_phone)

                    # Status updates (delivery receipts) — batch silently
                    for status in value.get("statuses", []):
                        await db.whatsapp_messages.update_one(
                            {"wa_message_id": status.get("id")},
                            {"$set": {"status": status.get("status"), "status_updated_at": datetime.now(timezone.utc).isoformat()}},
                        )

        except Exception as e:
            logger.error(f"Webhook async processing error: {e}")

    # --- Webhook Status ---
    @api_router.get("/whatsapp/webhook-status")
    async def webhook_status(_: dict = Depends(verify_token)):
        """Check webhook configuration status"""
        config = await get_wa_config()
        return {
            "configured": bool(config),
            "app_secret_set": bool(WA_APP_SECRET),
            "app_id": WA_APP_ID or None,
            "signature_validation": bool(WA_APP_SECRET),
            "verify_token_set": bool(config.get("webhook_verify_token")) if config else False,
            "webhook_url": "/api/whatsapp/webhook",
        }

    # --- Message History ---
    @api_router.get("/whatsapp/messages")
    async def get_messages(_: dict = Depends(verify_token)):
        messages = await db.whatsapp_messages.find({}, {"_id": 0}).sort("sent_at", -1).to_list(50)
        return {"messages": messages}
