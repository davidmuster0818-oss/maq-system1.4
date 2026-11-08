"""
Tracking module - GPS tracking for technicians on routes.
Uses Supabase Realtime Broadcast for live updates + MongoDB for last-known
position (for public tracking pages and admin live-mirror).

Public sharing: signed JWT tokens are issued per (route_id, os_number) and
expire automatically. Clients open `/track/{token}` to see the technician
moving in realtime — no login required.
"""
import os
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Depends, Header
import jwt

from supabase_db import db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tracking", tags=["tracking"])

JWT_SECRET = os.environ.get("JWT_SECRET")
if not JWT_SECRET or JWT_SECRET in ("default_secret", "change-me", ""):
    # Falhar na importação — qualquer módulo que use este import vai receber
    # a exceção durante o startup do backend, antes de servir qualquer
    # requisição. Pior cenário: backend não sobe (correto).
    raise RuntimeError("JWT_SECRET ausente ou inseguro em backend/.env")
JWT_ALGORITHM = "HS256"
SHARE_TOKEN_TTL_HOURS = 24


# Local copy of token verification to avoid circular imports with server.py.
async def verify_token(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    raw = authorization.split(" ", 1)[1].strip()
    try:
        payload = jwt.decode(raw, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
    # Reject share-tokens (different issuer): only auth tokens may call protected routes.
    if payload.get("iss") == "mastermaq-tracking":
        raise HTTPException(status_code=401, detail="Invalid token")
    import security
    return await security.check_session(payload)


# ─── Models ─────────────────────────────────────────────────────
class TrackingSession(BaseModel):
    route_id: str
    technician: str


class StopStatusUpdate(BaseModel):
    route_id: str
    os_number: str
    status: str  # 'pending', 'next', 'completed'


class BreadcrumbPoint(BaseModel):
    route_id: str
    lat: float
    lng: float
    heading: Optional[float] = 0
    speed: Optional[float] = 0
    timestamp: Optional[str] = None


class GPSUpdate(BaseModel):
    route_id: str
    lat: float
    lng: float
    heading: Optional[float] = 0
    speed: Optional[float] = 0
    technician: Optional[str] = ""
    active_os: Optional[str] = None       # OS currently in transit / being attended
    active_status: Optional[str] = None   # 'in_transit' | 'in_progress' | etc.
    # Polyline path (array of {lat,lng}) and traffic info for the current
    # navigation leg. Persisted so admin/public viewers can render the
    # exact same road-following route as the technician.
    nav_path: Optional[list] = None
    nav_distance_meters: Optional[int] = None
    nav_duration_seconds: Optional[int] = None
    nav_duration_in_traffic_seconds: Optional[int] = None
    nav_traffic_color: Optional[str] = None  # 'green'|'yellow'|'red'|'lightblue'
    nav_destination_lat: Optional[float] = None
    nav_destination_lng: Optional[float] = None


class ShareTokenRequest(BaseModel):
    route_id: str
    os_number: Optional[str] = None


# ─── Existing simple endpoints ──────────────────────────────────
@router.post("/start")
async def start_tracking(session: TrackingSession, _: dict = Depends(verify_token)):
    now = datetime.now(timezone.utc).isoformat()
    try:
        await db.routes.update_one(
            {"id": session.route_id},
            {"$set": {"status": "Em andamento", "updated_at": now}}
        )
    except Exception as e:
        logger.warning(f"Could not update route: {e}")
    return {"status": "active"}


@router.post("/end")
async def end_tracking(session: TrackingSession, _: dict = Depends(verify_token)):
    now = datetime.now(timezone.utc).isoformat()
    try:
        await db.routes.update_one(
            {"id": session.route_id},
            {"$set": {"updated_at": now}}
        )
        # Clear the live position when ending
        from server import mongo_db
        await mongo_db["tracking_live"].update_one(
            {"route_id": session.route_id},
            {"$set": {"active": False, "ended_at": now}},
            upsert=True
        )
    except Exception as e:
        logger.warning(f"Could not update route/live: {e}")
    return {"status": "completed"}


@router.post("/stop-status")
async def update_stop_status(update: StopStatusUpdate, _: dict = Depends(verify_token)):
    now = datetime.now(timezone.utc).isoformat()
    route = await db.routes.find_one({"id": update.route_id}, {"_id": 0})
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")

    orders = route.get("orders", [])
    for o in orders:
        if str(o.get("os_number")) == str(update.os_number):
            o["stop_status"] = update.status
            break

    await db.routes.update_one(
        {"id": update.route_id},
        {"$set": {"orders": orders, "updated_at": now}}
    )
    return {"ok": True}


@router.get("/config")
async def get_tracking_config(_: dict = Depends(verify_token)):
    return {
        "supabase_url": os.environ.get("SUPABASE_URL", ""),
        "supabase_anon_key": os.environ.get("SUPABASE_ANON_KEY", ""),
    }


@router.post("/breadcrumb")
async def save_breadcrumb(point: BreadcrumbPoint, _: dict = Depends(verify_token)):
    """Save a GPS breadcrumb point for route history."""
    from server import mongo_db
    now = datetime.now(timezone.utc).isoformat()
    await mongo_db["tracking_breadcrumbs"].insert_one({
        "route_id": point.route_id,
        "lat": point.lat,
        "lng": point.lng,
        "heading": point.heading,
        "speed": point.speed,
        "timestamp": point.timestamp or now,
        "created_at": datetime.now(timezone.utc),  # TTL index (30 dias)
    })
    return {"ok": True}


@router.get("/breadcrumbs/{route_id}")
async def get_breadcrumbs(route_id: str, _: dict = Depends(verify_token)):
    """Get all breadcrumb points for a route."""
    from server import mongo_db
    points = []
    async for doc in mongo_db["tracking_breadcrumbs"].find(
        {"route_id": route_id}, {"_id": 0, "created_at": 0}
    ).sort("timestamp", 1):
        points.append(doc)
    return {"points": points}


# ─── Live position persistence (admin mirror + public tracking) ─
@router.post("/gps")
async def upsert_gps(point: GPSUpdate, _: dict = Depends(verify_token)):
    """Persist last-known GPS position for a route. Called by the technician's
    browser every few seconds. Public tracking pages and admin live-mirror
    fetch from this collection (Supabase realtime is best-effort transport;
    Mongo is the source of truth for late joiners)."""
    from server import mongo_db
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "route_id": point.route_id,
        "lat": point.lat,
        "lng": point.lng,
        "heading": point.heading or 0,
        "speed": point.speed or 0,
        "technician": point.technician or "",
        "active_os": point.active_os,
        "active_status": point.active_status,
        "updated_at": now,
        "active": True,
    }
    # Persist nav data only if provided (don't overwrite existing nav with None)
    if point.nav_path is not None:
        doc["nav_path"] = point.nav_path
    if point.nav_distance_meters is not None:
        doc["nav_distance_meters"] = point.nav_distance_meters
    if point.nav_duration_seconds is not None:
        doc["nav_duration_seconds"] = point.nav_duration_seconds
    if point.nav_duration_in_traffic_seconds is not None:
        doc["nav_duration_in_traffic_seconds"] = point.nav_duration_in_traffic_seconds
    if point.nav_traffic_color is not None:
        doc["nav_traffic_color"] = point.nav_traffic_color
    if point.nav_destination_lat is not None:
        doc["nav_destination_lat"] = point.nav_destination_lat
    if point.nav_destination_lng is not None:
        doc["nav_destination_lng"] = point.nav_destination_lng
    await mongo_db["tracking_live"].update_one(
        {"route_id": point.route_id},
        {"$set": doc},
        upsert=True
    )
    return {"ok": True, "updated_at": now}


@router.get("/live/{route_id}")
async def get_live_position(route_id: str, _: dict = Depends(verify_token)):
    """Admin live-mirror — returns latest GPS for a route + active OS info +
    the technician's per-OS stop_statuses pulled from the active session.
    This is the single endpoint admin clients poll every 5s to mirror the
    technician's screen in realtime."""
    from server import mongo_db
    doc = await mongo_db["tracking_live"].find_one({"route_id": route_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Sem dados de localização para este roteiro")
    # Pull stop_statuses from the active session for this route (if any)
    session = await mongo_db["tracking_sessions"].find_one(
        {"route_id": route_id, "active": True},
        {"_id": 0, "stop_statuses": 1, "technician_name": 1, "started_at": 1, "updated_at": 1}
    )
    if session:
        doc["stop_statuses"] = session.get("stop_statuses") or {}
        doc["session_started_at"] = session.get("started_at")
        doc["session_updated_at"] = session.get("updated_at")
        if session.get("technician_name") and not doc.get("technician"):
            doc["technician"] = session["technician_name"]
    else:
        doc["stop_statuses"] = {}
    return doc


# ─── Persistent navigation sessions (survive reload / app close) ────
class SessionStart(BaseModel):
    route_id: str
    technician_name: Optional[str] = ""


class StopStatusesUpdate(BaseModel):
    route_id: str
    stop_statuses: dict  # {os_number: status}


@router.post("/session/start")
async def start_session(body: SessionStart, payload: dict = Depends(verify_token)):
    """Mark a navigation session as active. Idempotent — upserts by user+route."""
    from server import mongo_db
    user_email = (payload.get("email") or "").lower()
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "route_id": body.route_id,
        "user_email": user_email,
        "user_name": payload.get("name") or "",
        "technician_name": body.technician_name or payload.get("name") or "",
        "active": True,
        "started_at": now,
        "updated_at": now,
    }
    await mongo_db["tracking_sessions"].update_one(
        {"user_email": user_email, "route_id": body.route_id},
        {"$set": doc, "$setOnInsert": {"id": str(uuid.uuid4()), "stop_statuses": {}}},
        upsert=True,
    )
    # Mark all other active sessions for this user as inactive (single active route)
    await mongo_db["tracking_sessions"].update_many(
        {"user_email": user_email, "route_id": {"$ne": body.route_id}, "active": True},
        {"$set": {"active": False, "ended_at": now}},
    )
    return {"ok": True, "started_at": now}


@router.post("/session/stop")
async def stop_session(body: SessionStart, payload: dict = Depends(verify_token)):
    from server import mongo_db
    user_email = (payload.get("email") or "").lower()
    now = datetime.now(timezone.utc).isoformat()
    await mongo_db["tracking_sessions"].update_one(
        {"user_email": user_email, "route_id": body.route_id},
        {"$set": {"active": False, "ended_at": now, "updated_at": now}},
    )
    # Also mark the live position as inactive so admin/public stop showing "live"
    await mongo_db["tracking_live"].update_one(
        {"route_id": body.route_id},
        {"$set": {"active": False, "ended_at": now}},
    )
    return {"ok": True}


@router.get("/session/current")
async def current_session(payload: dict = Depends(verify_token)):
    """Return the user's currently active navigation session, if any.
    Frontend calls this on mount to auto-resume the navigation modal."""
    from server import mongo_db
    user_email = (payload.get("email") or "").lower()
    doc = await mongo_db["tracking_sessions"].find_one(
        {"user_email": user_email, "active": True},
        {"_id": 0}
    )
    if not doc:
        return {"active": False}
    return {"active": True, "session": doc}


@router.post("/session/stop-statuses")
async def update_stop_statuses(body: StopStatusesUpdate, payload: dict = Depends(verify_token)):
    """Persist per-OS stop statuses on the session so they survive reloads."""
    from server import mongo_db
    user_email = (payload.get("email") or "").lower()
    now = datetime.now(timezone.utc).isoformat()
    await mongo_db["tracking_sessions"].update_one(
        {"user_email": user_email, "route_id": body.route_id, "active": True},
        {"$set": {"stop_statuses": body.stop_statuses, "updated_at": now}},
    )
    return {"ok": True}


# ─── Public shareable link (Uber-like) ──────────────────────────
# Estado do mapa por roteiro (ordem, avulsas, removidas, concluídas, retorno) — vale em qualquer aparelho.
class MapState(BaseModel):
    rtb: bool = True
    order: list = []
    extras: list = []
    removed: list = []
    status: dict = {}


@router.get("/map-state/{route_id}")
async def get_map_state(route_id: str, _: dict = Depends(verify_token)):
    from server import mongo_db
    doc = await mongo_db["route_map_state"].find_one({"route_id": route_id}, {"_id": 0, "route_id": 0})
    return doc or {}


@router.put("/map-state/{route_id}")
async def put_map_state(route_id: str, body: MapState, _: dict = Depends(verify_token)):
    from server import mongo_db
    await mongo_db["route_map_state"].update_one(
        {"route_id": route_id},
        {"$set": {**body.model_dump(), "route_id": route_id, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return {"ok": True}

@router.post("/share-token")
async def create_share_token(body: ShareTokenRequest, _: dict = Depends(verify_token)):
    """Issue a short-lived signed token that grants public read-only access
    to the technician's live position for a specific OS on a specific route."""
    # Validate that the route exists and contains this OS
    route = await db.routes.find_one({"id": body.route_id}, {"_id": 0})
    if not route:
        raise HTTPException(status_code=404, detail="Roteiro não encontrado")
    orders = [o for o in (route.get("orders") or []) if o.get("os_number")]
    if body.os_number:
        target = next((o for o in orders if str(o.get("os_number")) == str(body.os_number)), None)
        if not target:
            raise HTTPException(status_code=400, detail="OS não pertence a este roteiro")
    else:
        target = next((o for o in orders if o.get("stop_status") != "completed"), None)
        if not target:
            raise HTTPException(status_code=400, detail="Todas as OSs deste roteiro já foram concluídas")
    if target.get("stop_status") == "completed":
        raise HTTPException(status_code=400, detail="Esta OS já foi concluída")
    payload = {
        "route_id": body.route_id,
        "os_number": str(target.get("os_number")),
        "iss": "mastermaq-tracking",
        "exp": datetime.now(timezone.utc) + timedelta(hours=SHARE_TOKEN_TTL_HOURS),
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return {
        "token": token,
        "expires_in_hours": SHARE_TOKEN_TTL_HOURS,
        "os_number": str(target.get("os_number")),
        "customer_name": target.get("customer_name") or "",
        "phone": target.get("phone1") or "",
    }


@router.get("/public/{token}")
async def public_tracking(token: str):
    """Resolve a share token and return technician position + OS info for the
    public tracking page. NO auth — only the token is required."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=410, detail="Link expirado")
    except Exception:
        raise HTTPException(status_code=401, detail="Token inválido")
    if payload.get("iss") != "mastermaq-tracking":
        raise HTTPException(status_code=401, detail="Token inválido")

    route_id = payload.get("route_id")
    os_number = str(payload.get("os_number"))

    route = await db.routes.find_one({"id": route_id}, {"_id": 0})
    if not route:
        raise HTTPException(status_code=404, detail="Roteiro não encontrado")

    target_order = None
    for o in (route.get("orders") or []):
        if str(o.get("os_number")) == os_number:
            target_order = o
            break
    if not target_order:
        raise HTTPException(status_code=404, detail="OS não encontrada")
    if target_order.get("stop_status") == "completed":
        raise HTTPException(status_code=410, detail="Atendimento concluído")

    from server import mongo_db
    live = await mongo_db["tracking_live"].find_one({"route_id": route_id}, {"_id": 0})

    # Privacy filter: never expose phone, exact number, email, etc. — only the
    # information the customer needs to identify himself and follow the tech.
    safe_order = {
        "os_number": target_order.get("os_number"),
        "customer_name": target_order.get("customer_name"),
        "neighborhood": target_order.get("neighborhood"),
        "city": target_order.get("city"),
        "address": target_order.get("address"),  # street only — no number
        "lat": target_order.get("lat"),
        "lng": target_order.get("lng"),
    }
    if safe_order["lat"] is None:
        from routes_module import _geocode_os
        pt, _ = await _geocode_os(target_order)
        if pt:
            safe_order["lat"], safe_order["lng"] = pt

    response = {
        "os": safe_order,
        "technician_name": route.get("technician") or "",
        "route_name": route.get("name") or "",
        "route_id": route_id,
        "map": {"maps_api_key": os.environ.get("GOOGLE_MAPS_API_KEY"), "map_id": os.environ.get("GOOGLE_MAPS_MAP_ID") or "DEMO_MAP_ID"},
        "live": None,
    }
    if live and live.get("active") is not False:
        response["live"] = {
            "lat": live.get("lat"),
            "lng": live.get("lng"),
            "heading": live.get("heading", 0),
            "speed": live.get("speed", 0),
            "active_os": live.get("active_os"),
            "active_status": live.get("active_status"),
            "updated_at": live.get("updated_at"),
            "nav_path": live.get("nav_path") or [],
            "nav_distance_meters": live.get("nav_distance_meters"),
            "nav_duration_seconds": live.get("nav_duration_seconds"),
            "nav_duration_in_traffic_seconds": live.get("nav_duration_in_traffic_seconds"),
            "nav_traffic_color": live.get("nav_traffic_color"),
        }
    return response
