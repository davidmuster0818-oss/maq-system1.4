"""Debug tool: verify which of the OSs extracted by the scraper are missing from Supabase."""
import os, sys, asyncio
from pathlib import Path
from dotenv import load_dotenv
sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv(dotenv_path=Path(__file__).parent.parent / '.env')

from supabase_db import db, _get_client, _headers, SUPABASE_URL
import httpx

extracted = ['72804679','72796823','72788337','72778815','72753931','72750634','72744306','72744173','72744092','72742796','72722386','72722342','72714529','72702859','72678082','72677844','72659114','72648536','72646049','72645208','72628700','72626077','72622844','72612845','72612390','72611207','72606880','72600155','72592454','72582731','72577953','72574925','72527294','72524071','72513001','72504914','72497107','72495645','72493709','72487286','72479671','72476919','72466945','72465987','72464803','72464241','72452576','72452512','72445795','72443549','72440206','72434937','72426288','72392112']

async def main():
    found = {}
    for os_num in extracted:
        doc = await db.service_orders.find_one({'os_number': os_num}, {'os_number':1,'customer_name':1,'source':1})
        if doc:
            found[os_num] = doc

    print(f"Encontrados no DB: {len(found)} de {len(extracted)}")
    missing = [o for o in extracted if o not in found]
    print(f"\nFALTANDO NO DB ({len(missing)}):")
    for m in missing:
        print(f"  {m}")

    print(f"\nExistentes com source != telecontrol_hisense:")
    for os_num, r in found.items():
        if r.get('source') != 'telecontrol_hisense':
            print(f"  OS {os_num} — {r.get('customer_name')} — source={r.get('source')}")

asyncio.run(main())

