"""Camada de segurança: páginas por usuário (RBAC no servidor), sessões revogáveis, limites e registro de eventos."""
import os
import time
import logging
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Optional

import jwt
from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

log = logging.getLogger("security")

ALL_PAGES = ["service-orders", "routes", "inventory", "financial", "manuais", "mi", "whatsapp", "users", "webhooks", "labels"]
ROLE_DEFAULT_PAGES = {"admin": ALL_PAGES, "technician": ["routes", "manuais"], "invisacook": ["service-orders"]}
ADMIN_ONLY_PAGES = {"users"}

# (páginas que liberam, prefixo, métodos ou None, só caminho exato)
_RULES = [
    (("inventory",), "/api/inventory", None, False),
    (("manuais",), "/api/manuais", None, False),
    (("mi",), "/api/mi", None, False),
    (("whatsapp",), "/api/whatsapp", None, False),
    (("users",), "/api/users", None, False),
    (("webhooks",), "/api/webhooks", None, False),
    (("labels",), "/api/label-templates", {"POST", "PUT", "PATCH", "DELETE"}, False),
    (("financial",), "/api/finance", None, False),
    (("financial",), "/api/banks", None, False),
    (("financial",), "/api/assistants", None, False),
    (("routes",), "/api/routes", None, False),
    (("routes",), "/api/rf", None, False),
    (("routes",), "/api/tracking", None, False),
    (("service-orders", "routes"), "/api/service-orders", {"GET"}, True),
    (("service-orders",), "/api/dashboard", None, False),
    (("service-orders",), "/api/telecontrol", None, False),
    (("service-orders",), "/api/notifications", None, False),
    (("service-orders",), "/api/scrapers", None, False),
]
_PUBLIC = ("/api/tracking/public/", "/api/whatsapp/webhook")
_RATE_PUBLIC = ("/api/os/public", "/api/product/public", "/api/tracking/public", "/api/public/sign", "/api/files/temp-pdf", "/api/auth/login")

_mongo = None
_user_cache: dict = {}
_hits: dict = defaultdict(deque)


def init(mongo_db):
    global _mongo
    _mongo = mongo_db


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return (fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "")) or "?"


def hit(key: str, limit: int, window: int) -> bool:
    """True quando o limite foi ultrapassado."""
    now = time.time()
    q = _hits[key]
    while q and now - q[0] > window:
        q.popleft()
    q.append(now)
    return len(q) > limit


async def event(kind: str, request: Optional[Request] = None, **data):
    """Registro de segurança (nunca guarda senha/token)."""
    doc = {"ts": datetime.now(timezone.utc).isoformat(), "type": kind, **data}
    if request is not None:
        doc.update(ip=client_ip(request), path=request.url.path, method=request.method)
    log.warning("security %s %s", kind, {k: v for k, v in doc.items() if k != "ts"})
    try:
        await _mongo["security_events"].insert_one(doc)
    except Exception:
        pass


def master_email() -> str:
    return (os.environ.get("APP_LOGIN_EMAIL") or "").strip().lower()


async def get_user(email: str) -> Optional[dict]:
    email = (email or "").strip().lower()
    c = _user_cache.get(email)
    if c and time.time() - c[0] < 20:
        return c[1]
    u = await _mongo["users"].find_one({"email": email}, {"_id": 0, "password_hash": 0})
    _user_cache[email] = (time.time(), u)
    return u


def forget_user(email: str):
    _user_cache.pop((email or "").strip().lower(), None)


def pages_of(user: Optional[dict], role: str, email: str) -> list:
    if email == master_email():
        return ALL_PAGES
    if user and user.get("pages") is not None:
        return [p for p in user["pages"] if p in ALL_PAGES and (p not in ADMIN_ONLY_PAGES or user.get("role") == "admin")]
    return ROLE_DEFAULT_PAGES.get((user or {}).get("role") or role, [])


async def check_session(payload: dict) -> dict:
    """Revoga tokens de usuários excluídos/inativos ou emitidos antes da última troca de senha/desativação."""
    email = (payload.get("email") or "").strip().lower()
    user = await get_user(email)
    if user is None:
        if email and email == master_email():
            return payload
        raise HTTPException(status_code=401, detail="Sessão inválida")
    if not user.get("active", True):
        raise HTTPException(status_code=401, detail="Sessão inválida")
    after = user.get("tokens_valid_after")
    if after and float(payload.get("iat") or 0) < float(after):
        raise HTTPException(status_code=401, detail="Sessão expirada")
    payload["role"] = user.get("role", payload.get("role"))
    return payload


async def effective_pages(payload: dict) -> list:
    email = (payload.get("email") or "").strip().lower()
    return pages_of(await get_user(email), payload.get("role", ""), email)


def pages_for(path: str, method: str, any_method: bool = False):
    if path.startswith(_PUBLIC):
        return None
    for pages, prefix, methods, exact in _RULES:
        if (path == prefix or path.rstrip("/") == prefix) if exact else (path == prefix or path.startswith(prefix + "/")):
            if any_method or methods is None or method in methods:
                return pages
    return None


async def admin_or_granted(request: Request, payload: dict) -> dict:
    """Admin passa; outro perfil só se o admin liberou a página daquela rota (nunca 'users')."""
    if payload.get("role") == "admin":
        return payload
    pages = pages_for(request.url.path, request.method, any_method=True) or ()
    mine = await effective_pages(payload)
    if any(p in mine and p not in ADMIN_ONLY_PAGES for p in pages):
        return payload
    await event("forbidden_admin", request, email=payload.get("email"))
    raise HTTPException(status_code=403, detail="Acesso restrito a administradores")


class PageGuardMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, secret: str, algorithm: str):
        super().__init__(app)
        self.secret, self.algorithm = secret, algorithm

    async def dispatch(self, request, call_next):
        path = request.url.path
        if path.startswith(_RATE_PUBLIC) and hit(f"pub:{client_ip(request)}", 60, 60):
            await event("rate_limited", request)
            return JSONResponse({"detail": "Muitas requisições. Tente novamente em instantes."}, status_code=429)
        pages = pages_for(path, request.method)
        auth = request.headers.get("authorization", "")
        if pages and auth.lower().startswith("bearer "):
            try:
                payload = jwt.decode(auth.split(" ", 1)[1].strip(), self.secret, algorithms=[self.algorithm])
            except Exception:
                payload = None
            if payload and payload.get("iss") != "mastermaq-tracking":
                mine = await effective_pages(payload)
                if not any(p in mine for p in pages):
                    await event("forbidden_page", request, email=payload.get("email"), page=pages[0])
                    return JSONResponse({"detail": "Você não tem acesso a esta página."}, status_code=403)
        return await call_next(request)


_CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline' https://maps.googleapis.com https://maps.gstatic.com https://assets.emergent.sh https://*.posthog.com",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' data: https://fonts.gstatic.com",
    "img-src 'self' data: blob: https:",
    "connect-src 'self' https: wss:",
    "media-src 'self' blob: data: https:",
    "worker-src 'self' blob:",
    "frame-src 'self' blob: https:",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'self'",
])


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        h = response.headers
        h["X-Content-Type-Options"] = "nosniff"
        h["X-Frame-Options"] = "SAMEORIGIN"
        h["Referrer-Policy"] = "strict-origin-when-cross-origin"
        h["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        h["Permissions-Policy"] = "camera=(self), microphone=(self), geolocation=(self)"
        h["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups"
        if not request.url.path.startswith("/api/"):
            h["Content-Security-Policy"] = _CSP
        if "server" in h:
            del h["server"]
        return response
