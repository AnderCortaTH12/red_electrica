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


def forecast_unpublished_hours(
    df: pd.DataFrame,
    catalog: list[dict],
    model,
    feature_columns: list[str],
    hours: int = 24,
) -> pd.DataFrame:
    """Predice las próximas `hours` horas cuyo precio spot TODAVÍA NO se
    ha publicado, es decir, las estrictamente posteriores al último
    `precio_spot` conocido en `df`.

    Por qué "no publicado" y no "las últimas horas disponibles": el
    mercado diario español (OMIE) es una subasta que publica DE GOLPE
    las 24 horas del día siguiente sobre las 13:00 CET. Predecir horas
    anteriores a ese corte no es predecir: su precio ya está publicado y
    es un dato conocido, no una incógnita. La versión anterior de esta
    función cogía `.tail(hours)` de las filas con features completas, lo
    que en la práctica devolvía siempre horas ya publicadas y las
    etiquetaba como "predicción" en el dashboard.

    El job diario corre a las 06:00 UTC (08:00 CET), antes de esa
    subasta, así que el horizonte genuinamente desconocido en ese
    momento son las 24 horas de mañana (D+1) -- que es justo lo que
    tiene valor predecir.

    Se exige que las FEATURES estén completas, pero NO el target: para
    una hora futura el precio real no existe todavía por definición (es
    lo que se predice), así que un dropna() sobre el frame completo
    tiraría siempre esas filas.

    Las columnas derivadas de indicadores "reales" (lag24h/48h/168h y
    rollmean24h/168h) solo se pueden calcular de verdad hasta la última
    hora con dato real conocido: una media móvil de las últimas 168h de
    un indicador real, calculada para una fila 5 horas en el futuro,
    necesitaría datos reales de dentro de 3 horas -- que no existen
    todavía. Más allá de ese punto se "congela" el último valor conocido
    hacia adelante (forward-fill) en vez de dejarlo en NaN: es la
    técnica estándar en forecasting multi-step para features derivadas
    de historia reciente que aún no ha ocurrido.

    Devuelve un DataFrame con columnas datetime_utc, predicted_price.
    Vacío si no hay ninguna hora futura con features completas -- p.ej.
    si las previsiones D+1 de ESIOS aún no cubren el día siguiente.
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

    # ultimo instante con precio ya publicado: todo lo posterior es lo
    # unico que tiene sentido llamar "prediccion"
    known_prices = df["precio_spot"].dropna() if "precio_spot" in df.columns else pd.Series(dtype=float)
    if not known_prices.empty:
        usable = usable[usable.index > known_prices.index.max()]

    if usable.empty:
        return pd.DataFrame(columns=["datetime_utc", "predicted_price"])

    horizon = usable.head(hours)
    predictions = model.predict(horizon[feature_columns])

    return pd.DataFrame({"datetime_utc": horizon.index, "predicted_price": predictions})
