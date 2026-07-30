"""Periodos de régimen regulatorio del mercado eléctrico español,
relevantes para el precio spot: el "tope al gas" (mecanismo ibérico de
ajuste, Real Decreto-ley 10/2022) limitó el precio del gas usado para
fijar el precio marginal entre 2022-06-15 y 2023-12-31.

Fechas en calendario de Europe/Madrid (el mecanismo se definió en hora
local española, no UTC).
"""

from __future__ import annotations

import pandas as pd

REGIME_ORDER = ["normal", "tope_gas", "post_tope"]

TOPE_GAS_INICIO = pd.Timestamp("2022-06-15").date()
TOPE_GAS_FIN = pd.Timestamp("2023-12-31").date()
POST_TOPE_INICIO = pd.Timestamp("2024-01-01").date()


def assign_regime(index: pd.DatetimeIndex) -> pd.Series:
    """Devuelve una Series categórica ('normal'/'tope_gas'/'post_tope')
    alineada con `index` (debe ser tz-aware, se convierte a
    Europe/Madrid para comparar fechas de calendario)."""
    local_dates = index.tz_convert("Europe/Madrid").date
    regime = pd.Series("normal", index=index, dtype="object")
    regime[local_dates >= TOPE_GAS_INICIO] = "tope_gas"
    regime[local_dates >= POST_TOPE_INICIO] = "post_tope"
    return pd.Series(
        pd.Categorical(regime, categories=REGIME_ORDER, ordered=True), index=index
    )
