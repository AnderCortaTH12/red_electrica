"""Entrena (sin entrenar nada, es una regla fija) y evalúa el baseline
seasonal naïve: precio de ayer a la misma hora.

Es el número de referencia para toda la Fase 5: cualquier modelo
posterior (LightGBM) tiene que batir esto o no vale la pena.

Uso:
    python -m scripts.train_baseline
"""

import json
import sqlite3

from src.features.load import load_catalog, load_wide_dataframe
from src.model.baseline import naive_forecast
from src.model.evaluate import evaluate_by_year, train_test_split_by_date
from src.model.metrics import mae, n_valid, rmse

DB_PATH = "data/electricidad.db"
TEST_START = "2025-08-01T00:00"  # ultimos ~12 meses como test, resto como "pasado"
LAG_HOURS = 24
OUTPUT_PATH = "models/baseline_metrics.json"


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    catalog = load_catalog()
    df = load_wide_dataframe(conn, catalog)
    conn.close()

    y_true = df["precio_spot"]
    y_pred = naive_forecast(df, lag_hours=LAG_HOURS)

    print("== Baseline seasonal naive (precio de ayer a la misma hora) ==\n")

    print("-- MAE/RMSE por año (histórico completo 2014-hoy) --")
    yearly = evaluate_by_year(y_true, y_pred)
    print(yearly.to_string(index=False, float_format=lambda x: f"{x:,.2f}"))

    _, test = train_test_split_by_date(df, TEST_START)
    y_true_test = test["precio_spot"]
    y_pred_test = naive_forecast(df, lag_hours=LAG_HOURS).loc[test.index]

    test_mae = mae(y_true_test, y_pred_test)
    test_rmse = rmse(y_true_test, y_pred_test)
    test_n = n_valid(y_true_test, y_pred_test)

    print(f"\n-- Periodo de test (holdout, {TEST_START} -> hoy) --")
    print(f"MAE:  {test_mae:.2f} EUR/MWh")
    print(f"RMSE: {test_rmse:.2f} EUR/MWh")
    print(f"N:    {test_n} horas")

    results = {
        "modelo": "baseline_naive",
        "lag_hours": LAG_HOURS,
        "test_start": TEST_START,
        "test_mae": test_mae,
        "test_rmse": test_rmse,
        "test_n": test_n,
        "por_anio": yearly.to_dict(orient="records"),
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nGuardado: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
