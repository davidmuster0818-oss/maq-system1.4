from fastapi import FastAPI, APIRouter, HTTPException, Depends, BackgroundTasks, Request, Header
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
import os
import sys
import io
import logging
from pathlib import Path
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
import uuid
import json
import subprocess
from datetime import datetime, timezone, timedelta
import jwt
import httpx
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import time as _time

ROOT_DIR = Path(__file__).parent

# ─── In-memory cache ──────────────────────────────────────────────
class SimpleCache:
    """Lightweight in-memory cache with TTL."""
    def __init__(self):
        self._store = {}
    
    def get(self, key):
        entry = self._store.get(key)
        if entry and _time.time() < entry["exp"]:
            return entry["val"]
        self._store.pop(key, None)
        return None
    
    def set(self, key, val, ttl=60):
        self._store[key] = {"val": val, "exp": _time.time() + ttl}
    
    def delete(self, key):
        self._store.pop(key, None)
    
    def invalidate(self, prefix=""):
        if not prefix:
            self._store.clear()
        else:
            keys = [k for k in self._store if k.startswith(prefix)]
            for k in keys:
                del self._store[k]

cache = SimpleCache()
# ──────────────────────────────────────────────────────────────────

# Load .env file ONLY if it exists and ONLY for development
# In production (Railway), environment variables should be set via the dashboard
env_file = ROOT_DIR / '.env'
if env_file.exists():
    load_dotenv(env_file, override=False)  # Don't override existing env vars

# Configure logging - WARNING level reduces Railway log volume (INFO for startup only)
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Keep main app at INFO, libs at WARNING

# MongoDB for local metadata (priority, etc.)
MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
DB_NAME = os.environ.get('DB_NAME', 'test_database')
mongo_client = AsyncIOMotorClient(MONGO_URL)
mongo_db = mongo_client[DB_NAME]
os_metadata_col = mongo_db["os_metadata"]

# Supabase configuration
supabase_url = os.environ.get('SUPABASE_URL')
supabase_key = os.environ.get('SUPABASE_SERVICE_KEY')

logger.info(f"=== Environment Configuration ===")
logger.info(f"SUPABASE_URL configured: {'Yes' if supabase_url else 'No'}")

if not supabase_url or not supabase_key:
    logger.error("SUPABASE_URL or SUPABASE_SERVICE_KEY not set!")
    sys.exit(1)

# Import Supabase DB adapter
from supabase_db import db
logger.info("Supabase DB adapter initialized")

# JWT config — falha rápido se não houver segredo configurado em prod.
# Antes usávamos "default_secret" como fallback, o que é um buraco grave:
# qualquer agente com conhecimento do fallback poderia forjar tokens.
JWT_SECRET = os.environ.get('JWT_SECRET')
if not JWT_SECRET or JWT_SECRET in ('default_secret', 'change-me', ''):
    logger.error("JWT_SECRET ausente ou inseguro — defina uma string forte em backend/.env")
    sys.exit(1)
JWT_ALGORITHM = "HS256"

# Telecontrol credentials
TELECONTROL_LOGIN = os.environ.get('TELECONTROL_LOGIN', '')
TELECONTROL_PASSWORD = os.environ.get('TELECONTROL_PASSWORD', '')
TELECONTROL_LOGIN_HQ = os.environ.get('TELECONTROL_LOGIN_HQ', '')
TELECONTROL_PASSWORD_HQ = os.environ.get('TELECONTROL_PASSWORD_HQ', '')
TELECONTROL_BASE_URL = os.environ.get('TELECONTROL_BASE_URL', 'https://posvenda.telecontrol.com.br')

# App credentials
APP_LOGIN_EMAIL = os.environ.get('APP_LOGIN_EMAIL', '')
APP_LOGIN_PASSWORD = os.environ.get('APP_LOGIN_PASSWORD', '')

# Try to import scraper (optional - requires Playwright)
try:
    from telecontrol_scraper import scraper, scraper_hisense, scraper_hq
    SCRAPER_AVAILABLE = True
    logger.info("Telecontrol scrapers loaded successfully (Hisense + HQ)")
except ImportError as e:
    SCRAPER_AVAILABLE = False
    scraper = None
    scraper_hisense = None
    scraper_hq = None
    logger.warning(f"Telecontrol scraper not available: {e}")
except Exception as e:
    SCRAPER_AVAILABLE = False
    scraper = None
    scraper_hisense = None
    scraper_hq = None
    logger.error(f"Error loading Telecontrol scraper: {e}")

# Create the main app
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

import security  # noqa: E402
security.init(mongo_db)
app.add_middleware(security.PageGuardMiddleware, secret=JWT_SECRET, algorithm=JWT_ALGORITHM)
app.add_middleware(security.SecurityHeadersMiddleware)


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s", request.url.path)
    return JSONResponse({"detail": "Erro interno do servidor"}, status_code=500)


# CORS must be FIRST middleware (before any route processing)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=False,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Cache-Control middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response as StarletteResponse

class CacheHeaderMiddleware(BaseHTTPMiddleware):
    """
    Cache policy:
      - Live data (service-orders, routes, notifications, tracking, statuses):
        no-store so iOS/Android browsers ALWAYS revalidate. Otherwise mobile
        Safari/Chrome keep stale data for minutes even after admin updates.
      - Static-ish endpoints (manuais previews, label templates): allow caching.
    """
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        path = request.url.path
        if request.method == "GET" and "/api/" in path:
            if "/manuais" in path and "/slide/" in path:
                # Manual slide PNGs are immutable per upload — cache 24h
                response.headers["Cache-Control"] = "private, max-age=86400"
            elif "/label-templates" in path:
                response.headers["Cache-Control"] = "private, max-age=60"
            elif path.endswith("/service-orders/statuses") or path.endswith("/service-orders/brands"):
                # Catalog endpoints: rarely change, allow browser caching 10 min
                response.headers["Cache-Control"] = "private, max-age=600"
            else:
                # Live data — always revalidate so mobile clients see updates immediately
                response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
                response.headers["Pragma"] = "no-cache"
                response.headers["Expires"] = "0"
        return response

app.add_middleware(CacheHeaderMiddleware)

# Register manuais module
from manuais_module import setup_manuais_routes, init_storage as init_manuais_storage
from whatsapp_module import setup_whatsapp_routes
from users_module import (
    setup_users_routes,
    seed_admin as seed_admin_user,
    find_user_by_email,
    verify_password as verify_user_password,
)
from label_templates_module import setup_label_templates_routes

@app.on_event("startup")
async def startup_ensure_playwright_browser():
    """Download Playwright chromium at runtime if missing.

    Cloud Build cannot fetch the ~180MB chromium binary during image build
    (network sandbox), so we install it lazily on container boot. This runs
    in the background so it doesn't delay FastAPI startup, and the auto-sync
    loop already sleeps 60s before first run — enough time for the download.
    """
    if not SCRAPER_AVAILABLE:
        logger.info("Skip playwright browser install: scraper not available")
        return

    async def _install():
        try:
            browsers_path = os.environ.get('PLAYWRIGHT_BROWSERS_PATH', '/root/.cache/ms-playwright')
            if os.path.isdir(browsers_path):
                entries = os.listdir(browsers_path)
                if any(name.startswith('chromium') for name in entries):
                    logger.info(f"Playwright chromium already present at {browsers_path}")
                    return
            logger.info("Installing Playwright chromium (first boot, may take ~60s)...")
            proc = await asyncio.create_subprocess_exec(
                sys.executable, '-m', 'playwright', 'install', 'chromium',
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0:
                logger.info("Playwright chromium installed successfully")
            else:
                logger.error(
                    f"Playwright install failed (rc={proc.returncode}): "
                    f"{stderr.decode(errors='ignore')[:500]}"
                )
        except Exception as e:
            logger.error(f"ensure_playwright_browser error: {e}")

    asyncio.create_task(_install())


@app.on_event("startup")
async def startup_breadcrumb_ttl():
    """Breadcrumbs de GPS expiram 30 dias após created_at (TTL index do Mongo)."""
    try:
        await mongo_db["tracking_breadcrumbs"].create_index("created_at", expireAfterSeconds=30 * 86400)
    except Exception as e:
        logger.error(f"breadcrumb TTL index error: {e}")


@app.on_event("startup")
async def startup_migrate():
    """Auto-migrate on startup: source names and status normalization"""
    try:
        # Init object storage
        try:
            init_manuais_storage()
        except Exception as e:
            logger.warning(f"Object storage init failed (non-fatal): {e}")

        # Migrate source 'telecontrol' -> 'telecontrol_hisense'
        r1 = await db.service_orders.update_many(
            {"source": "telecontrol"},
            {"$set": {"source": "telecontrol_hisense"}}
        )
        if r1.modified_count > 0:
            logger.info(f"Startup: migrated {r1.modified_count} OS source telecontrol -> telecontrol_hisense")

        # Migrate status 'AGUARDANDO ANÁLISE' -> 'Aguardando Análise A.T'
        r2 = await db.service_orders.update_many(
            {"status": {"$regex": "^AGUARDANDO AN[AÁ]LISE$", "$options": "i"}},
            {"$set": {"status": "Aguardando Análise A.T"}}
        )
        if r2.modified_count > 0:
            logger.info(f"Startup: migrated {r2.modified_count} OS status -> Aguardando Análise A.T")

    except Exception as e:
        logger.warning(f"Startup migration failed (non-fatal): {e}")

    # Seed master admin user (bcrypt) — idempotent
    try:
        await seed_admin_user(mongo_db)
        logger.info("Master admin seeded/validated")
    except Exception as e:
        logger.warning(f"Admin seeding failed (non-fatal): {e}")


@app.on_event("startup")
async def startup_auto_sync():
    """Start background auto-sync loop for Telecontrol HISENSE only.

    HQ is NOT auto-synced — it runs only on manual trigger via the
    "Sincronizar" button (POST /api/telecontrol/sync).

    ⚠️  HISENSE auto-sync is now GATED by env `HISENSE_AUTO_SYNC_ENABLED`
        (default: "false" — desligado). Motivo: em produção tier_0 (512Mi)
        o loop lançava Playwright/chromium a cada 30 min e causava
        pressão de memória → OOM-kill do chromium → conexões TCP resetadas
        → Cloudflare devolvia HTTP 520 no login. Diagnóstico do RCA
        `deployer-agent-docs/RCA_f694aa85-*.MD` (30/08/2026).

        Para religar em preview/dev, defina no `.env`:
            HISENSE_AUTO_SYNC_ENABLED=true

        Em produção, mantenha desligado e use o botão "Sincronizar" no
        painel para puxar manualmente (mesmo fluxo do HQ). O botão dispara
        `POST /api/telecontrol/sync` que roda em background e é isolado
        (não fica em loop consumindo memória).

    Tracks scraper health: each source has a consecutive_failures counter.
    When >= 2, scraper is considered DOWN and surfaced via /api/scrapers/health.
    On recovery (next successful run), an auto-resync of last 60 days runs to
    capture OSs missed during the outage.
    """
    import asyncio

    hisense_auto = os.environ.get("HISENSE_AUTO_SYNC_ENABLED", "false").strip().lower() in {"1", "true", "yes", "y"}

    async def hisense_loop():
        interval = int(os.environ.get('SYNC_INTERVAL_MINUTES', 10))
        window_days = int(os.environ.get('HISENSE_SYNC_WINDOW_DAYS', 14))
        logger.info(f"Auto-sync HISENSE loop started: every {interval} minutes ({window_days}-day window)")
        logger.info("HQ auto-sync DISABLED — HQ runs only on manual sync (Sincronizar button)")
        await asyncio.sleep(60)  # Wait 1 min after startup before first sync
        while True:
            try:
                if SCRAPER_AVAILABLE and scraper_hisense and TELECONTROL_LOGIN:
                    end_date = datetime.now()
                    start_date = end_date - timedelta(days=window_days)
                    start_str = start_date.strftime("%d/%m/%Y")
                    end_str = end_date.strftime("%d/%m/%Y")
                    await _run_sync_with_health("hisense", scraper_hisense, start_str, end_str)
            except Exception as e:
                logger.error(f"Hisense sync loop error: {e}")
            await asyncio.sleep(interval * 60)

    # Load persisted scraper health on boot (independe do loop, só mantém badge coerente)
    # Deve rodar ANTES de setar "manual" para não sobrescrever depois.
    await _load_health_from_db()

    if hisense_auto:
        asyncio.create_task(hisense_loop())
        # Watchdog só faz sentido se o loop está ativo.
        asyncio.create_task(_scraper_watchdog())
    else:
        logger.info(
            "Hisense auto-sync DISABLED (HISENSE_AUTO_SYNC_ENABLED=false). "
            "Use o botão 'Sincronizar' no painel para puxar manualmente."
        )
        # Zera o status para o badge parar de indicar "down" — o loop foi
        # desligado por decisão operacional, não por falha do scraper.
        SCRAPER_HEALTH["hisense"].update({
            "status": "manual",
            "consecutive_failures": 0,
            "last_error": None,
        })
        try:
            await _persist_health("hisense")
        except Exception:  # noqa: BLE001
            pass


async def _scraper_watchdog():
    """Background task that flips a scraper to `down` when its last run is
    stale (older than 3× SYNC_INTERVAL_MINUTES). Runs every minute.

    Only checks HISENSE (HQ is manual-only — no expectation of periodic
    runs, so a stale HQ isn't a bug).
    """
    import asyncio
    interval_min = int(os.environ.get('SYNC_INTERVAL_MINUTES', 10))
    stale_threshold_sec = interval_min * 60 * 3
    # Wait a bit after boot so we don't fire on a fresh container.
    await asyncio.sleep(60)
    while True:
        try:
            h = SCRAPER_HEALTH.get("hisense")
            if h and h.get("last_run"):
                try:
                    last_run_dt = datetime.fromisoformat(h["last_run"].replace("Z", "+00:00"))
                    age_sec = (datetime.now(timezone.utc) - last_run_dt).total_seconds()
                    if age_sec > stale_threshold_sec:
                        # Only escalate if we're not already down.
                        if h.get("status") != "down":
                            h["status"] = "down"
                            h["last_error"] = (
                                f"Watchdog: sem sync há {int(age_sec/60)} min "
                                f"(esperado a cada {interval_min} min). Processo travado?"
                            )
                            logger.error(f"[watchdog] {h['last_error']}")
                            await _persist_health("hisense")
                except (TypeError, ValueError):
                    pass
        except Exception as e:  # noqa: BLE001
            logger.warning(f"watchdog tick error: {e}")
        await asyncio.sleep(60)


# === Scraper Health tracking ===
# In-memory dict updated by sync runs. Persisted to MongoDB collection `scraper_health`
# so the badge survives backend restarts.
SCRAPER_HEALTH = {
    "hisense": {"status": "unknown", "consecutive_failures": 0, "last_success": None, "last_failure": None, "last_error": None, "last_run": None, "last_volume": None, "recent_volumes": []},
    "hq": {"status": "unknown", "consecutive_failures": 0, "last_success": None, "last_failure": None, "last_error": None, "last_run": None, "last_volume": None, "recent_volumes": []},
}

# Use MongoDB (not Supabase) to persist scraper health - this collection does not exist in Supabase schema.
scraper_health_col = mongo_db["scraper_health"]


async def _load_health_from_db():
    try:
        async for doc in scraper_health_col.find({}, {"_id": 0}):
            src = doc.get("source")
            if src in SCRAPER_HEALTH:
                SCRAPER_HEALTH[src].update({k: v for k, v in doc.items() if k != "source"})
    except Exception as e:
        logger.warning(f"Could not load scraper health from DB: {e}")


async def _persist_health(source: str):
    try:
        await scraper_health_col.update_one(
            {"source": source},
            {"$set": {**SCRAPER_HEALTH[source], "source": source}},
            upsert=True,
        )
    except Exception as e:
        logger.warning(f"Could not persist scraper health for {source}: {e}")


async def _run_sync_with_health(source: str, scraper, start_str: str, end_str: str):
    """Run scraper sync, update health metrics, and trigger auto-resync on recovery.

    Hardened after the 28/07/2026 silent-truncation incident:
      * `result["success"] = False` (login failed / pagination broke) is
        treated as a real failure and increments `consecutive_failures`.
      * Anomalous volume detection: if this sync collected < 20% of the
        recent average (last 5 successful syncs), we bump the status to
        `warning` even though no exception was raised. The badge shows
        "Scraper instável" so the ops team investigates instead of
        finding out days later that pages got dropped mid-run.
    """
    h = SCRAPER_HEALTH[source]
    was_down = h["consecutive_failures"] >= 2
    try:
        result = await scraper.sync_orders(start_str, end_str, db)
        synced = result.get("orders_synced", 0)
        updated = result.get("orders_updated", 0)
        errors_list = result.get("errors", []) or []

        # Explicit-failure path — scraper returned success=False (broken
        # login or pagination). Route into the except-arm behaviour so the
        # badge lights up.
        if not result.get("success", False):
            raise RuntimeError(
                f"scraper reported success=False; errors={errors_list[:3]}"
            )

        # Success path
        h["status"] = "ok"
        h["consecutive_failures"] = 0
        h["last_success"] = datetime.now(timezone.utc).isoformat()
        h["last_error"] = None
        h["last_volume"] = synced + updated

        # Anomaly detection: compare with historical mean. Threshold is
        # kept generous (20% of average) so normal quiet periods don't
        # trigger — the goal is to catch pagination truncation, not to
        # nag on slow days.
        try:
            history = h.get("recent_volumes") or []
            history.append(synced + updated)
            history = history[-10:]  # keep last 10 runs
            h["recent_volumes"] = history
            eligible = [v for v in history[:-1] if v > 0]
            if len(eligible) >= 5:
                avg = sum(eligible) / len(eligible)
                if (synced + updated) < 0.2 * avg:
                    h["status"] = "warning"
                    h["last_error"] = (
                        f"Volume anômalo: {synced + updated} vs. média "
                        f"{avg:.1f} (últimos {len(eligible)} ciclos). "
                        f"Pode ser paginação truncada."
                    )
                    logger.warning(
                        f"[{source}] {h['last_error']}"
                    )
        except Exception as ae:  # noqa: BLE001
            logger.debug(f"volume anomaly check failed (non-fatal): {ae}")

        # Record the "when" so the watchdog can detect stalls
        h["last_run"] = datetime.now(timezone.utc).isoformat()
        logger.info(f"Auto-sync {source.title()}: {synced} new, {updated} updated")
        await _persist_health(source)

        # Recovery: scraper was DOWN -> trigger 60-day catch-up resync.
        if was_down:
            logger.warning(f"Scraper {source} RECOVERED — triggering 60-day catch-up resync")
            try:
                catchup = await scraper.sync_orders(start_str, end_str, db)
                logger.info(f"Catch-up {source.title()}: {catchup.get('orders_synced', 0)} new, {catchup.get('orders_updated', 0)} updated")
            except Exception as ce:
                logger.error(f"Catch-up {source} failed: {ce}")
    except Exception as e:
        h["status"] = "down" if h["consecutive_failures"] + 1 >= 2 else "warning"
        h["consecutive_failures"] += 1
        h["last_failure"] = datetime.now(timezone.utc).isoformat()
        h["last_run"] = datetime.now(timezone.utc).isoformat()
        h["last_error"] = str(e)[:300]
        logger.error(f"Auto-sync {source.title()} error: {e} (consecutive failures: {h['consecutive_failures']})")
        await _persist_health(source)

# Health check endpoint - dedicated for Railway deployment
@app.get("/health")
async def health_check():
    # Check if frontend build exists and when it was created
    build_info = "no_build"
    build_path = Path(__file__).parent.parent / "frontend" / "build"
    if build_path.exists():
        index = build_path / "index.html"
        if index.exists():
            import time
            mtime = index.stat().st_mtime
            build_info = time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(mtime))
    return {"status": "ok", "build_time": build_info}

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Health also on /api/health for deploy compatibility
@api_router.get("/health")
async def api_health():
    return {"status": "ok", "service": "mastermaq-api"}


