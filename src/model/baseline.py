"""Baseline seasonal naïve: la predicción para la hora H es el precio
real de hace `lag_hours` horas (por defecto 24h -> "mañana a esta hora
costará lo mismo que hoy a esta hora").

Es el número a batir. Si LightGBM (Fase 5, siguiente paso) no le gana
con margen, no vale la pena el modelo complejo.
"""

from __future__ import annotations

import pandas as pd


def naive_forecast(df: pd.DataFrame, lag_hours: int = 24, target_col: str = "precio_spot") -> pd.Series:
    """Predicción naive: shift(lag_hours) sobre la columna objetivo.

    No "entrena" nada -- es una regla fija. Las primeras `lag_hours`
    filas quedan en NaN (no hay pasado suficiente todavía).
    """
    return df[target_col].shift(lag_hours).rename(f"{target_col}_naive_lag{lag_hours}h")
