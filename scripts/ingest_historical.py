"""Ingesta histórica de los indicadores del catálogo, desde su
cobertura_desde hasta hoy, a SQLite.

Idempotente y reanudable:
- Cada indicador se trocea en ventanas de 3 meses (evita pedir años de
  golpe y limita el daño si una ventana falla).
- Antes de pedir una ventana a la API se comprueba en `ingestion_log`
  si ya se descargó con éxito; si es así, se salta sin gastar petición.
- Los valores se insertan con INSERT OR IGNORE sobre la clave primaria
  (source, indicator_id, datetime_utc, geo_id), así que aunque se
  reprocese una ventana no se duplica nada.
- Si una ventana falla (error de red, HTTP, etc.) se marca como
  'failed' y se continúa con la siguiente: un fallo puntual no tira
  toda la ingesta ni pierde el progreso ya hecho.

Uso:
    python scripts\\ingest_historical.py
"""

import json
import logging
import sys
from datetime import datetime

from dotenv import load_dotenv

from src.ingestion.date_ranges import chunk_range
from src.ingestion.esios_client import ESIOSAPIError, ESIOSClient
from src.storage.db import get_connection, init_db, insert_observations, is_period_done, mark_period, upsert_catalog

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("ingest_historical")

CATALOG_PATH = "data/esios_indicators_catalog.json"
DB_PATH = "data/electricidad.db"
# Mensual, no trimestral: para el precio spot (id 600) en 2025 una ventana
# de 3 meses ronda o supera los 60s de timeout (una petición de 1 mes ya
# pesa ~3.7MB / ~16s), detectado empíricamente al fallar de forma
# reproducible en esas ventanas. Mensual deja margen de sobra.
MONTHS_PER_CHUNK = 1


def main() -> None:
    load_dotenv()

    with open(CATALOG_PATH, encoding="utf-8") as f:
        catalog = json.load(f)

    client = ESIOSClient()
    conn = get_connection(DB_PATH)
    init_db(conn)
    upsert_catalog(conn, catalog)

    now = datetime.now()
    total_chunks = 0
    total_new_rows = 0
    total_skipped = 0
    total_failed = 0
    failed_periods: list[tuple[int, str, str]] = []

    for entry in catalog:
        indicator_id = entry["id"]
        source = entry["source"]
        chunks = chunk_range(entry["cobertura_desde"], now, MONTHS_PER_CHUNK)
        logger.info(
            "Indicador %d (%s): %d ventanas desde %s",
            indicator_id,
            entry["name"],
            len(chunks),
            entry["cobertura_desde"],
        )

        for chunk_start, chunk_end in chunks:
            total_chunks += 1
            period_start = chunk_start.strftime("%Y-%m-%d")
            period_end = chunk_end.strftime("%Y-%m-%d")

            if is_period_done(conn, source, indicator_id, period_start, period_end):
                total_skipped += 1
                continue

            start_param = chunk_start.strftime("%Y-%m-%dT00:00")
            end_param = chunk_end.strftime("%Y-%m-%dT23:59")

            try:
                df = client.fetch(indicator_id, start_param, end_param)
                n_new = insert_observations(conn, df)
                mark_period(conn, source, indicator_id, period_start, period_end, "done", len(df))
                total_new_rows += n_new
                logger.info(
                    "  %s -> %s: %d valores (%d nuevos)",
                    period_start,
                    period_end,
                    len(df),
                    n_new,
                )
            except ESIOSAPIError as exc:
                mark_period(conn, source, indicator_id, period_start, period_end, "failed", 0)
                total_failed += 1
                failed_periods.append((indicator_id, period_start, period_end))
                logger.error("  %s -> %s: FALLO (%s)", period_start, period_end, exc)

    conn.close()

    print("\n== Resumen de ingesta ==")
    print(f"Ventanas totales:  {total_chunks}")
    print(f"Ya hechas (skip):  {total_skipped}")
    print(f"Procesadas ahora:  {total_chunks - total_skipped}")
    print(f"Filas nuevas:      {total_new_rows}")
    print(f"Fallidas:          {total_failed}")
    if failed_periods:
        print("Ventanas fallidas (relanzar el script las reintentará):")
        for indicator_id, start, end in failed_periods:
            print(f"  indicator_id={indicator_id} {start} -> {end}")


if __name__ == "__main__":
    sys.exit(main())
