"""Compara las predicciones ya guardadas contra el precio real una vez
conocido, para trackear el error real fuera de muestra en el tiempo.

Lee las predicciones de `docs/data/predictions_log.json` (ver
src/storage/predictions_log.py), NO de la tabla SQLite `predictions`:
esa tabla vive en la cache de GitHub Actions, que `hourly.yml` no
guarda, así que cualquier predicción escrita solo ahí desaparecería
entre ejecuciones. El log en `docs/data/` se comitea a git en cada
ejecución y por eso sí es durable.

La Fase 5 ya estableció que el error del modelo crece de forma
estructural (régimen regulatorio + tendencia de volatilidad) — esto es
precisamente lo que avisa si el modelo se degrada MÁS de lo esperable,
no un añadido decorativo.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from src.model.metrics import mae, n_valid, rmse
from src.storage.predictions_log import load_predictions_log

PRECIO_SPOT_INDICATOR_ID = 600
PRECIO_SPOT_GEO_ID = 3


def load_predictions_with_actuals(conn: sqlite3.Connection, predictions_log_path: Path) -> pd.DataFrame:
    """Predicciones cuya hora objetivo ya tiene precio real conocido."""
    log = load_predictions_log(predictions_log_path)
    if log.empty:
        return pd.DataFrame(columns=["target_datetime_utc", "predicted_price", "actual_price"])

    query = """
        SELECT datetime_utc AS target_datetime_utc, value AS actual_price
        FROM observations
        WHERE source = 'esios' AND indicator_id = ? AND geo_id = ?
    """
    actuals = pd.read_sql_query(query, conn, params=(PRECIO_SPOT_INDICATOR_ID, PRECIO_SPOT_GEO_ID))

    merged = log.merge(actuals, on="target_datetime_utc", how="inner")
    merged["predicted_price"] = merged["predicted_price"].astype(float)
    merged["actual_price"] = merged["actual_price"].astype(float)
    return merged.sort_values("target_datetime_utc")


def recent_error(conn: sqlite3.Connection, predictions_log_path: Path, days: int = 7) -> dict:
    """MAE/RMSE de las predicciones de los últimos `days` días con
    precio real ya disponible."""
    df = load_predictions_with_actuals(conn, predictions_log_path)
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
