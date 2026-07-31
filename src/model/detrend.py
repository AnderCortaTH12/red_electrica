"""Modelo híbrido: tendencia lineal + residuo con árboles.

Los árboles de gradient boosting (LightGBM) no pueden predecir por
encima/debajo del rango de la variable objetivo visto en entrenamiento:
las predicciones se quedan anclada cerca del máximo/mínimo de train
mientras el precio real sigue subiendo (root cause documentado en el
README, sección Limitaciones conocidas -- confirmado con el MAE del
baseline escalando año a año dentro de post_tope).

DetrendedModel separa el problema en dos partes independientes:
- Una regresión lineal sobre 'dias_desde_referencia' captura la
  tendencia, que SÍ extrapola de forma nativa (una recta no tiene techo).
- LightGBM aprende solo el residuo (precio_spot menos esa tendencia):
  estacionalidad horaria, mix de generación, etc. -- un rango mucho más
  estable que no necesita extrapolar.

Expone .predict(X) igual que cualquier modelo sklearn/LightGBM, así que
sigue cumpliendo el contrato de src/model/artifact.py sin que la API
(src/serving/api.py) ni src/model/predict.py necesiten saber que por
debajo hay dos modelos en vez de uno.
"""

from __future__ import annotations

import pandas as pd
from sklearn.linear_model import LinearRegression

from src.model.lgbm import train as train_lgbm


class DetrendedModel:
    def __init__(self, trend_model: LinearRegression, residual_model, trend_feature: str):
        self.trend_model = trend_model
        self.residual_model = residual_model
        self.trend_feature = trend_feature

    def predict(self, X: pd.DataFrame):
        trend_pred = self.trend_model.predict(X[[self.trend_feature]])
        residual_pred = self.residual_model.predict(X)
        return trend_pred + residual_pred

    @property
    def feature_importances_(self):
        """Delegado al modelo de árboles (la tendencia no tiene 'importancia'
        por feature en ese sentido, es una única pendiente global)."""
        return self.residual_model.feature_importances_


def train(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    trend_feature: str = "dias_desde_referencia",
    residual_params: dict | None = None,
) -> DetrendedModel:
    trend_model = LinearRegression()
    trend_model.fit(X_train[[trend_feature]], y_train)

    residual_train = y_train - trend_model.predict(X_train[[trend_feature]])
    residual_model = train_lgbm(X_train, residual_train, params=residual_params)

    return DetrendedModel(trend_model, residual_model, trend_feature)


def predict(model: DetrendedModel, X: pd.DataFrame) -> pd.Series:
    return pd.Series(model.predict(X), index=X.index, name="precio_spot_pred")
