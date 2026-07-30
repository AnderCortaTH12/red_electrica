"""Descubre y documenta el catálogo de indicadores de ESIOS relevantes
para el proyecto de forecasting de precio eléctrico.

Hace UNA sola petición pesada (listado completo de indicadores) y luego
filtra en local por palabras clave, para no gastar peticiones repetidas
contra /indicators?text=... una por una.

Uso:
    python scripts\\discover_indicators.py

Salidas:
    data/esios_indicators_full.csv       catálogo completo (id, name)
    data/esios_indicators_catalog.json   catálogo final elegido, con
                                          notas de uso como variable
"""

import json
import os
import sys

import pandas as pd
import requests
from dotenv import load_dotenv

BASE_URL = "https://api.esios.ree.es"

# palabra clave -> (categoria, notas para el humano)
KEYWORDS = {
    "mercado diario": "precio",
    "PVPC": "precio",
    "demanda real": "demanda",
    "demanda programada": "demanda",
    "demanda prevista": "demanda",
    "eólica": "generacion",
    "fotovoltaica": "generacion",
    "solar térmica": "generacion",
    "nuclear": "generacion",
    "hidráulica": "generacion",
    "ciclo combinado": "generacion",
    "carbón": "generacion",
    "previsión eólica": "prevision_generacion",
    "previsión fotovoltaica": "prevision_generacion",
}

# Candidato mencionado por el usuario a verificar explícitamente
CANDIDATE_IDS_TO_VERIFY = {600: "supuesto precio spot mercado diario (OMIE)"}


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


def fetch_full_catalog(headers: dict) -> pd.DataFrame:
    print("Descargando listado completo de indicadores (GET /indicators)...")
    response = requests.get(f"{BASE_URL}/indicators", headers=headers, timeout=60)
    response.raise_for_status()
    indicators = response.json()["indicators"]
    df = pd.DataFrame(indicators)[["id", "name", "short_name"]]
    print(f"  {len(df)} indicadores en total.")
    return df


def verify_candidates(headers: dict) -> None:
    print("\nVerificando indicadores candidatos mencionados a mano:")
    for indicator_id, guess in CANDIDATE_IDS_TO_VERIFY.items():
        response = requests.get(
            f"{BASE_URL}/indicators/{indicator_id}", headers=headers, timeout=30
        )
        if response.status_code != 200:
            print(f"  id={indicator_id}: HTTP {response.status_code}, no se pudo verificar")
            continue
        info = response.json()["indicator"]
        print(f"  id={indicator_id} (suposición: {guess})")
        print(f"    name: {info.get('name')}")
        print(f"    short_name: {info.get('short_name')}")
        print(f"    description (recortada): {(info.get('description') or '')[:150]}")


def filter_by_keywords(df: pd.DataFrame) -> pd.DataFrame:
    matches = []
    seen_ids = set()
    for keyword, categoria in KEYWORDS.items():
        mask = df["name"].str.contains(keyword, case=False, na=False)
        subset = df[mask].copy()
        subset["matched_keyword"] = keyword
        subset["categoria_sugerida"] = categoria
        for _, row in subset.iterrows():
            if row["id"] not in seen_ids:
                matches.append(row)
                seen_ids.add(row["id"])
    return pd.DataFrame(matches)


def main() -> None:
    headers = get_headers()

    full_df = fetch_full_catalog(headers)
    full_df.to_csv("data/esios_indicators_full.csv", index=False, encoding="utf-8")
    print("Guardado: data/esios_indicators_full.csv")

    verify_candidates(headers)

    shortlist = filter_by_keywords(full_df)
    print(f"\n{len(shortlist)} indicadores coinciden con las palabras clave:")
    for _, row in shortlist.sort_values("categoria_sugerida").iterrows():
        print(f"  [{row['categoria_sugerida']:<20}] id={row['id']:<6} {row['name']}")

    shortlist_records = shortlist.to_dict(orient="records")
    with open("data/esios_indicators_shortlist.json", "w", encoding="utf-8") as f:
        json.dump(shortlist_records, f, ensure_ascii=False, indent=2)
    print("\nGuardado: data/esios_indicators_shortlist.json")
    print(
        "\nRevisa la shortlist a mano: hay que elegir, para cada variable "
        "que queremos predecir, el/los id definitivos (puede haber "
        "duplicados o variantes por tipo de mercado/agregación)."
    )


if __name__ == "__main__":
    main()
