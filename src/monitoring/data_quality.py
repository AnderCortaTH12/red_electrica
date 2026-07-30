"""Chequeos de calidad de datos sobre `observations`: huecos recientes,
valores fuera de rango, e indicadores que han dejado de traer datos
nuevos. Pensado para correr a diario (scripts/monitor.py) y avisar
pronto de problemas de la fuente (ESIOS) o de la propia ingesta.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pandas as pd

# Rangos "sanos" (no de negocio estrictos, solo para pillar errores
# groseros: nulos convertidos en 0, unidades mal escaladas, etc.)
RANGOS_SANOS = {
    "precio_spot": (-500, 5000),
    "pvpc": (-500, 5000),
    "demanda_real": (0, 60000),
    "demanda_prevista": (0, 60000),
}
RANGO_GENERACION_DEFECTO = (-1000, 100000)

STALE_HOURS = 48
GAP_CHECK_HOURS = 72
GAP_TOLERANCE = 0.9  # tolera hasta un 10% de huecos (revisiones/festivos, etc.)


def _window_start(hours: int) -> str:
    start = datetime.now(timezone.utc) - timedelta(hours=hours)
    return start.strftime("%Y-%m-%dT%H:%M:%SZ")


def check_gaps(
    conn: sqlite3.Connection, catalog: list[dict], window_hours: int = GAP_CHECK_HOURS
) -> list[dict]:
    """¿Cuántas filas se esperaban en las últimas `window_hours` horas
    para cada indicador, frente a las que hay realmente?"""
    problems = []
    window_start = _window_start(window_hours)
    for entry in catalog:
        found = conn.execute(
            """
            SELECT COUNT(*) FROM observations
            WHERE source = ? AND indicator_id = ? AND geo_id = ? AND datetime_utc >= ?
            """,
            (entry["source"], entry["id"], entry["geo_id_objetivo"], window_start),
        ).fetchone()[0]
        if found < window_hours * GAP_TOLERANCE:
            problems.append(
                {
                    "indicator_id": entry["id"],
                    "nombre": entry["name"],
                    "tipo": "hueco",
                    "filas_esperadas_aprox": window_hours,
                    "filas_encontradas": found,
                }
            )
    return problems


def check_stale_indicators(
    conn: sqlite3.Connection, catalog: list[dict], stale_hours: int = STALE_HOURS
) -> list[dict]:
    """¿Qué indicadores llevan más de `stale_hours` sin traer un dato
    nuevo (o no tienen ninguno)?"""
    problems = []
    now = datetime.now(timezone.utc)
    for entry in catalog:
        last = conn.execute(
            "SELECT MAX(datetime_utc) FROM observations WHERE source = ? AND indicator_id = ?",
            (entry["source"], entry["id"]),
        ).fetchone()[0]
        if last is None:
            problems.append({"indicator_id": entry["id"], "nombre": entry["name"], "tipo": "sin_datos"})
            continue
        last_ts = pd.Timestamp(last)
        if last_ts.tzinfo is None:
            last_ts = last_ts.tz_localize("UTC")
        gap_hours = (now - last_ts.to_pydatetime()).total_seconds() / 3600
        if gap_hours > stale_hours:
            problems.append(
                {
                    "indicator_id": entry["id"],
                    "nombre": entry["name"],
                    "tipo": "obsoleto",
                    "ultimo_dato": last,
                    "horas_sin_actualizar": round(gap_hours, 1),
                }
            )
    return problems


def check_out_of_range(
    conn: sqlite3.Connection, catalog: list[dict], window_hours: int = GAP_CHECK_HOURS
) -> list[dict]:
    """¿Hay valores fuera de un rango "sano" en las últimas
    `window_hours` horas para cada indicador?"""
    problems = []
    window_start = _window_start(window_hours)
    for entry in catalog:
        lo, hi = RANGOS_SANOS.get(entry["columna"], RANGO_GENERACION_DEFECTO)
        found = conn.execute(
            """
            SELECT COUNT(*) FROM observations
            WHERE source = ? AND indicator_id = ? AND geo_id = ? AND datetime_utc >= ?
                  AND (value < ? OR value > ?)
            """,
            (entry["source"], entry["id"], entry["geo_id_objetivo"], window_start, lo, hi),
        ).fetchone()[0]
        if found > 0:
            problems.append(
                {
                    "indicator_id": entry["id"],
                    "nombre": entry["name"],
                    "tipo": "fuera_de_rango",
                    "rango_esperado": [lo, hi],
                    "filas_fuera_de_rango": found,
                }
            )
    return problems
