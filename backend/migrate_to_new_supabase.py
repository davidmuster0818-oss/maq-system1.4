"""
Supabase Database Migration Script
===================================
Creates all tables and imports data from CSV files into a NEW Supabase project.

Usage:
    1. Create a new Supabase project
    2. Get the new SUPABASE_URL and SUPABASE_SERVICE_KEY
    3. Run: python3 migrate_to_new_supabase.py --url <URL> --key <KEY>
    
    Or set environment variables:
        NEW_SUPABASE_URL=...
        NEW_SUPABASE_KEY=...
"""
import os
import csv
import json
import sys
import argparse
import time

try:
    import httpx
except ImportError:
    print("Installing httpx...")
    os.system("pip install httpx")
    import httpx

CSV_DIR = "/tmp/banco_csv/banco=tabelas-csv"

# ─── Table schemas (SQL CREATE statements) ────────────────────────

SCHEMAS = {
    "service_orders": """
CREATE TABLE IF NOT EXISTS service_orders (
    id text PRIMARY KEY,
    os_number text UNIQUE,
    customer_name text,
    registration_date text,
    attendance_date text,
    cep text,
    address text,
    number text,
    neighborhood text,
    city text,
    state text,
    complement text,
    phone1 text,
    phone2 text,
    landline text,
    email text,
    visit_fee numeric,
    reference_point text,
    service_type text,
    product text,
    brand text,
    model text,
    serial_number text,
    batch text,
    reported_defect text,
    observations text,
    status text,
    sub_status text,
    micro_status text,
    technical_diagnosis text,
    installation_correct text,
    required_parts text,
    technician text,
    voltage_f1f2 text,
    voltage_f1_terra text,
    voltage_f2_terra text,
    photo_1 text,
    photo_2 text,
    photo_3 text,
    photo_4 text,
    photo_5 text,
    photo_6 text,
    photo_7 text,
    photo_8 text,
    photo_9 text,
    signature_technician text,
    signature_client text,
    signature_client_name text,
    signature_client_cpf text,
    signature_date text,
    assinafy_document_id text,
    assinafy_status text,
    status_orcamento text,
    conclusao_orcamento text,
    scheduling_history jsonb DEFAULT '[]'::jsonb,
    source text DEFAULT 'local',
    sort_date timestamptz,
    lat double precision,
    lng double precision,
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now(),
    signature_tech_name text,
    priority boolean DEFAULT false
);
CREATE INDEX IF NOT EXISTS idx_so_os_number ON service_orders(os_number);
CREATE INDEX IF NOT EXISTS idx_so_status ON service_orders(status);
CREATE INDEX IF NOT EXISTS idx_so_source ON service_orders(source);
CREATE INDEX IF NOT EXISTS idx_so_customer ON service_orders(customer_name);
CREATE INDEX IF NOT EXISTS idx_so_sort_date ON service_orders(sort_date DESC);
""",

    "routes": """
CREATE TABLE IF NOT EXISTS routes (
    id text PRIMARY KEY,
    name text,
    technician text,
    date text,
    orders jsonb DEFAULT '[]'::jsonb,
    total_distance text,
    total_duration text,
    status text DEFAULT 'Pendente',
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now()
);
""",

    "notifications": """
CREATE TABLE IF NOT EXISTS notifications (
    id text PRIMARY KEY,
    message text,
    os_number text,
    old_status text,
    new_status text,
    read boolean DEFAULT false,
    created_at timestamptz DEFAULT now()
);
""",

    "manuais": """
CREATE TABLE IF NOT EXISTS manuais (
    id text PRIMARY KEY,
    storage_path text,
    original_filename text,
    content_type text,
    size bigint,
    extension text,
    brand text,
    category text,
    is_deleted boolean DEFAULT false,
    created_at timestamptz DEFAULT now()
);
""",

    "laudo_drafts": """
CREATE TABLE IF NOT EXISTS laudo_drafts (
    os_number text PRIMARY KEY,
    batch text,
    brand text,
    customer_name text,
    date text,
    final_status text,
    images_count integer DEFAULT 0,
    installation_correct text,
    location text,
    model text,
    reported_defect text,
    required_parts text,
    serial_number text,
    service_type text,
    technical_diagnosis text,
    technical_notes text,
    technician text,
    updated_at timestamptz DEFAULT now(),
    voltage_f1_terra text,
    voltage_f1f2 text,
    voltage_f2_terra text
);
""",

    "laudo_history": """
CREATE TABLE IF NOT EXISTS laudo_history (
    id text PRIMARY KEY,
    os_number text,
    customer_name text,
    model text,
    technician text,
    generated_at timestamptz DEFAULT now()
);
""",

    "geocode_cache": """
CREATE TABLE IF NOT EXISTS geocode_cache (
    id text PRIMARY KEY,
    address_hash text,
    address text,
    lat double precision,
    lng double precision,
    cached_at timestamptz DEFAULT now()
);
""",

    "sync_logs": """
CREATE TABLE IF NOT EXISTS sync_logs (
    id text PRIMARY KEY,
    ts timestamptz DEFAULT now(),
    status text,
    orders_synced integer DEFAULT 0,
    orders_updated integer DEFAULT 0,
    total_in_db integer DEFAULT 0,
    days_range integer,
    date_range text,
    errors jsonb DEFAULT '[]'::jsonb,
    completed_at timestamptz
);
""",

    "whatsapp_config": """
CREATE TABLE IF NOT EXISTS whatsapp_config (
    id text PRIMARY KEY,
    access_token text,
    phone_number_id text,
    waba_id text,
    webhook_verify_token text,
    display_phone text,
    updated_at timestamptz DEFAULT now(),
    app_secret text
);
""",

    "whatsapp_messages": """
CREATE TABLE IF NOT EXISTS whatsapp_messages (
    id text PRIMARY KEY,
    direction text,
    to_number text,
    from_number text,
    type text,
    body text,
    wa_message_id text,
    status text,
    contact_name text,
    ts timestamptz DEFAULT now(),
    sent_at timestamptz,
    received_at timestamptz,
    status_updated_at timestamptz
);
""",

    "movements": """
CREATE TABLE IF NOT EXISTS movements (
    id text PRIMARY KEY,
    product_code text,
    quantity integer,
    movement_type text,
    reason text,
    document text,
    notes text,
    date text,
    previous_stock integer,
    new_stock integer
);
""",

    "serials": """
CREATE TABLE IF NOT EXISTS serials (
    serial_number text PRIMARY KEY,
    product_code text,
    supplier text,
    status text,
    os_number text,
    entry_date text
);
""",
}

