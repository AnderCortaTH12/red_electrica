"""Genera predicciones reutilizando el mismo pipeline de features que
el entrenamiento (build_training_frame + add_trend_feature + filtro de
régimen post_tope). Compartido por la API (src/serving/api.py) y por
el job diario (scripts/predict_and_log.py) para que ambos predigan
exactamente igual.
"""

from __future__ import annotations

import pandas as pd

from src.features.build import add_trend_feature, build_training_frame
from src.model.regimes import assign_regime

POST_TOPE_INICIO = "2024-01-01T00:00"


def latest_predictions(
    df: pd.DataFrame,
    catalog: list[dict],
    model,
    feature_columns: list[str],
    hours: int = 24,
) -> pd.DataFrame:
    """Predicciones sobre las últimas `hours` horas con features
    completas disponibles en `df`.

    NO son todavía una previsión real de horas futuras: son las horas
    más recientes para las que hay datos completos en la base de datos
    (ver nota en src/serving/api.py sobre el alcance actual).

    Devuelve un DataFrame con columnas datetime_utc, predicted_price
    (vacío si no hay ninguna fila usable).
    """
    frame = build_training_frame(df, catalog)
    frame = add_trend_feature(frame, reference_date=POST_TOPE_INICIO)
    regime = assign_regime(frame.index)
    usable = frame[regime.values == "post_tope"].dropna()

    if usable.empty:
        return pd.DataFrame(columns=["datetime_utc", "predicted_price"])

    recent = usable.tail(hours)
    predictions = model.predict(recent[feature_columns])

    return pd.DataFrame({"datetime_utc": recent.index, "predicted_price": predictions})
