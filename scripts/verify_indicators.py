"""Verifica metadatos y disponibilidad histórica (¿llega a 2014?) de la
shortlist curada a mano de indicadores ESIOS relevantes para el proyecto.

Uso:
    python scripts\\verify_indicators.py

Para cada candidato:
    - confirma el nombre real en ESIOS
    - comprueba si hay datos en una ventana de enero de 2014
    - comprueba si hay datos recientes (últimos 2 días)

Guarda el catálogo final verificado en data/esios_indicators_catalog.json
"""

import json
import os
import sys
import time

import requests
from dotenv import load_dotenv

BASE_URL = "https://api.esios.ree.es"

# Catálogo curado a mano a partir de la shortlist de discover_indicators.py
# categoria -> {id: (nombre_esperado, rol_como_variable)}
CANDIDATES = {
    "precio": {
        600: "Precio mercado SPOT Diario -> TARGET a predecir",
        1001: "Término de facturación de energía activa del PVPC 2.0TD -> precio PVPC (regulado, distinto del spot)",
    },
    "demanda": {
        544: "Demanda prevista -> feature (previsión, disponible antes de la hora H)",
        1293: "Demanda real -> solo como lag (real, no disponible a priori en la hora H)",
    },
    "generacion_real": {
        551: "Generación T.Real eólica -> lag / feature de mix energético",
        1295: "Generación T.Real Solar fotovoltaica -> lag / feature de mix energético",
        1294: "Generación T.Real Solar térmica -> lag / feature de mix energético",
        549: "Generación T.Real nuclear -> lag / feature de mix energético (muy estable)",
        546: "Generación T.Real hidráulica -> lag / feature de mix energético",
        2041: "Generación T.Real ciclo combinado nacional -> lag / feature de mix energético",
        547: "Generación T.Real carbón -> lag / feature de mix energético",
    },
    "prevision_generacion": {
        1777: "Previsión diaria D+1 eólica -> feature (disponible antes de la hora H)",
        1779: "Previsión diaria D+1 fotovoltaica -> feature (disponible antes de la hora H)",
    },
}


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


def check_window(headers: dict, indicator_id: int, start: str, end: str) -> int:
    """Devuelve el nº de valores encontrados en la ventana [start, end]."""
    response = requests.get(
        f"{BASE_URL}/indicators/{indicator_id}",
        headers=headers,
        params={"start_date": start, "end_date": end, "time_trunc": "hour"},
        timeout=30,
    )
    if response.status_code != 200:
        return -1
    values = response.json()["indicator"]["values"]
    return len(values)


def main() -> None:
    headers = get_headers()
    catalog = []

    for categoria, ids in CANDIDATES.items():
        print(f"\n== {categoria} ==")
        for indicator_id, rol in ids.items():
            meta = requests.get(
                f"{BASE_URL}/indicators/{indicator_id}", headers=headers, timeout=30
            )
            if meta.status_code != 200:
                print(f"  id={indicator_id}: ERROR HTTP {meta.status_code} al pedir metadatos")
                continue
            info = meta.json()["indicator"]
            name = info.get("name")

            n_2014 = check_window(headers, indicator_id, "2014-01-01T00:00", "2014-01-02T00:00")
            time.sleep(0.3)
            n_recent = check_window(headers, indicator_id, "2026-07-25T00:00", "2026-07-26T00:00")
            time.sleep(0.3)

            disponible_2014 = "SI" if n_2014 > 0 else ("NO" if n_2014 == 0 else "ERROR")
            disponible_reciente = "SI" if n_recent > 0 else ("NO" if n_recent == 0 else "ERROR")

            print(f"  id={indicator_id} | {name}")
            print(f"    rol: {rol}")
            print(f"    datos en 2014-01-01..02: {disponible_2014} ({n_2014} valores)")
            print(f"    datos recientes (25-26 jul 2026): {disponible_reciente} ({n_recent} valores)")

            catalog.append(
                {
                    "id": indicator_id,
                    "name": name,
                    "categoria": categoria,
                    "rol": rol,
                    "disponible_desde_2014": n_2014 > 0,
                    "disponible_reciente": n_recent > 0,
                }
            )

    with open("data/esios_indicators_catalog.json", "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)
    print("\nGuardado: data/esios_indicators_catalog.json")


if __name__ == "__main__":
    main()
