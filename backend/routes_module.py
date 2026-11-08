"""
Routes module - Backend CRUD for route planning + geocode caching + Google Routes API proxy

Optimizations:
- Address-based geocode cache (geocode_cache table) to avoid redundant Google API calls
- Shared httpx client for connection reuse
"""
import asyncio
import logging
import os
import uuid
import hashlib
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel, Field
from typing import List, Optional
import httpx
import jwt

logger = logging.getLogger(__name__)

JWT_SECRET = os.environ.get('JWT_SECRET')
if not JWT_SECRET or JWT_SECRET in ('default_secret', 'change-me', ''):
    raise RuntimeError("JWT_SECRET ausente ou inseguro em backend/.env")

# Local copy of token verification to avoid circular imports with server.py.
async def verify_token(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
    if payload.get("iss") == "mastermaq-tracking":
        raise HTTPException(status_code=401, detail="Invalid token")
    import security
    return await security.check_session(payload)


router = APIRouter(prefix="/routes", tags=["routes"], dependencies=[Depends(verify_token)])


class RouteOS(BaseModel):
    os_number: str
    customer_name: Optional[str] = None
    neighborhood: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None
    number: Optional[str] = None
    phone1: Optional[str] = None
    technician: Optional[str] = None
    conclusion: Optional[str] = None
    observation: Optional[str] = None
    sequence: Optional[int] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    attendance_date: Optional[str] = None
    status: Optional[str] = None

class RouteCreate(BaseModel):
    name: Optional[str] = None
    technician: str
    date: str
    orders: List[RouteOS]
    total_distance: Optional[str] = None
    total_duration: Optional[str] = None
    status: str = "Pendente"

class RouteUpdate(BaseModel):
    name: Optional[str] = None
    technician: Optional[str] = None
    date: Optional[str] = None
    orders: Optional[List[RouteOS]] = None
    total_distance: Optional[str] = None
    total_duration: Optional[str] = None
    status: Optional[str] = None
    needs_recalculation: Optional[bool] = None


def get_db():
    from server import db
    return db


def _address_hash(address: str) -> str:
    """Create a normalized hash for an address to use as cache key"""
    # Normalize: lowercase, remove extra spaces, remove accents-ish
    normalized = " ".join(address.lower().strip().split())
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()


def _os_address(o: dict) -> str:
    """Chave única de endereço (cache e geocode): 'Rua X 123, Bairro, Cidade, UF'."""
    street = " ".join(str(o.get(k) or "").strip() for k in ("address", "number")).strip()
    parts = [street, o.get("neighborhood"), o.get("city"), o.get("state") or "MG"]
    return ", ".join(str(p).strip() for p in parts if p and str(p).strip())


def _valid_br(lat, lng) -> bool:
    """Dentro do Brasil (lat -34..6, lng -74..-28) — pega lat/lng invertidos ou zerados."""
    try:
        lat, lng = float(lat), float(lng)
    except (TypeError, ValueError):
        return False
    return -34.0 <= lat <= 6.0 and -74.5 <= lng <= -28.0


async def _get_cached_geocode(db, address: str):
    """Look up address in geocode_cache table"""
    addr_hash = _address_hash(address)
    cached = await db.geocode_cache.find_one(
        {"address_hash": addr_hash},
        {"_id": 0, "lat": 1, "lng": 1}
    )
    return cached


async def _store_geocode_cache(db, address: str, lat: float, lng: float):
    """Store geocoded address in cache for future reuse"""
    addr_hash = _address_hash(address)
    doc = {"address_hash": addr_hash, "address": address[:500], "lat": lat, "lng": lng,
           "cached_at": datetime.now(timezone.utc).isoformat()}
    if await db.geocode_cache.find_one({"address_hash": addr_hash}, {"address_hash": 1}):
        await db.geocode_cache.update_one({"address_hash": addr_hash}, {"$set": doc})
    else:
        await db.geocode_cache.insert_one({"id": str(uuid.uuid4()), **doc})


def _is_own(technician: str, payload: dict) -> bool:
    """Admin/outros perfis: sempre. Técnico: só se o roteiro é dele (nome completo ou primeiro nome)."""
    if (payload or {}).get("role") != "technician":
        return True
    name = (payload.get("name") or "").strip().lower()
    rt = (technician or "").strip().lower()
    if not name or not rt:
        return False
    first = name.split()[0]
    return rt == name or rt == first or rt.startswith(first + " ")


async def _own_route(db, route_id: str, payload: dict) -> dict:
    route = await db.routes.find_one({"id": route_id}, {"_id": 0})
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")
    if not _is_own(route.get("technician"), payload):
        raise HTTPException(status_code=403, detail="Acesso restrito a roteiros do próprio técnico")
    return route


@router.get("/")
async def list_routes(payload: dict = Depends(verify_token)):
    db = get_db()
    routes = await db.routes.find({}, {"_id": 0}).sort("created_at", -1).to_list(5000)
    # Técnico: filtra em Python com a mesma regra de dono (sem regex — nome com caractere especial quebrava).
    return [r for r in routes if _is_own(r.get("technician"), payload)]


@router.get("/{route_id}")
async def get_route_by_id(route_id: str, payload: dict = Depends(verify_token)):
    return await _own_route(get_db(), route_id, payload)


@router.post("/")
async def create_route(route_data: RouteCreate, payload: dict = Depends(verify_token)):
    db = get_db()
    if not _is_own(route_data.technician, payload):
        raise HTTPException(status_code=403, detail="Técnico só pode criar roteiro para si mesmo")
    route_dict = route_data.dict()
    route_dict["id"] = str(uuid.uuid4())
    route_dict["created_at"] = datetime.now(timezone.utc).isoformat()
    route_dict["updated_at"] = datetime.now(timezone.utc).isoformat()
    route_dict["orders"] = [o.dict() if hasattr(o, 'dict') else o for o in route_dict["orders"]]
    await db.routes.insert_one(route_dict)
    route_dict.pop("_id", None)
    # Mensagem de agendamento automática no WhatsApp para cada OS do roteiro.
    from whatsapp_module import send_route_schedule
    asyncio.create_task(send_route_schedule(db, dict(route_dict)))
    return route_dict


@router.put("/{route_id}")
async def update_route(route_id: str, route_update: RouteUpdate, payload: dict = Depends(verify_token)):
    db = get_db()
    old_route = await _own_route(db, route_id, payload)
    if route_update.technician is not None and not _is_own(route_update.technician, payload):
        raise HTTPException(status_code=403, detail="Técnico não pode passar o roteiro para outro técnico")
    if route_update.orders is not None and len(route_update.orders) == 0:
        raise HTTPException(status_code=400, detail="Lista de OSs vazia — roteiro não alterado")
    update_data = {k: v for k, v in route_update.dict().items() if v is not None}
    if "orders" in update_data:
        update_data["orders"] = [o.dict() if hasattr(o, 'dict') else o for o in update_data["orders"]]
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.routes.update_one({"id": route_id}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Route not found")
    route = await db.routes.find_one({"id": route_id}, {"_id": 0})
    if "orders" in update_data:
        # OS (re)incluída no roteiro volta a aparecer no mapa mesmo se antes foi removida lá.
        old = {str(o.get("os_number")) for o in (old_route or {}).get("orders") or []}
        added = [f"os-{o.get('os_number')}" for o in update_data["orders"] if str(o.get("os_number")) not in old]
        if added:
            from server import mongo_db
            await mongo_db["route_map_state"].update_one({"route_id": route_id}, {"$pull": {"removed": {"$in": added}}})
    # Roteiro concluído → todas as OSs dele viram "Visita Realizada".
    if update_data.get("status") == "Concluído":
        for o in route.get("orders") or []:
            if o.get("os_number"):
                await db.service_orders.update_one(
                    {"os_number": o["os_number"]},
                    {"$set": {"status": "Visita Realizada", "updated_at": update_data["updated_at"]}},
                )
    return route


@router.delete("/{route_id}")
async def delete_route(route_id: str, payload: dict = Depends(verify_token)):
    db = get_db()
    await _own_route(db, route_id, payload)
    result = await db.routes.delete_one({"id": route_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Route not found")
    return {"message": "Route deleted"}


@router.post("/{route_id}/duplicate")
async def duplicate_route(route_id: str, payload: dict = Depends(verify_token)):
    db = get_db()
    route = await _own_route(db, route_id, payload)
    route["id"] = str(uuid.uuid4())
    route["name"] = f"{route.get('name', 'Roteiro')} (Copia)"
    route["status"] = "Pendente"
    route["created_at"] = datetime.now(timezone.utc).isoformat()
    route["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.routes.insert_one(route)
    route.pop("_id", None)
    return route


@router.put("/{route_id}/conclusion/{os_number}")
async def update_os_conclusion(route_id: str, os_number: str, body: dict, payload: dict = Depends(verify_token)):
    db = get_db()
    conclusion = body.get("conclusion", "")
    observation = body.get("observation", None)
    route = await _own_route(db, route_id, payload)
    orders = route.get("orders", [])
    for order in orders:
        if order["os_number"] == os_number:
            order["conclusion"] = conclusion
            if observation is not None:
                order["observation"] = observation
            break
    await db.routes.update_one({"id": route_id}, {"$set": {"orders": orders, "updated_at": datetime.now(timezone.utc).isoformat()}})
    if conclusion:
        await db.service_orders.update_one(
            {"os_number": os_number},
            {"$set": {"technical_diagnosis": conclusion, "updated_at": datetime.now(timezone.utc).isoformat()}}
        )
    return {"message": "Updated"}


# === GEOCODE CACHE ENDPOINTS ===
class GeocodeRequest(BaseModel):
    os_numbers: List[str]

class CacheCoordsItem(BaseModel):
    os_number: str
    lat: float
    lng: float
    precision: Optional[str] = None

class CacheCoordsRequest(BaseModel):
    coords: List[CacheCoordsItem]


_geo_fail: dict = {}  # endereço -> motivo (não repete chamada paga que já falhou)


def _norm(s) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", str(s or "").lower()) if unicodedata.category(c) != "Mn").strip()


async def _geocode_os(o: dict):
    """Geocodifica o endereço completo. Só aceita ponto exato (número da casa) na cidade certa.
    Retorna ((lat, lng), 'exact') ou (None, 'approximate'|'not_found'|'incomplete')."""
    key = os.environ.get('GOOGLE_MAPS_API_KEY', '')
    if not key or not o.get("address") or not o.get("city"):
        return None, "incomplete"
    addr = _os_address(o)
    if addr in _geo_fail:
        return None, _geo_fail[addr]
    cached = await _get_cached_geocode(get_db(), addr)
    if cached and _valid_br(cached.get("lat"), cached.get("lng")):
        return (float(cached["lat"]), float(cached["lng"])), "exact"
    query = ", ".join(p for p in [addr, o.get("cep")] if p)
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get("https://maps.googleapis.com/maps/api/geocode/json",
                            params={"address": query, "components": "country:BR", "region": "br", "key": key})
        res = (r.json().get("results") or [None])[0]
    except Exception as e:
        logger.warning(f"geocode {o.get('os_number')}: {e!r}")
        return None, "not_found"
    if not res:
        _geo_fail[addr] = "not_found"
        return None, "not_found"
    comps = res.get("address_components") or []
    types = {t for c in comps for t in c.get("types", [])}
    cities = {_norm(c.get("long_name")) for c in comps if {"administrative_area_level_2", "locality"} & set(c.get("types", []))}
    exact = (res.get("geometry", {}).get("location_type") in ("ROOFTOP", "RANGE_INTERPOLATED")
             and "street_number" in types and _norm(str(o.get("city") or "").split("/")[0]) in cities
             and _valid_br(res["geometry"]["location"]["lat"], res["geometry"]["location"]["lng"]))
    if not exact:
        _geo_fail[addr] = "approximate"
        return None, "approximate"
    loc = res["geometry"]["location"]
    await _store_geocode_cache(get_db(), addr, loc["lat"], loc["lng"])
    return (loc["lat"], loc["lng"]), "exact"


@router.post("/geocode")
async def get_cached_coords(req: GeocodeRequest):
    """
    Return cached lat/lng for the given OS numbers.
    Checks: 1) OS record lat/lng, 2) address-based geocode_cache.
    Frontend only geocodes truly uncached addresses client-side.
    """
    db = get_db()
    orders = await db.service_orders.find(
        {"os_number": {"$in": req.os_numbers}},
        {"_id": 0, "os_number": 1, "lat": 1, "lng": 1, "address": 1, "number": 1, "neighborhood": 1, "city": 1, "state": 1, "cep": 1}
    ).to_list(len(req.os_numbers))

    sem = asyncio.Semaphore(5)
    results = []
    missing = []
    for o in orders:
        has_coords = _valid_br(o.get("lat"), o.get("lng"))
        precision = "cached" if has_coords else None

        # If OS doesn't have coords, try the address-based cache
        if not has_coords:
            cached = await _get_cached_geocode(db, _os_address(o))
            if cached and _valid_br(cached.get("lat"), cached.get("lng")):
                # Found in address cache! Update the OS record too
                o["lat"] = cached["lat"]
                o["lng"] = cached["lng"]
                has_coords = True
                # Save back to OS for next time
                await db.service_orders.update_one(
                    {"os_number": o["os_number"]},
                    {"$set": {"lat": cached["lat"], "lng": cached["lng"]}}
                )
                precision = "cached"

        item = {"os_number": o["os_number"], "lat": o.get("lat"), "lng": o.get("lng"), "cached": has_coords, "precision": precision}
        results.append(item)
        if not has_coords:
            missing.append((o, item))

    # Tenta localizar de novo quem não tem coordenada (máx. 30 por chamada).
    async def _retry(o, item):
        async with sem:
            coords, item["precision"] = await _geocode_os(o)
        if coords:
            item.update(lat=coords[0], lng=coords[1], cached=True)
            await db.service_orders.update_one({"os_number": o["os_number"]}, {"$set": {"lat": coords[0], "lng": coords[1]}})
    await asyncio.gather(*[_retry(o, it) for o, it in missing[:30]])

    found_nums = {o["os_number"] for o in orders}
    for os_num in req.os_numbers:
        if os_num not in found_nums:
            results.append({"os_number": os_num, "lat": None, "lng": None, "cached": False, "precision": "not_found"})

    cached_count = sum(1 for r in results if r["cached"])
    return {"results": results, "total": len(results), "cached": cached_count, "uncached": len(results) - cached_count}


@router.post("/cache-coords")
async def cache_coords(req: CacheCoordsRequest):
    """
    Cache geocoded coordinates in the service_orders collection AND in geocode_cache.
    Called by the frontend after client-side geocoding.
    """
    db = get_db()
    updated = 0
    for item in req.coords:
        # Só grava ponto validado (exato e dentro do Brasil).
        if item.precision != "exact" or not _valid_br(item.lat, item.lng):
            continue
        result = await db.service_orders.update_one(
            {"os_number": item.os_number},
            {"$set": {"lat": item.lat, "lng": item.lng}}
        )
        if result.modified_count > 0:
            updated += 1

        # Also store in address-based cache for future OS with same address
        os_data = await db.service_orders.find_one(
            {"os_number": item.os_number},
            {"_id": 0, "address": 1, "number": 1, "neighborhood": 1, "city": 1, "state": 1}
        )
        if os_data:
            await _store_geocode_cache(db, _os_address(os_data), item.lat, item.lng)

    return {"updated": updated, "total": len(req.coords)}



# === GOOGLE ROUTES API PROXY ===

class Waypoint(BaseModel):
    address: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None

class ComputeRouteRequest(BaseModel):
    origin: Waypoint
    destination: Optional[Waypoint] = None
    intermediates: List[Waypoint] = []
    optimize_waypoint_order: bool = False
    round_trip: bool = False


def _build_waypoint(wp: Waypoint):
    if wp.lat is not None and wp.lng is not None:
        return {"location": {"latLng": {"latitude": wp.lat, "longitude": wp.lng}}}
    return {"address": wp.address}


@router.post("/compute-route")
async def compute_route(req: ComputeRouteRequest):
    """
    Proxy to Google Routes API (computeRoutes) to avoid frontend API key referrer issues.
    Returns polyline, legs, distances, durations, and optimized waypoint order.
    """
    api_key = os.environ.get('GOOGLE_MAPS_API_KEY', '')
    if not api_key:
        raise HTTPException(status_code=500, detail="GOOGLE_MAPS_API_KEY not configured")

    inter = list(req.intermediates)
    for wp in [req.origin, req.destination, *inter]:
        if wp is None:
            continue
        if (wp.lat is None) != (wp.lng is None) or (wp.lat is not None and not _valid_br(wp.lat, wp.lng)):
            raise HTTPException(status_code=400, detail=f"Coordenada inválida: {wp.lat},{wp.lng}")
        if wp.lat is None and not (wp.address or "").strip():
            raise HTTPException(status_code=400, detail="Parada sem coordenada e sem endereço")
    dest = req.destination
    same = dest is not None and dest.lat is not None and dest.lat == req.origin.lat and dest.lng == req.origin.lng
    # Sem round_trip não assume ida e volta: a última parada vira o destino.
    if not req.round_trip and (dest is None or same) and inter:
        dest = inter.pop()
    if dest is None:
        raise HTTPException(status_code=400, detail="Informe o destino ou ao menos uma parada")

    body = {
        "origin": _build_waypoint(req.origin),
        "destination": _build_waypoint(dest),
        "intermediates": [_build_waypoint(wp) for wp in inter],
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE",
        "optimizeWaypointOrder": req.optimize_waypoint_order and len(inter) > 1,
        "languageCode": "pt-BR",
        "units": "METRIC",
    }

    field_mask = ",".join([
        "routes.duration",
        "routes.distanceMeters",
        "routes.polyline.encodedPolyline",
        "routes.legs.distanceMeters",
        "routes.legs.duration",
        "routes.legs.polyline.encodedPolyline",
        "routes.legs.startLocation",
        "routes.legs.endLocation",
        "routes.legs.steps.distanceMeters",
        "routes.legs.steps.staticDuration",
        "routes.legs.steps.polyline.encodedPolyline",
        "routes.legs.steps.startLocation",
        "routes.legs.steps.endLocation",
        "routes.legs.steps.navigationInstruction",
        "routes.optimizedIntermediateWaypointIndex",
    ])

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": field_mask,
    }
    
    try:
        async with httpx.AsyncClient() as http_client:
            response = await http_client.post(
                "https://routes.googleapis.com/directions/v2:computeRoutes",
                json=body,
                headers=headers,
                timeout=30.0,
            )

        if response.status_code != 200:
            logger.error(f"Routes API error {response.status_code}: {response.text}")
            raise HTTPException(status_code=response.status_code, detail=response.text)

        data = response.json()
        if not data.get("routes"):
            raise HTTPException(status_code=400, detail="No routes found for the given waypoints")

        return data

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Google Routes API timeout")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Routes API unexpected error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# === NAV-LEG (live navigation, per-segment traffic) ===

class NavLegRequest(BaseModel):
    origin_lat: float
    origin_lng: float
    dest_lat: float
    dest_lng: float
    origin_heading: Optional[int] = None  # 0-360, sentido do veículo


@router.post("/nav-leg")
async def nav_leg(req: NavLegRequest):
    """
    Single origin→destination route used by the live-navigation map.
    Returns the encoded polyline plus `speedReadingIntervals` so the
    frontend can color each road segment by traffic level (NORMAL,
    SLOW, TRAFFIC_JAM). This mirrors Google Maps' UX where only the
    congested portion is colored, not the entire route.
    """
    api_key = os.environ.get('GOOGLE_MAPS_API_KEY', '')
    if not api_key:
        raise HTTPException(status_code=500, detail="GOOGLE_MAPS_API_KEY not configured")

    origin = {"location": {"latLng": {"latitude": req.origin_lat, "longitude": req.origin_lng}}}
    if req.origin_heading is not None:
        origin["location"]["heading"] = req.origin_heading % 360
    body = {
        "origin": origin,
        "destination": {"location": {"latLng": {"latitude": req.dest_lat, "longitude": req.dest_lng}}},
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE_OPTIMAL",
        "extraComputations": ["TRAFFIC_ON_POLYLINE"],
        "polylineQuality": "HIGH_QUALITY",
        "languageCode": "pt-BR",
        "units": "METRIC",
    }
    field_mask = ",".join([
        "routes.duration",
        "routes.staticDuration",
        "routes.distanceMeters",
        "routes.polyline.encodedPolyline",
        "routes.travelAdvisory.speedReadingIntervals",
        "routes.legs.distanceMeters",
        "routes.legs.duration",
        "routes.legs.staticDuration",
    ])
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": field_mask,
    }
    try:
        async with httpx.AsyncClient() as http_client:
            response = await http_client.post(
                "https://routes.googleapis.com/directions/v2:computeRoutes",
                json=body, headers=headers, timeout=15.0,
            )
        if response.status_code != 200:
            logger.error(f"Nav-leg Routes API error {response.status_code}: {response.text}")
            raise HTTPException(status_code=response.status_code, detail=response.text)
        data = response.json()
        if not data.get("routes"):
            raise HTTPException(status_code=400, detail="No nav route found")
        route0 = data["routes"][0]
        return {
            "encoded_polyline": (route0.get("polyline") or {}).get("encodedPolyline", ""),
            "distance_meters": route0.get("distanceMeters", 0),
            "duration_seconds": int(str(route0.get("duration", "0s")).rstrip("s") or 0),
            # TRAFFIC_AWARE_OPTIMAL: `duration` já considera o trânsito.
            "duration_in_traffic_seconds": int(str(route0.get("duration", "0s")).rstrip("s") or 0),
            "static_duration_seconds": int(str(route0.get("staticDuration", "0s")).rstrip("s") or 0),
            "speed_reading_intervals": (route0.get("travelAdvisory") or {}).get("speedReadingIntervals", []),
        }
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Routes API timeout")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Nav-leg unexpected error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─── LLM-powered route suggestion analysis ─────────────────────────────
# Uses the Emergent LLM Key (OpenAI) to enrich the client-side proximity
# groupings with a human-friendly rationale. NEVER exposes the LLM key to
# the frontend — the frontend just sends the pre-computed groups.

class RouteAnalyzeOS(BaseModel):
    os_number: str
    customer_name: Optional[str] = None
    city: Optional[str] = None
    neighborhood: Optional[str] = None
    service_type: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[bool] = False
    days_open: Optional[int] = None
    lat: Optional[float] = None
    lng: Optional[float] = None


class RouteAnalyzeGroup(BaseModel):
    name: str
    orders: List[RouteAnalyzeOS]
    avg_dist_km: Optional[float] = None


class RouteAnalyzeRequest(BaseModel):
    groups: List[RouteAnalyzeGroup]
    base_lat: Optional[float] = -19.8881334
    base_lng: Optional[float] = -43.9420748


@router.post("/analyze-suggestions")
async def analyze_route_suggestions(body: RouteAnalyzeRequest):
    """Analisa as sugestões de rota pré-computadas e retorna um resumo/
    rationale para cada grupo, considerando: Região, Proximidade da Base,
    Tempo em aberto (>10 dias) e Prioridade. Usa OpenAI via Emergent LLM Key.

    Retorno: { groups: [ { name, rationale, priority_score, tags, top_reason } ] }
    Se a LLM falhar, retorna um fallback determinístico (sem quebrar a UX).
    """
    import json as _json
    emergent_key = os.environ.get("EMERGENT_LLM_KEY")

    # Fallback determinístico caso a LLM falhe / não haja chave.
    def _deterministic_fallback():
        out = []
        for g in body.groups:
            os_list = g.orders or []
            urgentes = [o for o in os_list if (o.days_open or 0) > 10]
            prioritarias = [o for o in os_list if o.priority]
            cities = {}
            for o in os_list:
                c = (o.city or "").strip() or "?"
                cities[c] = cities.get(c, 0) + 1
            top_city = max(cities.items(), key=lambda x: x[1])[0] if cities else "-"
            tags = []
            if g.avg_dist_km is not None and g.avg_dist_km < 8:
                tags.append("perto-da-base")
            if len(urgentes) >= max(1, len(os_list) // 3):
                tags.append("atraso-alto")
            if prioritarias:
                tags.append("prioridade")
            score = (
                (0 if g.avg_dist_km is None else max(0, 40 - min(g.avg_dist_km, 40))) * 0.4
                + min(len(urgentes) * 5, 30) * 0.4
                + min(len(prioritarias) * 8, 30) * 0.2
            )
            rationale = (
                f"{len(os_list)} OSs concentradas em {top_city}. "
                f"{len(urgentes)} OS em atraso (>10 dias), {len(prioritarias)} marcada(s) como prioridade. "
                f"Distância média até a base: {g.avg_dist_km:.1f} km."
                if g.avg_dist_km is not None
                else f"{len(os_list)} OSs em {top_city}. {len(urgentes)} em atraso (>10 dias)."
            )
            out.append({
                "name": g.name,
                "rationale": rationale,
                "priority_score": round(score, 1),
                "tags": tags,
                "top_reason": tags[0] if tags else "distribuicao-equilibrada",
            })
        # Ordena por score desc
        out.sort(key=lambda x: -x["priority_score"])
        return {"groups": out, "source": "fallback"}

    if not emergent_key:
        logger.warning("EMERGENT_LLM_KEY ausente — usando fallback determinístico")
        return _deterministic_fallback()

    # Compact payload — evita estourar tokens quando houver muitas OSs.
    compact_groups = []
    for g in body.groups:
        compact_groups.append({
            "name": g.name,
            "avg_dist_km": round(g.avg_dist_km, 2) if g.avg_dist_km is not None else None,
            "os_count": len(g.orders or []),
            "os": [
                {
                    "n": o.os_number,
                    "cli": (o.customer_name or "")[:40],
                    "city": o.city or "",
                    "bairro": o.neighborhood or "",
                    "tipo": o.service_type or "",
                    "prio": bool(o.priority),
                    "dias_aberto": o.days_open or 0,
                }
                for o in (g.orders or [])[:25]  # cap por grupo
            ],
        })

    system_msg = (
        "Você é um planejador de rotas para técnicos de campo em Belo Horizonte/MG. "
        "Analise cada grupo de OSs (Ordens de Serviço) e devolva um JSON válido com a chave "
        "'groups', uma lista onde cada item contém: "
        "'name' (mantenha o nome enviado), "
        "'rationale' (1-2 frases em pt-BR explicando POR QUE atender esse grupo primeiro), "
        "'priority_score' (0-100, quanto maior mais urgente), "
        "'tags' (lista curta de strings: 'perto-da-base', 'atraso-alto', 'prioridade', 'regiao-densa', 'alternativa'), "
        "'top_reason' (um único motivo principal). "
        "Considere: 1) Região/proximidade (avg_dist_km), 2) Tempo em aberto (dias_aberto > 10 = urgente), "
        "3) Prioridade (prio=true = crítico), 4) Concentração geográfica (mesma cidade/bairro). "
        "Retorne APENAS o JSON, sem markdown."
    )
    user_text = _json.dumps({"base": {"lat": body.base_lat, "lng": body.base_lng}, "groups": compact_groups}, ensure_ascii=False)

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(
            api_key=emergent_key,
            session_id=f"route-analyze-{uuid.uuid4()}",
            system_message=system_msg,
        ).with_model("openai", "gpt-5.4-mini")
        response = await chat.send_message(UserMessage(text=user_text))
        text = (response or "").strip()
        # Remove possíveis code fences
        if text.startswith("```"):
            text = text.strip("`")
            # remove leading "json\n"
            if text.lower().startswith("json"):
                text = text[4:].lstrip()
        parsed = _json.loads(text)
        groups_out = parsed.get("groups") or []
        if not isinstance(groups_out, list) or not groups_out:
            raise ValueError("LLM retornou payload inesperado")
        # Ordena por score desc
        try:
            groups_out.sort(key=lambda x: -(x.get("priority_score") or 0))
        except Exception:
            pass
        return {"groups": groups_out, "source": "llm"}
    except Exception as e:
        logger.warning(f"[analyze-suggestions] LLM falhou, usando fallback: {e}")
        return _deterministic_fallback()
