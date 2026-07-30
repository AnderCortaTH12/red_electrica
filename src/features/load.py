"""Carga los datos de `observations` (formato largo: una fila por
indicador/hora) y los convierte a formato ancho (una fila por hora,
una columna por indicador) listo para EDA y feature engineering.

Cada indicador se filtra por su `geo_id_objetivo` del catálogo: varios
indicadores devuelven varios ámbitos geográficos por hora (p.ej. el
precio spot trae también Portugal, Francia, Alemania... o el PVPC trae
Canarias/Baleares/Ceuta/Melilla) y mezclarlos sin filtrar duplicaría
señal de mercados/tarifas distintas bajo el mismo nombre de columna.
"""

from __future__ import annotations

import json
import sqlite3

import pandas as pd

CATALOG_PATH = "data/esios_indicators_catalog.json"


def load_catalog(path: str = CATALOG_PATH) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_wide_dataframe(
    conn: sqlite3.Connection, catalog: list[dict] | None = None
) -> pd.DataFrame:
    """Devuelve un DataFrame indexado por datetime_utc (hora, UTC), con
    una columna por indicador (nombre = catalog[i]['columna']).

    Las horas sin dato para un indicador quedan como NaN (no se rellenan
    aquí): el hueco es información — hay que verlo en el EDA antes de
    decidir cómo tratarlo.
    """
    catalog = catalog or load_catalog()
    series = []

    for entry in catalog:
        df = pd.read_sql_query(
            """
            SELECT datetime_utc, value
            FROM observations
            WHERE source = ? AND indicator_id = ? AND geo_id = ?
            ORDER BY datetime_utc
            """,
            conn,
            params=(entry["source"], entry["id"], entry["geo_id_objetivo"]),
        )
        s = pd.Series(
            df["value"].values,
            index=pd.to_datetime(df["datetime_utc"], utc=True),
            name=entry["columna"],
        )
        series.append(s)

    wide = pd.concat(series, axis=1).sort_index()
    wide.index.name = "datetime_utc"
    return wide
