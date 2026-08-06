"""Monitorización del observatorio: dos chequeos, pensados para correr
tras cada ingesta (`scripts/monitor.py`, parte de
`.github/workflows/mensual.yml`).

1. **¿Llevamos demasiados días sin un periodo nuevo?** La ingesta
   depende de un patrón de URL, no de una API (ver
   `src/ingestion/enagas_source.py`): si Enagás cambia el nombrado de
   los ficheros (como ya pasó con el sufijo "rev", ver Fase 4), el
   pipeline deja de encontrar meses nuevos en silencio -- sin fallar,
   porque "PDF no publicado todavía" es un estado válido. Este chequeo
   es lo que distingue esa situación normal de un problema real.
2. **Resumen de la última validación**: relee el periodo más reciente
   de `data/gas.csv` con `validar_periodo` (sin tocar PDFs) para dejar
   constancia de errores/avisos en el informe, aunque `ingest_month.py`
   ya haya impedido que datos inválidos lleguen al CSV.

Un aviso aquí es `::warning::`, no hace fallar el job -- es una señal
para que un humano lo revise, no necesariamente un fallo del pipeline
(ver la misma filosofía en `src/extraccion/validar.py`).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from src.extraccion.validar import validar_periodo

UMBRAL_DIAS_SIN_PERIODO_NUEVO = 45


def check_periodo_desactualizado(
    df: pd.DataFrame, hoy: date, umbral_dias: int = UMBRAL_DIAS_SIN_PERIODO_NUEVO
) -> dict | None:
    """None si todo va bien. Si no hay ningún periodo en el CSV, o si
    la última vez que el pipeline consiguió ingerir un periodo (columna
    `extraido_el`, no el mes calendario del propio periodo) fue hace
    más de `umbral_dias` días, devuelve el detalle del aviso.

    Importante: se mide contra `extraido_el`, NO contra el mes que
    cubre el `periodo` más reciente. Enagás publica con ~1 mes de
    retraso (el Boletín de junio se publica en julio), así que un
    `periodo` reciente siempre "parece" viejo en días de calendario
    aunque el pipeline esté funcionando perfectamente -- lo que de
    verdad indica un problema (URL rota, patrón de nombrado cambiado)
    es que haya pasado mucho tiempo desde la ÚLTIMA ingesta exitosa,
    no desde el mes que esa ingesta cubre.
    """
    if df.empty:
        return {
            "tipo": "sin_datos",
            "detalle": "data/gas.csv está vacío: no se ha ingerido ningún periodo todavía",
        }

    ultima_ingesta = pd.to_datetime(df["extraido_el"]).max().date()
    dias_desde_ultima_ingesta = (hoy - ultima_ingesta).days

    if dias_desde_ultima_ingesta > umbral_dias:
        ultimo_periodo = sorted(df["periodo"].unique())[-1]
        return {
            "tipo": "periodo_desactualizado",
            "ultimo_periodo": ultimo_periodo,
            "ultima_ingesta_el": ultima_ingesta.isoformat(),
            "dias_desde_ultima_ingesta": dias_desde_ultima_ingesta,
            "umbral_dias": umbral_dias,
            "detalle": (
                f"La última vez que se ingirió un periodo nuevo en gas.csv fue "
                f"el {ultima_ingesta.isoformat()} (periodo {ultimo_periodo}), "
                f"hace {dias_desde_ultima_ingesta} días. Puede que Enagás haya "
                "cambiado el patrón de nombrado de los PDF -- revisar "
                "src/ingestion/enagas_source.py."
            ),
        }
    return None


def resumen_ultima_validacion(df: pd.DataFrame, catalogo: list[dict]) -> dict | None:
    """Re-valida el periodo más reciente del CSV (sin tocar PDFs) para
    dejar constancia en el informe de monitorización."""
    if df.empty:
        return None

    ultimo_periodo = sorted(df["periodo"].unique())[-1]
    grupo = df[df["periodo"] == ultimo_periodo]

    filas = []
    for row in grupo.to_dict("records"):
        dimension = row.get("dimension")
        valor = row.get("valor")
        var_pct = row.get("var_pct_interanual")
        filas.append(
            {
                **row,
                "dimension": "" if pd.isna(dimension) else dimension,
                "valor": None if pd.isna(valor) else float(valor),
                "var_pct_interanual": None if pd.isna(var_pct) else float(var_pct),
            }
        )

    resultado = validar_periodo(filas, catalogo)
    return {
        "periodo": ultimo_periodo,
        "es_valido": resultado.es_valido,
        "n_errores": len(resultado.errores),
        "n_avisos": len(resultado.avisos),
        "errores": resultado.errores,
        "avisos": resultado.avisos,
    }


def generar_informe(gas_csv_path: Path, catalogo: list[dict], hoy: date | None = None) -> dict:
    hoy = hoy or date.today()
    df = pd.read_csv(gas_csv_path, dtype={"periodo": str}) if gas_csv_path.exists() else pd.DataFrame()

    return {
        "generado_el": hoy.isoformat(),
        "periodo_desactualizado": check_periodo_desactualizado(df, hoy),
        "ultima_validacion": resumen_ultima_validacion(df, catalogo),
    }
