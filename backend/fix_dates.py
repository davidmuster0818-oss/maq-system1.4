"""Normalize dd/mm/yyyy dates to yyyy-mm-dd in service_orders"""
import requests, re, os

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

date_pattern = re.compile(r'^(\d{2})/(\d{2})/(\d{4})$')
offset = 0
total_fixed = 0

while True:
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/service_orders?select=id,registration_date,attendance_date&offset={offset}&limit=1000",
        headers=headers
    )
    orders = resp.json()
    if not orders:
        break
    
    for o in orders:
        updates = {}
        for field in ['registration_date', 'attendance_date']:
            val = o.get(field, '')
            if val:
                m = date_pattern.match(str(val).strip())
                if m:
                    day, month, year = m.groups()
                    updates[field] = f"{year}-{month}-{day}"
        
        if updates:
            resp2 = requests.patch(
                f"{SUPABASE_URL}/rest/v1/service_orders?id=eq.{o['id']}",
                headers=headers,
                json=updates
            )
            if resp2.status_code == 200:
                total_fixed += 1
    
    offset += len(orders)
    print(f"Processed {offset} records, fixed {total_fixed} so far...")
    if len(orders) < 1000:
        break

print(f"\nDone! Fixed {total_fixed} records total")
