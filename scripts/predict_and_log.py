"""Genera la predicción con el modelo activo y la guarda: en la tabla
`predictions` de SQLite (para monitor.py dentro de la MISMA ejecución) y
en `docs/data/predictions_log.json`, versionado en git (para que
sobreviva entre ejecuciones -- ver src/storage/predictions_log.py para
el porqué de necesitar ambas).

Uso:
    python -m scripts.predict_and_log
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

from src.features.load import load_catalog, load_wide_dataframe
from src.model.artifact import load_model_artifact
from src.model.predict import forecast_unpublished_hours
from src.storage.db import get_connection, init_db, insert_predictions
from src.storage.predictions_log import append_predictions_log

DB_PATH = "data/electricidad.db"
PREDICTIONS_LOG_PATH = Path("docs/data/predictions_log.json")
HOURS = 24


def main() -> int:
    try:
        model, metadata = load_model_artifact()
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}")
        return 1

    conn = get_connection(DB_PATH)
    init_db(conn)
    catalog = load_catalog()
    df = load_wide_dataframe(conn, catalog)

    preds = forecast_unpublished_hours(df, catalog, model, metadata["feature_columns"], hours=HOURS)
    if preds.empty:
        print("No hay horas sin publicar que predecir ahora mismo; nada que guardar.")
        conn.close()
        return 0

    append_predictions_log(PREDICTIONS_LOG_PATH, preds, metadata["model_version"])

    # el formato canonico ...Z lo aplica insert_predictions (ver
    # normalize_datetime_utc en src/storage/db.py); aqui basta con
    # pasar los Timestamp tal cual
    preds_for_db = preds.rename(columns={"datetime_utc": "target_datetime_utc"})
    preds_for_db["model_version"] = metadata["model_version"]
    preds_for_db["made_at"] = datetime.now(timezone.utc).isoformat()

    n_new = insert_predictions(conn, preds_for_db)
    conn.close()

    print(
        f"{len(preds)} predicciones generadas (modelo {metadata['model_version']}), "
        f"{n_new} nuevas en la tabla SQLite, log persistente actualizado en {PREDICTIONS_LOG_PATH}."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
