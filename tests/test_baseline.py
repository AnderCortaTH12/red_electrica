import numpy as np
import pandas as pd
import pytest

from src.model.baseline import naive_forecast
from src.model.evaluate import evaluate_by_year, train_test_split_by_date
from src.model.metrics import mae, n_valid, rmse


@pytest.fixture
def price_df():
    idx = pd.date_range("2020-01-01", periods=48, freq="h", tz="UTC")
    values = np.arange(48, dtype=float)
    return pd.DataFrame({"precio_spot": values}, index=idx)


def test_naive_forecast_shifts_by_lag(price_df):
    pred = naive_forecast(price_df, lag_hours=24)
    assert pred.iloc[30] == price_df["precio_spot"].iloc[30 - 24]


def test_naive_forecast_first_rows_nan(price_df):
    pred = naive_forecast(price_df, lag_hours=24)
    assert pred.iloc[:24].isna().all()


def test_naive_forecast_column_name(price_df):
    pred = naive_forecast(price_df, lag_hours=24)
    assert pred.name == "precio_spot_naive_lag24h"


def test_mae_basic():
    y_true = pd.Series([10.0, 20.0, 30.0])
    y_pred = pd.Series([12.0, 18.0, 33.0])
    assert mae(y_true, y_pred) == pytest.approx((2 + 2 + 3) / 3)


def test_mae_ignores_nan_pairs():
    y_true = pd.Series([10.0, np.nan, 30.0])
    y_pred = pd.Series([12.0, 18.0, np.nan])
    # solo la fila 0 tiene ambos valores validos
    assert mae(y_true, y_pred) == pytest.approx(2.0)


def test_rmse_basic():
    y_true = pd.Series([0.0, 0.0])
    y_pred = pd.Series([3.0, 4.0])
    assert rmse(y_true, y_pred) == pytest.approx(3.5355339059)


def test_mae_handles_negative_and_zero_prices():
    """El precio spot espanol puede ser negativo o cero -- confirmar
    que mae() no rompe con esos valores (a diferencia de un MAPE)."""
    y_true = pd.Series([-10.0, 0.0, 5.0])
    y_pred = pd.Series([-8.0, 1.0, 4.0])
    assert mae(y_true, y_pred) == pytest.approx((2 + 1 + 1) / 3)


def test_n_valid_counts_only_aligned_non_nan():
    y_true = pd.Series([1.0, np.nan, 3.0, 4.0])
    y_pred = pd.Series([1.0, 2.0, np.nan, 4.0])
    assert n_valid(y_true, y_pred) == 2


def test_train_test_split_by_date(price_df):
    train, test = train_test_split_by_date(price_df, test_start="2020-01-02T00:00")
    assert len(train) == 24
    assert len(test) == 24
    assert train.index.max() < test.index.min()


def test_evaluate_by_year_groups_correctly():
    idx = pd.to_datetime(
        ["2020-01-01", "2020-06-01", "2021-01-01", "2021-06-01"], utc=True
    )
    y_true = pd.Series([10.0, 20.0, 30.0, 40.0], index=idx)
    y_pred = pd.Series([12.0, 18.0, 33.0, 42.0], index=idx)

    result = evaluate_by_year(y_true, y_pred)

    assert set(result["periodo"]) == {"2020", "2021", "total"}
    row_2020 = result[result["periodo"] == "2020"].iloc[0]
    assert row_2020["mae"] == pytest.approx((2 + 2) / 2)
    assert row_2020["n"] == 2
    row_total = result[result["periodo"] == "total"].iloc[0]
    assert row_total["n"] == 4


def test_evaluate_by_year_skips_years_with_no_valid_pairs():
    idx = pd.to_datetime(["2020-01-01", "2021-01-01"], utc=True)
    y_true = pd.Series([10.0, 20.0], index=idx)
    y_pred = pd.Series([np.nan, 22.0], index=idx)  # 2020 no tiene prediccion valida

    result = evaluate_by_year(y_true, y_pred)

    assert "2020" not in set(result["periodo"])
    assert "2021" in set(result["periodo"])
