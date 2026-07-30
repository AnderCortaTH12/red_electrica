"""Tests de feature engineering, con foco en detectar data leakage:
que ningún feature use información que no estaría disponible en el
momento de predecir la hora H.
"""

import numpy as np
import pandas as pd
import pytest

from src.features.build import (
    add_calendar_features,
    add_lags,
    add_renewable_ratio_lag24h,
    add_rolling_means,
    build_training_frame,
)


@pytest.fixture
def sample_df():
    idx = pd.date_range("2024-01-01", periods=200, freq="h", tz="UTC")
    rng = np.random.default_rng(42)
    return pd.DataFrame(
        {
            "precio_spot": rng.uniform(10, 100, len(idx)),
            "pvpc": rng.uniform(10, 100, len(idx)),
            "demanda_prevista": rng.uniform(20000, 30000, len(idx)),
            "demanda_real": rng.uniform(20000, 30000, len(idx)),
            "gen_eolica": rng.uniform(1000, 5000, len(idx)),
            "gen_solar_fv": rng.uniform(0, 3000, len(idx)),
            "gen_solar_termica": rng.uniform(0, 500, len(idx)),
            "gen_nuclear": rng.uniform(5000, 6000, len(idx)),
            "gen_hidraulica": rng.uniform(500, 2000, len(idx)),
            "gen_ciclo_combinado": rng.uniform(1000, 4000, len(idx)),
            "gen_carbon": rng.uniform(0, 1000, len(idx)),
            "prevision_eolica": rng.uniform(1000, 5000, len(idx)),
            "prevision_fv": rng.uniform(0, 3000, len(idx)),
        },
        index=idx,
    )


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


def test_add_lags_shifts_correctly(sample_df):
    out = add_lags(sample_df, columns=["precio_spot"], lags=[24])
    # el lag24 de la fila 30 debe ser igual al valor original de la fila 6
    assert out["precio_spot_lag24h"].iloc[30] == sample_df["precio_spot"].iloc[30 - 24]


def test_add_lags_first_rows_are_nan(sample_df):
    out = add_lags(sample_df, columns=["precio_spot"], lags=[24])
    assert out["precio_spot_lag24h"].iloc[:24].isna().all()


def test_rolling_mean_excludes_current_hour(sample_df):
    out = add_rolling_means(sample_df, columns=["precio_spot"], windows=[24])
    # la media movil en la fila i debe usar filas [i-24, i-1], nunca la fila i
    expected = sample_df["precio_spot"].iloc[76:100].mean()  # filas 76..99 (24 valores)
    assert out["precio_spot_rollmean24h"].iloc[100] == pytest.approx(expected)


def test_rolling_mean_does_not_equal_including_current_hour(sample_df):
    out = add_rolling_means(sample_df, columns=["precio_spot"], windows=[24])
    including_current = sample_df["precio_spot"].rolling(24).mean()
    # la version segura (excluye hora H) no deberia coincidir con la
    # version que si incluye la hora H (si coincidieran, habria leakage)
    assert not np.isclose(
        out["precio_spot_rollmean24h"].iloc[100], including_current.iloc[100]
    )


def test_calendar_features_no_nan_after_first_rows(sample_df):
    out = add_calendar_features(sample_df)
    assert out["hour"].between(0, 23).all()
    assert out["dayofweek"].between(0, 6).all()
    assert out["is_weekend"].dtype == bool
    assert out["is_holiday"].isin([True, False]).all()


def test_calendar_new_year_is_holiday(sample_df):
    out = add_calendar_features(sample_df)
    new_year_rows = out.index.tz_convert("Europe/Madrid").normalize() == pd.Timestamp(
        "2024-01-01", tz="Europe/Madrid"
    )
    assert out.loc[new_year_rows, "is_holiday"].all()


def test_renewable_ratio_uses_lag24_columns(sample_df):
    lagged = add_lags(
        sample_df,
        columns=["gen_eolica", "gen_solar_fv", "gen_solar_termica", "gen_hidraulica", "demanda_real"],
        lags=[24],
    )
    out = add_renewable_ratio_lag24h(lagged)
    row = 50
    expected = (
        sample_df["gen_eolica"].iloc[row - 24]
        + sample_df["gen_solar_fv"].iloc[row - 24]
        + sample_df["gen_solar_termica"].iloc[row - 24]
        + sample_df["gen_hidraulica"].iloc[row - 24]
    ) / sample_df["demanda_real"].iloc[row - 24]
    assert out["ratio_renovables_lag24h"].iloc[row] == pytest.approx(expected)


def test_build_training_frame_excludes_real_indicators_at_lag_zero(sample_df):
    """Ningun indicador 'real' (demanda_real, gen_*, pvpc) debe aparecer
    en el dataset final sin sufijo _lag/_rollmean: en lag 0 no estarian
    disponibles al predecir la hora H."""
    catalog = sample_catalog()
    train = build_training_frame(sample_df, catalog)

    real_columns = [e["columna"] for e in catalog if not e["disponible_antes_de_hora_h"]]
    for col in real_columns:
        if col == "precio_spot":
            continue  # el target si va en lag 0 (es la columna a predecir, no una feature)
        assert col not in train.columns, f"{col} en lag 0 seria leakage"


def test_build_training_frame_includes_forecast_indicators_at_lag_zero(sample_df):
    """demanda_prevista/prevision_eolica/prevision_fv SI son seguras en
    lag 0 porque son previsiones publicadas con antelacion."""
    catalog = sample_catalog()
    train = build_training_frame(sample_df, catalog)

    forecast_columns = [e["columna"] for e in catalog if e["disponible_antes_de_hora_h"]]
    for col in forecast_columns:
        assert col in train.columns


def test_build_training_frame_no_duplicate_columns(sample_df):
    catalog = sample_catalog()
    train = build_training_frame(sample_df, catalog)
    assert train.columns.duplicated().sum() == 0


def test_build_training_frame_has_target(sample_df):
    catalog = sample_catalog()
    train = build_training_frame(sample_df, catalog)
    assert "precio_spot" in train.columns
