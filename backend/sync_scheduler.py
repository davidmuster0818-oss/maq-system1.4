import asyncio
import logging
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from telecontrol_scraper import scraper_hisense, scraper_hq

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

SYNC_INTERVAL_MINUTES = int(os.environ.get('SYNC_INTERVAL_MINUTES', 10))

TELECONTROL_LOGIN = os.environ.get('TELECONTROL_LOGIN', '')
TELECONTROL_LOGIN_HQ = os.environ.get('TELECONTROL_LOGIN_HQ', '')


async def run_sync():
    """Run sync for both Hisense and HQ Telecontrol"""
    logger.info("Starting dual Telecontrol sync...")

    end_date = datetime.now()
    start_date = end_date - timedelta(days=60)
    start_str = start_date.strftime("%d/%m/%Y")
    end_str = end_date.strftime("%d/%m/%Y")

    sync_log = {
        "id": f"sync-{datetime.now().timestamp()}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "running",
        "orders_synced": 0,
        "orders_updated": 0,
        "errors": []
    }
    await db.sync_logs.insert_one(sync_log)

    total_synced = 0
    total_updated = 0
    all_errors = []

    # Sync Hisense
    if TELECONTROL_LOGIN:
        try:
            logger.info("Syncing Hisense Telecontrol...")
            result = await scraper_hisense.sync_orders(start_str, end_str, db)
            total_synced += result.get("orders_synced", 0)
            total_updated += result.get("orders_updated", 0)
            if result.get("errors"):
                all_errors.extend([f"[Hisense] {e}" for e in result["errors"]])
            logger.info(f"Hisense: {result.get('orders_synced', 0)} new, {result.get('orders_updated', 0)} updated")
        except Exception as e:
            logger.error(f"Hisense sync error: {e}")
            all_errors.append(f"[Hisense] {str(e)}")
        finally:
            await scraper_hisense.close_browser()

    # Sync HQ
    if TELECONTROL_LOGIN_HQ:
        try:
            logger.info("Syncing HQ Telecontrol...")
            result = await scraper_hq.sync_orders(start_str, end_str, db)
            total_synced += result.get("orders_synced", 0)
            total_updated += result.get("orders_updated", 0)
            if result.get("errors"):
                all_errors.extend([f"[HQ] {e}" for e in result["errors"]])
            logger.info(f"HQ: {result.get('orders_synced', 0)} new, {result.get('orders_updated', 0)} updated")
        except Exception as e:
            logger.error(f"HQ sync error: {e}")
            all_errors.append(f"[HQ] {str(e)}")
        finally:
            await scraper_hq.close_browser()

    await db.sync_logs.update_one(
        {"id": sync_log["id"]},
        {"$set": {
            "status": "completed" if not all_errors else "completed_with_errors",
            "orders_synced": total_synced,
            "orders_updated": total_updated,
            "errors": all_errors,
            "completed_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    logger.info(f"Dual sync completed: {total_synced} synced, {total_updated} updated")


async def scheduler():
    """Run sync periodically every SYNC_INTERVAL_MINUTES"""
    logger.info(f"Starting dual scheduler (Hisense + HQ) with {SYNC_INTERVAL_MINUTES} minute interval")

    while True:
        try:
            await run_sync()
        except Exception as e:
            logger.error(f"Scheduler error: {e}")

        logger.info(f"Next sync in {SYNC_INTERVAL_MINUTES} minutes")
        await asyncio.sleep(SYNC_INTERVAL_MINUTES * 60)


if __name__ == "__main__":
    asyncio.run(scheduler())
