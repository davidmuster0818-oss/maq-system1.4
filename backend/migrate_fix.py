"""
Fix migration: insert missing service_orders and sync_logs with normalized keys
"""
import httpx
import json
import time
from pymongo import MongoClient

SUPABASE_URL = "https://dgddkhihghejaejixqyy.supabase.co"
SERVICE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImRnZGRraGloZ2hlamFlaml4cXl5Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NDE5NDYwNSwiZXhwIjoyMDg5NzcwNjA1fQ.b0j27JFmN_9SPjrC7Qg3Mdy8q7dj8vI3TmRsgsEWpG8"
HEADERS = {
    "apikey": SERVICE_KEY,
    "Authorization": f"Bearer {SERVICE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal,resolution=ignore-duplicates"
}

client = MongoClient("mongodb://localhost:27017")
db = client["test_database"]

SO_COLUMNS = [
    "id","os_number","customer_name","registration_date","attendance_date",
    "cep","address","number","neighborhood","city","state","complement",
    "phone1","phone2","landline","email","visit_fee","reference_point","service_type",
    "product","brand","model","serial_number","batch","reported_defect","observations",
    "status","sub_status","micro_status","technical_diagnosis","installation_correct",
    "required_parts","technician","voltage_f1f2","voltage_f1_terra","voltage_f2_terra",
    "photo_1","photo_2","photo_3","photo_4","photo_5","photo_6","photo_7","photo_8","photo_9",
    "signature_technician","signature_client","signature_client_name","signature_client_cpf",
    "signature_date","signature_tech_name","assinafy_document_id","assinafy_status",
    "status_orcamento","conclusao_orcamento","scheduling_history",
    "source","sort_date","lat","lng","created_at","updated_at"
]

SYNC_COLUMNS = ["id","ts","status","orders_synced","orders_updated","total_in_db","days_range","date_range","errors","completed_at"]


def normalize(doc, columns, remap=None):
    """Ensure doc has exactly the specified columns, with None for missing"""
    doc.pop("_id", None)
    if remap:
        for old_k, new_k in remap.items():
            if old_k in doc:
                doc[new_k] = doc.pop(old_k)
    return {col: doc.get(col) for col in columns}


def insert_batch(table, rows):
    if not rows:
        return 0
    r = httpx.post(f"{SUPABASE_URL}/rest/v1/{table}", json=rows, headers=HEADERS, timeout=60)
    if r.status_code not in (200, 201):
        print(f"  ERROR {table}: {r.status_code} - {r.text[:200]}")
        return 0
    return len(rows)


def main():
    # 1. Get already migrated os_numbers
    print("Fetching migrated os_numbers from Supabase...")
    migrated = set()
    offset = 0
    while True:
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/service_orders?select=os_number&offset={offset}&limit=1000",
            headers={"apikey": SERVICE_KEY, "Authorization": f"Bearer {SERVICE_KEY}"},
            timeout=30
        )
        rows = r.json()
        if not rows:
            break
        for row in rows:
            migrated.add(row["os_number"])
        offset += 1000
    print(f"  Already migrated: {len(migrated)}")

    # 2. Find and insert missing service_orders
    missing_docs = []
    for doc in db.service_orders.find({}, {"_id": 0}):
        if doc.get("os_number") not in migrated:
            missing_docs.append(normalize(doc, SO_COLUMNS))

    print(f"  Missing service_orders: {len(missing_docs)}")
    inserted = 0
    for i in range(0, len(missing_docs), 200):
        batch = missing_docs[i:i+200]
        n = insert_batch("service_orders", batch)
        inserted += n
        print(f"  service_orders: {inserted}/{len(missing_docs)}", end="\r")
        time.sleep(0.1)
    print(f"  service_orders: {inserted}/{len(missing_docs)} inserted")

    # 3. Migrate sync_logs with normalized keys
    print("\nMigrating sync_logs...")
    sync_docs = []
    for doc in db.sync_logs.find({}, {"_id": 0}):
        sync_docs.append(normalize(doc, SYNC_COLUMNS, remap={"timestamp": "ts"}))
    n = insert_batch("sync_logs", sync_docs)
    print(f"  sync_logs: {n}/{len(sync_docs)} inserted")

    # 4. Final verification
    print("\n=== Final Verification ===")
    tables_mongo = {
        "service_orders": db.service_orders.count_documents({}),
        "routes": db.routes.count_documents({}),
        "manuais": db.manuais.count_documents({}),
        "laudo_drafts": db.laudo_drafts.count_documents({}),
        "laudo_history": db.laudo_history.count_documents({}),
        "sync_logs": db.sync_logs.count_documents({}),
        "notifications": db.notifications.count_documents({}),
        "movements": db.movements.count_documents({}),
        "serials": db.serials.count_documents({}),
    }
    for t, mongo_count in tables_mongo.items():
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/{t}?select=*&limit=0",
            headers={**{"apikey": SERVICE_KEY, "Authorization": f"Bearer {SERVICE_KEY}"}, "Prefer": "count=exact"},
            timeout=10
        )
        supa_count = r.headers.get("content-range", "*/0").split("/")[-1]
        match = "OK" if str(mongo_count) == supa_count else "MISMATCH"
        print(f"  {t}: MongoDB={mongo_count} Supabase={supa_count} [{match}]")


if __name__ == "__main__":
    main()
