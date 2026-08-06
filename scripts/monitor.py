"""Monitorización del observatorio: genera `data/informe_monitorizacion.json`
con el chequeo de "¿llevamos demasiado sin un periodo nuevo?" y un
resumen de la validación del periodo más reciente.

Nunca falla el job (siempre exit 0): un aviso aquí es una señal a
revisar, no un fallo del pipeline -- eso ya lo hace `ingest_month.py`
al negarse a escribir un periodo inválido en el CSV.

Uso:
    python -m scripts.monitor
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from src.extraccion.catalogo import cargar_catalogo
from src.monitoring.informe import generar_informe

GAS_CSV_PATH = Path("data/gas.csv")
INFORME_PATH = Path("data/informe_monitorizacion.json")


def main() -> int:
    catalogo = cargar_catalogo()
    informe = generar_informe(GAS_CSV_PATH, catalogo)

    with open(INFORME_PATH, "w", encoding="utf-8") as f:
        json.dump(informe, f, ensure_ascii=False, indent=2)
        f.write("\n")

    desactualizado = informe["periodo_desactualizado"]
    if desactualizado is not None:
        print(f"::warning::{desactualizado['detalle']}")

    validacion = informe["ultima_validacion"]
    if validacion is not None:
        for aviso in validacion["avisos"]:
            print(f"::warning::{validacion['periodo']}: {aviso}")
        if not validacion["es_valido"]:
            # No debería pasar nunca (ingest_month.py no deja escribir
            # un periodo inválido), pero si pasa -- p.ej. alguien tocó
            # el CSV a mano -- es una señal fuerte, no un simple aviso.
            print(f"::warning::El periodo más reciente ({validacion['periodo']}) ya escrito en gas.csv NO revalida limpio -- revisar manualmente.")

    print(f"Informe de monitorización escrito en {INFORME_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
