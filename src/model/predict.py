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
    """Predicciones sobre las últimas `hours` horas con FEATURES
    completas disponibles en `df` -- incluye horas futuras si las
    previsiones D+1 (demanda_prevista, prevision_eolica, prevision_fv)
    ya están ingeridas para esas horas (ver scripts/ingest_incremental.py,
    FORECAST_HORIZON_HOURS).

    Importante: se exige que las FEATURES estén completas, pero NO el
    target (`precio_spot`) -- para una hora futura el precio real
    todavía no existe por definición (es lo que se predice), así que
    un dropna() sobre el frame completo tiraría siempre esas filas.

    Las columnas derivadas de indicadores "reales" (lag24h/48h/168h y
    rollmean24h/168h) solo se pueden calcular de verdad hasta la última
    hora con dato real conocido: una media móvil de las últimas 168h
    de un indicador real, calculada para una fila 5 horas en el
    futuro, necesitaría datos reales de dentro de 3 horas -- que no
    existen todavía. Más allá de ese punto se "congela" el último
    valor conocido hacia adelante (forward-fill) en vez de dejarlo en
    NaN: es la técnica estándar en forecasting multi-step para
    features derivadas de historia reciente que aún no ha ocurrido
    (asume que la tendencia reciente se mantiene en el corto plazo).

    Devuelve un DataFrame con columnas datetime_utc, predicted_price
    (vacío si no hay ninguna fila usable).
    """
    frame = build_training_frame(df, catalog)
    frame = add_trend_feature(frame, reference_date=POST_TOPE_INICIO)

    derived_columns = [c for c in frame.columns if "_lag" in c or "_rollmean" in c]
    frame[derived_columns] = frame[derived_columns].ffill()

    regime = assign_regime(frame.index)
    post_tope = frame[regime.values == "post_tope"]
    usable = post_tope.dropna(subset=feature_columns)

    if usable.empty:
        return pd.DataFrame(columns=["datetime_utc", "predicted_price"])

    recent = usable.tail(hours)
    predictions = model.predict(recent[feature_columns])

    return pd.DataFrame({"datetime_utc": recent.index, "predicted_price": predictions})