CSV_MAP = {
    "service_orders": "service_orders_rows.csv",
    "routes": "routes_rows.csv",
    "notifications": "notifications_rows.csv",
    "manuais": "manuais_rows.csv",
    "laudo_drafts": "laudo_drafts_rows.csv",
    "laudo_history": "laudo_history_rows.csv",
    "geocode_cache": "geocode_cache_rows.csv",
    "sync_logs": "sync_logs_rows.csv",
    "whatsapp_config": "whatsapp_config_rows.csv",
    "whatsapp_messages": "whatsapp_messages_rows.csv",
    "movements": "movements_rows.csv",
    "serials": "serials_rows.csv",
}

# Enable RLS policies
RLS_POLICIES = """
-- Enable RLS but allow service_role full access
ALTER TABLE service_orders ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_all" ON service_orders FOR ALL USING (true) WITH CHECK (true);
ALTER TABLE routes ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_all" ON routes FOR ALL USING (true) WITH CHECK (true);
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_all" ON notifications FOR ALL USING (true) WITH CHECK (true);
ALTER TABLE manuais ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_all" ON manuais FOR ALL USING (true) WITH CHECK (true);
ALTER TABLE laudo_drafts ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_all" ON laudo_drafts FOR ALL USING (true) WITH CHECK (true);
ALTER TABLE laudo_history ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_all" ON laudo_history FOR ALL USING (true) WITH CHECK (true);
ALTER TABLE geocode_cache ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_all" ON geocode_cache FOR ALL USING (true) WITH CHECK (true);
ALTER TABLE sync_logs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_all" ON sync_logs FOR ALL USING (true) WITH CHECK (true);
ALTER TABLE whatsapp_config ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_all" ON whatsapp_config FOR ALL USING (true) WITH CHECK (true);
ALTER TABLE whatsapp_messages ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_all" ON whatsapp_messages FOR ALL USING (true) WITH CHECK (true);
ALTER TABLE movements ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_all" ON movements FOR ALL USING (true) WITH CHECK (true);
ALTER TABLE serials ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_all" ON serials FOR ALL USING (true) WITH CHECK (true);
"""


def read_csv(filepath):
    """Read CSV and return list of dicts"""
    rows = []
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            clean = {}
            for k, v in row.items():
                if v == '' or v == 'NULL' or v is None:
                    clean[k] = None
                elif v == 'true':
                    clean[k] = True
                elif v == 'false':
                    clean[k] = False
                else:
                    # Try parse JSON for jsonb columns
                    if k in ('scheduling_history', 'orders', 'errors') and v.startswith('['):
                        try:
                            clean[k] = json.loads(v)
                        except Exception:
                            clean[k] = v
                    else:
                        clean[k] = v
            rows.append(clean)
    return rows


