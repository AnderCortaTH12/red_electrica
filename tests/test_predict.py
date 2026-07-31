import numpy as np
import pandas as pd
import pytest

from src.features.build import add_trend_feature, build_training_frame
from src.model.predict import forecast_unpublished_hours

FORECAST_COLS = {"demanda_prevista", "prevision_eolica", "prevision_fv"}


def sample_catalog():
    all_cols = [
        "precio_spot", "pvpc", "demanda_prevista", "demanda_real", "gen_eolica",
        "gen_solar_fv", "gen_solar_termica", "gen_nuclear", "gen_hidraulica",
        "gen_ciclo_combinado", "gen_carbon", "prevision_eolica", "prevision_fv",
    ]
    return [{"columna": c, "disponible_antes_de_hora_h": c in FORECAST_COLS} for c in all_cols]


def synthetic_wide_df(n=400, start="2024-02-01"):
    idx = pd.date_range(start, periods=n, freq="h", tz="UTC")
    rng = np.random.default_rng(0)
    cols = [e["columna"] for e in sample_catalog()]
    return pd.DataFrame({c: rng.uniform(10, 100, n) for c in cols}, index=idx)


def df_with_unpublished_tail(n=400, unpublished=24):
    """Escenario realista: las ultimas `unpublished` horas todavia no
    tienen precio publicado por OMIE ni datos de indicadores 'reales',
    pero SI tienen las previsiones D+1 que ESIOS publica por adelantado.
    """
    df = synthetic_wide_df(n=n)
    real_cols = [c for c in df.columns if c not in FORECAST_COLS]
    df.loc[df.index[-unpublished:], real_cols] = float("nan")
    return df


class DummyModel:
    def predict(self, X):
        return np.full(len(X), 42.0)


def feature_columns_for(df, catalog):
    frame = build_training_frame(df, catalog)
    frame = add_trend_feature(frame)
    return [c for c in frame.columns if c != "precio_spot"]


def test_predicts_only_hours_after_the_last_published_price():
    """El nucleo del contrato: OMIE publica de golpe las 24h del dia
    siguiente, asi que solo las horas posteriores al ultimo precio
    conocido son una prediccion de verdad. Predecir horas ya publicadas
    seria etiquetar como 'prediccion' un dato ya conocido.
    """
    catalog = sample_catalog()
    df = df_with_unpublished_tail(unpublished=24)
    cols = feature_columns_for(synthetic_wide_df(), catalog)

    result = forecast_unpublished_hours(df, catalog, DummyModel(), cols, hours=24)

    ultimo_publicado = df["precio_spot"].dropna().index.max()
    assert len(result) == 24
    assert result["datetime_utc"].min() > ultimo_publicado
    assert result["datetime_utc"].max() == df.index.max()


def test_empty_when_every_hour_already_has_a_published_price():
    """Si no hay ninguna hora sin publicar, no hay nada que predecir --
    devolver las ultimas horas conocidas (comportamiento anterior) era
    justamente el bug."""
    catalog = sample_catalog()
    df = synthetic_wide_df()  # precio_spot completo hasta el final
    cols = feature_columns_for(df, catalog)

    result = forecast_unpublished_hours(df, catalog, DummyModel(), cols, hours=24)

    assert result.empty
    assert list(result.columns) == ["datetime_utc", "predicted_price"]


def test_respects_the_hours_limit():
    catalog = sample_catalog()
    df = df_with_unpublished_tail(unpublished=24)
    cols = feature_columns_for(synthetic_wide_df(), catalog)

    result = forecast_unpublished_hours(df, catalog, DummyModel(), cols, hours=6)

    assert len(result) == 6
    # las 6 PRIMERAS horas no publicadas, no las 6 ultimas
    ultimo_publicado = df["precio_spot"].dropna().index.max()
    assert result["datetime_utc"].min() == ultimo_publicado + pd.Timedelta(hours=1)


def test_returns_dataframe_shape_and_model_output():
    catalog = sample_catalog()
    df = df_with_unpublished_tail(unpublished=10)
    cols = feature_columns_for(synthetic_wide_df(), catalog)

    result = forecast_unpublished_hours(df, catalog, DummyModel(), cols, hours=10)

    assert list(result.columns) == ["datetime_utc", "predicted_price"]
    assert (result["predicted_price"] == 42.0).all()


def test_empty_when_no_post_tope_data():
    # todo el rango cae en 'normal' (antes de 2024-01-01)
    df = df_with_unpublished_tail(n=400)
    df.index = pd.date_range("2015-01-01", periods=len(df), freq="h", tz="UTC")
    catalog = sample_catalog()
    cols = feature_columns_for(synthetic_wide_df(), catalog)

    result = forecast_unpublished_hours(df, catalog, DummyModel(), cols, hours=24)

    assert result.empty


def test_missing_feature_column_raises_keyerror():
    df = df_with_unpublished_tail()
    catalog = sample_catalog()

    with pytest.raises(KeyError):
        forecast_unpublished_hours(df, catalog, DummyModel(), ["columna_inventada"], hours=5)


def test_forward_fills_derived_columns_for_future_rows():
    """Los lag/rollmean de indicadores 'reales' no se pueden calcular
    para horas futuras (necesitarian datos que aun no existen); sin el
    forward-fill quedarian NaN y bloquearian la prediccion."""
    catalog = sample_catalog()
    df = df_with_unpublished_tail(unpublished=3)

    frame = build_training_frame(df, catalog)
    frame = add_trend_feature(frame)
    derived_cols = [c for c in frame.columns if "_lag" in c or "_rollmean" in c]
    assert frame[derived_cols].tail(3).isna().any().any()  # sin ffill: NaN

    cols = feature_columns_for(synthetic_wide_df(), catalog)
    result = forecast_unpublished_hours(df, catalog, DummyModel(), cols, hours=3)

    assert len(result) == 3