@api_router.get("/admin/env-check")
async def env_check(secret: str = ""):
    """Production diagnostic endpoint.
    
    Lists the 28 env vars the app needs and shows which ones are MISSING or
    blank. Does NOT expose any actual values — only `true/false` flags + the
    first 4 characters of present values (so the user can confirm they
    pasted the right secret in production).
    
    For SUPABASE_URL, exposes the project ref (the subdomain) so the user
    can verify they are pointing at the *correct* Supabase instance
    (vqzwgkevsaihlgmcswvi = new, vvipycbtdcpzxfoebmia = old/exhausted).
    
    Also runs a live test query to confirm whether the `products` table
    is actually reachable from this runtime.
    
    Protected by a shared secret matching JWT_SECRET to avoid leaking env
    presence info publicly. Pass `?secret=<JWT_SECRET>`.
    """
    import hmac
    if not secret or not hmac.compare_digest(secret, os.environ.get('JWT_SECRET', '')):
        raise HTTPException(status_code=401, detail="missing or wrong ?secret=")
    
    required = [
        "MONGO_URL", "DB_NAME",
        "SUPABASE_URL", "SUPABASE_SERVICE_KEY", "SUPABASE_ANON_KEY", "SUPABASE_SENHA",
        "APP_LOGIN_EMAIL", "APP_LOGIN_PASSWORD", "JWT_SECRET",
        "CORS_ORIGINS",
        "TELECONTROL_LOGIN", "TELECONTROL_PASSWORD",
        "TELECONTROL_LOGIN_HQ", "TELECONTROL_PASSWORD_HQ",
        "TELECONTROL_BASE_URL",
        "SYNC_INTERVAL_MINUTES", "HISENSE_SYNC_WINDOW_DAYS",
        "PLAYWRIGHT_BROWSERS_PATH",
        "WA_APP_SECRET", "WA_APP_ID", "WA_PERMANENT_TOKEN",
        "GOOGLE_MAPS_API_KEY",
        "ASSINAFY_API_KEY", "ASSINAFY_WORKSPACE_ID", "ASSINAFY_API_URL",
        "EMERGENT_LLM_KEY",
        "EXTERNAL_API_KEY", "EXTERNAL_WEBHOOK_URL",
    ]
    
    present: dict = {}
    missing: list = []
    for k in required:
        v = (os.environ.get(k) or "").strip()
        if not v:
            missing.append(k)
        else:
            present[k] = f"{v[:4]}…(len={len(v)})"
    
    # Reveal the Supabase project ref so the user can confirm the correct
    # instance is configured (old vs new — both URLs are 40 chars otherwise).
    supabase_url = os.environ.get("SUPABASE_URL", "")
    project_ref = ""
    if "supabase.co" in supabase_url:
        try:
            project_ref = supabase_url.split("//")[1].split(".")[0]
        except Exception:
            project_ref = "unparseable"
    
    # Live test: hit /products?limit=0 and report status + Postgrest error if any
    live_test: dict = {}
    try:
        from supabase_db import _get_client, _headers, SUPABASE_URL as adapter_url
        c = _get_client()
        r = await c.get(f"{adapter_url}/rest/v1/products?select=code&limit=1",
                        headers=_headers(), timeout=10)
        live_test = {
            "url_resolved": f"{adapter_url}/rest/v1/products",
            "http_status": r.status_code,
            "response_first_200": r.text[:200],
        }
    except Exception as e:
        live_test = {"error": str(e)[:200]}
    
    return {
        "total_required": len(required),
        "present_count": len(present),
        "missing_count": len(missing),
        "missing": missing,
        "present_preview": present,
        "supabase_project_ref": project_ref,
        "expected_supabase_ref": "vqzwgkevsaihlgmcswvi (current/active)",
        "old_exhausted_ref": "vvipycbtdcpzxfoebmia (egress quota exhausted)",
        "live_products_query": live_test,
        "hint": (
            "If supabase_project_ref != 'vqzwgkevsaihlgmcswvi', that's the bug — "
            "you're pointing at the OLD exhausted Supabase. Update SUPABASE_URL, "
            "SUPABASE_SERVICE_KEY and SUPABASE_ANON_KEY in production secrets."
        ),
    }


http_bearer = HTTPBearer()

# OS Status colors mapping
OS_STATUS_COLORS = {
    "Aguardando Peças": {"bg": "#FEF3C7", "text": "#92400E"},
    "Aguardando Conserto": {"bg": "#F3E8FF", "text": "#7C3AED"},
    "Aguardando Retirada": {"bg": "#EDE9FE", "text": "#6D28D9"},
    "Finalizada": {"bg": "#D1FAE5", "text": "#065F46"},
    "Aguard. Abastecimento Estoque": {"bg": "#DBEAFE", "text": "#1E40AF"},
    "Em transito": {"bg": "#F3F4F6", "text": "#4B5563"},
    "Em auditoria": {"bg": "#FEE2E2", "text": "#991B1B"},
    "Aguardando Analise A.T": {"bg": "#FECACA", "text": "#B91C1C"},
    "Aberta Call-Center": {"bg": "#F9FAFB", "text": "#6B7280"},
    "Aguardando Confirmação Cliente": {"bg": "#E0F2FE", "text": "#0369A1"},
    "Aguardando Produto": {"bg": "#FFEDD5", "text": "#C2410C"},
    "OS Cancelada": {"bg": "#FEE2E2", "text": "#7F1D1D"},
    "Visita Realizada": {"bg": "#CCFBF1", "text": "#0F766E"},
    "AGUARDANDO ANÁLISE": {"bg": "#FEF3C7", "text": "#92400E"},
}

# Pydantic Models
class LoginRequest(BaseModel):
    email: str
    password: str

class LoginResponse(BaseModel):
    token: str
    email: str
    role: str = "admin"
    name: str = ""

class ServiceOrderCreate(BaseModel):
    os_number: str
    customer_name: str
    registration_date: str
    attendance_date: Optional[str] = None
    cep: str
    address: str
    number: str
    neighborhood: str
    city: str
    state: str
    complement: Optional[str] = None
    phone1: str
    phone2: Optional[str] = None
    landline: Optional[str] = None
    email: Optional[str] = None
    visit_fee: Optional[float] = None
    reference_point: Optional[str] = None
    service_type: Optional[str] = None
    product: str
    brand: str
    model: str
    reported_defect: str
    observations: Optional[str] = None
    status: Optional[str] = "Orçamento"
    sub_status: Optional[str] = "Aguardando"
    micro_status: Optional[str] = None

