"""Compara las predicciones ya guardadas (tabla `predictions`) contra
el precio real una vez conocido, para trackear el error real fuera de
muestra en el tiempo.

La Fase 5 ya estableció que el error del modelo crece de forma
estructural (régimen regulatorio + tendencia de volatilidad) — esto es
precisamente lo que avisa si el modelo se degrada MÁS de lo esperable,
no un añadido decorativo.
"""

from __future__ import annotations

import sqlite3

import pandas as pd

from src.model.metrics import mae, n_valid, rmse

PRECIO_SPOT_INDICATOR_ID = 600
PRECIO_SPOT_GEO_ID = 3


def load_predictions_with_actuals(conn: sqlite3.Connection) -> pd.DataFrame:
    """Predicciones cuya hora objetivo ya tiene precio real conocido."""
    query = """
        SELECT
            p.model_version,
            p.target_datetime_utc,
            p.predicted_price,
            p.made_at,
            o.value AS actual_price
        FROM predictions p
        JOIN observations o
          ON o.source = 'esios'
             AND o.indicator_id = ?
             AND o.geo_id = ?
             AND o.datetime_utc = p.target_datetime_utc
        ORDER BY p.target_datetime_utc
    """
    return pd.read_sql_query(query, conn, params=(PRECIO_SPOT_INDICATOR_ID, PRECIO_SPOT_GEO_ID))


def recent_error(conn: sqlite3.Connection, days: int = 7) -> dict:
    """MAE/RMSE de las predicciones de los últimos `days` días con
    precio real ya disponible."""
    df = load_predictions_with_actuals(conn)
    if df.empty:
        return {"n": 0, "mae": None, "rmse": None, "dias": days}

    df["target_datetime_utc"] = pd.to_datetime(df["target_datetime_utc"], utc=True)
    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=days)
    recent = df[df["target_datetime_utc"] >= cutoff]

    if recent.empty:
        return {"n": 0, "mae": None, "rmse": None, "dias": days}

    return {
        "n": n_valid(recent["actual_price"], recent["predicted_price"]),
        "mae": mae(recent["actual_price"], recent["predicted_price"]),
        "rmse": rmse(recent["actual_price"], recent["predicted_price"]),
        "dias": days,
    }
