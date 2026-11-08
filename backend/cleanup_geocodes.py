"""Limpa coordenadas gravadas sem validação para que sejam geocodificadas de novo (só ponto exato).

Mantém: entradas do geocode_cache gravadas pelo geocode validado (cached_at >= KEEP_SINCE) e as OSs
cujo lat/lng bate com uma dessas entradas pelo mesmo endereço padronizado (_os_address).
Faz backup em backend/backups/ antes de apagar.

    python cleanup_geocodes.py           # só mostra o que faria
    python cleanup_geocodes.py --apply   # aplica
"""
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
from supabase_db import db  # noqa: E402
from routes_module import _address_hash, _os_address, _valid_br  # noqa: E402

KEEP_SINCE = "2026-10-27T20:05"


async def main(apply: bool):
    cache = await db.geocode_cache.find({}, {"_id": 0}).to_list(100000)
    keep = {c["address_hash"]: c for c in cache if (c.get("cached_at") or "") >= KEEP_SINCE and _valid_br(c.get("lat"), c.get("lng"))}
    drop_cache = [c for c in cache if c["address_hash"] not in keep]
    orders = await db.service_orders.find({}, {"_id": 0, "os_number": 1, "lat": 1, "lng": 1, "address": 1, "number": 1,
                                               "neighborhood": 1, "city": 1, "state": 1}).to_list(100000)
    drop_os = []
    for o in orders:
        if o.get("lat") in (None, "") and o.get("lng") in (None, ""):
            continue
        k = keep.get(_address_hash(_os_address(o)))
        ok = k and abs(float(k["lat"]) - float(o["lat"])) < 1e-5 and abs(float(k["lng"]) - float(o["lng"])) < 1e-5
        if not ok:
            drop_os.append(o)
    print(f"geocode_cache: {len(cache)} total, mantém {len(keep)}, apaga {len(drop_cache)}")
    print(f"service_orders com coordenada a limpar: {len(drop_os)}")
    if not apply:
        return
    bk = Path(__file__).parent / "backups"
    bk.mkdir(exist_ok=True)
    f = bk / f"geocodes_{datetime.now():%Y%m%d_%H%M%S}.json"
    f.write_text(json.dumps({"geocode_cache": drop_cache, "service_orders": drop_os,
                             "routes": await db.routes.find({}, {"_id": 0, "id": 1, "orders": 1}).to_list(10000)},
                            ensure_ascii=False, default=str))
    print("backup:", f)
    for c in drop_cache:
        await db.geocode_cache.delete_one({"address_hash": c["address_hash"]})
    for o in drop_os:
        await db.service_orders.update_one({"os_number": o["os_number"]}, {"$set": {"lat": None, "lng": None}})
    # Roteiros guardam cópia de lat/lng por parada: alinha com a OS (validada) ou zera.
    good = {o["os_number"]: o for o in orders if o not in drop_os and _valid_br(o.get("lat"), o.get("lng"))}
    fixed = 0
    for r in await db.routes.find({}, {"_id": 0, "id": 1, "orders": 1}).to_list(10000):
        new = []
        for s in r.get("orders") or []:
            g = good.get(s.get("os_number"))
            new.append({**s, "lat": float(g["lat"]) if g else None, "lng": float(g["lng"]) if g else None})
        if new and new != r.get("orders"):
            await db.routes.update_one({"id": r["id"]}, {"$set": {"orders": new}})
            fixed += 1
    print("roteiros ajustados:", fixed)
    print("feito")


if __name__ == "__main__":
    asyncio.run(main("--apply" in sys.argv))
