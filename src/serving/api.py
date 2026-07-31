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

from src.features.load import load_catalog, load_wide_dataframe
from src.model.artifact import load_model_artifact
from src.model.predict import forecast_unpublished_hours
from src.storage.db import normalize_datetime_utc

DB_PATH = "data/electricidad.db"

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
    completas disponibles en la base de datos -- incluye futuro real
    si las previsiones D+1 (demanda_prevista/prevision_eolica/
    prevision_fv) ya están ingeridas para esas horas (ver
    scripts/ingest_incremental.py, FORECAST_HORIZON_HOURS=48h).

    El horizonte real de predicción varía día a día: está acotado por
    cuál de esas 3 previsiones tenga el horizonte publicado más corto
    en ese momento (ESIOS no publica todas con la misma antelación —
    p.ej. demanda_prevista suele llegar menos lejos que las de
    eólica/fotovoltaica). Si se piden más `hours` de las que hay datos
    para predecir, se devuelven las que haya disponibles, no un error.
    """
    try:
        model, metadata = load_model_artifact()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    conn = sqlite3.connect(DB_PATH)
    catalog = load_catalog()
    df = load_wide_dataframe(conn, catalog)
    conn.close()

    feature_columns = metadata["feature_columns"]
    try:
        preds_df = forecast_unpublished_hours(df, catalog, model, feature_columns, hours=hours)
    except KeyError as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "El modelo espera columnas que ya no existen en el pipeline "
                f"de features actual: {exc}. Reentrena el modelo."
            ),
        ) from exc

    if preds_df.empty:
        raise HTTPException(
            status_code=503,
            detail=(
                "No hay horas que predecir ahora mismo: o bien OMIE ya ha publicado "
                "el precio de todas las horas con features disponibles, o las "
                "previsiones D+1 de ESIOS aun no cubren el dia siguiente."
            ),
        )

    points = [
        PredictionPoint(
            datetime_utc=normalize_datetime_utc(row.datetime_utc),
            predicted_price_eur_mwh=float(row.predicted_price),
        )
        for row in preds_df.itertuples()
    ]

    return PredictResponse(
        model_type=metadata["model_type"],
        model_version=metadata["model_version"],
        trained_at=metadata["trained_at"],
        note=(
            "Incluye horas futuras reales mientras las previsiones D+1 de "
            "ESIOS (demanda, eólica, fotovoltaica) estén ingeridas para "
            "ellas; el horizonte varía día a día según cuánto haya "
            "publicado ESIOS en cada previsión en el momento de la consulta."
        ),
        predictions=points,
    )
