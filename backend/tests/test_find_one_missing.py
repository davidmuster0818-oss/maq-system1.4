"""Debug: test find_one with source filter for OSs that should be missing."""
import sys, asyncio
from pathlib import Path
from dotenv import load_dotenv
sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv(dotenv_path=Path(__file__).parent.parent / '.env')

from supabase_db import db

MISSING = ['72804679', '72788337', '72778815', '72753931', '72750634']

async def main():
    print("=== Sem filtro de source ===")
    for os_num in MISSING:
        doc = await db.service_orders.find_one({'os_number': os_num})
        print(f"  {os_num}: {'EXISTE' if doc else 'NADA'}"
              + (f" (source={doc.get('source')})" if doc else ""))
    print("\n=== Com filtro source=telecontrol_hisense ===")
    for os_num in MISSING:
        doc = await db.service_orders.find_one({'os_number': os_num, 'source': 'telecontrol_hisense'})
        print(f"  {os_num}: {'EXISTE' if doc else 'NADA'}")
    print("\n=== ARTHUR (72796823) ===")
    for src in ['local', 'telecontrol_hisense', None]:
        q = {'os_number': '72796823'} if src is None else {'os_number': '72796823', 'source': src}
        doc = await db.service_orders.find_one(q)
        print(f"  filtro={q}: {'EXISTE' if doc else 'NADA'}"
              + (f" (source={doc.get('source')})" if doc else ""))

asyncio.run(main())
