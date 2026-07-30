"""Entrena LightGBM SOLO sobre el régimen post_tope (2024-01-01 -> hoy)
y lo compara contra el baseline naive en el mismo holdout.

Decisión (usuario, tras el análisis de régimen en notebooks/01_eda.ipynb):
sin dummy de régimen -- en producción el modelo siempre correrá en
post_tope (el mecanismo ibérico del tope al gas terminó y no va a
reaparecer), meter categorías de regímenes pasados que nunca se repiten
en inferencia añade complejidad sin beneficio real. En su lugar, se
añade 'dias_desde_referencia' (tendencia) porque el propio post_tope no
es homogéneo: el MAE del baseline escala año a año dentro de él
(18.3 en 2024 -> 36.6 en 2025 -> 66.8 en 2026).

Uso:
    python -m scripts.train_lightgbm
"""

import json
import sqlite3

from src.features.build import add_trend_feature, build_training_frame
from src.features.load import load_catalog, load_wide_dataframe
from src.model.artifact import save_model_artifact
from src.model.baseline import naive_forecast
from src.model.evaluate import evaluate_by_year, train_test_split_by_date
from src.model.lgbm import predict, train
from src.model.metrics import mae, rmse
from src.model.regimes import assign_regime

DB_PATH = "data/electricidad.db"
TEST_START = "2025-08-01T00:00"  # mismo holdout que scripts/train_baseline.py
POST_TOPE_INICIO = "2024-01-01T00:00"
METRICS_OUTPUT = "models/lightgbm_metrics.json"  # informe detallado (este experimento)


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    catalog = load_catalog()
    df = load_wide_dataframe(conn, catalog)
    conn.close()

    # features leakage-safe sobre el historico completo: los lags de las
    # primeras filas de post_tope usan datos de antes de 2024, es correcto
    # (un lag mira al pasado real, no depende de en que regimen estemos)
    frame = build_training_frame(df, catalog)
    frame = add_trend_feature(frame, reference_date=POST_TOPE_INICIO)

    regime = assign_regime(frame.index)
    post_tope = frame[regime.values == "post_tope"].dropna()

    train_df, test_df = train_test_split_by_date(post_tope, TEST_START)
    print(f"Train: {len(train_df)} filas ({train_df.index.min()} -> {train_df.index.max()})")
    print(f"Test:  {len(test_df)} filas ({test_df.index.min()} -> {test_df.index.max()})")

    X_train, y_train = train_df.drop(columns=["precio_spot"]), train_df["precio_spot"]
    X_test, y_test = test_df.drop(columns=["precio_spot"]), test_df["precio_spot"]

    model = train(X_train, y_train)
    y_pred = predict(model, X_test)

    lgbm_mae, lgbm_rmse = mae(y_test, y_pred), rmse(y_test, y_pred)
    print(f"\n== LightGBM (post_tope, holdout {TEST_START} -> hoy) ==")
    print(f"MAE:  {lgbm_mae:.2f} EUR/MWh")
    print(f"RMSE: {lgbm_rmse:.2f} EUR/MWh")

    # comparacion directa contra el baseline naive, en el MISMO holdout
    baseline_pred_full = naive_forecast(df, lag_hours=24)
    baseline_pred_test = baseline_pred_full.loc[y_test.index]
    baseline_mae = mae(y_test, baseline_pred_test)
    baseline_rmse = rmse(y_test, baseline_pred_test)
    improvement_pct = (baseline_mae - lgbm_mae) / baseline_mae * 100

    print("\n== Baseline naive (mismo holdout, para comparar) ==")
    print(f"MAE:  {baseline_mae:.2f} EUR/MWh")
    print(f"RMSE: {baseline_rmse:.2f} EUR/MWh")
    print(f"\nMejora de LightGBM sobre el baseline: {improvement_pct:+.1f}% en MAE")

    # desglose año a año dentro de post_tope: ¿LightGBM tambien degrada
    # progresivamente, o se mantiene mas estable que el baseline?
    full_pred = predict(model, post_tope.drop(columns=["precio_spot"]))
    lgbm_yearly = evaluate_by_year(post_tope["precio_spot"], full_pred)
    baseline_yearly = evaluate_by_year(
        post_tope["precio_spot"], baseline_pred_full.loc[post_tope.index]
    )

    print("\n-- LightGBM por año (post_tope completo) --")
    print(lgbm_yearly.to_string(index=False, float_format=lambda x: f"{x:,.2f}"))
    print("\n-- Baseline por año (post_tope completo, para comparar) --")
    print(baseline_yearly.to_string(index=False, float_format=lambda x: f"{x:,.2f}"))

    feature_importance = dict(
        sorted(
            zip(X_train.columns, [int(v) for v in model.feature_importances_]),
            key=lambda kv: kv[1],
            reverse=True,
        )
    )

    results = {
        "modelo": "lightgbm",
        "regimen": "post_tope",
        "test_start": TEST_START,
        "n_train": len(train_df),
        "n_test": len(test_df),
        "lightgbm_mae": lgbm_mae,
        "lightgbm_rmse": lgbm_rmse,
        "baseline_mae": baseline_mae,
        "baseline_rmse": baseline_rmse,
        "mejora_pct_mae": improvement_pct,
        "lightgbm_por_anio": lgbm_yearly.to_dict(orient="records"),
        "baseline_por_anio": baseline_yearly.to_dict(orient="records"),
        "feature_importance": feature_importance,
    }
    with open(METRICS_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"Métricas guardadas: {METRICS_OUTPUT}")

    # Modelo servido en produccion (src/serving/api.py): se reentrena con
    # TODO el post_tope disponible (train+test), no solo con train_df --
    # las metricas de arriba (holdout honesto) son las que se reportan,
    # pero el modelo que sirve la API aprovecha tambien los datos mas
    # recientes. La API solo conoce el contrato de save_model_artifact,
    # nunca lightgbm directamente: cambiar de algoritmo aqui no requiere
    # tocar src/serving/api.py.
    X_full = post_tope.drop(columns=["precio_spot"])
    y_full = post_tope["precio_spot"]
    final_model = train(X_full, y_full)
    metadata = save_model_artifact(
        final_model,
        feature_columns=list(X_full.columns),
        model_type="lightgbm",
        metrics={
            "holdout_mae": lgbm_mae,
            "holdout_rmse": lgbm_rmse,
            "baseline_holdout_mae": baseline_mae,
            "regimen": "post_tope",
            "nota": "modelo placeholder: pierde contra el baseline, ver README",
        },
    )
    print(f"\nModelo de produccion guardado (version {metadata['model_version']})")


if __name__ == "__main__":
    main()
