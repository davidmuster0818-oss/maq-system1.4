import os
import logging
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import time
from collections import defaultdict, deque
from datetime import datetime, timezone

from tracking_module import verify_token

# RotaFlow (mapa do roteiro) — porte do projeto Mapaflow. Caches no Mongo; auth do sistema.
router = APIRouter(prefix="/rf")


class _DB:
    def __getattr__(self, name):
        from server import mongo_db
        return mongo_db[f"rf_{name}"]


db = _DB()
_hits: dict = defaultdict(deque)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def rate_limit(key: str, limit: int, window: int):
    q, t = _hits[key], time.time()
    while q and q[0] < t - window:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(status_code=429, detail="Muitas requisições. Aguarde alguns segundos.")
    q.append(t)


async def get_current_user(payload: dict = Depends(verify_token)) -> dict:
    return {**payload, "id": payload.get("email") or payload.get("sub") or "user"}


BASE = {"lat": -19.8881334, "lng": -43.9420748, "address": "Rua Descalvado, 636 - Renascença, Belo Horizonte - MG"}
logger = logging.getLogger("maps")

ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
PLACES_URL = "https://places.googleapis.com/v1"
TIMEOUT = httpx.Timeout(12.0, connect=5.0)

ROUTE_FIELDS = ",".join([
    "routes.distanceMeters", "routes.duration", "routes.staticDuration", "routes.polyline.encodedPolyline",
    "routes.description", "routes.routeLabels", "routes.warnings", "routes.optimizedIntermediateWaypointIndex",
    "routes.travelAdvisory", "routes.legs.distanceMeters", "routes.legs.duration", "routes.legs.staticDuration",
    "routes.legs.polyline.encodedPolyline", "routes.legs.startLocation", "routes.legs.endLocation",
    "routes.legs.travelAdvisory", "routes.legs.steps.distanceMeters", "routes.legs.steps.staticDuration",
    "routes.legs.steps.polyline.encodedPolyline", "routes.legs.steps.navigationInstruction",
    "routes.legs.steps.startLocation", "routes.legs.steps.endLocation",
])


class LatLng(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class GeocodeIn(BaseModel):
    address: str = Field(min_length=3, max_length=300)


class AutocompleteIn(BaseModel):
    input: str = Field(min_length=2, max_length=200)
    session_token: Optional[str] = Field(default=None, max_length=100)


class ComputeRouteIn(BaseModel):
    origin: LatLng
    destination: LatLng
    intermediates: List[LatLng] = Field(default_factory=list, max_length=25)
    optimize: bool = False
    alternatives: bool = True
    avoid_tolls: bool = False
    avoid_highways: bool = False


class NavLegIn(BaseModel):
    origin: LatLng
    heading: Optional[float] = Field(default=None, ge=0, le=360)
    destination: LatLng


def _key() -> str:
    key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not key:
        raise HTTPException(status_code=503, detail="Chave do Google Maps não configurada no servidor")
    return key


async def _google(method: str, url: str, *, params=None, json=None, field_mask=None) -> dict:
    headers = {"X-Goog-Api-Key": _key()}
    if field_mask:
        headers["X-Goog-FieldMask"] = field_mask
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as http:
            r = await http.request(method, url, params=params, json=json, headers=headers)
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="O serviço de mapas demorou para responder. Tente novamente.")
    except httpx.HTTPError as e:
        logger.warning("Google request error: %s", e)
        raise HTTPException(status_code=502, detail="Falha de conexão com o serviço de mapas")
    data = r.json() if r.content else {}
    if r.status_code >= 400:
        msg = (data.get("error") or {}).get("message", r.text[:200])
        logger.warning("Google API %s -> %s: %s", url, r.status_code, msg)
        raise HTTPException(status_code=502, detail=f"Google Maps: {msg}")
    return data


def _ll(loc: Optional[dict]) -> Optional[dict]:
    if not loc:
        return None
    ll = loc.get("latLng", loc)
    return {"lat": ll.get("latitude", 0.0), "lng": ll.get("longitude", 0.0)}


def _secs(v) -> int:
    return int(float(str(v).rstrip("s"))) if v else 0


def _traffic(adv: Optional[dict]) -> list:
    return [{"start": i.get("startPolylinePointIndex", 0), "end": i.get("endPolylinePointIndex", 0),
             "speed": i.get("speed", "NORMAL")} for i in (adv or {}).get("speedReadingIntervals", [])]


