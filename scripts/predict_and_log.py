"""Genera la predicción con el modelo activo y la guarda en la tabla
`predictions`, para poder comparar más tarde contra el precio real ya
conocido (ver scripts/monitor.py y src/monitoring/error_tracking.py).

Uso:
    python -m scripts.predict_and_log
"""

import sys
from datetime import datetime, timezone

from src.features.load import load_catalog, load_wide_dataframe
from src.model.artifact import load_model_artifact
from src.model.predict import latest_predictions
from src.storage.db import get_connection, init_db, insert_predictions

DB_PATH = "data/electricidad.db"
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

    preds = latest_predictions(df, catalog, model, metadata["feature_columns"], hours=HOURS)
    if preds.empty:
        print("No hay datos recientes suficientes para predecir; nada que guardar.")
        conn.close()
        return 0

    preds["datetime_utc"] = preds["datetime_utc"].apply(lambda t: t.isoformat())
    preds = preds.rename(
        columns={"datetime_utc": "target_datetime_utc", "predicted_price": "predicted_price"}
    )
    preds["model_version"] = metadata["model_version"]
    preds["made_at"] = datetime.now(timezone.utc).isoformat()

    n_new = insert_predictions(conn, preds)
    conn.close()

    print(
        f"{len(preds)} predicciones generadas (modelo {metadata['model_version']}), "
        f"{n_new} nuevas guardadas en la tabla predictions."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
