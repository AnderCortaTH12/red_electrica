import numpy as np
import pandas as pd
import pytest

from src.model.lgbm import predict, train


@pytest.fixture
def synthetic_data():
    rng = np.random.default_rng(0)
    n = 300
    X = pd.DataFrame(
        {
            "hour": rng.integers(0, 24, n),
            "dias_desde_referencia": np.arange(n, dtype=float),
        },
        index=pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC"),
    )
    # target aprendible: depende linealmente de las features + algo de ruido
    y = 10 + 2 * X["hour"] + 0.5 * X["dias_desde_referencia"] + rng.normal(0, 1, n)
    y = pd.Series(y, index=X.index, name="precio_spot")
    return X, y


def test_train_returns_fitted_model(synthetic_data):
    X, y = synthetic_data
    model = train(X, y, params={"n_estimators": 20})
    assert hasattr(model, "predict")
    assert len(model.feature_importances_) == X.shape[1]


def test_predict_returns_series_aligned_with_index(synthetic_data):
    X, y = synthetic_data
    model = train(X, y, params={"n_estimators": 20})
    preds = predict(model, X)
    assert isinstance(preds, pd.Series)
    assert list(preds.index) == list(X.index)
    assert preds.name == "precio_spot_pred"


def test_model_learns_better_than_predicting_the_mean(synthetic_data):
    X, y = synthetic_data
    split = 250
    X_train, y_train = X.iloc[:split], y.iloc[:split]
    X_test, y_test = X.iloc[split:], y.iloc[split:]

    model = train(X_train, y_train, params={"n_estimators": 50})
    preds = predict(model, X_test)

    mae_model = (y_test - preds).abs().mean()
    mae_mean_baseline = (y_test - y_train.mean()).abs().mean()
    assert mae_model < mae_mean_baseline
