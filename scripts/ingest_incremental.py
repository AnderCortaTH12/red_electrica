"""Ingesta incremental diaria: trae los datos nuevos de cada indicador
desde el último dato ya guardado en la bbdd hasta ahora (una petición
por indicador, no re-trocea todo el histórico).

Si un indicador no tiene datos previos o lleva más de 30 días sin
actualizarse (p.ej. porque se perdió el estado persistido entre
ejecuciones de CI), hace backfill completo para ese indicador en su
lugar — autorreparable sin intervención manual.

Uso:
    python -m scripts.ingest_incremental
"""

import json
import logging
import sys

from dotenv import load_dotenv

from src.ingestion.esios_client import ESIOSClient
from src.ingestion.pipeline import update_indicator_incremental
from src.storage.db import get_connection, init_db, upsert_catalog

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ingest_incremental")

CATALOG_PATH = "data/esios_indicators_catalog.json"
DB_PATH = "data/electricidad.db"


def main() -> int:
    load_dotenv()
    with open(CATALOG_PATH, encoding="utf-8") as f:
        catalog = json.load(f)

    client = ESIOSClient()
    conn = get_connection(DB_PATH)
    init_db(conn)
    upsert_catalog(conn, catalog)

    total_new = 0
    total_failed = 0
    for entry in catalog:
        result = update_indicator_incremental(client, conn, entry)
        total_new += result.get("nuevas_filas", 0)
        total_failed += result.get("fallidas", 0)
        logger.info("Indicador %d (%s): %s", entry["id"], entry["name"], result)

    conn.close()
    print(f"\nFilas nuevas: {total_new} | fallos: {total_failed}")
    return 1 if total_failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
