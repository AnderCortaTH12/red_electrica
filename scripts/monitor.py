"""Monitorización diaria: calidad de datos + error real de las
predicciones ya verificables. Escribe data/monitoring_report.json y
emite avisos de GitHub Actions (`::warning::`) si algo destaca.

No falla el job por un error alto: un error alto es una señal a
vigilar (esperable dado que el error crece de forma estructural, ver
Fase 5), no necesariamente un fallo del pipeline. Si el propio job
falla (ingesta o reentrenamiento con error), eso YA lo marca GitHub
Actions como fallo del workflow — este script solo añade la señal más
sutil de "algo va peor de lo normal aunque nada se haya roto".

Uso:
    python -m scripts.monitor
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from src.features.load import load_catalog
from src.monitoring.data_quality import check_gaps, check_out_of_range, check_stale_indicators
from src.monitoring.error_tracking import recent_error

DB_PATH = "data/electricidad.db"
OUTPUT_PATH = "data/monitoring_report.json"
PREDICTIONS_LOG_PATH = Path("docs/data/predictions_log.json")

# El baseline naive ya llega a MAE ~67 EUR/MWh en 2026 (ver README);
# ponemos el umbral bastante por encima para no disparar avisos por el
# deterioro estructural ya conocido, solo por algo genuinamente peor.
MAE_ALERT_THRESHOLD_EUR_MWH = 150.0


def warn(message: str) -> None:
    # sintaxis especial de GitHub Actions: marca un aviso visible en la
    # UI del workflow sin fallar el job.
    print(f"::warning::{message}")
    print(f"AVISO: {message}")


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    catalog = load_catalog()

    gaps = check_gaps(conn, catalog)
    stale = check_stale_indicators(conn, catalog)
    out_of_range = check_out_of_range(conn, catalog)
    error_7d = recent_error(conn, PREDICTIONS_LOG_PATH, days=7)

    conn.close()

    for p in gaps:
        warn(
            f"Hueco de datos: indicador {p['indicator_id']} ({p['nombre']}) - "
            f"{p['filas_encontradas']}/{p['filas_esperadas_aprox']} filas en las últimas 72h"
        )
    for p in stale:
        detalle = p.get("horas_sin_actualizar", "sin ningún dato")
        warn(f"Indicador obsoleto: {p['indicator_id']} ({p['nombre']}) - {detalle}")
    for p in out_of_range:
        warn(
            f"Valores fuera de rango: indicador {p['indicator_id']} ({p['nombre']}) - "
            f"{p['filas_fuera_de_rango']} filas fuera de {p['rango_esperado']}"
        )
    if error_7d["mae"] is not None and error_7d["mae"] > MAE_ALERT_THRESHOLD_EUR_MWH:
        warn(
            f"MAE de los últimos 7 días ({error_7d['mae']:.2f} EUR/MWh) "
            f"supera el umbral de alerta ({MAE_ALERT_THRESHOLD_EUR_MWH})"
        )

    n_problems = len(gaps) + len(stale) + len(out_of_range)
    print(f"\n{n_problems} problema(s) de calidad de datos.")
    print(f"Error real (7 días): {error_7d}")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "gaps": gaps,
        "stale_indicators": stale,
        "out_of_range": out_of_range,
        "error_ultimos_7_dias": error_7d,
        "mae_alert_threshold_eur_mwh": MAE_ALERT_THRESHOLD_EUR_MWH,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\nInforme guardado: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