def _tolls(adv: Optional[dict]) -> dict:
    info = (adv or {}).get("tollInfo")
    if info is None:
        return {"has_tolls": False, "prices": []}
    prices = [{"currency": p.get("currencyCode", "BRL"), "amount": int(p.get("units", 0)) + p.get("nanos", 0) / 1e9}
              for p in info.get("estimatedPrice", [])]
    return {"has_tolls": True, "prices": prices}


def _normalize(route: dict, index: int) -> dict:
    legs = []
    for leg in route.get("legs", []):
        steps = [{
            "distance_m": s.get("distanceMeters", 0),
            "duration_s": _secs(s.get("staticDuration")),
            "polyline": (s.get("polyline") or {}).get("encodedPolyline", ""),
            "maneuver": (s.get("navigationInstruction") or {}).get("maneuver", "STRAIGHT"),
            "instruction": (s.get("navigationInstruction") or {}).get("instructions", "Siga em frente"),
            "start": _ll(s.get("startLocation")), "end": _ll(s.get("endLocation")),
        } for s in leg.get("steps", [])]
        legs.append({
            "distance_m": leg.get("distanceMeters", 0), "duration_s": _secs(leg.get("duration")),
            "static_duration_s": _secs(leg.get("staticDuration")),
            "polyline": (leg.get("polyline") or {}).get("encodedPolyline", ""),
            "start": _ll(leg.get("startLocation")), "end": _ll(leg.get("endLocation")),
            "traffic": _traffic(leg.get("travelAdvisory")), "tolls": _tolls(leg.get("travelAdvisory")),
            "steps": steps,
        })
    return {
        "index": index, "labels": route.get("routeLabels", []), "description": route.get("description", ""),
        "distance_m": route.get("distanceMeters", 0), "duration_s": _secs(route.get("duration")),
        "static_duration_s": _secs(route.get("staticDuration")),
        "polyline": (route.get("polyline") or {}).get("encodedPolyline", ""),
        "warnings": route.get("warnings", []),
        "optimized_order": route.get("optimizedIntermediateWaypointIndex"),
        "traffic": _traffic(route.get("travelAdvisory")), "tolls": _tolls(route.get("travelAdvisory")),
        "legs": legs,
    }


def _wp(p: LatLng, heading: Optional[float] = None) -> dict:
    loc = {"latLng": {"latitude": p.lat, "longitude": p.lng}}
    if heading is not None:
        loc["heading"] = int(heading) % 360
    return {"location": loc}


async def _compute(origin, destination, intermediates, *, optimize=False, alternatives=False,
                   avoid_tolls=False, avoid_highways=False, heading=None) -> list:
    body = {
        "origin": _wp(origin, heading), "destination": _wp(destination),
        "intermediates": [_wp(i) for i in intermediates],
        "travelMode": "DRIVE", "routingPreference": "TRAFFIC_AWARE",
        "computeAlternativeRoutes": bool(alternatives and not intermediates),
        "optimizeWaypointOrder": bool(optimize and len(intermediates) > 1),
        "routeModifiers": {"avoidTolls": avoid_tolls, "avoidHighways": avoid_highways},
        "extraComputations": ["TRAFFIC_ON_POLYLINE", "TOLLS"],
        "polylineQuality": "HIGH_QUALITY",
        "languageCode": "pt-BR", "regionCode": "BR", "units": "METRIC",
    }
    data = await _google("POST", ROUTES_URL, json=body, field_mask=ROUTE_FIELDS)
    routes = data.get("routes") or []
    if not routes:
        raise HTTPException(status_code=422, detail="Nenhuma rota encontrada entre os pontos informados")
    return [_normalize(r, i) for i, r in enumerate(routes)]


async def _geocode(address: str) -> dict:
    norm = " ".join(address.lower().split())
    cached = await db.geocode_cache.find_one({"query": norm}, {"_id": 0})
    if cached:
        return cached["result"]
    params = {"address": address, "key": _key(), "language": "pt-BR", "region": "br"}
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as http:
            r = await http.get(GEOCODE_URL, params=params)
        data = r.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Geocodificação demorou para responder")
    except (httpx.HTTPError, ValueError):
        raise HTTPException(status_code=502, detail="Falha de conexão com o serviço de geocodificação")
    status = data.get("status")
    if status == "ZERO_RESULTS":
        raise HTTPException(status_code=404, detail="Endereço não encontrado")
    if status != "OK":
        raise HTTPException(status_code=502, detail=f"Google Geocoding: {data.get('error_message') or status}")
    top = data["results"][0]
    loc = top["geometry"]["location"]
    result = {"address": top["formatted_address"], "lat": loc["lat"], "lng": loc["lng"], "place_id": top.get("place_id")}
    await db.geocode_cache.update_one({"query": norm}, {"$set": {"query": norm, "result": result, "cached_at": now_iso()}}, upsert=True)
    return result


