"""Wrapper delgado sobre LightGBM (regresión) para el precio spot."""

from __future__ import annotations

import lightgbm as lgb
import pandas as pd

DEFAULT_PARAMS = {
    "objective": "regression",
    "metric": "mae",
    "n_estimators": 500,
    "learning_rate": 0.05,
    "num_leaves": 31,
    "random_state": 42,
    "verbosity": -1,
}


def train(
    X_train: pd.DataFrame, y_train: pd.Series, params: dict | None = None
) -> lgb.LGBMRegressor:
    model = lgb.LGBMRegressor(**{**DEFAULT_PARAMS, **(params or {})})
    model.fit(X_train, y_train)
    return model


def predict(model: lgb.LGBMRegressor, X: pd.DataFrame) -> pd.Series:
    preds = model.predict(X)
    return pd.Series(preds, index=X.index, name="precio_spot_pred")
