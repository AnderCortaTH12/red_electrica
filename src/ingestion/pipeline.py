"""Lógica de ingesta compartida entre el backfill histórico
(scripts/ingest_historical.py) y la actualización diaria
(scripts/ingest_incremental.py).

`update_indicator_incremental` es la pieza clave del job diario: en vez
de re-trocear todo el histórico, busca el último dato ya guardado en la
bbdd para ese indicador y pide solo lo nuevo, en una única petición. Si
no hay dato previo o el hueco es mayor que `stale_days` (p.ej. porque
se perdió el estado persistido entre ejecuciones de CI), cae de vuelta
al backfill troceado completo para ese indicador — el job diario se
autorrepara solo sin intervención manual.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd

from src.ingestion.date_ranges import chunk_range
from src.ingestion.esios_client import ESIOSAPIError
from src.storage.db import insert_observations, is_period_done, mark_period

logger = logging.getLogger(__name__)

MONTHS_PER_CHUNK = 1
DEFAULT_OVERLAP_HOURS = 6
DEFAULT_STALE_DAYS = 30


def backfill_indicator(client, conn, entry: dict) -> dict:
    """Descarga todo el histórico de un indicador en ventanas mensuales,
    saltando lo ya marcado como 'done' en ingestion_log."""
    indicator_id, source = entry["id"], entry["source"]
    chunks = chunk_range(entry["cobertura_desde"], datetime.now(), MONTHS_PER_CHUNK)
    summary = {"modo": "backfill", "ventanas": len(chunks), "skip": 0, "nuevas_filas": 0, "fallidas": 0}

    for chunk_start, chunk_end in chunks:
        period_start, period_end = chunk_start.strftime("%Y-%m-%d"), chunk_end.strftime("%Y-%m-%d")
        if is_period_done(conn, source, indicator_id, period_start, period_end):
            summary["skip"] += 1
            continue
        try:
            df = client.fetch(
                indicator_id,
                chunk_start.strftime("%Y-%m-%dT00:00"),
                chunk_end.strftime("%Y-%m-%dT23:59"),
            )
            n_new = insert_observations(conn, df)
            mark_period(conn, source, indicator_id, period_start, period_end, "done", len(df))
            summary["nuevas_filas"] += n_new
        except ESIOSAPIError as exc:
            mark_period(conn, source, indicator_id, period_start, period_end, "failed", 0)
            summary["fallidas"] += 1
            logger.error("Backfill falló %s %s->%s: %s", indicator_id, period_start, period_end, exc)

    return summary


def update_indicator_incremental(
    client,
    conn,
    entry: dict,
    overlap_hours: int = DEFAULT_OVERLAP_HOURS,
    stale_days: int = DEFAULT_STALE_DAYS,
) -> dict:
    """Trae los datos nuevos de un indicador desde el último dato
    conocido en la bbdd hasta ahora, en una sola petición.

    `overlap_hours` repite un pequeño margen hacia atrás por si ESIOS
    revisa/corrige valores recientes tras publicarlos (INSERT OR IGNORE
    hace que no importe si se repite algo ya guardado).
    """
    indicator_id, source = entry["id"], entry["source"]
    row = conn.execute(
        "SELECT MAX(datetime_utc) FROM observations WHERE source = ? AND indicator_id = ?",
        (source, indicator_id),
    ).fetchone()
    last_known = pd.Timestamp(row[0]) if row and row[0] else None
    now = pd.Timestamp(datetime.now(timezone.utc))

    if last_known is None or (now - last_known).days > stale_days:
        logger.info(
            "Indicador %d sin datos recientes (último: %s): backfill completo",
            indicator_id,
            last_known,
        )
        return backfill_indicator(client, conn, entry)

    start = (last_known - pd.Timedelta(hours=overlap_hours)).strftime("%Y-%m-%dT%H:%M")
    end = now.strftime("%Y-%m-%dT%H:%M")

    try:
        df = client.fetch(indicator_id, start, end)
        n_new = insert_observations(conn, df)
        return {"modo": "incremental", "nuevas_filas": n_new, "fallidas": 0}
    except ESIOSAPIError as exc:
        logger.error("Incremental falló para %d: %s", indicator_id, exc)
        return {"modo": "incremental", "nuevas_filas": 0, "fallidas": 1}
