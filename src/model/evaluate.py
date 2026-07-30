"""Utilidades de evaluación temporal. Nunca split aleatorio: es una
serie temporal, así que se entrena con el pasado y se valida con el
futuro (walk-forward / backtesting).
"""

from __future__ import annotations

import pandas as pd

from src.model.metrics import mae, n_valid, rmse


def train_test_split_by_date(
    df: pd.DataFrame, test_start: str
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Corta por fecha: todo lo anterior a `test_start` es train, el
    resto es test. `test_start` en ISO 8601, comparable al índice
    (tz-aware UTC)."""
    cutoff = pd.Timestamp(test_start, tz="UTC")
    train = df[df.index < cutoff]
    test = df[df.index >= cutoff]
    return train, test


def evaluate_by_year(y_true: pd.Series, y_pred: pd.Series) -> pd.DataFrame:
    """MAE/RMSE por año natural, más una fila 'total'. Útil para ver si
    el error es estable en el tiempo o se dispara en algún periodo
    (p.ej. la crisis energética de 2021-2022)."""
    years = sorted(y_true.index.year.unique())
    rows = []
    for year in years:
        mask = y_true.index.year == year
        yt, yp = y_true[mask], y_pred[mask]
        n = n_valid(yt, yp)
        if n == 0:
            continue  # sin pares validos (p.ej. el primer dia, antes de que exista el lag)
        rows.append({"periodo": str(year), "mae": mae(yt, yp), "rmse": rmse(yt, yp), "n": n})
    rows.append(
        {"periodo": "total", "mae": mae(y_true, y_pred), "rmse": rmse(y_true, y_pred), "n": n_valid(y_true, y_pred)}
    )
    return pd.DataFrame(rows)
