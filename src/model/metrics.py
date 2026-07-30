"""Métricas de evaluación para el forecasting de precio.

MAE es la métrica PRINCIPAL: el precio spot español puede ser negativo
o cero (exceso de renovables, confirmado en el EDA — 1487h negativas,
1203h en cero sobre ~110k), lo que rompe el MAPE (división por casi
cero o por cero). RMSE se reporta como secundaria (penaliza más los
errores grandes).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _aligned_valid(y_true: pd.Series, y_pred: pd.Series) -> tuple[pd.Series, pd.Series]:
    mask = y_true.notna() & y_pred.notna()
    return y_true[mask], y_pred[mask]


def mae(y_true: pd.Series, y_pred: pd.Series) -> float:
    y_true, y_pred = _aligned_valid(y_true, y_pred)
    return float(np.abs(y_true - y_pred).mean())


def rmse(y_true: pd.Series, y_pred: pd.Series) -> float:
    y_true, y_pred = _aligned_valid(y_true, y_pred)
    return float(np.sqrt(((y_true - y_pred) ** 2).mean()))


def n_valid(y_true: pd.Series, y_pred: pd.Series) -> int:
    y_true, _ = _aligned_valid(y_true, y_pred)
    return int(len(y_true))
