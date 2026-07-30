import numpy as np
import pandas as pd
import pytest

from src.features.build import add_trend_feature, build_training_frame
from src.model.predict import latest_predictions


def sample_catalog():
    forecast_cols = {"demanda_prevista", "prevision_eolica", "prevision_fv"}
    all_cols = [
        "precio_spot", "pvpc", "demanda_prevista", "demanda_real", "gen_eolica",
        "gen_solar_fv", "gen_solar_termica", "gen_nuclear", "gen_hidraulica",
        "gen_ciclo_combinado", "gen_carbon", "prevision_eolica", "prevision_fv",
    ]
    return [{"columna": c, "disponible_antes_de_hora_h": c in forecast_cols} for c in all_cols]


def synthetic_wide_df(n=400, start="2024-02-01"):
    idx = pd.date_range(start, periods=n, freq="h", tz="UTC")
    rng = np.random.default_rng(0)
    cols = [e["columna"] for e in sample_catalog()]
    return pd.DataFrame({c: rng.uniform(10, 100, n) for c in cols}, index=idx)


class DummyModel:
    def predict(self, X):
        return np.full(len(X), 42.0)


def feature_columns_for(df, catalog):
    frame = build_training_frame(df, catalog)
    frame = add_trend_feature(frame)
    return [c for c in frame.columns if c != "precio_spot"]


def test_latest_predictions_returns_requested_hours():
    df = synthetic_wide_df()
    catalog = sample_catalog()
    cols = feature_columns_for(df, catalog)

    result = latest_predictions(df, catalog, DummyModel(), cols, hours=10)

    assert len(result) == 10
    assert list(result.columns) == ["datetime_utc", "predicted_price"]
    assert (result["predicted_price"] == 42.0).all()


def test_latest_predictions_uses_most_recent_rows():
    df = synthetic_wide_df()
    catalog = sample_catalog()
    cols = feature_columns_for(df, catalog)

    result = latest_predictions(df, catalog, DummyModel(), cols, hours=5)

    assert result["datetime_utc"].max() == df.index.max()


def test_latest_predictions_empty_when_no_post_tope_data():
    # todo el rango cae en 'normal' (antes de 2024-01-01)
    df = synthetic_wide_df(start="2015-01-01")
    catalog = sample_catalog()
    cols = feature_columns_for(synthetic_wide_df(), catalog)  # cols validas cualquiera

    result = latest_predictions(df, catalog, DummyModel(), cols, hours=24)

    assert result.empty
    assert list(result.columns) == ["datetime_utc", "predicted_price"]


def test_latest_predictions_missing_feature_column_raises_keyerror():
    df = synthetic_wide_df()
    catalog = sample_catalog()

    with pytest.raises(KeyError):
        latest_predictions(df, catalog, DummyModel(), ["columna_inventada"], hours=5)
