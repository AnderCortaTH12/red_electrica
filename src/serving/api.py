"""API de servicio del modelo de precio spot.

Agnóstica al algoritmo: solo conoce el contrato de
`src.model.artifact` (model.joblib + model_metadata.json). Nunca
importa lightgbm, sklearn ni ningún algoritmo concreto directamente —
cambiar de modelo (features, algoritmo, target) solo requiere que el
script de entrenamiento de turno llame a `save_model_artifact()` con
la forma esperada; esta API no cambia.

Arranque local:
    uvicorn src.serving.api:app --reload
"""

from __future__ import annotations

import sqlite3

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from src.features.build import add_trend_feature, build_training_frame
from src.features.load import load_catalog, load_wide_dataframe
from src.model.artifact import load_model_artifact
from src.model.regimes import assign_regime

DB_PATH = "data/electricidad.db"
POST_TOPE_INICIO = "2024-01-01T00:00"

app = FastAPI(
    title="Forecasting Eléctrico API",
    description="Sirve el modelo de precio spot actualmente entrenado, sea cual sea.",
)


class PredictionPoint(BaseModel):
    datetime_utc: str
    predicted_price_eur_mwh: float


class PredictResponse(BaseModel):
    model_type: str
    model_version: str
    trained_at: str
    note: str
    predictions: list[PredictionPoint]


class HealthResponse(BaseModel):
    status: str
    model_type: str | None = None
    model_version: str | None = None
    trained_at: str | None = None


def _model_info() -> dict | None:
    try:
        _, metadata = load_model_artifact()
    except FileNotFoundError:
        return None
    return metadata


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness + qué modelo está cargado ahora mismo (si hay alguno)."""
    metadata = _model_info()
    if metadata is None:
        return HealthResponse(status="ok_sin_modelo")
    return HealthResponse(
        status="ok",
        model_type=metadata["model_type"],
        model_version=metadata["model_version"],
        trained_at=metadata["trained_at"],
    )


@app.get("/predict", response_model=PredictResponse)
def predict(hours: int = 24) -> PredictResponse:
    """Predicciones sobre las últimas `hours` horas con features
    completas disponibles en la base de datos.

    IMPORTANTE (honesto sobre el alcance actual): esto NO es todavía
    una previsión de las próximas 24h reales. Sería eso si la ingesta
    diaria (Fase 7) trajera también las previsiones D+1 de demanda/
    eólica/fotovoltaica que publica ESIOS con antelación -- hoy la
    ingesta solo trae datos hasta "ahora", así que la ventana más
    reciente con features completas es, como mucho, el presente
    reciente, no el futuro. El campo `note` de la respuesta lo deja
    explícito para quien consuma la API sin leer el código.
    """
    try:
        model, metadata = load_model_artifact()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    conn = sqlite3.connect(DB_PATH)
    catalog = load_catalog()
    df = load_wide_dataframe(conn, catalog)
    conn.close()

    frame = build_training_frame(df, catalog)
    frame = add_trend_feature(frame, reference_date=POST_TOPE_INICIO)
    regime = assign_regime(frame.index)
    usable = frame[regime.values == "post_tope"].dropna()

    if usable.empty:
        raise HTTPException(
            status_code=503, detail="No hay datos recientes suficientes para predecir."
        )

    feature_columns = metadata["feature_columns"]
    missing = set(feature_columns) - set(usable.columns)
    if missing:
        raise HTTPException(
            status_code=500,
            detail=(
                "El modelo espera columnas que ya no existen en el pipeline "
                f"de features actual: {sorted(missing)}. Reentrena el modelo."
            ),
        )

    recent = usable.tail(hours)
    predictions = model.predict(recent[feature_columns])

    points = [
        PredictionPoint(
            datetime_utc=timestamp.isoformat(), predicted_price_eur_mwh=float(value)
        )
        for timestamp, value in zip(recent.index, predictions)
    ]

    return PredictResponse(
        model_type=metadata["model_type"],
        model_version=metadata["model_version"],
        trained_at=metadata["trained_at"],
        note=(
            "Predicciones sobre las horas más recientes con datos completos "
            "en la base de datos, no una previsión real de horas futuras "
            "todavía (pendiente de la ingesta diaria de previsiones D+1, "
            "Fase 7)."
        ),
        predictions=points,
    )
