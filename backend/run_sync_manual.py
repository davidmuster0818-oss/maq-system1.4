"""
Script para rodar o sync do Telecontrol manualmente, cobrindo um período
específico — útil para recuperar OSs que ficaram de fora por causa da
falha de paginação (ex: 28/07).

Como usar:
    python run_sync_manual.py --start 20/07/2026 --end 31/07/2026
    python run_sync_manual.py --start 20/07/2026 --end 31/07/2026 --source hisense
    python run_sync_manual.py --start 20/07/2026 --end 31/07/2026 --source hq

Se --source não for passado, roda para Hisense E HQ.
Datas no formato dd/mm/aaaa (mesmo formato que o scraper já usa internamente).

É seguro rodar mais de uma vez / com datas sobrepostas: o sync já verifica
se a OS existe (por os_number + source) antes de inserir, então não duplica
— só atualiza status/campos se algo mudou.
"""

import argparse
import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
import os

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# CRÍTICO: usar o MESMO adapter que o server.py (Supabase). Antes usávamos
# `AsyncIOMotorClient` (MongoDB local) — mas o app real vive no Supabase.
# Isso causava o scraper manual a escrever no MongoDB (que ninguém lê),
# enquanto o frontend seguia apontando pro Supabase → OSs "capturadas" mas
# invisíveis no sistema. Descoberto 11/09/2026 investigando as 5 OSs
# faltando (72804679, 72788337, 72778815, 72753931, 72750634) que o
# scraper "capturava com sucesso" mas nunca apareciam no painel.
from supabase_db import db
from telecontrol_scraper import scraper_hisense, scraper_hq

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def validate_date(value: str) -> str:
    try:
        datetime.strptime(value, "%d/%m/%Y")
    except ValueError:
        raise argparse.ArgumentTypeError(f"Data inválida: '{value}'. Use o formato dd/mm/aaaa.")
    return value


async def run_manual_sync(start_date: str, end_date: str, source: str):
    # `db` já foi importado do supabase_db no topo — é o MESMO objeto que
    # o server.py usa em produção. Não criar um cliente novo aqui.

    targets = []
    if source in ("hisense", "all"):
        targets.append(("Hisense", scraper_hisense))
    if source in ("hq", "all"):
        targets.append(("HQ", scraper_hq))

    logger.info(f"Rodando sync manual de {start_date} a {end_date} para: {[t[0] for t in targets]}")

    for label, scraper in targets:
        try:
            logger.info(f"--- Iniciando {label} ---")
            result = await scraper.sync_orders(start_date, end_date, db)
            logger.info(
                f"[{label}] Concluído: {result.get('orders_synced', 0)} novas, "
                f"{result.get('orders_updated', 0)} atualizadas, "
                f"success={result.get('success')}"
            )
            if result.get("errors"):
                logger.warning(f"[{label}] Erros durante o sync:")
                for err in result["errors"]:
                    logger.warning(f"  - {err}")
        except Exception as e:
            logger.error(f"[{label}] Falha ao rodar sync manual: {e}")
        finally:
            await scraper.close_browser()

    # Registra esse sync manual no histórico, marcado como manual para diferenciar do automático.
    # source_scope não existe no schema atual da tabela sync_logs; guardamos
    # a informação dentro do date_range pra não travar a inserção.
    try:
        await db.sync_logs.insert_one({
            "id": f"manual-sync-{datetime.now().timestamp()}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "manual",
            "date_range": f"[{source}] {start_date} a {end_date}",
            "completed_at": datetime.now(timezone.utc).isoformat()
        })
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Falha opcional ao registrar sync_log: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Roda o sync manual do Telecontrol para um período específico.")
    parser.add_argument("--start", type=validate_date, required=True, help="Data inicial (dd/mm/aaaa)")
    parser.add_argument("--end", type=validate_date, required=True, help="Data final (dd/mm/aaaa)")
    parser.add_argument("--source", choices=["hisense", "hq", "all"], default="all", help="Qual fonte sincronizar")
    args = parser.parse_args()

    asyncio.run(run_manual_sync(args.start, args.end, args.source))