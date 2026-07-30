"""Utilidades de evaluación temporal. Nunca split aleatorio: es una
serie temporal, así que se entrena con el pasado y se valida con el
futuro (walk-forward / backtesting).
"""

from __future__ import annotations

import pandas as pd

from src.model.metrics import mae, n_valid, rmse
from src.model.regimes import REGIME_ORDER, assign_regime


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


def evaluate_by_regime(y_true: pd.Series, y_pred: pd.Series) -> pd.DataFrame:
    """Media, desviación estándar (de y_true) y MAE/RMSE del baseline
    por régimen regulatorio (normal / tope_gas / post_tope, ver
    src.model.regimes), más una fila 'total'.

    Sirve para distinguir si un salto de error es volatilidad genérica
    o coincide con un cambio de régimen regulatorio real.
    """
    regime = assign_regime(y_true.index)
    rows = []
    for label in REGIME_ORDER:
        mask = (regime == label).to_numpy()
        yt, yp = y_true[mask], y_pred[mask]
        n = n_valid(yt, yp)
        if n == 0:
            continue
        rows.append(
            {
                "regimen": label,
                "media": float(yt.mean()),
                "std": float(yt.std()),
                "mae": mae(yt, yp),
                "rmse": rmse(yt, yp),
                "n": n,
            }
        )
    rows.append(
        {
            "regimen": "total",
            "media": float(y_true.mean()),
            "std": float(y_true.std()),
            "mae": mae(y_true, y_pred),
            "rmse": rmse(y_true, y_pred),
            "n": n_valid(y_true, y_pred),
        }
    )
    return pd.DataFrame(rows)
