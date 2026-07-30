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


def test_latest_predictions_reaches_genuine_future_rows():
    """Regresion: si las previsiones D+1 (demanda_prevista/prevision_eolica/
    prevision_fv) llegan mas lejos en el tiempo que los indicadores
    'reales' (que por definicion no existen para el futuro), las horas
    futuras deben poder predecirse igualmente -- ni el target ausente
    ni los lags/rollmeans de los indicadores reales (congelados hacia
    adelante) deben bloquearlas.
    """
    catalog = sample_catalog()
    df = synthetic_wide_df(n=400)

    # simula "ahora": las columnas 'reales' (todo menos las 3 previsiones
    # D+1) no tienen datos en las ultimas 5 horas, pero las previsiones
    # SI (como pasa de verdad: ESIOS las publica con antelacion)
    forecast_cols = {"demanda_prevista", "prevision_eolica", "prevision_fv"}
    real_cols = [c for c in df.columns if c not in forecast_cols]
    df.loc[df.index[-5:], real_cols] = float("nan")

    cols = feature_columns_for(synthetic_wide_df(n=400), catalog)

    result = latest_predictions(df, catalog, DummyModel(), cols, hours=10)

    assert result["datetime_utc"].max() == df.index.max()
    assert len(result) == 10


def test_latest_predictions_forward_fills_derived_columns_for_future_rows():
    catalog = sample_catalog()
    df = synthetic_wide_df(n=400)
    forecast_cols = {"demanda_prevista", "prevision_eolica", "prevision_fv"}
    real_cols = [c for c in df.columns if c not in forecast_cols]
    df.loc[df.index[-3:], real_cols] = float("nan")

    frame = build_training_frame(df, catalog)
    frame = add_trend_feature(frame)
    derived_cols = [c for c in frame.columns if "_lag" in c or "_rollmean" in c]

    # sin forward-fill, las filas futuras tendrian NaN en las columnas derivadas
    assert frame[derived_cols].tail(3).isna().any().any()

    cols = feature_columns_for(synthetic_wide_df(n=400), catalog)
    result = latest_predictions(df, catalog, DummyModel(), cols, hours=3)

    # con el forward-fill dentro de latest_predictions, si se pueden predecir
    assert len(result) == 3
