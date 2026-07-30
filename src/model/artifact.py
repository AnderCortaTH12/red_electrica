"""Convención de guardado/carga de modelos, agnóstica al algoritmo.

Cualquier script de entrenamiento (LightGBM hoy, otra cosa mañana)
solo tiene que llamar a `save_model_artifact()` con estos argumentos.
El servicio (`src/serving/api.py`) solo conoce este contrato — nunca
importa lightgbm, sklearn ni ningún algoritmo concreto directamente,
así que cambiar de modelo no requiere tocar la API.

`model_version` es el propio timestamp de entrenamiento (UTC, ISO
8601): simple, monótono, y responde directamente a "¿de cuándo es el
modelo que me está sirviendo esto?" sin tener que mirar el código.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import joblib

MODEL_PATH = Path("models/model.joblib")
METADATA_PATH = Path("models/model_metadata.json")


class PredictiveModel(Protocol):
    """Cualquier objeto con .predict(X) -> array-like sirve (sklearn,
    LightGBM, o un wrapper propio)."""

    def predict(self, X: Any) -> Any: ...


def save_model_artifact(
    model: PredictiveModel,
    feature_columns: list[str],
    model_type: str,
    metrics: dict,
    target: str = "precio_spot",
    model_path: Path = MODEL_PATH,
    metadata_path: Path = METADATA_PATH,
) -> dict:
    """Guarda el modelo + su metadata en el formato que espera la API.

    Devuelve la metadata guardada (útil para tests/logging).
    """
    trained_at = datetime.now(timezone.utc).isoformat()
    metadata = {
        "model_type": model_type,
        "model_version": trained_at,
        "trained_at": trained_at,
        "target": target,
        "feature_columns": feature_columns,
        "metrics": metrics,
    }
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, model_path)
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    return metadata


def load_model_artifact(
    model_path: Path = MODEL_PATH, metadata_path: Path = METADATA_PATH
) -> tuple[PredictiveModel, dict]:
    """Carga el modelo activo + su metadata. Lanza FileNotFoundError
    con un mensaje claro si todavía no se ha entrenado nada."""
    if not model_path.exists() or not metadata_path.exists():
        raise FileNotFoundError(
            f"No hay modelo entrenado en {model_path}. "
            "Ejecuta un script de entrenamiento primero "
            "(p.ej. python -m scripts.train_lightgbm)."
        )
    model = joblib.load(model_path)
    with open(metadata_path, encoding="utf-8") as f:
        metadata = json.load(f)
    return model, metadata
