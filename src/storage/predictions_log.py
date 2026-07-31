"""Registro histórico de predicciones, versionado en git
(`docs/data/predictions_log.json`) -- NO solo en la tabla `predictions`
de SQLite.

Por qué hace falta además de la tabla SQL: `data/electricidad.db` vive
en la cache de GitHub Actions, y `hourly.yml` la restaura pero no la
guarda (a propósito, para no subir 230MB de cache 24 veces al día -- ver
ese fichero). Cualquier predicción que un run horario escriba solo en
SQLite desaparece en cuanto termina el job: el siguiente run horario
restaura otra vez el snapshot que dejó el último `daily.yml`, sin rastro
de lo que se predijo entre medias. Además, como OMIE publica el día
completo con antelación, ni siquiera el job diario encuentra casi nunca
horas "sin publicar" que predecir en el momento en que corre -- así que
la tabla SQL rara vez llega a tener filas en producción.

Este fichero, en cambio, vive en `docs/data/` y se comitea a git en
CADA ejecución (diaria u horaria) junto al resto del dashboard: es
durable por construcción, sin depender de que la cache sobreviva.

Formato `{columns, rows}` con una fila por línea de texto (igual que
`summary.json`), para que el diff de cada commit sea pequeño.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

LOG_COLUMNS = ["target_datetime_utc", "predicted_price", "model_version", "made_at"]


def _normalize_utc(value) -> str:
    ts = pd.Timestamp(value)
    ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def load_predictions_log(path: Path) -> pd.DataFrame:
    """Lee el log completo. Vacío (con las columnas correctas) si el
    fichero todavía no existe -- la primera vez que corre el pipeline."""
    if not path.exists():
        return pd.DataFrame(columns=LOG_COLUMNS)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return pd.DataFrame(data["rows"], columns=data["columns"])


def append_predictions_log(path: Path, preds_df: pd.DataFrame, model_version: str) -> pd.DataFrame:
    """Añade (o actualiza, si la hora ya estaba) las predicciones de
    `preds_df` (columnas datetime_utc, predicted_price) al log
    persistente, y lo reescribe en disco.

    Si una misma hora objetivo se predice varias veces en runs
    sucesivos (normal: sigue "sin publicar" hasta que OMIE publica su
    precio), se queda con la ÚLTIMA -- la previsión más informada antes
    de que el precio se conociera. Una vez esa hora deja de aparecer en
    `preds_df` (porque ya se publicó su precio), su fila queda congelada
    tal cual: es el registro histórico de "qué predijimos antes de
    saberlo", que es lo que hace falta para el scatter predicho-vs-real
    y para el error real de monitorización.

    Devuelve el log completo ya actualizado.
    """
    existing = load_predictions_log(path)
    made_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    new_rows = pd.DataFrame(
        {
            "target_datetime_utc": [_normalize_utc(t) for t in preds_df["datetime_utc"]],
            "predicted_price": [round(float(v), 2) for v in preds_df["predicted_price"]],
            "model_version": model_version,
            "made_at": made_at,
        }
    )

    combined = pd.concat([existing, new_rows], ignore_index=True)
    combined = combined.drop_duplicates(subset="target_datetime_utc", keep="last")
    combined = combined.sort_values("target_datetime_utc").reset_index(drop=True)

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("{\n")
        f.write('  "columns": ' + json.dumps(LOG_COLUMNS, ensure_ascii=False) + ",\n")
        f.write('  "rows": [\n')
        rows = combined[LOG_COLUMNS].values.tolist()
        for i, row in enumerate(rows):
            comma = "," if i < len(rows) - 1 else ""
            f.write("    " + json.dumps(row, ensure_ascii=False) + comma + "\n")
        f.write("  ]\n}\n")

    return combined