async def get_base() -> dict:
    return dict(BASE)


@router.get("/config")
async def config(user: dict = Depends(get_current_user)):
    base, base_error = None, None
    try:
        base = await get_base()
        base["name"] = "Base operacional"
    except HTTPException as e:
        base_error = e.detail
    return {"maps_api_key": os.environ.get("GOOGLE_MAPS_API_KEY"), "map_id": os.environ.get("GOOGLE_MAPS_MAP_ID") or "DEMO_MAP_ID",
            "base": base, "base_error": base_error}


@router.post("/routes/geocode")
async def geocode(body: GeocodeIn, user: dict = Depends(get_current_user)):
    rate_limit(f"geo:{user['id']}", 30, 60)
    return await _geocode(body.address)


@router.post("/routes/autocomplete")
async def autocomplete(body: AutocompleteIn, user: dict = Depends(get_current_user)):
    rate_limit(f"ac:{user['id']}", 90, 60)
    base = await get_base()
    payload = {"input": body.input, "languageCode": "pt-BR", "includedRegionCodes": ["br"],
               "locationBias": {"circle": {"center": {"latitude": base["lat"], "longitude": base["lng"]}, "radius": 50000.0}}}
    if body.session_token:
        payload["sessionToken"] = body.session_token
    try:
        data = await _google("POST", f"{PLACES_URL}/places:autocomplete", json=payload)
    except HTTPException as e:
        if e.status_code != 502:
            raise
        return await _geocode_suggestions(body.input, base)
    out = []
    for s in data.get("suggestions", []):
        p = s.get("placePrediction")
        if not p:
            continue
        fmt = p.get("structuredFormat") or {}
        out.append({"place_id": p.get("placeId"), "main": (fmt.get("mainText") or {}).get("text") or (p.get("text") or {}).get("text", ""),
                    "secondary": (fmt.get("secondaryText") or {}).get("text", "")})
    return out


async def _geocode_suggestions(text: str, base: dict) -> list:
    d = 0.35
    params = {"address": text, "key": _key(), "language": "pt-BR", "region": "br",
              "bounds": f"{base['lat'] - d},{base['lng'] - d}|{base['lat'] + d},{base['lng'] + d}"}
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as http:
            data = (await http.get(GEOCODE_URL, params=params)).json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(status_code=502, detail="Falha de conexão com o serviço de geocodificação")
    if data.get("status") not in ("OK", "ZERO_RESULTS"):
        raise HTTPException(status_code=502, detail=f"Google Geocoding: {data.get('error_message') or data.get('status')}")
    out = []
    for r in data.get("results", [])[:5]:
        parts = r["formatted_address"].split(" - ", 1)
        loc = r["geometry"]["location"]
        out.append({"place_id": r.get("place_id"), "main": parts[0], "secondary": parts[1] if len(parts) > 1 else "",
                    "address": r["formatted_address"], "lat": loc["lat"], "lng": loc["lng"]})
    return out


@router.get("/routes/place/{place_id}")
async def place_details(place_id: str, session_token: Optional[str] = None, user: dict = Depends(get_current_user)):
    rate_limit(f"pl:{user['id']}", 40, 60)
    cached = await db.place_cache.find_one({"place_id": place_id}, {"_id": 0})
    if cached:
        return cached["result"]
    params = {"languageCode": "pt-BR"}
    if session_token:
        params["sessionToken"] = session_token
    data = await _google("GET", f"{PLACES_URL}/places/{place_id}", params=params,
                         field_mask="id,displayName,formattedAddress,location")
    loc = data.get("location")
    if not loc or "latitude" not in loc:
        raise HTTPException(status_code=422, detail="Local sem coordenadas válidas")
    result = {"place_id": data.get("id", place_id), "label": (data.get("displayName") or {}).get("text", ""),
              "address": data.get("formattedAddress", ""), "lat": loc["latitude"], "lng": loc["longitude"]}
    await db.place_cache.update_one({"place_id": place_id}, {"$set": {"place_id": place_id, "result": result, "cached_at": now_iso()}}, upsert=True)
    return result


