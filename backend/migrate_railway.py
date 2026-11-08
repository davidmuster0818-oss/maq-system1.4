"""
Migration: Railway MongoDB (production) → Supabase (PostgreSQL)
Clears test data and imports real production data.
"""
import httpx
import json
import time
import uuid
from pymongo import MongoClient

RAILWAY_URL = "mongodb://mongo:caYzAUDaGQQLslpsFinviwTrPDqcoryz@tramway.proxy.rlwy.net:54090"
SUPABASE_URL = "https://dgddkhihghejaejixqyy.supabase.co"
SERVICE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImRnZGRraGloZ2hlamFlaml4cXl5Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NDE5NDYwNSwiZXhwIjoyMDg5NzcwNjA1fQ.b0j27JFmN_9SPjrC7Qg3Mdy8q7dj8vI3TmRsgsEWpG8"

HEADERS = {
    "apikey": SERVICE_KEY,
    "Authorization": f"Bearer {SERVICE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal"
}

BATCH_SIZE = 200

# Column definitions for each table
TABLE_COLUMNS = {
    "service_orders": [
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
    ],
    "routes": ["id","name","technician","date","orders","total_distance","total_duration","status","created_at","updated_at"],
    "manuais": ["id","storage_path","original_filename","content_type","size","extension","brand","category","is_deleted","created_at"],
    "laudo_drafts": ["os_number","batch","brand","customer_name","date","final_status","images_count","installation_correct","location","model","reported_defect","required_parts","serial_number","service_type","technical_diagnosis","technical_notes","technician","updated_at","voltage_f1_terra","voltage_f1f2","voltage_f2_terra"],
    "laudo_history": ["os_number","customer_name","model","technician","generated_at"],
    "sync_logs": ["id","ts","status","orders_synced","orders_updated","total_in_db","days_range","date_range","errors","completed_at"],
    "notifications": ["id","message","os_number","old_status","new_status","read","created_at"],
    "whatsapp_config": ["access_token","phone_number_id","waba_id","webhook_verify_token","display_phone","updated_at"],
}

FIELD_REMAP = {
    "sync_logs": {"timestamp": "ts"},
}


def normalize(doc, columns, remap=None):
    doc.pop("_id", None)
    if remap:
        for old_k, new_k in remap.items():
            if old_k in doc:
                doc[new_k] = doc.pop(old_k)
    result = {}
    for col in columns:
        val = doc.get(col)
        if isinstance(val, bytes):
            val = val.decode("utf-8", errors="replace")
        result[col] = val
    # Ensure id exists for tables that need it
    if "id" in columns and not result.get("id"):
        result["id"] = str(uuid.uuid4())
    return result


def clear_table(table):
    """Delete all rows from a Supabase table"""
    # Use a broad filter to delete everything
    r = httpx.delete(
        f"{SUPABASE_URL}/rest/v1/{table}?id=not.is.null",
        headers={**HEADERS, "Prefer": "return=representation"},
        timeout=60
    )
    if r.status_code == 200:
        count = len(r.json()) if r.json() else 0
        return count
    # For tables with different PK
    for pk in ["os_number", "serial_number", "name", "code"]:
        r = httpx.delete(
            f"{SUPABASE_URL}/rest/v1/{table}?{pk}=not.is.null",
            headers={**HEADERS, "Prefer": "return=representation"},
            timeout=60
        )
        if r.status_code == 200:
            return len(r.json()) if r.json() else 0
    # For serial PK tables
    r = httpx.delete(
        f"{SUPABASE_URL}/rest/v1/{table}?id=gt.0",
        headers={**HEADERS, "Prefer": "return=representation"},
        timeout=60
    )
    return len(r.json()) if r.status_code == 200 and r.json() else 0


def insert_batch(table, rows):
    if not rows:
        return 0
    r = httpx.post(
        f"{SUPABASE_URL}/rest/v1/{table}",
        json=rows,
        headers={**HEADERS, "Prefer": "return=minimal,resolution=ignore-duplicates"},
        timeout=60
    )
    if r.status_code not in (200, 201):
        print(f"  ERROR {table}: {r.status_code} - {r.text[:300]}")
        return 0
    return len(rows)


def get_supabase_count(table):
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/{table}?select=*&limit=0",
        headers={**HEADERS, "Prefer": "count=exact"},
        timeout=10
    )
    try:
        return int(r.headers.get("content-range", "*/0").split("/")[-1])
    except Exception:
        return 0


def main():
    print("=== Railway MongoDB → Supabase Migration (Production Data) ===\n")
    
    client = MongoClient(RAILWAY_URL, serverSelectionTimeoutMS=10000)
    railway_db = client["mastermaq_os"]

    tables_to_migrate = [
        "service_orders", "routes", "manuais", "laudo_drafts",
        "laudo_history", "sync_logs", "notifications", "whatsapp_config"
    ]

    for table in tables_to_migrate:
        mongo_coll = railway_db[table]
        mongo_count = mongo_coll.count_documents({})
        columns = TABLE_COLUMNS.get(table)
        remap = FIELD_REMAP.get(table)

        if not columns:
            print(f"  SKIP {table}: no column def")
            continue

        # 1. Clear existing test data
        print(f"\n[{table}] Railway: {mongo_count} docs")
        cleared = clear_table(table)
        print(f"  Cleared {cleared} test rows from Supabase")

        if mongo_count == 0:
            print(f"  No data to migrate")
            continue

        # 2. Export from Railway and normalize
        docs = []
        for doc in mongo_coll.find({}, {"_id": 0}):
            docs.append(normalize(doc, columns, remap))

        # 3. Insert in batches
        inserted = 0
        for i in range(0, len(docs), BATCH_SIZE):
            batch = docs[i:i + BATCH_SIZE]
            n = insert_batch(table, batch)
            inserted += n
            print(f"  Migrating: {inserted}/{len(docs)}", end="\r")
            time.sleep(0.1)

        supa_count = get_supabase_count(table)
        match = "OK" if supa_count == mongo_count else f"MISMATCH ({supa_count})"
        print(f"  {table}: {inserted}/{mongo_count} migrated [{match}]")

    # Final verification
    print("\n=== Final Verification ===")
    for table in tables_to_migrate:
        mongo_count = railway_db[table].count_documents({})
        supa_count = get_supabase_count(table)
        status = "OK" if supa_count == mongo_count else "DIFF"
        print(f"  {table}: Railway={mongo_count} Supabase={supa_count} [{status}]")

    client.close()
    print("\n=== Migration Complete ===")


if __name__ == "__main__":
    main()
