"""Tests de la API de servicio. La API es agnostica al algoritmo, asi
que los tests mockean load_model_artifact() con un modelo de juguete
(no lightgbm) para verificar justamente eso: que la API no depende de
ningun algoritmo concreto. La capa de datos (load_wide_dataframe) se
mockea para no depender de electricidad.db; el resto del pipeline de
features (build_training_frame, add_trend_feature, assign_regime)
corre de verdad sobre datos sinteticos.
"""

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import src.serving.api as api_module
from src.serving.api import app


class DummyModel:
    def predict(self, X):
        return np.full(len(X), 55.5)


def sample_catalog():
    forecast_cols = {"demanda_prevista", "prevision_eolica", "prevision_fv"}
    all_cols = [
        "precio_spot",
        "pvpc",
        "demanda_prevista",
        "demanda_real",
        "gen_eolica",
        "gen_solar_fv",
        "gen_solar_termica",
        "gen_nuclear",
        "gen_hidraulica",
        "gen_ciclo_combinado",
        "gen_carbon",
        "prevision_eolica",
        "prevision_fv",
    ]
    return [{"columna": c, "disponible_antes_de_hora_h": c in forecast_cols} for c in all_cols]


def synthetic_wide_df(n=400):
    idx = pd.date_range("2024-02-01", periods=n, freq="h", tz="UTC")
    rng = np.random.default_rng(0)
    cols = [e["columna"] for e in sample_catalog()]
    data = {c: rng.uniform(10, 100, n) for c in cols}
    return pd.DataFrame(data, index=idx)


class DummyConnection:
    def close(self):
        pass


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(api_module, "load_catalog", lambda *a, **kw: sample_catalog())
    monkeypatch.setattr(api_module, "load_wide_dataframe", lambda *a, **kw: synthetic_wide_df())
    monkeypatch.setattr(api_module.sqlite3, "connect", lambda *a, **kw: DummyConnection())
    return TestClient(app)


def fake_metadata():
    return {
        "model_type": "dummy",
        "model_version": "2026-01-01T00:00:00+00:00",
        "trained_at": "2026-01-01T00:00:00+00:00",
        "target": "precio_spot",
        "feature_columns": None,  # se rellena por test segun columnas reales
        "metrics": {},
    }


def test_health_without_model(client, monkeypatch):
    def raise_not_found(*a, **kw):
        raise FileNotFoundError("no model")

    monkeypatch.setattr(api_module, "load_model_artifact", raise_not_found)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok_sin_modelo"


def test_health_with_model_exposes_version_and_trained_at(client, monkeypatch):
    metadata = fake_metadata()
    monkeypatch.setattr(api_module, "load_model_artifact", lambda: (DummyModel(), metadata))

    response = client.get("/health")

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "ok"
    assert body["model_type"] == "dummy"
    assert body["model_version"] == "2026-01-01T00:00:00+00:00"
    assert body["trained_at"] == "2026-01-01T00:00:00+00:00"


def test_predict_without_model_returns_503(client, monkeypatch):
    def raise_not_found(*a, **kw):
        raise FileNotFoundError("no model")

    monkeypatch.setattr(api_module, "load_model_artifact", raise_not_found)

    response = client.get("/predict")

    assert response.status_code == 503


def test_predict_returns_predictions_with_model_metadata(client, monkeypatch):
    # feature_columns validos: las que produce build_training_frame para
    # el catalogo sintetico (calendario + previsiones + lags/rollmeans)
    from src.features.build import add_trend_feature, build_training_frame

    frame = build_training_frame(synthetic_wide_df(), sample_catalog())
    frame = add_trend_feature(frame)
    feature_columns = [c for c in frame.columns if c != "precio_spot"]

    metadata = fake_metadata()
    metadata["feature_columns"] = feature_columns
    monkeypatch.setattr(api_module, "load_model_artifact", lambda: (DummyModel(), metadata))

    response = client.get("/predict?hours=5")

    assert response.status_code == 200
    body = response.json()
    assert body["model_type"] == "dummy"
    assert body["model_version"] == metadata["model_version"]
    assert "note" in body and len(body["note"]) > 0
    assert len(body["predictions"]) == 5
    assert all(p["predicted_price_eur_mwh"] == 55.5 for p in body["predictions"])


def test_predict_missing_feature_columns_returns_500(client, monkeypatch):
    metadata = fake_metadata()
    metadata["feature_columns"] = ["una_columna_que_no_existe"]
    monkeypatch.setattr(api_module, "load_model_artifact", lambda: (DummyModel(), metadata))

    response = client.get("/predict")

    assert response.status_code == 500


def test_predict_default_hours_is_24(client, monkeypatch):
    from src.features.build import add_trend_feature, build_training_frame

    frame = build_training_frame(synthetic_wide_df(), sample_catalog())
    frame = add_trend_feature(frame)
    feature_columns = [c for c in frame.columns if c != "precio_spot"]

    metadata = fake_metadata()
    metadata["feature_columns"] = feature_columns
    monkeypatch.setattr(api_module, "load_model_artifact", lambda: (DummyModel(), metadata))

    response = client.get("/predict")

    assert len(response.json()["predictions"]) == 24