def insert_batch(client, url, key, table, rows, batch_size=50):
    """Insert rows in batches via Supabase REST API"""
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal,resolution=merge-duplicates",
    }
    
    total = len(rows)
    inserted = 0
    errors = 0
    
    for i in range(0, total, batch_size):
        batch = rows[i:i+batch_size]
        try:
            r = client.post(
                f"{url}/rest/v1/{table}",
                json=batch,
                headers=headers,
                timeout=30,
            )
            if r.status_code in (200, 201):
                inserted += len(batch)
            else:
                print(f"  ⚠ Batch {i//batch_size+1}: {r.status_code} - {r.text[:200]}")
                errors += len(batch)
        except Exception as e:
            print(f"  ✗ Batch {i//batch_size+1}: {e}")
            errors += len(batch)
        
        # Progress
        pct = min(100, (i + batch_size) * 100 // total)
        print(f"  [{pct:3d}%] {table}: {inserted}/{total} inserted", end='\r')
    
    print(f"  [100%] {table}: {inserted}/{total} inserted, {errors} errors")
    return inserted, errors


def main():
    parser = argparse.ArgumentParser(description='Migrate Mastermaq DB to new Supabase')
    parser.add_argument('--url', default=os.environ.get('NEW_SUPABASE_URL', ''), help='New Supabase URL')
    parser.add_argument('--key', default=os.environ.get('NEW_SUPABASE_KEY', ''), help='New Supabase service_role key')
    parser.add_argument('--csv-dir', default=CSV_DIR, help='Directory with CSV files')
    parser.add_argument('--tables', default='all', help='Comma-separated table names or "all"')
    parser.add_argument('--skip-schema', action='store_true', help='Skip table creation (tables already exist)')
    args = parser.parse_args()
    
    if not args.url or not args.key:
        print("❌ Missing --url and --key. Provide new Supabase credentials.")
        print("   Example: python3 migrate_to_new_supabase.py --url https://xxx.supabase.co --key eyJ...")
        sys.exit(1)
    
    tables = list(SCHEMAS.keys()) if args.tables == 'all' else [t.strip() for t in args.tables.split(',')]
    
    print(f"🚀 Migrating to: {args.url}")
    print(f"📁 CSV dir: {args.csv_dir}")
    print(f"📋 Tables: {', '.join(tables)}")
    print()
    
    if not args.skip_schema:
        print("=" * 50)
        print("📌 STEP 1: Create tables")
        print("=" * 50)
        print()
        print("Execute the following SQL in your Supabase SQL Editor:")
        print("(Dashboard → SQL Editor → New Query → Paste → Run)")
        print()
        print("--- START SQL ---")
        for table in tables:
            if table in SCHEMAS:
                print(SCHEMAS[table])
        print(RLS_POLICIES)
        print("--- END SQL ---")
        print()
        input("Press ENTER after executing the SQL in Supabase SQL Editor...")
    
    print()
    print("=" * 50)
    print("📌 STEP 2: Import data from CSV")
    print("=" * 50)
    
    client = httpx.Client()
    
    total_inserted = 0
    total_errors = 0
    
    # Import order matters (service_orders first, then dependents)
    import_order = [
        "service_orders", "routes", "notifications", "manuais",
        "laudo_drafts", "laudo_history", "geocode_cache", "sync_logs",
        "whatsapp_config", "whatsapp_messages", "movements", "serials",
    ]
    
    for table in import_order:
        if table not in tables:
            continue
        csv_file = CSV_MAP.get(table)
        if not csv_file:
            continue
        filepath = os.path.join(args.csv_dir, csv_file)
        if not os.path.exists(filepath):
            print(f"  ⚠ {csv_file} not found, skipping")
            continue
        
        rows = read_csv(filepath)
        if not rows:
            print(f"  ⚠ {table}: empty CSV, skipping")
            continue
        
        print(f"\n📦 {table} ({len(rows)} rows)")
        
        # For service_orders, use smaller batches due to large payloads
        batch_size = 20 if table == 'service_orders' else 50
        inserted, errors = insert_batch(client, args.url, args.key, table, rows, batch_size)
        total_inserted += inserted
        total_errors += errors
    
    client.close()
    
    print()
    print("=" * 50)
    print(f"✅ Migration complete!")
    print(f"   Total inserted: {total_inserted}")
    print(f"   Total errors: {total_errors}")
    print()
    print("📌 STEP 3: Update your .env with new credentials:")
    print(f"   SUPABASE_URL={args.url}")
    print(f"   SUPABASE_SERVICE_KEY=<your_service_key>")
    print(f"   SUPABASE_ANON_KEY=<your_anon_key>")


if __name__ == "__main__":
    main()
