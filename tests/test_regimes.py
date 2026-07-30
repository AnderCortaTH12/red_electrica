import numpy as np
import pandas as pd
import pytest

from src.model.evaluate import evaluate_by_regime
from src.model.regimes import assign_regime


def test_assign_regime_boundaries():
    idx = pd.to_datetime(
        [
            "2022-06-14T22:00:00Z",  # 2022-06-15 00:00 Madrid (verano, CEST=UTC+2) -> tope_gas
            "2022-06-14T20:00:00Z",  # 2022-06-14 22:00 Madrid -> normal
            "2023-12-31T23:00:00Z",  # 2024-01-01 00:00 Madrid (invierno, CET=UTC+1) -> post_tope
            "2023-12-31T20:00:00Z",  # 2023-12-31 21:00 Madrid -> tope_gas
            "2014-01-01T00:00:00Z",  # claramente normal
            "2026-01-01T00:00:00Z",  # claramente post_tope
        ],
        utc=True,
    )
    result = assign_regime(idx)
    assert list(result) == ["tope_gas", "normal", "post_tope", "tope_gas", "normal", "post_tope"]


def test_assign_regime_returns_categorical_with_expected_order():
    idx = pd.to_datetime(["2020-01-01"], utc=True)
    result = assign_regime(idx)
    assert list(result.cat.categories) == ["normal", "tope_gas", "post_tope"]


def test_evaluate_by_regime_splits_correctly():
    idx = pd.to_datetime(
        ["2020-01-01", "2022-08-01", "2023-08-01", "2025-01-01"], utc=True
    )
    y_true = pd.Series([10.0, 100.0, 120.0, 200.0], index=idx)
    y_pred = pd.Series([12.0, 90.0, 130.0, 180.0], index=idx)

    result = evaluate_by_regime(y_true, y_pred)

    assert set(result["regimen"]) == {"normal", "tope_gas", "post_tope", "total"}
    row_tope = result[result["regimen"] == "tope_gas"].iloc[0]
    assert row_tope["n"] == 2
    assert row_tope["media"] == pytest.approx((100.0 + 120.0) / 2)
    row_total = result[result["regimen"] == "total"].iloc[0]
    assert row_total["n"] == 4


def test_evaluate_by_regime_skips_empty_regimes():
    # todo el rango cae en 'normal', no debe aparecer tope_gas/post_tope
    idx = pd.to_datetime(["2015-01-01", "2016-01-01"], utc=True)
    y_true = pd.Series([10.0, 20.0], index=idx)
    y_pred = pd.Series([11.0, 19.0], index=idx)

    result = evaluate_by_regime(y_true, y_pred)

    assert set(result["regimen"]) == {"normal", "total"}
