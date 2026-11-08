"""
Migration script: MongoDB → Supabase (PostgreSQL via REST API)
Exports all data from local MongoDB and inserts into Supabase tables.
"""
import httpx
import json
import sys
import time
from pymongo import MongoClient

SUPABASE_URL = "https://dgddkhihghejaejixqyy.supabase.co"
SERVICE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImRnZGRraGloZ2hlamFlaml4cXl5Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NDE5NDYwNSwiZXhwIjoyMDg5NzcwNjA1fQ.b0j27JFmN_9SPjrC7Qg3Mdy8q7dj8vI3TmRsgsEWpG8"

HEADERS = {
    "apikey": SERVICE_KEY,
    "Authorization": f"Bearer {SERVICE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal"
}

BATCH_SIZE = 200

client = MongoClient("mongodb://localhost:27017")
db = client["test_database"]


def clean_doc(doc):
    """Remove MongoDB _id and convert non-serializable types"""
    doc.pop("_id", None)
    for k, v in list(doc.items()):
        if v is None:
            doc[k] = None
        elif isinstance(v, bytes):
            doc[k] = v.decode("utf-8", errors="replace")
    return doc


def insert_batch(table, rows):
    """Insert a batch of rows into Supabase via REST API"""
    if not rows:
        return 0
    r = httpx.post(
        f"{SUPABASE_URL}/rest/v1/{table}",
        json=rows,
        headers={**HEADERS, "Prefer": "return=minimal,resolution=ignore-duplicates"},
        timeout=60
    )
    if r.status_code not in (200, 201):
        print(f"  ERROR inserting into {table}: {r.status_code} - {r.text[:300]}")
        return 0
    return len(rows)


def migrate_collection(mongo_collection, supabase_table, field_remap=None):
    """Migrate a MongoDB collection to a Supabase table"""
    docs = list(mongo_collection.find({}, {"_id": 0}))
    total = len(docs)
    if total == 0:
        print(f"  {supabase_table}: 0 docs (skip)")
        return

    # Apply field remapping if needed
    if field_remap:
        for doc in docs:
            for old_key, new_key in field_remap.items():
                if old_key in doc:
                    doc[new_key] = doc.pop(old_key)

    # Clean all docs
    docs = [clean_doc(d) for d in docs]

    inserted = 0
    for i in range(0, total, BATCH_SIZE):
        batch = docs[i:i + BATCH_SIZE]
        n = insert_batch(supabase_table, batch)
        inserted += n
        if n > 0:
            print(f"  {supabase_table}: {inserted}/{total}", end="\r")
        time.sleep(0.1)  # Rate limiting

    print(f"  {supabase_table}: {inserted}/{total} migrated")


def main():
    print("=== MongoDB → Supabase Migration ===\n")

    # 1. service_orders (largest table)
    print("Migrating service_orders...")
    migrate_collection(db.service_orders, "service_orders")

    # 2. routes
    print("Migrating routes...")
    migrate_collection(db.routes, "routes")

    # 3. manuais
    print("Migrating manuais...")
    migrate_collection(db.manuais, "manuais")

    # 4. laudo_drafts
    print("Migrating laudo_drafts...")
    migrate_collection(db.laudo_drafts, "laudo_drafts")

    # 5. laudo_history
    print("Migrating laudo_history...")
    migrate_collection(db.laudo_history, "laudo_history")

    # 6. sync_logs (remap 'timestamp' → 'ts')
    print("Migrating sync_logs...")
    migrate_collection(db.sync_logs, "sync_logs", field_remap={"timestamp": "ts"})

    # 7. notifications
    print("Migrating notifications...")
    migrate_collection(db.notifications, "notifications")

    # 8. movements
    print("Migrating movements...")
    migrate_collection(db.movements, "movements")

    # 9. serials
    print("Migrating serials...")
    migrate_collection(db.serials, "serials")

    # 10. products
    print("Migrating products...")
    migrate_collection(db.products, "products")

    # 11. suppliers
    print("Migrating suppliers...")
    migrate_collection(db.suppliers, "suppliers")

    # Verify counts
    print("\n=== Verification ===")
    tables = ["service_orders", "routes", "manuais", "laudo_drafts", "laudo_history",
              "sync_logs", "notifications", "movements", "serials", "products", "suppliers"]
    for t in tables:
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/{t}?select=*&limit=0",
            headers={**HEADERS, "Prefer": "count=exact"},
            timeout=10
        )
        count = r.headers.get("content-range", "*/0").split("/")[-1]
        print(f"  {t}: {count} rows in Supabase")

    print("\n=== Migration Complete ===")


if __name__ == "__main__":
    main()