@router.post("/routes/compute-route")
async def compute_route(body: ComputeRouteIn, user: dict = Depends(get_current_user)):
    rate_limit(f"rt:{user['id']}", 20, 60)
    routes = await _compute(body.origin, body.destination, body.intermediates, optimize=body.optimize,
                            alternatives=body.alternatives, avoid_tolls=body.avoid_tolls, avoid_highways=body.avoid_highways)
    return {"routes": routes}


@router.post("/routes/nav-leg")
async def nav_leg(body: NavLegIn, user: dict = Depends(get_current_user)):
    rate_limit(f"nav:{user['id']}", 40, 60)
    routes = await _compute(body.origin, body.destination, [], heading=body.heading)
    return {"route": routes[0]}


# Fundo da janela flutuante (PiP): imagem do mapa via Maps Static API, servida pela mesma origem.
@router.get("/static-map")
async def static_map(lat: float, lng: float, zoom: int = 16, user: dict = Depends(get_current_user)):
    from fastapi.responses import Response
    rate_limit(f"sm:{user['id']}", 30, 60)
    params = {"center": f"{lat:.5f},{lng:.5f}", "zoom": max(12, min(zoom, 18)), "size": "640x640", "scale": 1,
              "key": os.environ.get("GOOGLE_MAPS_API_KEY")}
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get("https://maps.googleapis.com/maps/api/staticmap", params=params)
    if r.status_code != 200 or not r.headers.get("content-type", "").startswith("image/"):
        raise HTTPException(status_code=503, detail="Mapa estático indisponível (ative a Maps Static API na chave do Google).")
    return Response(content=r.content, media_type=r.headers["content-type"], headers={"Cache-Control": "private, max-age=600"})




# ─── OSs do sistema como paradas ───
OS_PROJ = {"_id": 0, "os_number": 1, "customer_name": 1, "address": 1, "number": 1, "neighborhood": 1, "city": 1,
           "state": 1, "lat": 1, "lng": 1, "phone1": 1, "status": 1}


async def _os_stop(o: dict) -> dict:
    """Coordenada da OS: salva/validada > geocode exato > aproximado (marcado)."""
    from routes_module import _valid_br, _geocode_os, _os_address
    from server import db as sysdb
    o = {k: v for k, v in o.items() if k != "_id"}
    if _valid_br(o.get("lat"), o.get("lng")):
        return {**o, "lat": float(o["lat"]), "lng": float(o["lng"]), "precision": "exact"}
    coords, prec = await _geocode_os(o)
    if coords:
        await sysdb.service_orders.update_one({"os_number": o["os_number"]}, {"$set": {"lat": coords[0], "lng": coords[1]}})
        return {**o, "lat": coords[0], "lng": coords[1], "precision": "exact"}
    addr = _os_address(o)
    try:
        g = await _geocode(addr) if addr else None
    except HTTPException:
        g = None
    if g and _valid_br(g.get("lat"), g.get("lng")):
        return {**o, "lat": g["lat"], "lng": g["lng"], "precision": "approximate"}
    return {**o, "lat": None, "lng": None, "precision": prec or "not_found"}


class OSStopsIn(BaseModel):
    os_numbers: List[str] = Field(default_factory=list, max_length=40)


@router.post("/os-stops")
async def os_stops(body: OSStopsIn, user: dict = Depends(get_current_user)):
    from server import db as sysdb
    out = []
    for n in body.os_numbers:
        o = await sysdb.service_orders.find_one({"os_number": str(n)}, OS_PROJ)
        out.append(await _os_stop(o) if o else {"os_number": str(n), "lat": None, "lng": None, "precision": "not_found"})
    return out


@router.get("/os-search")
async def os_search(q: str, user: dict = Depends(get_current_user)):
    import unicodedata
    from server import db as sysdb
    norm = lambda s: "".join(c for c in unicodedata.normalize("NFD", str(s or "").lower()) if unicodedata.category(c) != "Mn")  # noqa: E731
    q = q.strip()
    if len(q) < 2:
        return []
    docs = await sysdb.service_orders.find({}, OS_PROJ).sort("created_at", -1).to_list(3000)
    nq = norm(q)
    hits = [d for d in docs if str(d.get("os_number", "")).startswith(q)
            or nq in norm(d.get("customer_name")) or nq in norm(d.get("neighborhood")) or nq in norm(d.get("address"))]
    return hits[:8]


@router.post("/os-stop")
async def os_stop_one(body: OSStopsIn, user: dict = Depends(get_current_user)):
    return (await os_stops(body, user))[:1]
