"""Almacenamiento SQLite multi-fuente para el pipeline de forecasting.

Esquema pensado para varias fuentes de datos (ESIOS hoy; MIBGAS,
Open-Meteo, reserva hidráulica más adelante) sin tener que migrar:

- observations: los valores en sí, con `source` como parte de la clave
  primaria junto a indicator_id/datetime_utc/geo_id. Idempotente por
  construcción (INSERT OR IGNORE): reinsertar el mismo dato no duplica.
- indicators_catalog: metadatos de cada indicador (de qué fuente es,
  para qué sirve, desde cuándo hay datos).
- ingestion_log: qué rango de fechas de qué indicador ya se descargó
  con éxito, para que la ingesta histórica se pueda cortar y reanudar
  sin repetir peticiones a la API.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pandas as pd

SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    source        TEXT    NOT NULL,
    indicator_id  INTEGER NOT NULL,
    datetime_utc  TEXT    NOT NULL,
    geo_id        INTEGER NOT NULL DEFAULT 0,
    value         REAL,
    PRIMARY KEY (source, indicator_id, datetime_utc, geo_id)
);

CREATE INDEX IF NOT EXISTS idx_observations_source_indicator
    ON observations(source, indicator_id, datetime_utc);

CREATE TABLE IF NOT EXISTS indicators_catalog (
    source           TEXT    NOT NULL,
    indicator_id     INTEGER NOT NULL,
    name             TEXT,
    categoria        TEXT,
    rol              TEXT,
    cobertura_desde  TEXT,
    PRIMARY KEY (source, indicator_id)
);

CREATE TABLE IF NOT EXISTS ingestion_log (
    source        TEXT    NOT NULL,
    indicator_id  INTEGER NOT NULL,
    period_start  TEXT    NOT NULL,
    period_end    TEXT    NOT NULL,
    status        TEXT    NOT NULL,
    rows_fetched  INTEGER,
    fetched_at    TEXT    NOT NULL,
    PRIMARY KEY (source, indicator_id, period_start, period_end)
);
"""


def get_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def upsert_catalog(conn: sqlite3.Connection, entries: list[dict]) -> None:
    """Inserta o actualiza metadatos de indicadores en indicators_catalog."""
    conn.executemany(
        """
        INSERT INTO indicators_catalog (source, indicator_id, name, categoria, rol, cobertura_desde)
        VALUES (:source, :id, :name, :categoria, :rol, :cobertura_desde)
        ON CONFLICT(source, indicator_id) DO UPDATE SET
            name = excluded.name,
            categoria = excluded.categoria,
            rol = excluded.rol,
            cobertura_desde = excluded.cobertura_desde
        """,
        entries,
    )
    conn.commit()


def insert_observations(conn: sqlite3.Connection, df: pd.DataFrame) -> int:
    """Inserta observaciones, ignorando duplicados (misma clave primaria).

    Devuelve el nº de filas realmente nuevas insertadas.
    """
    if df.empty:
        return 0
    before = conn.total_changes
    conn.executemany(
        """
        INSERT OR IGNORE INTO observations (source, indicator_id, datetime_utc, geo_id, value)
        VALUES (?, ?, ?, ?, ?)
        """,
        df[["source", "indicator_id", "datetime_utc", "geo_id", "value"]].itertuples(
            index=False, name=None
        ),
    )
    conn.commit()
    return conn.total_changes - before


def is_period_done(
    conn: sqlite3.Connection, source: str, indicator_id: int, period_start: str, period_end: str
) -> bool:
    row = conn.execute(
        """
        SELECT 1 FROM ingestion_log
        WHERE source = ? AND indicator_id = ? AND period_start = ? AND period_end = ?
              AND status = 'done'
        """,
        (source, indicator_id, period_start, period_end),
    ).fetchone()
    return row is not None


def mark_period(
    conn: sqlite3.Connection,
    source: str,
    indicator_id: int,
    period_start: str,
    period_end: str,
    status: str,
    rows_fetched: int = 0,
) -> None:
    conn.execute(
        """
        INSERT INTO ingestion_log (source, indicator_id, period_start, period_end, status, rows_fetched, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source, indicator_id, period_start, period_end) DO UPDATE SET
            status = excluded.status,
            rows_fetched = excluded.rows_fetched,
            fetched_at = excluded.fetched_at
        """,
        (
            source,
            indicator_id,
            period_start,
            period_end,
            status,
            rows_fetched,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