class ServiceOrder(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    os_number: str
    customer_name: str
    registration_date: str
    attendance_date: Optional[str] = None
    cep: str
    address: str
    number: str
    neighborhood: str
    city: str
    state: str
    complement: Optional[str] = None
    phone1: str
    phone2: Optional[str] = None
    landline: Optional[str] = None
    email: Optional[str] = None
    visit_fee: Optional[float] = None
    reference_point: Optional[str] = None
    service_type: Optional[str] = None
    product: str
    brand: str
    model: str
    serial_number: Optional[str] = None
    batch: Optional[str] = None
    reported_defect: str
    observations: Optional[str] = None
    status: str = ""
    sub_status: Optional[str] = None
    micro_status: Optional[str] = None
    technical_diagnosis: Optional[str] = None
    installation_correct: Optional[str] = None
    required_parts: Optional[str] = None
    technician: Optional[str] = None
    voltage_f1f2: Optional[str] = None
    voltage_f1_terra: Optional[str] = None
    voltage_f2_terra: Optional[str] = None
    photo_1: Optional[str] = None
    photo_2: Optional[str] = None
    photo_3: Optional[str] = None
    photo_4: Optional[str] = None
    photo_5: Optional[str] = None
    photo_6: Optional[str] = None
    photo_7: Optional[str] = None
    photo_8: Optional[str] = None
    photo_9: Optional[str] = None
    signature_technician: Optional[str] = None
    signature_client: Optional[str] = None
    signature_client_name: Optional[str] = None
    signature_client_cpf: Optional[str] = None
    signature_date: Optional[str] = None
    assinafy_document_id: Optional[str] = None
    assinafy_status: Optional[str] = None
    status_orcamento: Optional[str] = None
    conclusao_orcamento: Optional[str] = None
    priority: Optional[bool] = False
    scheduling_history: Optional[List[dict]] = None
    source: str = "local"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @field_validator('visit_fee', mode='before')
    @classmethod
    def parse_visit_fee(cls, v):
        if v is None or v == '' or v == 'null':
            return None
        try:
            return float(v)
        except (ValueError, TypeError):
            return None

class ServiceOrderUpdate(BaseModel):
    customer_name: Optional[str] = None
    attendance_date: Optional[str] = None
    cep: Optional[str] = None
    address: Optional[str] = None
    number: Optional[str] = None
    neighborhood: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    complement: Optional[str] = None
    phone1: Optional[str] = None
    phone2: Optional[str] = None
    landline: Optional[str] = None
    email: Optional[str] = None
    visit_fee: Optional[float] = None
    visit_fee_paid: Optional[bool] = None
    reference_point: Optional[str] = None
    service_type: Optional[str] = None
    product: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    batch: Optional[str] = None
    reported_defect: Optional[str] = None
    observations: Optional[str] = None
    status: Optional[str] = None
    sub_status: Optional[str] = None
    micro_status: Optional[str] = None
    technical_diagnosis: Optional[str] = None
    installation_correct: Optional[str] = None
    required_parts: Optional[str] = None
    technician: Optional[str] = None
    voltage_f1f2: Optional[str] = None
    voltage_f1_terra: Optional[str] = None
    voltage_f2_terra: Optional[str] = None
    photo_1: Optional[str] = None
    photo_2: Optional[str] = None
    photo_3: Optional[str] = None
    photo_4: Optional[str] = None
    photo_5: Optional[str] = None
    photo_6: Optional[str] = None
    photo_7: Optional[str] = None
    photo_8: Optional[str] = None
    photo_9: Optional[str] = None
    status_orcamento: Optional[str] = None
    conclusao_orcamento: Optional[str] = None
    signature_technician: Optional[str] = None
    signature_client: Optional[str] = None
    signature_client_name: Optional[str] = None
    signature_client_cpf: Optional[str] = None
    signature_date: Optional[str] = None
    assinafy_document_id: Optional[str] = None
    assinafy_status: Optional[str] = None
    priority: Optional[bool] = None

    @field_validator('visit_fee', mode='before')
    @classmethod
    def parse_visit_fee(cls, v):
        if v is None or v == '' or v == 'null':
            return None
        try:
            return float(v)
        except (ValueError, TypeError):
            return None

class Notification(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    message: str
    os_number: str
    old_status: Optional[str] = None
    new_status: str
    read: bool = False
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class CEPResponse(BaseModel):
    cep: str
    logradouro: str
    bairro: str
    localidade: str
    uf: str

# Auth helpers
TOKEN_EXPIRY_SECONDS = 7 * 24 * 3600  # 7 dias (renovado automaticamente ao abrir o app)

def create_token(email: str, role: str = "admin", name: str = "", user_id: str = "") -> str:
    payload = {
        "email": email,
        "role": role,
        "name": name,
        "user_id": user_id,
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "exp": datetime.now(timezone.utc).timestamp() + TOKEN_EXPIRY_SECONDS
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(http_bearer)):
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    if payload.get("iss") == "mastermaq-tracking":
        raise HTTPException(status_code=401, detail="Invalid token")
    payload.setdefault("role", "technician")
    payload.setdefault("name", "")
    return await security.check_session(payload)


async def require_admin(request: Request, payload: dict = Depends(verify_token)):
    return await security.admin_or_granted(request, payload)


async def _assert_tech_os(payload: dict, os_number: str):
    """Técnico sem a página OS só acessa OSs que estão em roteiros dele (anti-IDOR)."""
    if payload.get("role") != "technician" or "service-orders" in await security.effective_pages(payload):
        return
    from routes_module import _is_own
    routes = await db.routes.find({}, {"_id": 0, "technician": 1, "orders": 1}).to_list(5000)
    for r in routes:
        if _is_own(r.get("technician"), payload) and any(str(o.get("os_number")) == str(os_number) for o in r.get("orders") or []):
            return
    raise HTTPException(status_code=403, detail="OS fora dos seus roteiros")

# Routes
@api_router.get("/")
async def root():
    return {"message": "Mastermaq OS Management API"}

@api_router.get("/dashboard")
async def get_dashboard(_: dict = Depends(verify_token)):
    """Aggregated dashboard - 1 call instead of 3+ separate calls"""
    cached = cache.get("dashboard")
    if cached: return cached
    
    statuses_raw = await db.service_orders.distinct("status")
    total_count = await db.service_orders.count_documents({})
    
    result = {
        "total_orders": total_count,
        "statuses": sorted([s for s in statuses_raw if s]),
    }
    cache.set("dashboard", result, ttl=300)
    return result


# ─── External OS intake API (no auth required - uses API key) ─────────
EXTERNAL_API_KEY = os.environ.get("EXTERNAL_API_KEY", "mastermaq_ext_2024_secure")
EXTERNAL_WEBHOOK_URL = os.environ.get("EXTERNAL_WEBHOOK_URL", "https://mastermaqassistencia.com.br/api/external/webhook/status")
MASTERMAQ_NOTIFY_PHONE = "553134225293"  # (31) 3422-5293

class ExternalOS(BaseModel):
    """OS received from external website/system"""
    customer_name: str
    phone1: str
    address: Optional[str] = None
    number: Optional[str] = None
    neighborhood: Optional[str] = None
    city: Optional[str] = "Belo Horizonte"
    state: Optional[str] = "MG"
    cep: Optional[str] = None
    email: Optional[str] = None
    product: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    reported_defect: Optional[str] = None
    observations: Optional[str] = None
    service_type: Optional[str] = "Orçamento"
    reference_point: Optional[str] = None
    complement: Optional[str] = None

def verify_api_key(x_api_key: str = Header(None)):
    if not x_api_key or x_api_key != EXTERNAL_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return True

async def send_webhook_status(os_number: str, status: str, technician: str = "", notes: str = "", event_type: str = "status_update"):
    """Fire-and-forget: notify external site about OS status change.
    Logs every attempt in `webhook_outbound_log` (Mongo) for auditing.
    Payload includes BOTH `os_number` and `external_os_number` so the receiver
    can match by either field.
    """
    payload = {
        "os_number": os_number,
        "external_os_number": os_number,
        "status": status,
        "event_type": event_type,
    }
    if technician:
        payload["technician"] = technician
    if notes:
        payload["notes"] = notes

    log_entry = {
        "id": str(uuid.uuid4()),
        "os_number": os_number,
        "url": EXTERNAL_WEBHOOK_URL,
        "payload": payload,
        "sent_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(
                EXTERNAL_WEBHOOK_URL,
                json=payload,
                headers={"Content-Type": "application/json", "X-API-Key": EXTERNAL_API_KEY},
            )
        log_entry["status_code"] = r.status_code
        log_entry["response_body"] = (r.text or "")[:500]
        log_entry["ok"] = 200 <= r.status_code < 300
        logger.info(f"Webhook sent for OS {os_number} -> {status}: HTTP {r.status_code}")
    except Exception as e:
        log_entry["error"] = str(e)
        log_entry["ok"] = False
        logger.warning(f"Webhook failed for OS {os_number}: {e}")
    try:
        await mongo_db["webhook_outbound_log"].insert_one(log_entry)
    except Exception:
        pass
    # Strip the ObjectId that insert_one mutated into the dict before returning.
    log_entry.pop("_id", None)
    return log_entry

async def send_wa_notification(text: str):
    """Send WhatsApp text message to Mastermaq office number."""
    try:
        config = await db.whatsapp_config.find_one({}, {"_id": 0})
        wa_token = os.environ.get("WA_PERMANENT_TOKEN", "")
        if not wa_token and config:
            wa_token = config.get("access_token", "")
        phone_id = config.get("phone_number_id", "") if config else ""
        if not wa_token or not phone_id:
            logger.warning("WhatsApp not configured, skipping notification")
            return
        url = f"https://graph.facebook.com/v21.0/{phone_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": MASTERMAQ_NOTIFY_PHONE,
            "type": "text",
            "text": {"preview_url": False, "body": text},
        }
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(url, json=payload, headers={"Authorization": f"Bearer {wa_token}", "Content-Type": "application/json"})
            if r.status_code >= 400:
                logger.warning(f"WA notification error {r.status_code}: {r.text[:200]}")
            else:
                logger.info(f"WA notification sent: {r.status_code}")
    except Exception as e:
        logger.warning(f"WA notification failed: {e}")

@api_router.post("/external/service-orders")
async def create_external_os(data: ExternalOS, background_tasks: BackgroundTasks, _: bool = Depends(verify_api_key)):
    """
    Create OS from external website/system.
    Uses the same numbering pattern as internal Mastermaq OS (sequential 5-digit).
    Source = "external_site". NEVER reuses an existing os_number from any source.
    """
    # Get next OS number - 5 digit sequential, scanning ALL sources to avoid collision.
    # Filter by known internal sources; telecontrol (8 digits) is naturally excluded.
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(
                f"{supabase_url}/rest/v1/service_orders?select=os_number&source=in.(local,mastermaq,external_site)&order=os_number.desc&limit=50",
                headers={"apikey": supabase_key, "Authorization": f"Bearer {supabase_key}"},
            )
        max_num = 27577
        if r.status_code == 200:
            for row in r.json():
                osn = str(row.get("os_number", "")).strip()
                # Only consider 5-digit numeric numbers (Mastermaq internal pattern)
                if osn.isdigit() and len(osn) <= 5:
                    max_num = max(max_num, int(osn))
        candidate = max_num + 1
    except Exception as e:
        logger.warning(f"Failed to get next OS number: {e}")
        candidate = int(datetime.now(timezone.utc).timestamp()) % 100000

    # Defensive: ensure candidate is unique. Walk forward until free (max 50 attempts).
    os_number = None
    for attempt in range(50):
        n = str(candidate + attempt)
        existing = await db.service_orders.find_one({"os_number": n}, {"_id": 0, "os_number": 1})
        if not existing:
            os_number = n
            break
    if os_number is None:
        # Extremely unlikely — fallback to timestamp-based unique number
        os_number = f"E{int(datetime.now(timezone.utc).timestamp())}"
        logger.error(f"create_external_os: could not find free 5-digit slot near {candidate}, using fallback {os_number}")

    os_id = f"ext-{os_number}-{int(datetime.now(timezone.utc).timestamp())}"
    now = datetime.now(timezone.utc)
    reg_date = now.strftime("%d/%m/%Y")

    # --- Business rule: classify service_type based on brand / warranty ---
    # If the external form sent "Instalação" (which is not a valid service_type in our system):
    #   1. Append "Instalação" to observations so the technician sees the context
    #   2. Infer the service_type from brand:
    #      - Hisense / HQ / Franke  -> Garantia <marca>  (these are our warranty partners)
    #      - Any other brand         -> Orçamento        (assumed out of warranty by default)
    raw_svc = (data.service_type or "").strip()
    raw_svc_lc = raw_svc.lower()
    brand_lc = (data.brand or "").strip().lower()
    observations_in = data.observations or ""
    inferred_svc = raw_svc
    extra_obs = None

    if raw_svc_lc in ("instalação", "instalacao", "instalacaoo", "install"):
        extra_obs = "Instalação"
        if "hisense" in brand_lc:
            inferred_svc = "Garantia Hisense"
        elif brand_lc == "hq" or brand_lc.startswith("hq "):
            inferred_svc = "Garantia HQ"
        elif "franke" in brand_lc:
            inferred_svc = "Garantia Franke"
        else:
            inferred_svc = "Orçamento"
    elif not raw_svc:
        inferred_svc = "Orçamento"

    # OSs do site: texto do formulário vai para site_info (não para Observações).
    final_obs = extra_obs or ""
    
    order_doc = {
        "id": os_id,
        "os_number": os_number,
        "customer_name": data.customer_name,
        "phone1": data.phone1,
        "phone2": "",
        "landline": "",
        "address": data.address or "",
        "number": data.number or "",
        "neighborhood": data.neighborhood or "",
        "city": data.city or "Belo Horizonte",
        "state": data.state or "MG",
        "cep": data.cep or "",
        "complement": data.complement or "",
        "email": data.email or "",
        "product": data.product or "",
        "brand": data.brand or "",
        "model": data.model or "",
        "serial_number": data.serial_number or "",
        "batch": "",
        "reported_defect": data.reported_defect or "",
        "observations": final_obs,
        "site_info": observations_in,
        "service_type": inferred_svc,
        "reference_point": data.reference_point or "",
        "status": "Aguardando Analise A.T",
        "sub_status": "",
        "micro_status": "",
        "technician": "",
        "source": "external_site",
        "registration_date": reg_date,
        "sort_date": now.isoformat(),
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }

    try:
        await db.service_orders.insert_one(order_doc)
    except RuntimeError as e:
        logger.error(f"create_external_os insert failed for OS {os_number}: {e}")
        raise HTTPException(status_code=409, detail=f"Conflict creating OS: {str(e)[:200]}")
    
    # Track external OS counter for polling
    await os_metadata_col.update_one(
        {"_key": "ext_os_counter"},
        {"$inc": {"count": 1}, "$set": {"last_os": os_number, "last_at": now.isoformat()}},
        upsert=True
    )
    
    # Invalidate caches
    cache.invalidate("os_list:")
    cache.invalidate("overdue")
    cache.invalidate("dashboard")
    
    logger.info(f"External OS created: {os_number} - {data.customer_name}")
    
    # Notify Mastermaq via WhatsApp
    msg = f"OS {os_number} chegou no sistema. Cliente: {data.customer_name}. Tel: {data.phone1}."
    if data.reported_defect:
        msg += f" Defeito: {data.reported_defect}."
    background_tasks.add_task(send_wa_notification, msg)
    
    return {
        "success": True,
        "os_number": os_number,
        "id": os_id,
        "status": "Aguardando Analise A.T",
        "message": f"OS {os_number} criada com sucesso"
    }

@api_router.get("/external/service-orders/{os_number}")
async def get_external_os_status(os_number: str, _: bool = Depends(verify_api_key)):
    """Check OS status from external system. Requires X-API-Key header."""
    order = await db.service_orders.find_one(
        {"os_number": os_number},
        {"_id": 0, "os_number": 1, "customer_name": 1, "status": 1, "technician": 1,
         "service_type": 1, "created_at": 1, "updated_at": 1}
    )
    if not order:
        raise HTTPException(status_code=404, detail="OS não encontrada")
    return order

@api_router.get("/new-external-os")
async def check_new_external_os(_: dict = Depends(verify_token)):
    """Poll endpoint: returns the current count + latest external OS.
    `new_os=True` means the count grew since the last cache window;
    `new_os=False` still returns the real count so the frontend can
    keep its reference in sync (preventing false alerts on cache misses).
    
    Egress optimization: full response cached for 60s. Multiple admin
    polls within that window share the same cached payload (no Supabase
    egress until the cache expires).
    """
    cached_resp = cache.get("new_ext_os_response")
    if cached_resp:
        return cached_resp
    
    cached_count = cache.get("last_ext_os_count")
    current = await os_metadata_col.find_one({"_key": "ext_os_counter"}, {"_id": 0})
    current_count = current.get("count", 0) if current else 0

    latest = await db.service_orders.find(
        {"source": "external_site"},
        {"_id": 0, "os_number": 1, "customer_name": 1, "phone1": 1, "reported_defect": 1, "created_at": 1}
    ).sort("created_at", -1).limit(1).to_list(1)

    is_new = cached_count is None or cached_count != current_count
    cache.set("last_ext_os_count", current_count, ttl=300)

    resp = {
        "new_os": is_new,
        "count": current_count,
        "latest": latest[0] if latest else None
    }
    # Cache the full response for 60s — saves ~75% of Supabase hits from
    # the admin's 15s frontend poll (now effectively 1 hit/min instead of 4).
    cache.set("new_ext_os_response", resp, ttl=60)
    return resp



@api_router.post("/auth/login", response_model=LoginResponse)
async def login(request: LoginRequest, http: Request):
    email = (request.email or "").strip().lower()
    ip = security.client_ip(http)
    if security.hit(f"loginip:{ip}", 20, 900) or security.hit(f"loginem:{email}", 8, 900):
        await security.event("login_blocked", http, email=email)
        raise HTTPException(status_code=429, detail="Muitas tentativas. Aguarde 15 minutos.")
    # 1) Try DB user (bcrypt). Seeded admin lives here too.
    user = await find_user_by_email(mongo_db, email)
    if user and user.get("active", True) and verify_user_password(request.password, user.get("password_hash", "")):
        token = create_token(
            email=user["email"],
            role=user.get("role", "technician"),
            name=user.get("name", ""),
            user_id=user.get("id", ""),
        )
        await security.event("login_ok", http, email=email)
        return LoginResponse(token=token, email=user["email"], role=user.get("role", "technician"), name=user.get("name", ""))

    # 2) Fallback: legacy env-based admin (in case seed hasn't run yet)
    import hmac
    if APP_LOGIN_PASSWORD and email == (APP_LOGIN_EMAIL or "").strip().lower() and hmac.compare_digest(request.password or "", APP_LOGIN_PASSWORD):
        token = create_token(email=email, role="admin", name="Administrador")
        await security.event("login_ok", http, email=email)
        return LoginResponse(token=token, email=email, role="admin", name="Administrador")

    await security.event("login_failed", http, email=email)
    raise HTTPException(status_code=401, detail="Credenciais inválidas")

@api_router.get("/auth/verify")
async def verify_auth(payload: dict = Depends(verify_token)):
    # Re-fetch role/name from DB so updates to user record are reflected immediately
    email = (payload.get("email") or "").strip().lower()
    user = await find_user_by_email(mongo_db, email)
    if user and user.get("active", True):
        return {
            "valid": True,
            "email": user["email"],
            "role": user.get("role", "technician"),
            "name": user.get("name", ""),
            "user_id": user.get("id", ""),
            "pages": security.pages_of(user, user.get("role", ""), email),
        }
    # Legacy env admin fallback
    if email == (APP_LOGIN_EMAIL or "").strip().lower():
        return {"valid": True, "email": email, "role": "admin", "name": payload.get("name") or "Administrador", "user_id": "", "pages": security.ALL_PAGES}
    raise HTTPException(status_code=401, detail="Usuário não encontrado ou inativo")

@api_router.post("/auth/refresh")
async def refresh_token(payload: dict = Depends(verify_token)):
    email = (payload.get("email") or "").strip().lower()
    user = await find_user_by_email(mongo_db, email)
    if user and user.get("active", True):
        new_token = create_token(email=user["email"], role=user.get("role", "technician"), name=user.get("name", ""), user_id=user.get("id", ""))
        return {"token": new_token, "email": user["email"], "role": user.get("role", "technician"), "name": user.get("name", "")}
    if email == (APP_LOGIN_EMAIL or "").strip().lower():
        new_token = create_token(email=email, role="admin", name=payload.get("name") or "Administrador")
        return {"token": new_token, "email": email, "role": "admin", "name": payload.get("name") or "Administrador"}
    raise HTTPException(status_code=401, detail="Usuário não encontrado")

# CEP lookup with fallback
@api_router.get("/cep/{cep}", response_model=CEPResponse)
async def lookup_cep(cep: str, _: dict = Depends(verify_token)):
    cep_clean = cep.replace("-", "").replace(".", "").strip()
    if len(cep_clean) != 8 or not cep_clean.isdigit():
        raise HTTPException(status_code=400, detail="CEP inválido")
    async with httpx.AsyncClient(timeout=15) as client:
        # Try ViaCEP first
        try:
            response = await client.get(f"https://viacep.com.br/ws/{cep_clean}/json/")
            if response.status_code == 200:
                data = response.json()
                if "erro" not in data:
                    return CEPResponse(
                        cep=data.get("cep", ""),
                        logradouro=data.get("logradouro", ""),
                        bairro=data.get("bairro", ""),
                        localidade=data.get("localidade", ""),
                        uf=data.get("uf", "")
                    )
        except Exception as e:
            logger.warning(f"ViaCEP failed: {e}")

        # Fallback: BrasilAPI
        try:
            response = await client.get(f"https://brasilapi.com.br/api/cep/v2/{cep_clean}")
            if response.status_code == 200:
                data = response.json()
                return CEPResponse(
                    cep=data.get("cep", ""),
                    logradouro=data.get("street", ""),
                    bairro=data.get("neighborhood", ""),
                    localidade=data.get("city", ""),
                    uf=data.get("state", "")
                )
        except Exception as e:
            logger.warning(f"BrasilAPI failed: {e}")

        raise HTTPException(status_code=404, detail="CEP não encontrado")

# Service Orders CRUD

# Get next OSE number for manual orders
@api_router.get("/service-orders/next-ose-number")
async def get_next_ose_number(_: dict = Depends(verify_token)):
    """Get the next available OSE number (Mastermaq internal: exactly 5 digits)"""
    async with httpx.AsyncClient() as c:
        r = await c.get(
            f"{supabase_url}/rest/v1/service_orders?select=os_number&order=os_number.desc&limit=500",
            headers={"apikey": supabase_key, "Authorization": f"Bearer {supabase_key}"},
            timeout=15
        )
    if r.status_code == 200:
        rows = r.json()
        # Only consider numeric OS numbers with <= 5 digits (Mastermaq internal pattern)
        max_num = 27577
        for row in rows:
            osn = str(row.get("os_number", "")).strip()
            if osn.isdigit() and len(osn) <= 5:
                max_num = max(max_num, int(osn))
        return {"next_ose_number": str(max_num + 1)}
    return {"next_ose_number": "27578"}


@api_router.get("/service-orders/next-invisacook-number")
async def get_next_invisacook_number(_: dict = Depends(verify_token)):
    """Return the next available Invisacook OS number (format INV-<5 digits>).

    Uses an atomic $inc + upsert on a dedicated counter document in Mongo so
    concurrent create requests never collide. If the counter drifts (e.g. a
    manual insertion introduced an INV-##### row), we walk forward until we
    find a free slot and bump the counter forward so the next call is O(1).
    """
    from pymongo import ReturnDocument
    counter_doc = await os_metadata_col.find_one_and_update(
        {"_key": "invisacook_seq"},
        {"$inc": {"seq": 1}, "$setOnInsert": {"_key": "invisacook_seq"}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    seq = int((counter_doc or {}).get("seq") or 1)

    # Walk forward until we find a free slot (typical case: 1 attempt).
    for offset in range(0, 200):
        candidate = f"INV-{(seq + offset):05d}"
        existing = await db.service_orders.find_one({"os_number": candidate}, {"_id": 0, "os_number": 1})
        if not existing:
            if offset > 0:
                await os_metadata_col.update_one(
                    {"_key": "invisacook_seq"},
                    {"$set": {"seq": seq + offset}},
                )
            return {"next_invisacook_number": candidate}

    # Extreme fallback (never expected)
    fallback = f"INV-{int(datetime.now(timezone.utc).timestamp())}"
    logger.error(f"get_next_invisacook_number: could not find free slot near seq {seq}, using fallback {fallback}")
    return {"next_invisacook_number": fallback}

@api_router.post("/service-orders")
async def create_service_order(order: ServiceOrderCreate, payload: dict = Depends(verify_token)):
    # Check if OS already exists
    existing = await db.service_orders.find_one({"os_number": order.os_number}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=400, detail="Ordem de Serviço já cadastrada")

    order_obj = ServiceOrder(**order.model_dump())
    doc = order_obj.model_dump()

    # RBAC: Invisacook users can only create OSs with source="invisacook".
    # We coerce the source here so a hand-crafted payload can't bypass it.
    if payload.get("role") == "invisacook":
        doc["source"] = "invisacook"
    # Add sort_date for proper ordering (ISO format from registration_date)
    reg = doc.get("registration_date", "")
    sort_date = None
    if reg:
        for fmt in ["%d/%m/%Y", "%Y-%m-%d"]:
            try:
                from datetime import datetime as _dt
                sort_date = _dt.strptime(reg.strip()[:10], fmt).isoformat()
                break
            except Exception:
                pass
    if not sort_date:
        sort_date = doc.get("created_at", datetime.now(timezone.utc).isoformat())
    doc["sort_date"] = sort_date
    await db.service_orders.insert_one(doc)
    return order_obj

@api_router.get("/service-orders")
async def get_service_orders(
    status: Optional[str] = None,
    exclude_status: Optional[str] = None,
    source: Optional[str] = None,
    brand: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    search: Optional[str] = None,
    priority: Optional[str] = None,
    page: int = 1,
    limit: int = 30,
    payload: dict = Depends(verify_token)
):
    # RBAC: Invisacook role sees ONLY Invisacook OSs, no matter what the
    # frontend requested. This is enforced server-side so a hand-crafted
    # request can't bypass the restriction.
    if payload.get("role") == "invisacook":
        source = "invisacook"

    # Cache key for identical requests (60s TTL). Includes role so admins and
    # invisacook users don't share the same cache slot.
    cache_key = f"os_list:{payload.get('role','admin')}:{status}:{exclude_status}:{source}:{brand}:{start_date}:{end_date}:{search}:{priority}:{page}:{limit}"
    cached = cache.get(cache_key)
    if cached:
        return cached
    
    query = {}
    
    if status and status != "all":
        statuses = [s.strip() for s in status.split(",") if s.strip()]
        if len(statuses) == 1:
            query["status"] = {"$regex": statuses[0], "$options": "i"}
        else:
            query["status"] = {"$in": statuses}
    elif exclude_status:
        # Negated filter — return everything EXCEPT these statuses.
        # Used by the "Criar Roteiro" modal to fetch ALL active OSs
        # (anything not Finalizada/Cancelada).
        excluded = [s.strip() for s in exclude_status.split(",") if s.strip()]
        if excluded:
            query["status"] = {"$nin": excluded}
    
    if source and source != "all":
        sources = [s.strip() for s in source.split(",") if s.strip()]
        # Map each filter chip to its underlying DB source values.
        # Frontend chips: external_site, mastermaq, telecontrol (all), telecontrol_hisense, telecontrol_hq, invisacook
        chip_to_db = {
            "external_site": ["external_site"],
            "mastermaq": ["local", "mastermaq"],  # internal manual entries
            "telecontrol": ["telecontrol", "telecontrol_hisense", "telecontrol_hq"],
            "telecontrol_hisense": ["telecontrol_hisense"],
            "telecontrol_hq": ["telecontrol_hq"],
            "invisacook": ["invisacook"],
        }
        expanded = []
        for s in sources:
            expanded.extend(chip_to_db.get(s, [s]))
        expanded = list(dict.fromkeys(expanded))  # dedupe preserving order
        if len(expanded) == 1:
            query["source"] = expanded[0]
        elif expanded:
            query["source"] = {"$in": expanded}
    
    if brand and brand != "all":
        brands = [b.strip() for b in brand.split(",") if b.strip()]
        if len(brands) == 1:
            query["brand"] = {"$regex": f"^{brands[0]}$", "$options": "i"}
        else:
            query["brand"] = {"$in": brands}
    
    if start_date or end_date:
        date_filter = {}
        if start_date:
            date_filter["$gte"] = start_date
        if end_date:
            date_filter["$lte"] = end_date
        query["registration_date"] = date_filter

    # Priority filter applied BEFORE pagination — otherwise the priority
    # check would only look at the current page (30 rows) and the badge count
    # in the sidebar would be wrong. Fetch priority OS numbers from MongoDB
    # and restrict the Supabase query to them (fixes: filter Prioridade
    # missing priority OSs across all pages, and finalized OSs still counting).
    if priority == "true":
        priority_os_numbers = []
        async for pdoc in os_metadata_col.find({"priority": True}, {"_id": 0, "os_number": 1}):
            osn = pdoc.get("os_number")
            if osn:
                priority_os_numbers.append(str(osn))
        if not priority_os_numbers:
            # Nothing marked priority — return an empty page early.
            result = {"orders": [], "total": 0, "page": page, "limit": limit, "total_pages": 0}
            cache.set(cache_key, result, ttl=60)
            return result
        # Merge with any existing os_number restriction (unlikely but safe).
        if "os_number" in query:
            existing = query["os_number"]
            if isinstance(existing, dict) and "$in" in existing:
                query["os_number"] = {"$in": list(set(existing["$in"]) & set(priority_os_numbers))}
            else:
                query["os_number"] = {"$in": [existing] if str(existing) in priority_os_numbers else []}
        else:
            query["os_number"] = {"$in": priority_os_numbers}
    
    if search:
        # Optimized: use direct Supabase REST with or() for fast search
        # Instead of the adapter's slow $or conversion, build a direct REST query
        search_clean = search.replace("'", "''").replace("%", "\\%")
        search_pattern = f"*{search_clean}*"
        or_fields = [
            "os_number", "customer_name", "product", "neighborhood", "address",
            "city", "phone1", "phone2", "brand", "model", "serial_number",
            "reported_defect", "technician", "status", "service_type", "email",
            "observations", "cep", "reference_point", "number", "batch"
        ]
        or_clause = ",".join(f"{f}.ilike.{search_pattern}" for f in or_fields)
        query["_raw_or"] = or_clause
    
    # Clamp limit: por padrão 30 (economia de egress); mas o modal de
    # Roteirização (que passa `exclude_status`) precisa carregar TODAS as
    # OSs ativas para filtrar por cidade/bairro/status no cliente — sobe
    # o cap para 5000 nesse caso.
    if exclude_status:
        limit = min(max(limit, 1), 5000)
    else:
        limit = min(max(limit, 1), 30)
    skip = (max(page, 1) - 1) * limit
    
    # Define minimal projection for list view (reduce egress dramatically)
    list_fields = {
        "_id": 0,
        "id": 1, "os_number": 1, "customer_name": 1, "registration_date": 1,
        "attendance_date": 1, "status": 1, "sub_status": 1, "service_type": 1,
        "source": 1, "brand": 1, "model": 1, "product": 1,
        "address": 1, "number": 1, "complement": 1, "neighborhood": 1, "city": 1, "state": 1,
        "phone1": 1, "phone2": 1, "landline": 1, "email": 1, "technician": 1, "sort_date": 1,
        "lat": 1, "lng": 1, "reported_defect": 1, "serial_number": 1,
        "batch": 1, "cep": 1, "reference_point": 1, "visit_fee": 1, "visit_fee_paid": 1,
        "scheduling_history": 1, "observations": 1, "priority": 1,
        # Needed for relevance-+-recency tiebreaker in search:
        "created_at": 1, "updated_at": 1,
    }
    
    total = await db.service_orders.count_documents(query)

    if search:
        # Fetch more results for in-memory ranking (up to 200), then paginate
        fetch_limit = min(total, 200)
        all_results = await db.service_orders.find(query, list_fields).sort("created_at", -1).skip(0).limit(fetch_limit).to_list(fetch_limit)
        
        # Rank results by relevance
        search_lower = search.lower().strip()
        search_terms = search_lower.split()
        
        def calc_score(order):
            score = 0
            # Higher-priority fields the user usually searches by.
            primary_fields = ["os_number", "customer_name", "phone1"]
            # Lower-priority person field — searching "felipe" rarely means
            # "show me OSs whose TECHNICIAN is Felipe"; it means "Felipe-the-
            # customer". Keep technician matchable but ranked below customer.
            person_fields = ["technician"]
            secondary_fields = ["address", "neighborhood", "city", "product", "brand", "model"]

            def word_match(value, term):
                """Whole-word boundary match (e.g. 'felipe' in 'Felipe Hudson')."""
                return any(w == term for w in value.split())

            for field in primary_fields:
                val = str(order.get(field, "") or "").lower()
                if val == search_lower:
                    score += 1500  # Exact match
                elif word_match(val, search_lower):
                    score += 1000  # Term matches a full word (e.g. first name)
                elif val.startswith(search_lower):
                    score += 600
                elif search_lower in val:
                    score += 250
                if len(search_terms) > 1:
                    matching_terms = sum(1 for t in search_terms if t in val)
                    if matching_terms == len(search_terms):
                        score += 800
                    elif matching_terms > 0:
                        score += matching_terms * 100

            for field in person_fields:
                val = str(order.get(field, "") or "").lower()
                if val == search_lower:
                    score += 400  # Technician exact match — useful but lower
                elif word_match(val, search_lower):
                    score += 300
                elif val.startswith(search_lower):
                    score += 150
                elif search_lower in val:
                    score += 50

            for field in secondary_fields:
                val = str(order.get(field, "") or "").lower()
                if val == search_lower:
                    score += 300
                elif val.startswith(search_lower):
                    score += 150
                elif search_lower in val:
                    score += 50
                if len(search_terms) > 1:
                    matching_terms = sum(1 for t in search_terms if t in val)
                    if matching_terms == len(search_terms):
                        score += 250
                    elif matching_terms > 0:
                        score += matching_terms * 30

            return score
        
        for o in all_results:
            o["_relevance"] = calc_score(o)
        
        # Sort by relevance DESC, then by recency DESC as tiebreaker.
        # Python sort is stable: pre-sorting by created_at desc means that
        # when relevance ties, the newer OS comes first (user expectation).
        all_results.sort(key=lambda o: (o.get("created_at") or o.get("registration_date") or ""), reverse=True)
        all_results.sort(key=lambda o: o.get("_relevance", 0), reverse=True)
        
        # Remove internal score field and paginate
        orders = all_results[skip:skip + limit]
        for o in orders:
            o.pop("_relevance", None)
    else:
        orders = await db.service_orders.find(query, list_fields).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    
    # Merge priority and print_count metadata from MongoDB
    if orders:
        os_numbers = [o.get("os_number") for o in orders if o.get("os_number")]
        if os_numbers:
            metadata = {}
            async for doc in os_metadata_col.find({"os_number": {"$in": os_numbers}}, {"_id": 0, "os_number": 1, "priority": 1, "print_count": 1}):
                metadata[doc["os_number"]] = doc
            for o in orders:
                meta = metadata.get(o.get("os_number"), {})
                o["priority"] = meta.get("priority", False)
                o["print_count"] = meta.get("print_count", 0)

    # NOTE: priority filtering was previously applied HERE (after pagination),
    # which caused the filter to only return matches from the current page and
    # to under-count the total. It's now applied to the Supabase query above
    # so pagination and totals are correct.

    result = {
        "orders": orders,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": (total + limit - 1) // limit if limit > 0 else 0
    }
    cache.set(cache_key, result, ttl=60)
    return result

# Print counter endpoints
@api_router.post("/service-orders/{os_number}/print-count")
async def increment_print_count(os_number: str, _: dict = Depends(verify_token)):
    """Increment and return print count for an OS."""
    await os_metadata_col.update_one(
        {"os_number": os_number},
        {"$inc": {"print_count": 1}, "$set": {"os_number": os_number, "last_printed": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    doc = await os_metadata_col.find_one({"os_number": os_number}, {"_id": 0, "print_count": 1})
    count = doc.get("print_count", 1) if doc else 1
    return {"os_number": os_number, "print_count": count}

@api_router.get("/service-orders/{os_number}/print-count")
async def get_print_count(os_number: str, _: dict = Depends(verify_token)):
    """Get print count for an OS."""
    doc = await os_metadata_col.find_one({"os_number": os_number}, {"_id": 0, "print_count": 1, "last_printed": 1})
    return {"os_number": os_number, "print_count": doc.get("print_count", 0) if doc else 0, "last_printed": doc.get("last_printed") if doc else None}

# IMPORTANT: This route MUST be before /{os_number} to avoid "statuses" being treated as an os_number
@api_router.get("/service-orders/search-clients")
async def search_clients(q: str, _: dict = Depends(verify_token)):
    """Search existing clients by name, phone, or address for auto-fill."""
    if not q or len(q) < 2:
        return {"clients": []}
    # Search via Supabase REST with OR conditions
    search_pattern = f"*{q}*"
    async with httpx.AsyncClient() as c:
        r = await c.get(
            f"{supabase_url}/rest/v1/service_orders?select=customer_name,phone1,phone2,landline,email,address,number,complement,neighborhood,city,state,cep,reference_point&or=(customer_name.ilike.{search_pattern},phone1.ilike.{search_pattern},phone2.ilike.{search_pattern},address.ilike.{search_pattern},email.ilike.{search_pattern})&limit=100",
            headers={"apikey": supabase_key, "Authorization": f"Bearer {supabase_key}"},
            timeout=15
        )
    if r.status_code != 200:
        return {"clients": []}
    rows = r.json()
    # Group by customer_name + phone1 + address (de-duplicate)
    seen = {}
    for row in rows:
        key = (row.get("customer_name", ""), row.get("phone1", ""), row.get("address", ""))
        if key not in seen:
            seen[key] = {**row, "os_count": 1}
        else:
            seen[key]["os_count"] += 1
    clients = sorted(seen.values(), key=lambda x: x.get("customer_name", ""))[:10]
    return {"clients": clients}

@api_router.get("/service-orders/statuses")
async def get_distinct_statuses(_: dict = Depends(verify_token)):
    cached = cache.get("statuses")
    if cached: return cached
    statuses = await db.service_orders.distinct("status")
    statuses = [s for s in statuses if s]
    result = {"statuses": sorted(statuses)}
    cache.set("statuses", result, ttl=600)
    return result

@api_router.get("/service-orders/brands")
async def get_distinct_brands(_: dict = Depends(verify_token)):
    cached = cache.get("brands")
    if cached: return cached
    brands = await db.service_orders.distinct("brand")
    brands = [b for b in brands if b and b.strip()]
    result = {"brands": sorted(set(b.strip() for b in brands), key=str.lower)}
    cache.set("brands", result, ttl=600)
    return result

# Overdue OS - "Aguardando Analise A.T" + "Aguardando Peças" + "Aguardando Conserto" > 10 days
@api_router.get("/service-orders/overdue-at")
async def get_overdue_at(_: dict = Depends(verify_token)):
    """Get OS with pending statuses older than 10 days"""
    cached = cache.get("overdue")
    if cached: return cached
    overdue_statuses = ["Aguardando Analise A.T", "Aguardando Peças", "Aguardando Conserto"]
    orders = await db.service_orders.find(
        {"status": {"$in": overdue_statuses}},
        {"_id": 0, "os_number": 1, "customer_name": 1, "brand": 1, "model": 1, "product": 1,
         "registration_date": 1, "attendance_date": 1, "created_at": 1, "city": 1, "neighborhood": 1, "phone1": 1, "status": 1}
    ).to_list(10000)

    now = datetime.now(timezone.utc)
    overdue = []
    for o in orders:
        parsed = None
        for field in ['attendance_date', 'registration_date', 'created_at']:
            val = o.get(field)
            if not val:
                continue
            s = str(val).strip()
            for fmt in ['%Y-%m-%dT%H:%M:%S', '%Y-%m-%d', '%d/%m/%Y']:
                try:
                    parsed = datetime.strptime(s[:min(19, len(s))], fmt)
                    break
                except Exception:
                    pass
            if parsed:
                break
        if parsed:
            days = (now - parsed.replace(tzinfo=timezone.utc)).days
            if days > 10:
                o["days_waiting"] = days
                overdue.append(o)
    
    overdue.sort(key=lambda x: x.get("days_waiting", 0), reverse=True)
    result = {"count": len(overdue), "orders": overdue}
    cache.set("overdue", result, ttl=300)
    return result

# ─── Alertas do cabeçalho (campainha) ─────────────────────────────
# Três gatilhos, todos derivados dos dados existentes (sem tabela nova):
#   1) OS nova vinda do Telecontrol (Hisense/HQ)
#   2) mudança de status em OS Hisense/HQ
#   3) OS em aberto há mais de ALERT_AGING_DAYS dias
ALERT_TELECONTROL_SOURCES = ["telecontrol", "telecontrol_hisense", "telecontrol_hq"]
ALERT_CLOSED_STATUSES = ["Finalizada", "OS Cancelada"]
ALERT_LOOKBACK_HOURS = int(os.environ.get("ALERT_LOOKBACK_HOURS", 24))
ALERT_AGING_DAYS = int(os.environ.get("ALERT_AGING_DAYS", 30))


def _parse_os_date(value):
    """Aceita os formatos de data usados em service_orders."""
    if not value:
        return None
    s = str(value).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s[:min(19, len(s))], fmt).replace(tzinfo=timezone.utc)
        except Exception:
            continue
    return None


def _tc_label(source: str) -> str:
    return "HQ" if source == "telecontrol_hq" else "Hisense"


@api_router.get("/alerts/summary")
async def get_alerts_summary(_: dict = Depends(verify_token)):
    """Alertas que devem tocar a campainha e acender o badge do cabeçalho."""
    cached = cache.get("alerts_summary")
    if cached:
        return cached

    now = datetime.now(timezone.utc)
    since = (now - timedelta(hours=ALERT_LOOKBACK_HOURS)).isoformat()
    items = []

    # 1) OS nova do Telecontrol (Hisense / HQ)
    try:
        new_orders = await db.service_orders.find(
            {"source": {"$in": ALERT_TELECONTROL_SOURCES}, "created_at": {"$gte": since}},
            {"_id": 0, "os_number": 1, "customer_name": 1, "source": 1, "status": 1, "created_at": 1},
        ).sort("created_at", -1).to_list(50)
    except Exception as e:
        logger.warning(f"alerts: falha ao buscar novas OS Telecontrol: {e}")
        new_orders = []

    for o in new_orders:
        label = _tc_label(o.get("source"))
        items.append({
            "id": f"new:{o.get('os_number')}",
            "type": "telecontrol_new_os",
            "os_number": o.get("os_number"),
            "source": o.get("source"),
            "title": f"Nova OS {label}",
            "message": f"OS {o.get('os_number')} chegou do Telecontrol {label} — {o.get('customer_name') or ''}".strip(" —"),
            "created_at": o.get("created_at"),
        })

    # 2) Mudança de status em OS Hisense / HQ
    try:
        notifs = await db.notifications.find(
            {"created_at": {"$gte": since}},
            {"_id": 0, "id": 1, "os_number": 1, "old_status": 1, "new_status": 1, "created_at": 1},
        ).sort("created_at", -1).to_list(200)
    except Exception as e:
        logger.warning(f"alerts: falha ao buscar notificações: {e}")
        notifs = []

    notif_os = list(dict.fromkeys([str(n.get("os_number")) for n in notifs if n.get("os_number")]))
    source_by_os = {}
    if notif_os:
        try:
            rows = await db.service_orders.find(
                {"os_number": {"$in": notif_os[:200]}},
                {"_id": 0, "os_number": 1, "source": 1},
            ).to_list(500)
            source_by_os = {str(r.get("os_number")): r.get("source") for r in rows}
        except Exception as e:
            logger.warning(f"alerts: falha ao resolver source das OSs: {e}")

    for n in notifs:
        os_num = str(n.get("os_number") or "")
        src = source_by_os.get(os_num)
        if src not in ALERT_TELECONTROL_SOURCES:
            continue
        label = _tc_label(src)
        items.append({
            "id": f"status:{n.get('id') or (os_num + str(n.get('created_at')))}",
            "type": "telecontrol_status_change",
            "os_number": os_num,
            "source": src,
            "title": f"Status alterado ({label})",
            "message": f"OS {os_num}: '{n.get('old_status') or '—'}' → '{n.get('new_status')}'",
            "created_at": n.get("created_at"),
        })

    # 3) OS em aberto há mais de 30 dias
    try:
        aging_rows = await db.service_orders.find(
            {"status": {"$nin": ALERT_CLOSED_STATUSES}},
            {"_id": 0, "os_number": 1, "customer_name": 1, "status": 1, "source": 1,
             "registration_date": 1, "attendance_date": 1, "created_at": 1},
        ).to_list(10000)
    except Exception as e:
        logger.warning(f"alerts: falha ao buscar OSs antigas: {e}")
        aging_rows = []

    for o in aging_rows:
        base = None
        for f in ("attendance_date", "registration_date", "created_at"):
            base = _parse_os_date(o.get(f))
            if base:
                break
        if not base:
            continue
        days = (now - base).days
        if days > ALERT_AGING_DAYS:
            items.append({
                "id": f"aging:{o.get('os_number')}",
                "type": "os_aging",
                "os_number": o.get("os_number"),
                "source": o.get("source"),
                "days": days,
                "title": f"OS com {days} dias",
                "message": f"OS {o.get('os_number')} aberta há {days} dias — {o.get('customer_name') or ''}".strip(" —"),
                "created_at": base.isoformat(),
            })

    items.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)
    result = {
        "count": len(items),
        "by_type": {
            "telecontrol_new_os": sum(1 for i in items if i["type"] == "telecontrol_new_os"),
            "telecontrol_status_change": sum(1 for i in items if i["type"] == "telecontrol_status_change"),
            "os_aging": sum(1 for i in items if i["type"] == "os_aging"),
        },
        "latest": items[0] if items else None,
        "items": items[:100],
    }
    cache.set("alerts_summary", result, ttl=60)
    return result


@api_router.get("/service-orders/{os_number}/customer-history")
async def get_customer_history(os_number: str, _: dict = Depends(verify_token)):
    """Get other service orders from the same customer"""
    order = await db.service_orders.find_one({"os_number": os_number}, {"_id": 0, "customer_name": 1, "phone1": 1})
    if not order:
        raise HTTPException(status_code=404, detail="OS não encontrada")
    
    customer_name = order.get("customer_name")
    phone1 = order.get("phone1")
    
    if not customer_name:
        return {"history": []}
    
    conditions = [{"customer_name": customer_name}]
    if phone1:
        conditions.append({"phone1": phone1})
    
    history = await db.service_orders.find(
        {"$or": conditions, "os_number": {"$ne": os_number}},
        {"_id": 0, "os_number": 1, "customer_name": 1, "product": 1, "brand": 1, "model": 1, "status": 1, "registration_date": 1, "service_type": 1, "reported_defect": 1}
    ).sort("created_at", -1).to_list(50)
    
    return {"history": history}

class SignRequest(BaseModel):
    # Ambos opcionais para suportar "completar" — o modal pode enviar
    # somente a assinatura do técnico quando o cliente já assinou por link.
    signature_technician: Optional[str] = None
    signature_client: Optional[str] = None
    signature_client_name: Optional[str] = None
    signature_client_cpf: Optional[str] = None
    signature_tech_name: Optional[str] = None

@api_router.post("/service-orders/{os_number}/sign")
async def sign_service_order(os_number: str, sign_data: SignRequest, background_tasks: BackgroundTasks, _: dict = Depends(verify_token)):
    """Sign an OS with technician and/or client signatures.

    Aceita três cenários:
      1. Fluxo completo: recebe as duas assinaturas → persiste ambas + Assinafy.
      2. Completar tech: cliente já assinou via link → recebe só a assinatura
         do técnico → persiste + dispara Assinafy (agora está completa).
      3. Completar cliente: técnico já assinou → recebe só o cliente → idem.
    """
    from assinafy_service import generate_os_pdf, upload_document_to_assinafy, create_signer, create_assignment

    order = await db.service_orders.find_one({"os_number": os_number}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="OS não encontrada")

    # Só barra se JÁ tem as duas. Caso contrário permite o completion.
    if order.get("signature_technician") and order.get("signature_client"):
        raise HTTPException(status_code=400, detail="OS já foi assinada")

    now = datetime.now(timezone.utc).isoformat()

    # Constrói update parcial — mantém o que já existe intacto.
    update_data = {"updated_at": now, "signature_date": now}
    if sign_data.signature_technician:
        update_data["signature_technician"] = sign_data.signature_technician
    if sign_data.signature_client:
        update_data["signature_client"] = sign_data.signature_client
    if sign_data.signature_client_name:
        update_data["signature_client_name"] = sign_data.signature_client_name
    if sign_data.signature_client_cpf:
        update_data["signature_client_cpf"] = sign_data.signature_client_cpf
    if sign_data.signature_tech_name:
        update_data["signature_tech_name"] = sign_data.signature_tech_name

    # Estado final (considerando o que veio no request + o que já estava)
    final_tech = sign_data.signature_technician or order.get("signature_technician")
    final_client = sign_data.signature_client or order.get("signature_client")

    # Create notification for signature (no status change)
    old_status = order.get("status")
    notification = Notification(
        message=f"OS {os_number} assinada (status mantido: '{old_status}')",
        os_number=os_number,
        old_status=old_status,
        new_status=old_status
    )
    await db.notifications.insert_one(notification.model_dump())
    
    # Try Assinafy integration in background
    async def assinafy_background(os_num, order_data, sig_tech, sig_client):
        try:
            pdf_bytes = generate_os_pdf(order_data, sig_tech, sig_client)
            doc = await upload_document_to_assinafy(pdf_bytes, f"OS_{os_num}.pdf")
            doc_id = doc.get("id")
            
            tech_name = order_data.get("technician") or "Tecnico"
            client_name = order_data.get("customer_name") or "Cliente"
            
            tech_signer = await create_signer(tech_name)
            client_signer = await create_signer(client_name)
            
            assignment = await create_assignment(doc_id, [tech_signer["id"], client_signer["id"]])
            
            await db.service_orders.update_one(
                {"os_number": os_num},
                {"$set": {
                    "assinafy_document_id": doc_id,
                    "assinafy_status": "uploaded"
                }}
            )
            logger.info(f"Assinafy integration complete for OS {os_num}, doc_id: {doc_id}")
        except Exception as e:
            logger.error(f"Assinafy integration failed for OS {os_num}: {e}")
            await db.service_orders.update_one(
                {"os_number": os_num},
                {"$set": {"assinafy_status": f"error: {str(e)[:200]}"}}
            )
    
    # Só dispara Assinafy quando a OS está totalmente assinada (as duas
    # assinaturas presentes). Se ainda falta uma, aguarda a próxima
    # chamada de sign (com a parte faltante) pra gerar o PDF completo.
    if final_tech and final_client:
        # Precisa mergear o update_data no order pra o PDF ter os dados frescos
        order_for_pdf = {**order, **update_data}
        background_tasks.add_task(assinafy_background, os_number, order_for_pdf, final_tech, final_client)

    await db.service_orders.update_one({"os_number": os_number}, {"$set": update_data})

    updated = await db.service_orders.find_one({"os_number": os_number}, {"_id": 0})
    return updated

@api_router.get("/service-orders/{os_number}/signatures")
async def get_signatures(os_number: str, _: dict = Depends(verify_token)):
    """Get signature data for an OS"""
    order = await db.service_orders.find_one(
        {"os_number": os_number},
        {"_id": 0, "signature_technician": 1, "signature_client": 1, "signature_date": 1,
         "signature_client_name": 1, "signature_client_cpf": 1, "signature_tech_name": 1,
         "assinafy_document_id": 1, "assinafy_status": 1, "customer_name": 1, "technician": 1,
         "os_number": 1, "product": 1, "brand": 1, "model": 1, "registration_date": 1,
         "service_type": 1, "reported_defect": 1, "technical_diagnosis": 1, "status": 1}
    )
    if not order:
        raise HTTPException(status_code=404, detail="OS não encontrada")

    has_signatures = bool(order.get("signature_technician") and order.get("signature_client"))
    return {
        "signed": has_signatures,
        "signature_technician": order.get("signature_technician"),
        "signature_client": order.get("signature_client"),
        "signature_client_name": order.get("signature_client_name"),
        "signature_client_cpf": order.get("signature_client_cpf"),
        "signature_tech_name": order.get("signature_tech_name"),
        "signature_date": order.get("signature_date"),
        "assinafy_document_id": order.get("assinafy_document_id"),
        "assinafy_status": order.get("assinafy_status"),
        "order_summary": {
            "os_number": order.get("os_number"),
            "customer_name": order.get("customer_name"),
            "technician": order.get("technician"),
            "product": order.get("product"),
            "brand": order.get("brand"),
            "model": order.get("model"),
            "registration_date": order.get("registration_date"),
            "service_type": order.get("service_type"),
            "reported_defect": order.get("reported_defect"),
            "technical_diagnosis": order.get("technical_diagnosis"),
            "status": order.get("status"),
        }
    }


# ─── Signature link (client signs remotely via WhatsApp) ─────────────────
# Fluxo:
#   1. Técnico abre o SignatureModal, capta a assinatura dele + dados do cliente.
#   2. Ao invés de pedir para o cliente assinar no aparelho do técnico, clica
#      "Enviar link" — o backend gera um token único (7d de expiração) e
#      guarda a assinatura do técnico + metadados dentro da collection
#      `signature_links` (MongoDB, sidecar — não polui a tabela do Supabase).
#   3. O frontend abre o WhatsApp Web/App do cliente com uma mensagem pronta
#      contendo `${origin}/sign/${token}`.
#   4. O cliente abre o link no celular, vê os dados da OS + a assinatura do
#      técnico já capturada, e só precisa assinar. Ao submeter, o backend
#      persiste as duas assinaturas na OS (mesmo caminho de `sign_service_order`).
#
# Segurança:
#   * O token é uuid4 (128 bits de entropia) — inadivinhável.
#   * A rota pública NÃO expõe telefone, endereço, valor ou defeito completo
#     — só o essencial para o cliente reconhecer que é a OS dele.
#   * Token é single-use: após submit vira `status: "used"` e novas chamadas
#     retornam 410 Gone.
#   * Se a OS já está assinada por outro caminho, o link é invalidado.

signature_links_col = mongo_db["signature_links"]

class SignatureLinkCreate(BaseModel):
    # technician_signature agora é OPCIONAL — permite o fluxo "cliente
    # assina primeiro, técnico assina depois". Se ausente, quando o cliente
    # submeter pelo link, apenas a assinatura do cliente é persistida na
    # OS; o técnico completa depois reabrindo o SignatureModal.
    technician_signature: Optional[str] = None
    technician_name: Optional[str] = None
    client_name: Optional[str] = None
    client_cpf: Optional[str] = None


@api_router.post("/service-orders/{os_number}/signature-link")
async def create_signature_link(
    os_number: str,
    body: SignatureLinkCreate,
    request: Request,
    _: dict = Depends(verify_token),
):
    """Gera um link público para o cliente assinar a OS pelo próprio celular."""
    order = await db.service_orders.find_one(
        {"os_number": os_number},
        {"_id": 0, "os_number": 1, "customer_name": 1, "phone1": 1,
         "product": 1, "brand": 1, "model": 1, "signature_client": 1}
    )
    if not order:
        raise HTTPException(status_code=404, detail="OS não encontrada")
    if order.get("signature_client"):
        raise HTTPException(status_code=400, detail="OS já foi assinada pelo cliente")
    # Se veio a assinatura do técnico, deve ser um dataURL válido; caso
    # contrário aceita None (fluxo "cliente assina primeiro").
    if body.technician_signature and not body.technician_signature.startswith("data:image"):
        raise HTTPException(status_code=400, detail="Assinatura do técnico inválida")

    token = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=7)

    await signature_links_col.insert_one({
        "token": token,
        "os_number": os_number,
        "technician_signature": body.technician_signature,
        "technician_name": (body.technician_name or "").strip(),
        "client_name_hint": (body.client_name or order.get("customer_name") or "").strip(),
        "client_cpf_hint": (body.client_cpf or "").strip(),
        "status": "pending",
        "created_at": now.isoformat(),
        "expires_at": expires.isoformat(),
    })

    # Base do link = origin público (front). Preferimos o Referer da chamada
    # (mesmo domínio do painel) para funcionar em preview E produção sem
    # depender de ENV extra. Fallback: REACT_APP_BACKEND_URL do env.
    origin = os.environ.get("PUBLIC_APP_URL") or request.headers.get("origin") or request.headers.get("referer") or ""
    if origin:
        # limpa path do referer
        try:
            from urllib.parse import urlparse
            u = urlparse(origin)
            origin = f"{u.scheme}://{u.netloc}"
        except Exception:
            pass
    if not origin:
        origin = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

    link_url = f"{origin}/sign/{token}"

    # Mensagem pronta para WhatsApp (encodada URL-safe)
    from urllib.parse import quote
    cust = (order.get("customer_name") or "").split(" ")[0] or "cliente"
    prod_desc = order.get("product") or "sua ordem de serviço"
    msg = (
        f"Olá {cust}! Aqui é da Mastermaq Assistência Técnica.\n\n"
        f"Para concluir a OS #{os_number} do seu {prod_desc}, "
        f"assine no link abaixo pelo seu próprio celular:\n\n"
        f"{link_url}\n\n"
        f"O link é único e expira em 7 dias. Qualquer dúvida, é só responder por aqui."
    )
    phone_digits = "".join(c for c in (order.get("phone1") or "") if c.isdigit())
    if phone_digits and not phone_digits.startswith("55"):
        phone_digits = "55" + phone_digits
    whatsapp_url = f"https://wa.me/{phone_digits}?text={quote(msg)}" if phone_digits else f"https://wa.me/?text={quote(msg)}"

    return {
        "token": token,
        "url": link_url,
        "whatsapp_url": whatsapp_url,
        "expires_at": expires.isoformat(),
    }


@api_router.get("/public/sign/{token}")
async def public_signature_view(token: str):
    """Retorna os dados mínimos que o cliente precisa para confirmar a OS
    antes de assinar. Rota PÚBLICA (sem auth). O token protege o acesso."""
    link = await signature_links_col.find_one({"token": token}, {"_id": 0})
    if not link:
        raise HTTPException(status_code=404, detail="Link inválido ou não encontrado")
    if link.get("status") == "used":
        raise HTTPException(status_code=410, detail="Este link já foi utilizado")
    try:
        exp = datetime.fromisoformat(link["expires_at"])
        if datetime.now(timezone.utc) > exp:
            raise HTTPException(status_code=410, detail="Este link expirou")
    except (KeyError, ValueError):
        pass

    order = await db.service_orders.find_one(
        {"os_number": link["os_number"]},
        {"_id": 0, "os_number": 1, "customer_name": 1, "product": 1,
         "brand": 1, "model": 1, "service_type": 1, "reported_defect": 1,
         "technical_diagnosis": 1, "status": 1, "registration_date": 1,
         "signature_client": 1}
    )
    if not order:
        raise HTTPException(status_code=404, detail="OS não encontrada")
    if order.get("signature_client"):
        # OS já assinada por outro caminho — invalida o link
        await signature_links_col.update_one({"token": token}, {"$set": {"status": "used"}})
        raise HTTPException(status_code=410, detail="Esta OS já foi assinada")

    return {
        "os_number": order.get("os_number"),
        "customer_name": order.get("customer_name"),
        "product": order.get("product"),
        "brand": order.get("brand"),
        "model": order.get("model"),
        "service_type": order.get("service_type"),
        "reported_defect": order.get("reported_defect"),
        "technical_diagnosis": order.get("technical_diagnosis"),
        "status": order.get("status"),
        "registration_date": order.get("registration_date"),
        "technician_name": link.get("technician_name"),
        "client_name_hint": link.get("client_name_hint"),
        "expires_at": link.get("expires_at"),
    }


class PublicSignSubmit(BaseModel):
    signature_client: str
    client_cpf: Optional[str] = None


@api_router.post("/public/sign/{token}/submit")
async def public_signature_submit(token: str, body: PublicSignSubmit, background_tasks: BackgroundTasks):
    """Persist client signature via the public link. Reuses the same PDF/
    Assinafy pipeline as `sign_service_order` para manter o dossiê consistente."""
    from assinafy_service import generate_os_pdf, upload_document_to_assinafy, create_signer, create_assignment

    link = await signature_links_col.find_one({"token": token}, {"_id": 0})
    if not link:
        raise HTTPException(status_code=404, detail="Link inválido")
    if link.get("status") == "used":
        raise HTTPException(status_code=410, detail="Link já utilizado")
    try:
        exp = datetime.fromisoformat(link["expires_at"])
        if datetime.now(timezone.utc) > exp:
            raise HTTPException(status_code=410, detail="Link expirado")
    except (KeyError, ValueError):
        pass

    if not body.signature_client or not body.signature_client.startswith("data:image"):
        raise HTTPException(status_code=400, detail="Assinatura do cliente inválida")

    os_number = link["os_number"]
    order = await db.service_orders.find_one({"os_number": os_number}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="OS não encontrada")
    if order.get("signature_client"):
        await signature_links_col.update_one({"token": token}, {"$set": {"status": "used"}})
        raise HTTPException(status_code=410, detail="OS já assinada")

    now = datetime.now(timezone.utc).isoformat()
    update_data = {
        "signature_client": body.signature_client,
        "signature_client_name": link.get("client_name_hint") or order.get("customer_name") or "",
        "signature_client_cpf": (body.client_cpf or link.get("client_cpf_hint") or "").strip(),
        "signature_date": now,
        "updated_at": now,
    }
    # Se o link foi criado JÁ com a assinatura do técnico, persiste as duas
    # de uma vez (fluxo tradicional). Caso contrário só persiste o cliente
    # e a OS fica em estado "parcial" — o técnico completa reabrindo o modal.
    link_tech_sig = link.get("technician_signature")
    link_tech_name = link.get("technician_name")
    fully_signed = bool(link_tech_sig)
    if link_tech_sig:
        update_data["signature_technician"] = link_tech_sig
    if link_tech_name:
        update_data["signature_tech_name"] = link_tech_name

    old_status = order.get("status")
    who = "cliente" if not fully_signed else "cliente e técnico"
    notification = Notification(
        message=f"OS {os_number} assinada pelo {who} via link (status mantido: '{old_status}')",
        os_number=os_number,
        old_status=old_status,
        new_status=old_status,
    )
    await db.notifications.insert_one(notification.model_dump())

    async def assinafy_background(os_num, order_data, sig_tech, sig_client):
        try:
            pdf_bytes = generate_os_pdf(order_data, sig_tech, sig_client)
            doc = await upload_document_to_assinafy(pdf_bytes, f"OS_{os_num}.pdf")
            doc_id = doc.get("id")
            tech_name = order_data.get("technician") or "Tecnico"
            client_name = order_data.get("customer_name") or "Cliente"
            tech_signer = await create_signer(tech_name)
            client_signer = await create_signer(client_name)
            await create_assignment(doc_id, [tech_signer["id"], client_signer["id"]])
            await db.service_orders.update_one(
                {"os_number": os_num},
                {"$set": {"assinafy_document_id": doc_id, "assinafy_status": "uploaded"}}
            )
            logger.info(f"Assinafy (public sign) complete for OS {os_num}, doc_id={doc_id}")
        except Exception as e:  # noqa: BLE001
            logger.error(f"Assinafy (public sign) failed for OS {os_num}: {e}")
            await db.service_orders.update_one(
                {"os_number": os_num},
                {"$set": {"assinafy_status": f"error: {str(e)[:200]}"}}
            )

    # Só dispara o pipeline Assinafy quando a OS está totalmente assinada.
    # Se só o cliente assinou, aguarda o técnico completar pra gerar o PDF.
    if fully_signed:
        background_tasks.add_task(assinafy_background, os_number, order, link_tech_sig, body.signature_client)
    await db.service_orders.update_one({"os_number": os_number}, {"$set": update_data})
    await signature_links_col.update_one({"token": token}, {"$set": {"status": "used", "used_at": now}})

    return {"success": True, "os_number": os_number, "fully_signed": fully_signed}

@api_router.get("/service-orders/{os_number}")
async def get_service_order(os_number: str, include_photos: bool = False, payload: dict = Depends(verify_token)):
    """OS detail. By default photos are EXCLUDED to drastically reduce egress
    (each photo can be a multi-MB base64 string). Pass ?include_photos=1 when
    the UI actually needs to render them (edit modal / laudo modal)."""
    if include_photos:
        order = await db.service_orders.find_one({"os_number": os_number}, {"_id": 0})
    else:
        # Inclusion projection — list every non-photo column.
        detail_fields = {
            "_id": 0,
            "id": 1, "os_number": 1, "customer_name": 1, "registration_date": 1,
            "attendance_date": 1, "status": 1, "sub_status": 1, "micro_status": 1,
            "service_type": 1, "source": 1, "brand": 1, "model": 1, "product": 1,
            "address": 1, "number": 1, "complement": 1, "neighborhood": 1,
            "city": 1, "state": 1, "cep": 1, "reference_point": 1,
            "phone1": 1, "phone2": 1, "landline": 1, "email": 1, "technician": 1,
            "serial_number": 1, "batch": 1, "reported_defect": 1,
            "technical_diagnosis": 1, "installation_correct": 1, "required_parts": 1,
            "voltage_f1f2": 1, "voltage_f1_terra": 1, "voltage_f2_terra": 1,
            "observations": 1, "priority": 1, "visit_fee": 1, "visit_fee_paid": 1,
            "lat": 1, "lng": 1, "sort_date": 1,
            "status_orcamento": 1, "conclusao_orcamento": 1,
            "signature_customer": 1, "signature_technician": 1,
            "signature_client": 1, "signature_client_name": 1,
            "signature_client_cpf": 1, "signature_date": 1, "signature_tech_name": 1,
            "assinafy_status": 1, "assinafy_document_id": 1,
            "scheduling_history": 1, "print_count": 1, "share_token": 1,
            "created_at": 1, "updated_at": 1,
        }
        order = await db.service_orders.find_one({"os_number": os_number}, detail_fields)
    if not order:
        raise HTTPException(status_code=404, detail="Ordem de Serviço não encontrada")

    # RBAC: Invisacook role may only view Invisacook OSs.
    if payload.get("role") == "invisacook" and order.get("source") != "invisacook":
        raise HTTPException(status_code=403, detail="Acesso restrito a OSs Invisacook")
    await _assert_tech_os(payload, os_number)
    # Merge priority and print_count from MongoDB
    meta = await os_metadata_col.find_one({"os_number": os_number}, {"_id": 0, "priority": 1, "print_count": 1})
    order["priority"] = meta.get("priority", False) if meta else False
    order["print_count"] = meta.get("print_count", 0) if meta else 0
    # Coerce None to empty string on string fields the frontend assumes are strings.
    string_fields = [
        "customer_name", "registration_date", "cep", "address", "number", "complement",
        "neighborhood", "city", "state", "phone1", "phone2", "landline", "email",
        "product", "brand", "model", "reported_defect", "service_type", "status",
        "technician", "reference_point", "observations"
    ]
    for f in string_fields:
        if order.get(f) is None:
            order[f] = ""
    return order


@api_router.get("/service-orders/{os_number}/photos")
async def get_service_order_photos(os_number: str, _: dict = Depends(verify_token)):
    """Dedicated endpoint to lazy-load photos only when needed (e.g. when the
    photos tab/modal opens). Isolates heavy base64 payloads to reduce egress."""
    proj = {"_id": 0, "os_number": 1}
    for i in range(1, 10):
        proj[f"photo_{i}"] = 1
    photos = await db.service_orders.find_one({"os_number": os_number}, proj)
    if not photos:
        raise HTTPException(status_code=404, detail="Ordem de Serviço não encontrada")
    return photos

@api_router.put("/service-orders/{os_number}")
async def update_service_order(os_number: str, updates: ServiceOrderUpdate, request: Request, background_tasks: BackgroundTasks, payload: dict = Depends(verify_token)):
    order = await db.service_orders.find_one({"os_number": os_number}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Ordem de Serviço não encontrada")
    await _assert_tech_os(payload, os_number)

    # RBAC: Invisacook role may only edit Invisacook OSs, and may never change
    # the source of an OS.
    if payload.get("role") == "invisacook":
        if order.get("source") != "invisacook":
            raise HTTPException(status_code=403, detail="Acesso restrito a OSs Invisacook")

    # Get raw JSON body to check for explicitly null fields
    try:
        raw_body = await request.json()
    except Exception:
        raw_body = {}

    # Invisacook may not change the OS source to anything else.
    if payload.get("role") == "invisacook" and raw_body.get("source") and raw_body.get("source") != "invisacook":
        raise HTTPException(status_code=403, detail="Perfil Invisacook não pode alterar a fonte da OS")

    # Fields that can be explicitly set to null (signature deletion) or false (priority)
    nullable_fields = ['signature_technician', 'signature_client', 'signature_date', 'assinafy_document_id', 'assinafy_status', 'priority']

    # Build update_data - include non-None values
    update_data = {k: v for k, v in updates.model_dump().items() if v is not None}

    # PHOTO PRESERVATION GUARD — never overwrite a stored photo with an empty
    # string unless the client explicitly asks. Autosave paths can send
    # `photo_i = ''` when their hydration hasn't finished (race), which used
    # to wipe photos already saved from another device. To EXPLICITLY clear
    # a photo, send `clear_photos: [1,3,...]` (indices 1..8) alongside the
    # PUT body — see LaudoModal.handleImageChange for the intended UX.
    clear_indices = set()
    raw_clear = raw_body.get("clear_photos")
    if isinstance(raw_clear, list):
        for idx in raw_clear:
            try: clear_indices.add(int(idx))
            except (TypeError, ValueError): pass
    for i in range(1, 9):
        key = f"photo_{i}"
        if key in update_data and update_data[key] == "" and i not in clear_indices:
            existing = order.get(key)
            if existing:
                # Silently drop the destructive empty-write. Log for visibility.
                logger.info(
                    f"PHOTO GUARD: refusing to clear {key} on OS {os_number} "
                    f"(client sent '' but a photo is stored). Send "
                    f"clear_photos=[{i}] to force."
                )
                update_data.pop(key, None)

    # Check if any nullable field was explicitly sent as null/false in the raw request
    for field in nullable_fields:
        if field in raw_body and (raw_body[field] is None or raw_body[field] is False):
            update_data[field] = raw_body[field]

    # Handle priority separately via MongoDB (not in Supabase schema).
    #
    # PRESERVATION RULE: priority is only mutated when the request body
    # *explicitly* mentions `priority`. Autosave paths (LaudoModal, quick
    # status edits) send a subset of fields without `priority`, and any OS
    # that already has priority=true must keep it — regressing to false on
    # every status change wiped the "prioritária" badge whenever an OS was
    # finalized (reported bug).
    if "priority" in raw_body:
        priority_value = raw_body["priority"]
        if priority_value is not None:
            await os_metadata_col.update_one(
                {"os_number": os_number},
                {"$set": {"os_number": os_number, "priority": bool(priority_value)}},
                upsert=True
            )
    # Pop the field from update_data regardless so it doesn't leak into
    # Supabase (which has no `priority` column).
    update_data.pop("priority", None)
    
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    # Check if status changed for notification
    old_status = order.get("status")
    new_status = update_data.get("status")
    
    if new_status and old_status != new_status:
        notification = Notification(
            message=f"OS {os_number} mudou de '{old_status}' para '{new_status}'",
            os_number=os_number,
            old_status=old_status,
            new_status=new_status
        )
        await db.notifications.insert_one(notification.model_dump())
        
        # Dispatch webhook to external site (fire-and-forget)
        tech = update_data.get("technician", order.get("technician", ""))
        background_tasks.add_task(send_webhook_status, os_number, new_status, tech, "", "status_update")
    
    await db.service_orders.update_one({"os_number": os_number}, {"$set": update_data})
    
    # Propagate changes to any routes containing this OS
    address_fields = {"address", "number", "complement", "neighborhood", "city", "cep", "state", "lat", "lng"}
    address_changed = bool(address_fields & set(update_data.keys()))
    route_sync_fields = {"customer_name", "phone1", "phone2", "landline", "email",
                         "address", "number", "complement", "neighborhood", "city", "cep", "state",
                         "product", "brand", "model", "service_type", "status", "technician",
                         "attendance_date", "reported_defect", "observations", "reference_point",
                         "lat", "lng", "visit_fee", "source", "priority"}
    route_updates = {k: update_data[k] for k in route_sync_fields if k in update_data}
    
    if route_updates:
        try:
            all_routes = await db.routes.find({}, {"_id": 0}).to_list(1000)
            for route in all_routes:
                orders = route.get("orders", [])
                changed = False
                for i, o in enumerate(orders):
                    if str(o.get("os_number")) == str(os_number):
                        for k, v in route_updates.items():
                            orders[i][k] = v
                        # Clear cached coords if address changed
                        if address_changed:
                            orders[i].pop("lat", None)
                            orders[i].pop("lng", None)
                            orders[i]["address_changed"] = True
                        changed = True
                        break
                if changed:
                    route_update = {"orders": orders, "updated_at": datetime.now(timezone.utc).isoformat()}
                    await db.routes.update_one({"id": route["id"]}, {"$set": route_update})
                    logger.info(f"Route {route['id']} updated with OS {os_number} changes (address_changed={address_changed})")
        except Exception as e:
            logger.error(f"Error propagating OS {os_number} changes to routes: {e}")
    
    updated_order = await db.service_orders.find_one({"os_number": os_number}, {"_id": 0})
    # Merge priority from MongoDB
    meta = await os_metadata_col.find_one({"os_number": os_number}, {"_id": 0, "priority": 1, "print_count": 1})
    updated_order["priority"] = meta.get("priority", False) if meta else False
    updated_order["print_count"] = meta.get("print_count", 0) if meta else 0
    # Coerce string-typed null fields (Telecontrol-imported records may have NULLs)
    for f in ["customer_name", "registration_date", "cep", "address", "number", "complement", "neighborhood", "city", "state", "phone1", "phone2", "landline", "email", "product", "brand", "model", "reported_defect", "service_type", "status", "technician", "reference_point", "observations"]:
        if updated_order.get(f) is None:
            updated_order[f] = ""
    # Invalidate caches
    cache.invalidate("os_list:")
    cache.invalidate("overdue")
    cache.invalidate("statuses")
    if {"status", "visit_fee", "visit_fee_paid"} & set(update_data.keys()):
        background_tasks.add_task(finance_module.on_os_updated, dict(updated_order))
    return updated_order

@api_router.delete("/service-orders/{os_number}")
async def delete_service_order(os_number: str, _: dict = Depends(verify_token)):
    result = await db.service_orders.delete_one({"os_number": os_number})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Ordem de Serviço não encontrada")
    return {"message": "Ordem de Serviço deletada com sucesso"}


# Migration endpoints
@api_router.post("/migration/start")
async def start_migration(_: dict = Depends(verify_token)):
    """Start the migration script in background"""
    import subprocess  # noqa: F811 — local import keeps startup light
    progress_file = Path(__file__).parent / "migration_progress.json"
    
    # Check if already running
    if progress_file.exists():
        with open(progress_file) as f:
            progress = json.load(f)
            if progress.get("status") == "running":
                return {"message": "Migration already running", "progress": progress}
    
    # Start migration in background
    subprocess.Popen(
        [sys.executable, str(Path(__file__).parent / "migration_script.py")],
        stdout=open('/app/backend/migration_stdout.log', 'w'),
        stderr=open('/app/backend/migration_stderr.log', 'w'),
        cwd=str(Path(__file__).parent)
    )
    return {"message": "Migration started", "status": "running"}

@api_router.get("/migration/progress")
async def get_migration_progress(_: dict = Depends(verify_token)):
    """Get current migration progress"""
    progress_file = Path(__file__).parent / "migration_progress.json"
    if not progress_file.exists():
        return {"status": "not_started"}
    with open(progress_file) as f:
        return json.load(f)

@api_router.get("/migration/summary")
async def get_migration_summary(_: dict = Depends(verify_token)):
    """Get migration summary after completion"""
    summary_file = Path(__file__).parent / "migration_summary.json"
    if not summary_file.exists():
        return {"status": "not_available"}
    with open(summary_file) as f:
        return json.load(f)


# Notifications
@api_router.get("/notifications", response_model=List[Notification])
async def get_notifications(_: dict = Depends(verify_token)):
    # Cache 30s — notification list is polled frequently by all logged-in
    # admins. Invalidated by mark-as-read / read-all endpoints below.
    cached = cache.get("notifications_list")
    if cached is not None:
        return cached
    notifications = await db.notifications.find({}, {"_id": 0}).sort("created_at", -1).to_list(100)
    cache.set("notifications_list", notifications, ttl=30)
    return notifications

@api_router.get("/notifications/unread-count")
async def get_unread_count(_: dict = Depends(verify_token)):
    cached = cache.get("notifications_unread_count")
    if cached is not None:
        return cached
    count = await db.notifications.count_documents({"read": False})
    resp = {"count": count}
    cache.set("notifications_unread_count", resp, ttl=15)
    return resp

@api_router.put("/notifications/{notification_id}/read")
async def mark_notification_read(notification_id: str, _: dict = Depends(verify_token)):
    await db.notifications.update_one({"id": notification_id}, {"$set": {"read": True}})
    cache.delete("notifications_list"); cache.delete("notifications_unread_count")
    return {"message": "Notificação marcada como lida"}

@api_router.put("/notifications/read-all")
async def mark_all_notifications_read(_: dict = Depends(verify_token)):
    await db.notifications.update_many({}, {"$set": {"read": True}})
    cache.delete("notifications_list"); cache.delete("notifications_unread_count")
    return {"message": "Todas notificações marcadas como lidas"}

# Status colors endpoint
@api_router.get("/status-colors")
async def get_status_colors(_: dict = Depends(verify_token)):
    return OS_STATUS_COLORS

# Telecontrol sync status
@api_router.get("/telecontrol/status")
async def get_telecontrol_status(_: dict = Depends(verify_token)):
    # Cache 60s — this is polled by the admin UI to display last sync info.
    # Sync events happen at most every 30min so 60s freshness is plenty.
    cached = cache.get("telecontrol_status")
    if cached is not None:
        return cached
    last_sync = await db.sync_logs.find({}, {"_id": 0}).sort("timestamp", -1).to_list(1)
    last_sync = last_sync[0] if last_sync else None
    
    # Check environment status
    env_status = {
        "scraper_available": SCRAPER_AVAILABLE,
        "hisense_configured": bool(TELECONTROL_LOGIN and TELECONTROL_PASSWORD),
        "hq_configured": bool(TELECONTROL_LOGIN_HQ and TELECONTROL_PASSWORD_HQ),
        "telecontrol_url": TELECONTROL_BASE_URL
    }
    
    resp = {
        "last_sync": last_sync.get("timestamp") if last_sync else None,
        "status": last_sync.get("status") if last_sync else "never_synced",
        "orders_synced": last_sync.get("orders_synced") if last_sync else 0,
        "orders_updated": last_sync.get("orders_updated") if last_sync else 0,
        "errors": last_sync.get("errors") if last_sync else [],
        "environment": env_status
    }
    cache.set("telecontrol_status", resp, ttl=60)
    return resp

# Laudo Generation Endpoints
from fastapi.responses import StreamingResponse
from laudo_generator import generate_laudo_from_template, generate_recall_laudo
from laudo_mastermaq_generator import generate_mastermaq_laudo
from inventory_routes import router as inventory_router

class LaudoData(BaseModel):
    os_number: str
    customer_name: str = ""
    model: str = ""
    serial_number: str = ""
    batch: str = ""
    brand: str = ""
    service_type: str = ""
    reported_defect: str = ""
    technical_diagnosis: str = ""
    installation_correct: str = ""
    required_parts: str = ""
    images: List[str] = []
    technical_notes: str = ""
    final_status: str = ""
    location: str = "BELO HORIZONTE"
    date: str = ""
    technician: str = ""
    voltage_f1f2: str = ""
    voltage_f1_terra: str = ""
    voltage_f2_terra: str = ""
    laudo_type: str = "hisense"
    photo_labels: List[str] = []

@api_router.post("/laudo/save")
async def save_laudo_data(request: Request, _: dict = Depends(verify_token)):
    """Save laudo draft data to database for persistence.
    
    ADDITIVE save: only fields explicitly present in the JSON payload are
    updated. Missing keys are left untouched in the DB. This prevents the
    common bug where the client sends a partial form and the endpoint wipes
    fields the user typed on a previous session (see report: "Dados para o
    Laudo apagados de um dia pro outro").
    
    Empty-string values ARE still saved (so the user can intentionally clear
    a field), but only if the client actually sent that key.
    """
    try:
        raw = await request.json()
        if not isinstance(raw, dict):
            raise HTTPException(status_code=400, detail="Payload must be a JSON object")
        os_number = (raw.get("os_number") or "").strip()
        if not os_number:
            raise HTTPException(status_code=400, detail="os_number is required")
        
        # Whitelist columns that exist in laudo_drafts
        allowed = {
            "os_number", "customer_name", "model", "serial_number", "batch",
            "brand", "service_type", "reported_defect", "technical_diagnosis",
            "installation_correct", "required_parts", "technical_notes",
            "final_status", "location", "date", "technician",
            "voltage_f1f2", "voltage_f1_terra", "voltage_f2_terra",
            "laudo_type", "photo_labels",
        }
        laudo_dict = {k: v for k, v in raw.items() if k in allowed}
        
        # Images are stripped (multi-MB base64s should not live in laudo_drafts
        # — they are persisted onto service_orders.photo_1..8 by the frontend's
        # runLaudoSave, and stored as file paths in photo_labels here).
        if "images" in raw and isinstance(raw["images"], list):
            laudo_dict["images_count"] = str(len(raw["images"]))
        
        laudo_dict["updated_at"] = datetime.now(timezone.utc).isoformat()
        laudo_dict["os_number"] = os_number  # ensure filter matches
        
        await db.laudo_drafts.update_one(
            {"os_number": os_number},
            {"$set": laudo_dict},
            upsert=True
        )
        return {"message": "Rascunho salvo com sucesso", "saved_keys": list(laudo_dict.keys())}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving laudo draft: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/laudo/draft/{os_number}")
async def get_laudo_draft(os_number: str, _: dict = Depends(verify_token)):
    """Load saved laudo draft data"""
    draft = await db.laudo_drafts.find_one({"os_number": os_number}, {"_id": 0})
    if draft:
        return draft
    return {}

@api_router.post("/laudo/generate-docx")
async def generate_laudo_word(data: LaudoData, _: dict = Depends(verify_token)):
    """Generate laudo DOCX by filling the template and save to history"""
    try:
        laudo_dict = data.dict()
        if data.laudo_type == 'recall':
            docx_bytes = generate_recall_laudo(laudo_dict)
            filename = f"Laudo_Recall_OS_{data.os_number}.docx"
        elif data.laudo_type == 'mastermaq':
            docx_bytes = generate_mastermaq_laudo(laudo_dict)
            filename = f"Laudo_Mastermaq_OS_{data.os_number}.docx"
        else:
            docx_bytes = generate_laudo_from_template(laudo_dict)
            filename = f"Laudo_OS_{data.os_number}.docx"
        
        # Save to laudo history
        history_entry = {
            "id": str(uuid.uuid4()),
            "os_number": data.os_number,
            "customer_name": data.customer_name,
            "model": data.model,
            "technician": data.technician,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            await db.laudo_history.insert_one(history_entry)
        except Exception as hist_err:
            # Don't fail laudo generation if history save fails
            logger.warning(f"Failed to save laudo history (laudo still generated): {hist_err}")
        
        return StreamingResponse(
            io.BytesIO(docx_bytes),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        logger.error(f"Error generating DOCX: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/laudo/mastermaq-digital")
async def generate_mastermaq_digital(data: LaudoData, _: dict = Depends(verify_token)):
    """Laudo Mastermaq digital: PDF permanente + link público."""
    import laudo_digital
    try:
        res = await laudo_digital.create(data.dict())
    except Exception as e:
        logger.error(f"laudo digital falhou: {e!r}")
        raise HTTPException(status_code=500, detail="Falha ao gerar o laudo digital")
    try:
        await db.laudo_history.insert_one({"id": str(uuid.uuid4()), "os_number": data.os_number, "customer_name": data.customer_name,
                                           "model": data.model, "technician": data.technician,
                                           "generated_at": datetime.now(timezone.utc).isoformat()})
    except Exception as hist_err:
        logger.warning(f"laudo history: {hist_err}")
    return res


@api_router.get("/laudo/history/{os_number}")
async def get_laudo_history(os_number: str, _: dict = Depends(verify_token)):
    """Get laudo generation history for an OS"""
    history = await db.laudo_history.find(
        {"os_number": os_number}, {"_id": 0}
    ).sort("generated_at", -1).to_list(50)
    return history


# Background sync task
async def run_background_sync(sync_id: str, days: int = 30):
    """Roda run_sync_manual.py --source hisense e --source hq simultaneamente (2 subprocessos)."""
    import re
    from dateutil.relativedelta import relativedelta
    try:
        end_date = datetime.now()
        # Padrão (30): 1 mês antes de hoje; outros valores do seletor continuam em dias.
        start_date = end_date - (relativedelta(months=1) if days == 30 else timedelta(days=days))
        
        start_str = start_date.strftime("%d/%m/%Y")
        end_str = end_date.strftime("%d/%m/%Y")
        
        total_synced = 0
        total_updated = 0
        all_errors = []
        
        async def _run(source):
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "run_sync_manual.py", "--start", start_str, "--end", end_str, "--source", source,
                cwd=str(ROOT_DIR), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            )
            out = (await proc.communicate())[0].decode(errors="replace")
            logger.info(f"run_sync_manual --source {source} exit={proc.returncode}\n{out[-3000:]}")
            return source, proc.returncode, out
        
        logger.info(f"Sync manual paralelo {start_str} a {end_str} (hisense + hq)")
        for source, code, out in await asyncio.gather(_run("hisense"), _run("hq")):
            tag = "Hisense" if source == "hisense" else "HQ"
            m = re.search(r"Concluído: (\d+) novas, (\d+) atualizadas, success=(\w+)", out)
            if m:
                total_synced += int(m.group(1))
                total_updated += int(m.group(2))
            if code != 0 or not m or m.group(3) != "True":
                tail = " | ".join(ln.strip() for ln in out.strip().splitlines()[-6:])[-600:]
                all_errors.append(f"[{tag}] falhou (exit={code}): {tail}")
        
        total_in_db = await db.service_orders.count_documents({})
        
        await db.sync_logs.update_one(
            {"id": sync_id},
            {"$set": {
                "status": "completed" if not all_errors else "completed_with_errors",
                "orders_synced": total_synced,
                "orders_updated": total_updated,
                "total_in_db": total_in_db,
                "days_range": days,
                "date_range": f"{start_str} - {end_str}",
                "errors": all_errors,
                "completed_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        logger.info(f"Dual sync completed: {total_synced} synced, {total_updated} updated, {total_in_db} total in DB")
        
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"Sync error: {e}")
        logger.error(f"Traceback: {error_details}")
        await db.sync_logs.update_one(
            {"id": sync_id},
            {"$set": {
                "status": "failed",
                "errors": [str(e), error_details],
                "completed_at": datetime.now(timezone.utc).isoformat()
            }}
        )

# Manual sync trigger with real Playwright scraping
@api_router.post("/telecontrol/sync")
async def trigger_telecontrol_sync(
    background_tasks: BackgroundTasks, 
    days: int = 30,
    _: dict = Depends(verify_token)
):
    # Check if scraper is available
    if not SCRAPER_AVAILABLE:
        logger.error("Scraper not available - Playwright not installed")
        raise HTTPException(
            status_code=503, 
            detail="Sincronização indisponível - Playwright não instalado neste ambiente"
        )
    
    # Check Telecontrol credentials (at least one set required)
    if not (TELECONTROL_LOGIN or TELECONTROL_LOGIN_HQ):
        logger.error("Telecontrol credentials not configured")
        raise HTTPException(
            status_code=503,
            detail="Credenciais do Telecontrol não configuradas."
        )
    
    # Clamp days to reasonable range
    days = min(max(days, 1), 365)
    
    # Check if sync is already running (auto-expire after 30 min)
    running_sync = await db.sync_logs.find_one({"status": "running"})
    if running_sync:
        ts = running_sync.get("timestamp", "")
        try:
            started = datetime.fromisoformat(ts.replace("+00:00", "+00:00"))
            if not started.tzinfo:
                started = started.replace(tzinfo=timezone.utc)
            if (datetime.now(timezone.utc) - started).total_seconds() > 1800:
                await db.sync_logs.update_one({"id": running_sync["id"]}, {"$set": {"status": "stale"}})
                logger.warning(f"Marked stale sync log: {running_sync['id']}")
            else:
                return {
                    "message": "Sincronização já em andamento",
                    "sync_id": running_sync["id"],
                    "status": "running"
                }
        except Exception:
            await db.sync_logs.update_one({"id": running_sync["id"]}, {"$set": {"status": "stale"}})
            logger.warning(f"Marked stale sync log (parse error): {running_sync['id']}")
    
    # Create sync log
    sync_id = str(uuid.uuid4())
    sync_log = {
        "id": sync_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "running",
        "orders_synced": 0,
        "orders_updated": 0,
        "days_range": days,
        "errors": []
    }
    await db.sync_logs.insert_one(sync_log)
    
    # Start background sync
    background_tasks.add_task(run_background_sync, sync_id, days)
    
    return {
        "message": "Sincronização iniciada",
        "sync_id": sync_id,
        "status": "running"
    }

# Get sync progress
@api_router.get("/telecontrol/sync/{sync_id}")
async def get_sync_status(sync_id: str, _: dict = Depends(verify_token)):
    sync_log = await db.sync_logs.find_one({"id": sync_id}, {"_id": 0})
    if not sync_log:
        raise HTTPException(status_code=404, detail="Sync not found")
    return sync_log


@api_router.get("/scrapers/health")
async def scrapers_health(_: dict = Depends(verify_token)):
    """Public health snapshot of Telecontrol scrapers used by the header badge.

    Returns:
        overall: 'ok' | 'warning' | 'down'
        overall_message: human-friendly badge text, e.g. "Scraper Hisense falhou"
        scrapers: per-source detail (consecutive_failures, last_success,
                  last_failure, last_error, last_run, recent_volumes, last_volume)
    """
    overall = "ok"
    # Deterministic label order so the badge message is stable.
    sources = sorted(SCRAPER_HEALTH.keys())
    down_sources = []
    warning_sources = []
    for src in sources:
        h = SCRAPER_HEALTH[src]
        if h["consecutive_failures"] >= 2 or h.get("status") == "down":
            down_sources.append(src)
        elif h["consecutive_failures"] >= 1 or h.get("status") == "warning":
            warning_sources.append(src)

    if down_sources:
        overall = "down"
    elif warning_sources:
        overall = "warning"

    if down_sources:
        names = ", ".join(s.title() for s in down_sources)
        message = f"Scraper {names} falhou"
    elif warning_sources:
        names = ", ".join(s.title() for s in warning_sources)
        message = f"Scraper {names} instável"
    else:
        message = "Scrapers OK"

    return {
        "overall": overall,
        "overall_message": message,
        "scrapers": SCRAPER_HEALTH,
    }


@api_router.post("/scrapers/{source}/resync")
async def force_resync(source: str, days: int = 60, background_tasks: BackgroundTasks = None, _: dict = Depends(verify_token)):
    """Force a catch-up resync for a specific scraper (Hisense or HQ)."""
    if source not in ("hisense", "hq"):
        raise HTTPException(status_code=400, detail="source must be 'hisense' or 'hq'")
    scraper = scraper_hisense if source == "hisense" else scraper_hq
    if not scraper:
        raise HTTPException(status_code=503, detail=f"Scraper {source} not available")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    start_str = start_date.strftime("%d/%m/%Y")
    end_str = end_date.strftime("%d/%m/%Y")
    background_tasks.add_task(_run_sync_with_health, source, scraper, start_str, end_str)
    return {"status": "scheduled", "source": source, "days": days, "start": start_str, "end": end_str}

@api_router.post("/admin/migrate-statuses")
async def migrate_statuses(_: dict = Depends(verify_token)):
    """
    One-time migration endpoint to:
    1. Replace status 'Orçamento' with 'Aguardando Analise A.T'
    2. Set all OS before 02/02/2026 to 'Finalizada'
    3. Set empty statuses to 'Importado'
    """
    from datetime import datetime as dt
    results = {}

    # 1. Replace Orçamento status
    r1 = await db.service_orders.update_many(
        {"status": "Orçamento"},
        {"$set": {"status": "Aguardando Analise A.T"}}
    )
    results["orcamento_to_at"] = r1.modified_count

    # 2. Update OS before 02/02/2026 to Finalizada
    cutoff = dt(2026, 2, 2)
    os_to_update = []
    docs = await db.service_orders.find(
        {"status": {"$nin": ["Finalizada", "OS Cancelada"]}},
    ).to_list(10000)
    for doc in docs:
        parsed = None
        for field in ['attendance_date', 'registration_date', 'created_at']:
            val = doc.get(field)
            if not val:
                continue
            if isinstance(val, dt):
                parsed = val
                break
            s = str(val).strip()
            for fmt in ['%Y-%m-%dT%H:%M:%S', '%Y-%m-%d', '%d/%m/%Y']:
                try:
                    parsed = dt.strptime(s[:min(19, len(s))], fmt)
                    break
                except Exception:
                    pass
            if parsed:
                break
        if parsed and parsed < cutoff:
            os_to_update.append(doc['os_number'])

    if os_to_update:
        # Update in batches of 100
        total_updated = 0
        for i in range(0, len(os_to_update), 100):
            batch = os_to_update[i:i+100]
            r2 = await db.service_orders.update_many(
                {"os_number": {"$in": batch}},
                {"$set": {"status": "Finalizada"}}
            )
            total_updated += r2.modified_count
        results["finalized"] = total_updated
    else:
        results["finalized"] = 0

    # 3. Set empty statuses to Importado
    r3 = await db.service_orders.update_many(
        {"status": {"$in": ["", None]}},
        {"$set": {"status": "Importado"}}
    )
    results["empty_to_importado"] = r3.modified_count

    results["total_checked"] = len(os_to_update)
    return results


# Migrate AGUARDANDO ANÁLISE → Aguardando Analise A.T
@api_router.post("/migrate/fix-status-aguardando")
async def migrate_fix_aguardando_status(_: dict = Depends(verify_token)):
    """Migrate all variations of 'AGUARDANDO ANÁLISE' to 'Aguardando Analise A.T'"""
    # Match various casings: "AGUARDANDO ANÁLISE", "Aguardando Análise", etc.
    result = await db.service_orders.update_many(
        {"status": {"$regex": "^aguardando an[aá]lise$", "$options": "i"}},
        {"$set": {"status": "Aguardando Analise A.T"}}
    )
    # Also fix "Importado" → "Aguardando Analise A.T" for recent ones
    result2 = await db.service_orders.update_many(
        {"status": "Importado"},
        {"$set": {"status": "Aguardando Analise A.T"}}
    )
    return {
        "aguardando_analise_fixed": result.modified_count,
        "importado_fixed": result2.modified_count,
        "total_fixed": result.modified_count + result2.modified_count
    }



# ─── Webhook audit log inspector ───────────────────────────────────
@api_router.get("/webhooks/outbound-log")
async def list_webhook_log(limit: int = 50, _: dict = Depends(verify_token)):
    """Return the most recent outbound webhook attempts (for debugging)."""
    cursor = mongo_db["webhook_outbound_log"].find({}, {"_id": 0}).sort("sent_at", -1).limit(min(max(limit, 1), 200))
    rows = await cursor.to_list(200)
    return {"count": len(rows), "webhook_url": EXTERNAL_WEBHOOK_URL, "rows": rows}


@api_router.post("/webhooks/outbound-log/{log_id}/replay")
async def replay_webhook(log_id: str, _: dict = Depends(require_admin)):
    """Resend the webhook payload of a previously logged attempt (admin only).
    Useful to retry failed sends, or to verify the receiver works."""
    entry = await mongo_db["webhook_outbound_log"].find_one({"id": log_id}, {"_id": 0})
    if not entry:
        raise HTTPException(status_code=404, detail="Log entry não encontrado")
    p = entry.get("payload") or {}
    new_log = await send_webhook_status(
        os_number=str(p.get("os_number") or entry.get("os_number") or ""),
        status=str(p.get("status") or ""),
        technician=str(p.get("technician") or ""),
        notes=str(p.get("notes") or ""),
        event_type=str(p.get("event_type") or "status_update"),
    )
    return {"ok": True, "new_log": new_log}


@api_router.post("/webhooks/test-fire")
async def fire_test_webhook(body: dict, _: dict = Depends(require_admin)):
    """Manually dispatch a webhook for diagnostic purposes (admin only).
    Body: {os_number, status, technician?, notes?}. The technician can use
    this from /admin/webhooks UI to verify the receiver works without changing
    real data."""
    os_number = str(body.get("os_number") or "").strip()
    status = str(body.get("status") or "").strip()
    if not os_number or not status:
        raise HTTPException(status_code=400, detail="os_number e status são obrigatórios")
    new_log = await send_webhook_status(
        os_number=os_number,
        status=status,
        technician=str(body.get("technician") or ""),
        notes=str(body.get("notes") or ""),
        event_type="manual_test",
    )
    return {"ok": True, "log": new_log}


@api_router.get("/webhooks/config")
async def get_webhook_config(_: dict = Depends(require_admin)):
    """Return the currently configured webhook target URL and a masked key
    so the admin can verify what is actually being sent."""
    key = EXTERNAL_API_KEY or ""
    masked = (key[:6] + "..." + key[-4:]) if len(key) > 12 else "***"
    return {
        "webhook_url": EXTERNAL_WEBHOOK_URL,
        "api_key_preview": masked,
        "api_key_length": len(key),
    }


# ─── WhatsApp "Enviar Cópia" — sends PDF document via Meta Graph API ────
class SendCopyRequest(BaseModel):
    phone: str  # destination phone, raw or with country code
    os_number: str
    pdf_base64: str  # base64-encoded PDF
    caption: Optional[str] = None
    filename: Optional[str] = None


@api_router.post("/whatsapp/send-copy")
async def whatsapp_send_copy(body: SendCopyRequest, _: dict = Depends(verify_token)):
    """
    Upload the PDF generated on the frontend to Meta Media API, then send it
    as a document message to the customer. Logs the message in whatsapp_messages.
    """
    import base64
    config = await db.whatsapp_config.find_one({}, {"_id": 0})
    wa_token = os.environ.get("WA_PERMANENT_TOKEN", "") or (config.get("access_token", "") if config else "")
    phone_id = (config or {}).get("phone_number_id", "")
    if not wa_token or not phone_id:
        raise HTTPException(status_code=400, detail="WhatsApp não configurado")

    # Normalize destination phone (digits only, BR prefix)
    digits = "".join(ch for ch in (body.phone or "") if ch.isdigit())
    if not digits:
        raise HTTPException(status_code=400, detail="Telefone inválido")
    if not digits.startswith("55"):
        digits = "55" + digits

    # Decode PDF
    try:
        b64 = body.pdf_base64
        if "," in b64:
            b64 = b64.split(",", 1)[1]
        pdf_bytes = base64.b64decode(b64)
    except Exception:
        raise HTTPException(status_code=400, detail="PDF inválido (base64)")

    filename = body.filename or f"OS_{body.os_number}.pdf"
    caption = body.caption or f"Cópia eletrônica da OS Nº {body.os_number}\n\nMastermaq Assistência Técnica\n(31) 3422-5293 | (31) 2526-8420"

    # Step 1: upload media → get media_id
    upload_url = f"https://graph.facebook.com/v21.0/{phone_id}/media"
    files = {
        "file": (filename, pdf_bytes, "application/pdf"),
        "type": (None, "application/pdf"),
        "messaging_product": (None, "whatsapp"),
    }
    async with httpx.AsyncClient(timeout=60) as client:
        up = await client.post(upload_url, files=files, headers={"Authorization": f"Bearer {wa_token}"})
    if up.status_code >= 400:
        detail = up.json() if up.headers.get("content-type", "").startswith("application/json") else up.text
        raise HTTPException(status_code=up.status_code, detail={"step": "upload", "error": detail})
    media_id = up.json().get("id")
    if not media_id:
        raise HTTPException(status_code=500, detail="Meta não retornou media_id")

    # Step 2: send document message referencing the uploaded media
    send_url = f"https://graph.facebook.com/v21.0/{phone_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": digits,
        "type": "document",
        "document": {
            "id": media_id,
            "filename": filename,
            "caption": caption,
        },
    }
    async with httpx.AsyncClient(timeout=30) as client:
        send = await client.post(send_url, json=payload, headers={"Authorization": f"Bearer {wa_token}", "Content-Type": "application/json"})
    if send.status_code >= 400:
        detail = send.json() if send.headers.get("content-type", "").startswith("application/json") else send.text
        raise HTTPException(status_code=send.status_code, detail={"step": "send", "error": detail})

    result = send.json()
    try:
        await db.whatsapp_messages.insert_one({
            "direction": "outbound",
            "to": digits,
            "type": "document",
            "body": f"[PDF OS {body.os_number}] {caption}",
            "media_id": media_id,
            "os_number": body.os_number,
            "wa_message_id": (result.get("messages") or [{}])[0].get("id"),
            "status": "sent",
            "sent_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception:
        pass
    return {"ok": True, "media_id": media_id, "wa_message_id": (result.get("messages") or [{}])[0].get("id")}


# ─── Public read-only OS share-token (signed JWT, used by QR code stickers) ──
class OSShareTokenRequest(BaseModel):
    os_number: str
    ttl_hours: Optional[int] = 24 * 30  # default 30 days


@api_router.post("/os/share-token")
async def create_os_share_token(body: OSShareTokenRequest, _: dict = Depends(verify_token)):
    """Issue a signed JWT granting public read-only access to a specific OS.
    Used by printed QR-code stickers — anyone with the link sees the OS without
    logging in. Token TTL defaults to 30 days."""
    payload = {
        "os_number": str(body.os_number),
        "iss": "mastermaq-os-share",
        "exp": datetime.now(timezone.utc) + timedelta(hours=max(1, int(body.ttl_hours or 24 * 30))),
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return {"token": token, "url_path": f"/os/{body.os_number}?t={token}"}


@api_router.get("/os/public/by-number/{os_number}")
async def os_public_view_by_number(os_number: str):
    """Privacy-safe public view of an OS by number — NO auth required.
    Returns the same masked subset as /os/public/{token} so the QR-scan flow
    can work without minting/sharing a JWT. Used by /os-view/:os_number
    pages opened by customers from the QR code on the thermal label."""
    order = await db.service_orders.find_one(
        {"os_number": str(os_number)},
        {"_id": 0,
         "os_number": 1, "customer_name": 1, "status": 1, "brand": 1, "model": 1,
         "product": 1, "reported_defect": 1, "neighborhood": 1, "city": 1,
         "created_at": 1, "updated_at": 1, "source": 1, "complement": 1, "address": 1}
    )
    if not order:
        raise HTTPException(status_code=404, detail="OS não encontrada")
    # Mask customer last names — first name + initials of remaining surnames
    cname = order.get("customer_name") or ""
    parts = cname.split()
    if len(parts) > 1:
        order["customer_name"] = parts[0] + " " + " ".join(p[0] + "." for p in parts[1:])
    # Strip trailing house numbers from address (privacy)
    addr = order.get("address") or ""
    if addr:
        import re as _re
        order["address"] = _re.sub(r",?\s*\d+\s*$", "", addr).strip()
    return order


@api_router.get("/product/public/by-code/{code}")
async def product_public_view_by_code(code: str):
    """Public product view used by the inventory QR code printed on labels.
    Returns ONLY a curated, customer-safe subset: category, name, brand, model,
    unit, sale_price. Cost / stock / suppliers are intentionally omitted."""
    p = await db.products.find_one(
        {"code": str(code)},
        {"_id": 0, "code": 1, "name": 1, "category": 1, "brand": 1,
         "model": 1, "unit": 1, "sale_price": 1}
    )
    if not p:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    return p


@api_router.get("/os/public/{token}")
async def os_public_view(token: str):
    """Resolve the signed token and return a privacy-safe view of the OS.
    NO auth required."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=410, detail="Link expirado")
    except Exception:
        raise HTTPException(status_code=401, detail="Token inválido")
    if payload.get("iss") != "mastermaq-os-share":
        raise HTTPException(status_code=401, detail="Token inválido")
    os_number = str(payload.get("os_number") or "")
    order = await db.service_orders.find_one(
        {"os_number": os_number},
        {"_id": 0,
         "os_number": 1, "customer_name": 1, "status": 1, "brand": 1, "model": 1,
         "product": 1, "reported_defect": 1, "neighborhood": 1, "city": 1,
         "created_at": 1, "updated_at": 1, "source": 1, "complement": 1, "address": 1}
    )
    if not order:
        raise HTTPException(status_code=404, detail="OS não encontrada")
    # Customer name → mask last names (privacy)
    cname = order.get("customer_name") or ""
    parts = cname.split()
    if len(parts) > 1:
        order["customer_name"] = parts[0] + " " + " ".join(p[0] + "." for p in parts[1:])
    # Strip street number if present in address
    addr = order.get("address") or ""
    if addr:
        # Drop trailing house numbers like ", 123" or " 123"
        import re as _re
        order["address"] = _re.sub(r",?\s*\d+\s*$", "", addr).strip()
    return order


# Include the router in the main app
# ─── Photos status helper (for technician mandatory-photos flow) ───
@api_router.get("/service-orders/{os_number}/photos-status")
async def get_photos_status(os_number: str, _: dict = Depends(verify_token)):
    """
    Return whether the OS has all 8 mandatory photos (photo_1..photo_8) filled.
    Used by the routes screen to allow/block "Concluir Atendimento".
    
    EGRESS-OPTIMIZED: calls a Postgres function via PostgREST RPC that runs
    `length(photo_X) > 0` server-side and returns only booleans. Previously
    this endpoint downloaded all 8 base64 photos (multi-MB per call) just to
    check truthiness — now the response is < 200 bytes.
    
    Result cached for 60s per OS — the routes page polls this frequently
    while photos are being uploaded, but they're written from the same UI so
    we know when to invalidate (via cache.delete on the photo POST path).
    """
    cache_key = f"photos_status:{os_number}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    
    # Call the Postgres function via PostgREST RPC. Lazy-imports the shared
    # httpx client from the adapter to reuse its connection pool.
    try:
        from supabase_db import _get_client, _headers, SUPABASE_URL as adapter_url
        c = _get_client()
        r = await c.post(
            f"{adapter_url}/rest/v1/rpc/photos_status_for",
            headers=_headers(),
            json={"os_num": os_number},
            timeout=10,
        )
        if r.status_code != 200:
            raise RuntimeError(f"RPC failed: {r.status_code} {r.text[:200]}")
        payload = r.json()
    except Exception as e:
        logger.error(f"photos-status RPC error for {os_number}: {e}")
        raise HTTPException(status_code=500, detail="photos_status_for RPC error")
    
    if payload is None:
        raise HTTPException(status_code=404, detail="OS não encontrada")
    
    cache.set(cache_key, payload, ttl=60)
    return payload


# ─── Temporary public PDF storage (WhatsApp fallback for allowlist limitations) ──
import base64 as _b64  # noqa: E402
import re as _re_pdf  # noqa: E402
from manuais_module import put_object as _put_object, get_object as _get_object  # noqa: E402


@api_router.post("/files/temp-pdf")
async def store_temp_pdf(body: dict, _: dict = Depends(verify_token)):
    """Salva o PDF no object storage (permanente, sem expiração) e devolve URL pública
    para o técnico enviar via wa.me."""
    b64 = body.get("pdf_base64") or ""
    if "," in b64:
        b64 = b64.split(",", 1)[1]
    try:
        data = _b64.b64decode(b64)
    except Exception:
        raise HTTPException(status_code=400, detail="PDF inválido (base64)")
    token = uuid.uuid4().hex
    try:
        await asyncio.to_thread(_put_object, f"mastermaq-manuais/shared-pdfs/{token}.pdf", data, "application/pdf")
    except Exception as e:
        logger.error(f"temp-pdf upload failed: {e!r}")
        raise HTTPException(status_code=502, detail="Falha ao salvar PDF")
    base = os.environ.get("PUBLIC_BACKEND_URL") or ""
    return {
        "token": token,
        "url": f"{base}/api/files/temp-pdf/{token}",
        "path": f"/api/files/temp-pdf/{token}",
    }


@api_router.get("/files/temp-pdf/{token}")
async def fetch_temp_pdf(token: str):
    """Public PDF download (no auth). Nunca expira."""
    if not _re_pdf.fullmatch(r"[0-9a-f]{32}", token):
        raise HTTPException(status_code=404, detail="PDF inexistente")
    try:
        data, _ = await asyncio.to_thread(_get_object, f"mastermaq-manuais/shared-pdfs/{token}.pdf")
    except Exception:
        raise HTTPException(status_code=404, detail="PDF inexistente")
    from fastapi.responses import Response
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename=\"OS_{token[:8]}.pdf\""},
    )

# Initialize inventory routes with db and JWT secret.
# `mongo_db` is a native Motor handle used by inventory_routes for the
# `product_metadata` sidecar (image_url + product_type). Once the SQL
# migration in /app/backend/migrations/products_add_image_and_type.sql is
# applied, this sidecar can be retired but keeps working as a fallback.
from inventory_routes import init as init_inventory
init_inventory(db, JWT_SECRET, mongo=mongo_db)
api_router.include_router(inventory_router)

# Include routes module
from routes_module import router as routes_router
api_router.include_router(routes_router)

from tracking_module import router as tracking_router
api_router.include_router(tracking_router)

from rotaflow_module import router as rotaflow_router
api_router.include_router(rotaflow_router)

# Register manuais routes
setup_manuais_routes(api_router, db, verify_token)
setup_whatsapp_routes(api_router, db, verify_token)
setup_users_routes(api_router, mongo_db, verify_token)
setup_label_templates_routes(api_router, mongo_db, verify_token)
import finance_module  # noqa: E402
finance_module.setup_finance(api_router, mongo_db, db, verify_token)


@app.on_event("startup")
async def startup_finance():
    await finance_module.startup()

from mi_module import setup_mi_routes, index_manuals as mi_index_manuals
setup_mi_routes(api_router, db, mongo_db, require_admin)


async def _mi_create_os(fields: dict, payload: dict):
    """Usado pela Mi (ação create_os confirmada). Preenche defaults dos campos obrigatórios."""
    if not fields.get("os_number"):
        fields["os_number"] = (await get_next_ose_number(payload))["next_ose_number"]
    base = {k: "" for k in ("cep", "address", "number", "neighborhood", "city", "state", "phone1", "product", "brand")}
    base.update(city="Belo Horizonte", state="MG", registration_date=datetime.now().strftime("%d/%m/%Y"))
    data = {**base, **{k: v for k, v in fields.items() if v is not None}}
    return await create_service_order(ServiceOrderCreate(**data), payload)

import mi_agent as _mi_agent  # noqa: E402
_mi_agent.CREATE_OS = _mi_create_os


async def _mi_sync_orders():
    """Mi (sync_orders confirmada): mesmo fluxo do botão Sincronizar (Hisense + HQ, último mês)."""
    if not SCRAPER_AVAILABLE:
        raise ValueError("Sincronização indisponível neste ambiente (Playwright ausente)")
    running = await db.sync_logs.find_one({"status": "running"})
    if running:
        return "Já existe uma sincronização em andamento."
    sync_id = str(uuid.uuid4())
    await db.sync_logs.insert_one({"id": sync_id, "timestamp": datetime.now(timezone.utc).isoformat(), "status": "running",
                                   "orders_synced": 0, "orders_updated": 0, "days_range": 30, "errors": []})
    asyncio.create_task(run_background_sync(sync_id, 30))
    return "Sincronização Hisense + HQ iniciada (último mês). As ordens aparecem em alguns minutos."

_mi_agent.SYNC_ORDERS = _mi_sync_orders


@app.on_event("startup")
async def startup_mi_index():
    asyncio.create_task(mi_index_manuals(db, mongo_db))

app.include_router(api_router)

# Serve static files from frontend build (for production)
FRONTEND_BUILD_PATH = Path(__file__).parent.parent / "frontend" / "build"
_FRONTEND_BUILD_EXISTS = FRONTEND_BUILD_PATH.exists()

if _FRONTEND_BUILD_EXISTS:
    logger.info(f"Frontend build found at {FRONTEND_BUILD_PATH}")
    # Serve static assets (js, css, images, etc.)
    static_dir = FRONTEND_BUILD_PATH / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=static_dir), name="static")
else:
    logger.warning(f"Frontend build NOT found at {FRONTEND_BUILD_PATH}")


# Single SPA/root catch-all — behavior branches on _FRONTEND_BUILD_EXISTS at
# request time so we only ever register ONE route for /{full_path:path}
# (avoids the route-shadowing conflict of registering the same path twice).
@app.get("/{full_path:path}")
async def serve_frontend_or_fallback(full_path: str):
    # If path starts with api, let FastAPI handle it
    if full_path.startswith("api"):
        raise HTTPException(status_code=404)

    if not _FRONTEND_BUILD_EXISTS:
        return {"status": "ok", "message": "Frontend build not available"}

    # Try to serve the requested file
    file_path = FRONTEND_BUILD_PATH / full_path
    if file_path.exists() and file_path.is_file():
        return FileResponse(file_path)

    # Fallback to index.html for SPA routing - with no-cache headers
    index_path = FRONTEND_BUILD_PATH / "index.html"
    if index_path.exists():
        return FileResponse(
            index_path,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )

    raise HTTPException(status_code=404)

@app.on_event("shutdown")
async def shutdown_db_client():
    pass  # Supabase REST API - no persistent connection to close
