import numpy as np
import pandas as pd
import pytest

from src.model.detrend import predict, train
from src.model.lgbm import train as train_lgbm


@pytest.fixture
def trending_data():
    rng = np.random.default_rng(0)
    n = 400
    X = pd.DataFrame(
        {
            "hour": rng.integers(0, 24, n),
            "dias_desde_referencia": np.arange(n, dtype=float),
        },
        index=pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC"),
    )
    # tendencia lineal fuerte + estacionalidad horaria + ruido pequeño,
    # simulando el patron real: precio_spot sube con el tiempo dentro
    # de post_tope ademas de variar por hora del dia
    y = 10 + 2 * X["hour"] + 0.8 * X["dias_desde_referencia"] + rng.normal(0, 1, n)
    y = pd.Series(y, index=X.index, name="precio_spot")
    return X, y


def test_train_returns_model_with_predict(trending_data):
    X, y = trending_data
    model = train(X, y, residual_params={"n_estimators": 20})
    assert hasattr(model, "predict")


def test_predict_returns_series_aligned_with_index(trending_data):
    X, y = trending_data
    model = train(X, y, residual_params={"n_estimators": 20})
    preds = predict(model, X)
    assert isinstance(preds, pd.Series)
    assert list(preds.index) == list(X.index)
    assert preds.name == "precio_spot_pred"


def test_extrapolates_beyond_training_range_unlike_plain_lgbm(trending_data):
    """El motivo de existir de este modulo: un LightGBM puro no puede
    predecir mas alla del maximo de precio_spot visto en entrenamiento
    (se queda anclado). DetrendedModel, gracias a la parte lineal, si
    debe seguir subiendo para dias_desde_referencia muy por encima del
    rango de entrenamiento."""
    X, y = trending_data
    split = 350
    X_train, y_train = X.iloc[:split], y.iloc[:split]

    detrended = train(X_train, y_train, residual_params={"n_estimators": 50})
    plain_lgbm = train_lgbm(X_train, y_train, params={"n_estimators": 50})

    # muy por delante del rango de entrenamiento (dias_desde_referencia < 350)
    future = pd.DataFrame(
        {"hour": [12], "dias_desde_referencia": [X_train["dias_desde_referencia"].max() + 200]}
    )

    detrended_pred = detrended.predict(future)[0]
    plain_pred = plain_lgbm.predict(future)[0]
    expected_true = 10 + 2 * 12 + 0.8 * future["dias_desde_referencia"].iloc[0]

    # el LightGBM puro se queda anclado cerca del maximo visto en train
    max_train_y = y_train.max()
    assert plain_pred <= max_train_y + 5

    # el modelo con detrend sigue la tendencia mucho mas de cerca
    assert abs(detrended_pred - expected_true) < abs(plain_pred - expected_true)


def test_feature_importances_delegates_to_residual_model(trending_data):
    X, y = trending_data
    model = train(X, y, residual_params={"n_estimators": 20})
    assert len(model.feature_importances_) == X.shape[1]
