"""Revalida `data/gas.csv` entero sin tocar PDFs ni llamar a la API.
Útil en CI (o a mano tras editar el catálogo) para comprobar que el
dataset ya escrito sigue cuadrando -- p.ej. después de ampliar el
catálogo o de corregir a mano un valor mal leído.

Uso:
    python -m scripts.validar_dataset
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from src.extraccion.catalogo import cargar_catalogo
from src.extraccion.validar import validar_periodo

CSV_PATH = Path("data/gas.csv")


def _filas_del_periodo(grupo: pd.DataFrame) -> list[dict]:
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
    return filas


def main() -> int:
    if not CSV_PATH.exists():
        print(f"No existe {CSV_PATH}, nada que validar")
        return 0

    catalogo = cargar_catalogo()
    df = pd.read_csv(CSV_PATH, dtype={"periodo": str})
    if df.empty:
        print("gas.csv está vacío, nada que validar")
        return 0

    hubo_error = False
    for periodo, grupo in df.groupby("periodo", sort=True):
        resultado = validar_periodo(_filas_del_periodo(grupo), catalogo)
        for aviso in resultado.avisos:
            print(f"::warning::{periodo}: {aviso}")
        if resultado.es_valido:
            print(f"{periodo}: OK ({len(grupo)} filas)")
        else:
            hubo_error = True
            print(f"{periodo}: FALLÓ")
            for error in resultado.errores:
                print(f"  - {error}")

    return 1 if hubo_error else 0


if __name__ == "__main__":
    sys.exit(main())
