"""Copia os arquivos dos manuais do storage antigo (Emergent) para o Supabase Storage. Idempotente."""
import asyncio
import sys
import requests
sys.path.insert(0, '/app/backend')
from dotenv import load_dotenv
load_dotenv('/app/backend/.env')
from supabase_db import db
import manuais_module as m


async def main():
    docs = await db.manuais.find({"is_deleted": False}, {"_id": 0, "storage_path": 1, "original_filename": 1, "content_type": 1}).to_list(1000)
    ok = fail = skip = 0
    for d in docs:
        p = d["storage_path"]
        if requests.head(f"{m.SB_BUCKET_URL}/{p}", headers=m._sb_headers(), timeout=30).status_code == 200:
            skip += 1
            continue
        try:
            data, ctype = m._legacy_get_object(p)
            m.put_object(p, data, d.get("content_type") or ctype)
            ok += 1
            print("ok", d["original_filename"], len(data), flush=True)
        except Exception as e:
            fail += 1
            print("FAIL", d["original_filename"], repr(e)[:200], flush=True)
    print(f"migrados={ok} ja_existiam={skip} falhas={fail} total={len(docs)}")

asyncio.run(main())
