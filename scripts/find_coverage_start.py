"""Añade el campo 'cobertura_desde' (YYYY-MM) a cada indicador del
catálogo, para que la ingesta histórica (Fase 3) sepa desde qué fecha
pedir cada indicador sin descubrirlo a base de peticiones fallidas.

Para los indicadores que ya sabíamos con datos en 2014, se asume
cobertura_desde = "2014-01" (no hace falta buscar más atrás, es
el límite que pidió el usuario). Para el resto, se hace una búsqueda
binaria mes a mes entre 2014-01 (sin datos, confirmado en verify_indicators.py)
y el mes actual (con datos, confirmado) para localizar el primer mes
con datos reales.

Uso:
    python scripts\\find_coverage_start.py
"""

import json
import os
import sys
import time

import requests
from dotenv import load_dotenv

BASE_URL = "https://api.esios.ree.es"
CATALOG_PATH = "data/esios_indicators_catalog.json"

START_YEAR, START_MONTH = 2014, 1
# mes "hi" de la búsqueda: el más reciente que sabemos con datos (verificado
# en verify_indicators.py con datos del 25-26 de julio de 2026)
END_YEAR, END_MONTH = 2026, 7


def get_headers() -> dict:
    load_dotenv()
    token = os.environ.get("ESIOS_API_KEY")
    if not token:
        print("ERROR: ESIOS_API_KEY no está definida.")
        sys.exit(1)
    return {
        "Accept": "application/json; application/vnd.esios-api-v1+json",
        "Content-Type": "application/json",
        "x-api-key": token,
    }


def month_offset_to_ym(offset: int) -> tuple[int, int]:
    total = (START_YEAR * 12 + (START_MONTH - 1)) + offset
    return total // 12, (total % 12) + 1


def has_data_in_month(headers: dict, indicator_id: int, year: int, month: int) -> bool:
    start = f"{year:04d}-{month:02d}-01T00:00"
    # día 2 del mes siempre existe, evita líos con meses de 28/30/31 días
    end = f"{year:04d}-{month:02d}-02T00:00"
    response = requests.get(
        f"{BASE_URL}/indicators/{indicator_id}",
        headers=headers,
        params={"start_date": start, "end_date": end, "time_trunc": "hour"},
        timeout=30,
    )
    response.raise_for_status()
    values = response.json()["indicator"]["values"]
    time.sleep(0.3)
    return len(values) > 0


def find_first_month_with_data(headers: dict, indicator_id: int) -> tuple[int, int]:
    """Búsqueda binaria: lo=sin datos, hi=con datos. Devuelve (year, month) de hi."""
    lo = 0
    hi = (END_YEAR * 12 + (END_MONTH - 1)) - (START_YEAR * 12 + (START_MONTH - 1))

    # comprobación de guarda: si lo (2014-01) ya tuviera datos, no hay nada que buscar
    while hi - lo > 1:
        mid = (lo + hi) // 2
        year, month = month_offset_to_ym(mid)
        if has_data_in_month(headers, indicator_id, year, month):
            hi = mid
        else:
            lo = mid

    return month_offset_to_ym(hi)


def main() -> None:
    headers = get_headers()

    with open(CATALOG_PATH, encoding="utf-8") as f:
        catalog = json.load(f)

    for entry in catalog:
        if entry.get("disponible_desde_2014"):
            entry["cobertura_desde"] = "2014-01"
            print(f"id={entry['id']:<6} {entry['name']}: cobertura_desde=2014-01 (ya confirmado)")
            continue

        year, month = find_first_month_with_data(headers, entry["id"])
        entry["cobertura_desde"] = f"{year:04d}-{month:02d}"
        print(f"id={entry['id']:<6} {entry['name']}: cobertura_desde={year:04d}-{month:02d}")

    with open(CATALOG_PATH, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)
    print(f"\nActualizado: {CATALOG_PATH}")


if __name__ == "__main__":
    main()
