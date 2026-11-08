"""
Migration script - Fetches service orders from the old Mastermaq system
and inserts them into the new system's MongoDB.

Uses GET database.php?nohtml&by=ose_id&find=OSNUM to fetch JSON data.
"""
import os
import sys
import json
import time
import re
import logging
import requests
from datetime import datetime, timezone
from pymongo import MongoClient, UpdateOne
from dotenv import load_dotenv

load_dotenv()

# Configuration
OLD_SYSTEM_BASE = "https://gestao.mastermaqassistencia.com.br/app"
LOGIN_URL = f"{OLD_SYSTEM_BASE}/login.php"
DATA_URL = f"{OLD_SYSTEM_BASE}/database.php"
EMAIL = "mastermaqassistencia@gmail.com"
PASSWORD = "atr132641"

MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME", "mastermaq_os")

OS_START = 24794
OS_END = 26250

BATCH_SIZE = 50
REQUEST_DELAY = 0.3  # seconds between requests

LOG_FILE = '/app/backend/migration.log'
PROGRESS_FILE = '/app/backend/migration_progress.json'
SUMMARY_FILE = '/app/backend/migration_summary.json'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger("migration")


def parse_visit_fee(fee_str):
    """Parse 'R$ 80,00' to 80.0"""
    if not fee_str or not isinstance(fee_str, str):
        return None
    cleaned = fee_str.replace("R$", "").replace(".", "").replace(",", ".").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def login(session):
    """Login to the old system"""
    log.info("Logging into old system...")
    resp = session.post(LOGIN_URL, data={
        "email": EMAIL,
        "senha": PASSWORD
    }, allow_redirects=True)
    if resp.status_code == 200 and "index.php" in resp.url:
        log.info("Login successful")
        return True
    log.error(f"Login failed. Status: {resp.status_code}")
    return False


def fetch_os_data(session, os_number):
    """Fetch a single OS from old system via JSON API"""
    try:
        resp = session.get(
            DATA_URL,
            params={"nohtml": "", "by": "ose_id", "find": str(os_number)},
            timeout=15
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        if isinstance(data, list) and len(data) > 0:
            return data[0]
        return None
    except (requests.RequestException, json.JSONDecodeError) as e:
        log.warning(f"Error fetching OS {os_number}: {e}")
        return None


def map_to_schema(raw):
    """Map old system fields to new system ServiceOrder schema"""
    now = datetime.now(timezone.utc).isoformat()
    return {
        "os_number": str(raw.get("ose_id", "")),
        "customer_name": (raw.get("nome") or "").strip(),
        "registration_date": (raw.get("data_cadastro") or "").strip(),
        "attendance_date": (raw.get("data") or "").strip(),
        "cep": (raw.get("cep") or "").strip(),
        "address": (raw.get("endereco") or "").strip(),
        "number": "",
        "neighborhood": (raw.get("bairro") or "").strip(),
        "city": (raw.get("cidade") or "").strip(),
        "state": (raw.get("uf") or "").strip(),
        "complement": "",
        "phone1": (raw.get("cel1") or "").strip(),
        "phone2": (raw.get("cel2") or "").strip(),
        "landline": (raw.get("fixo") or "").strip(),
        "email": (raw.get("email") or "").strip(),
        "visit_fee": parse_visit_fee(raw.get("taxa")),
        "reference_point": (raw.get("ponto_ref") or "").strip(),
        "service_type": (raw.get("tipo_atendimento") or "").strip(),
        "product": (raw.get("produto") or "").strip(),
        "brand": (raw.get("marca") or "").strip(),
        "model": (raw.get("modelo") or "").strip(),
        "serial_number": "",
        "batch": "",
        "reported_defect": (raw.get("defeito") or "").strip(),
        "observations": (raw.get("observacoes") or "").strip(),
        "status": "Importado",
        "source": "mastermaq",
        "created_at": now,
        "updated_at": now,
    }


def save_progress(current, total, fetched, inserted, empty, errors, elapsed):
    """Save progress to JSON file for monitoring"""
    progress = {
        "current_os": current,
        "total": total,
        "percent": round((current - OS_START) / total * 100, 1),
        "fetched": fetched,
        "inserted": inserted,
        "empty": empty,
        "errors": errors,
        "elapsed_seconds": round(elapsed, 1),
        "status": "running",
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(progress, f, indent=2)


def run_migration():
    total = OS_END - OS_START + 1
    log.info("=" * 60)
    log.info(f"MIGRATION START - OS {OS_START} to {OS_END} ({total} records)")
    log.info("=" * 60)

    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    collection = db["service_orders"]

    # Create index for upsert performance
    collection.create_index("os_number", unique=True, sparse=True)

    session = requests.Session()
    if not login(session):
        log.error("MIGRATION ABORTED: Could not login")
        with open(PROGRESS_FILE, 'w') as f:
            json.dump({"status": "failed", "error": "Login failed"}, f)
        return

    fetched = 0
    inserted = 0
    skipped = 0
    errors = 0
    empty = 0
    batch = []
    start_time = time.time()

    for os_num in range(OS_START, OS_END + 1):
        raw = fetch_os_data(session, os_num)

        if raw is None or not raw.get("nome"):
            empty += 1
        else:
            fetched += 1
            mapped = map_to_schema(raw)
            batch.append(
                UpdateOne(
                    {"os_number": mapped["os_number"]},
                    {"$set": mapped},
                    upsert=True
                )
            )

        # Insert batch
        if len(batch) >= BATCH_SIZE:
            try:
                result = collection.bulk_write(batch, ordered=False)
                inserted += result.upserted_count + result.modified_count
            except Exception as e:
                errors += len(batch)
                log.error(f"Batch error at OS {os_num}: {e}")
            batch = []
            elapsed = time.time() - start_time
            save_progress(os_num, total, fetched, inserted, empty, errors, elapsed)
            log.info(
                f"[{(os_num - OS_START + 1)}/{total}] "
                f"Fetched={fetched} Inserted={inserted} Empty={empty} Errors={errors} "
                f"Time={elapsed:.0f}s"
            )

        # Re-login every 400 requests to keep PHP session alive
        if (os_num - OS_START) % 400 == 399:
            log.info("Re-authenticating...")
            login(session)

        time.sleep(REQUEST_DELAY)

    # Insert remaining
    if batch:
        try:
            result = collection.bulk_write(batch, ordered=False)
            inserted += result.upserted_count + result.modified_count
        except Exception as e:
            errors += len(batch)
            log.error(f"Final batch error: {e}")

    elapsed = time.time() - start_time

    summary = {
        "status": "completed",
        "elapsed_seconds": round(elapsed, 1),
        "elapsed_minutes": round(elapsed / 60, 1),
        "total_checked": total,
        "fetched": fetched,
        "empty": empty,
        "inserted": inserted,
        "errors": errors,
        "completed_at": datetime.now(timezone.utc).isoformat()
    }

    with open(SUMMARY_FILE, 'w') as f:
        json.dump(summary, f, indent=2)
    with open(PROGRESS_FILE, 'w') as f:
        json.dump({**summary, "percent": 100.0}, f, indent=2)

    log.info("=" * 60)
    log.info(f"MIGRATION COMPLETE in {elapsed:.0f}s ({elapsed/60:.1f} min)")
    log.info(f"Fetched: {fetched} | Inserted: {inserted} | Empty: {empty} | Errors: {errors}")
    log.info("=" * 60)

    client.close()


if __name__ == "__main__":
    run_migration()
