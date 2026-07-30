"""Feature engineering para predecir el precio horario (precio_spot).

Regla de oro (data leakage): para predecir el precio de la hora H solo se
puede usar información disponible ANTES de la hora H. El catálogo marca
`disponible_antes_de_hora_h` por indicador:

- True  (demanda_prevista, prevision_eolica, prevision_fv): son
  PREVISIONES que ESIOS publica con antelación -> se pueden usar tal
  cual, en la propia hora H, sin lag.
- False (demanda_real, gen_* "T.Real", precio_spot, pvpc): son valores
  REALES que solo se conocen DESPUÉS de que pase la hora H -> nunca se
  usan en lag 0, solo como lag (p.ej. el precio de hace 24h).

Todas las funciones devuelven una copia del DataFrame de entrada.
"""

from __future__ import annotations

import pandas as pd

try:
    import holidays as holidays_lib
except ImportError:  # pragma: no cover
    holidays_lib = None

DEFAULT_LAGS = [24, 48, 168]  # horas: ayer, anteayer, hace una semana
DEFAULT_ROLLING_WINDOWS = [24, 168]  # horas: media del último día / semana

RENEWABLE_COLUMNS = ["gen_eolica", "gen_solar_fv", "gen_solar_termica", "gen_hidraulica"]


def add_calendar_features(df: pd.DataFrame) -> pd.DataFrame:
    """Hora, día de semana, mes, fin de semana y festivo (España).

    Estas features son intrínsecamente seguras: la hora, el día de la
    semana o si mañana es festivo se conocen con total antelación.
    """
    df = df.copy()
    idx = df.index.tz_convert("Europe/Madrid")

    df["hour"] = idx.hour
    df["dayofweek"] = idx.dayofweek  # 0=lunes
    df["month"] = idx.month
    df["is_weekend"] = idx.dayofweek >= 5

    if holidays_lib is not None:
        years = range(idx.year.min(), idx.year.max() + 1)
        es_holidays = holidays_lib.country_holidays("ES", years=years)
        # comparar como datetime.date evita líos de tz-aware vs tz-naive
        # al comparar contra las claves de `es_holidays` (que son `date`)
        df["is_holiday"] = [d in es_holidays for d in idx.date]
    else:  # pragma: no cover
        df["is_holiday"] = False

    return df


def add_lags(df: pd.DataFrame, columns: list[str], lags: list[int] = DEFAULT_LAGS) -> pd.DataFrame:
    """Añade columnas `{col}_lag{h}h` = valor de `col` hace `h` horas.

    Válido para CUALQUIER columna (reales o previsiones): un lag mira
    al pasado por definición, así que nunca hay leakage aquí. Lo que sí
    hay que vigilar es no usar la columna original (lag 0) de un
    indicador 'real' como si fuera una feature — eso se hace explícito
    no incluyéndola directamente en el dataset final de entrenamiento.
    """
    df = df.copy()
    for col in columns:
        for lag in lags:
            df[f"{col}_lag{lag}h"] = df[col].shift(lag)
    return df


def add_rolling_means(
    df: pd.DataFrame, columns: list[str], windows: list[int] = DEFAULT_ROLLING_WINDOWS
) -> pd.DataFrame:
    """Añade `{col}_rollmean{w}h` = media de `col` en las `w` horas
    ANTERIORES a la hora H (excluye la propia hora H: shift(1) antes
    de la media móvil), para que sea segura incluso sobre columnas
    'reales' que en lag 0 no se podrían usar.
    """
    df = df.copy()
    for col in columns:
        shifted = df[col].shift(1)
        for window in windows:
            df[f"{col}_rollmean{window}h"] = shifted.rolling(window).mean()
    return df


def add_renewable_ratio_lag24h(df: pd.DataFrame) -> pd.DataFrame:
    """Ratio renovables/demanda de hace 24h: (eólica+FV+térmica+hidráulica)/demanda_real,
    calculado sobre los valores de hace 24h (todos son indicadores
    'reales', así que en lag 0 no estarían disponibles).
    """
    df = df.copy()
    renewable_sum_lag24 = sum(df[f"{col}_lag24h"] for col in RENEWABLE_COLUMNS)
    df["ratio_renovables_lag24h"] = renewable_sum_lag24 / df["demanda_real_lag24h"]
    return df


def build_training_frame(df: pd.DataFrame, catalog: list[dict]) -> pd.DataFrame:
    """Construye el DataFrame final de features, respetando qué
    indicadores están disponibles en la propia hora H y cuáles solo
    como lag. `df` debe venir de `src.features.load.load_wide_dataframe`.
    """
    forecast_columns = [e["columna"] for e in catalog if e["disponible_antes_de_hora_h"]]
    real_columns = [
        e["columna"]
        for e in catalog
        if not e["disponible_antes_de_hora_h"] and e["columna"] != "precio_spot"
    ]

    out = add_calendar_features(df)
    out = add_lags(out, columns=["precio_spot"] + real_columns, lags=DEFAULT_LAGS)
    out = add_rolling_means(out, columns=["precio_spot"] + real_columns)
    out = add_renewable_ratio_lag24h(out)

    # columnas finales: calendario + previsiones (lag0, son seguras) +
    # lags/medias moviles de precio y de indicadores reales + target.
    # Los indicadores 'reales' en lag 0 (p.ej. demanda_real sin lag) se
    # excluyen a propósito: no estarían disponibles al predecir la hora H.
    # "ratio_renovables_lag24h" ya contiene "_lag" en el nombre, así que
    # el filtro genérico de abajo la incluye sola: no añadirla aparte o
    # queda duplicada en la lista de columnas.
    feature_columns = ["hour", "dayofweek", "month", "is_weekend", "is_holiday"] + forecast_columns + [
        c for c in out.columns if "_lag" in c or "_rollmean" in c
    ]
    return out[feature_columns + ["precio_spot"]]
