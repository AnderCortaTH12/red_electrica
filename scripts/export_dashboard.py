"""Genera los JSON estáticos que consume el dashboard (docs/index.html).

GitHub Pages es estático: no hay Python en runtime, así que todo lo que
el navegador necesita mostrar tiene que estar precalculado aquí.

Tres ficheros en docs/data/:
- catalogo.json: el catálogo de métricas tal cual (jerarquía, unidades,
  dimensión), para que el frontend sepa qué es cada metrica_id sin
  tener que hardcodear etiquetas.
- serie.json: el dataset completo de data/gas.csv en formato
  {columns, rows}, una fila por línea de texto (igual que hacía el
  proyecto anterior con summary.json) para que el diff de cada
  ejecución mensual sean unas pocas líneas, no el fichero entero.
- ultimo.json: KPIs del último periodo disponible + su serie mensual
  del año, para pintar la portada al instante sin esperar a que el
  navegador termine de parsear serie.json entero.

Reutilizable a mano:
    python -m scripts.export_dashboard

También es un paso de .github/workflows/mensual.yml, con
continue-on-error para no tumbar el resto del pipeline si falla.
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

import pandas as pd

from src.extraccion.catalogo import cargar_catalogo

GAS_CSV_PATH = Path("data/gas.csv")
DOCS_DATA_DIR = Path("docs/data")

SERIE_COLUMNS = [
    "periodo",
    "metrica_id",
    "dimension",
    "agregacion",
    "valor",
    "unidad",
    "var_pct_interanual",
]

# KPIs de la portada (Fase 6, sección 7.3, vista "Resumen").
KPI_METRICAS = [
    "total_salidas",
    "demanda_nacional",
    "demanda_convencional",
    "demanda_sector_electrico",
]


def _clean(value):
    """None para NaN/NaT, tipos nativos de Python para todo lo demás
    (json.dump no sabe serializar numpy.float64/int64)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if pd.isna(value) if not isinstance(value, (list, dict)) else False:
        return None
    if isinstance(value, (int, float)):
        return float(value) if isinstance(value, float) else int(value)
    return value


def write_rows_json(path: Path, payload: dict) -> None:
    """Escribe {..., columns, rows} con cada fila en su propia línea,
    para que git pueda hacer delta de los ficheros que se reescriben
    en cada ejecución (ver docstring del módulo)."""
    rows = payload["rows"]
    head = {k: v for k, v in payload.items() if k != "rows"}
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("{\n")
        for key, value in head.items():
            f.write(f"  {json.dumps(key, ensure_ascii=False)}: ")
            f.write(json.dumps(value, ensure_ascii=False) + ",\n")
        f.write('  "rows": [\n')
        for i, row in enumerate(rows):
            comma = "," if i < len(rows) - 1 else ""
            f.write("    " + json.dumps(row, ensure_ascii=False) + comma + "\n")
        f.write("  ]\n}\n")


def build_serie_rows(df: pd.DataFrame) -> list[list]:
    rows = []
    for row in df[SERIE_COLUMNS].itertuples(index=False):
        rows.append(
            [
                row.periodo,
                row.metrica_id,
                _clean(row.dimension),
                row.agregacion,
                _clean(row.valor),
                row.unidad,
                _clean(row.var_pct_interanual),
            ]
        )
    return rows


def _serie_mensual(df: pd.DataFrame, metrica_id: str) -> list[list]:
    """[[periodo, valor], ...] ordenado, solo agregacion=mes, escalar
    (sin dimensión) -- lo que pinta un sparkline."""
    sub = df[
        (df["metrica_id"] == metrica_id) & (df["agregacion"] == "mes") & (df["dimension"].isna())
    ].sort_values("periodo")
    return [[r.periodo, _clean(r.valor)] for r in sub.itertuples(index=False)]


def build_ultimo(df: pd.DataFrame, catalogo_idx: dict[str, dict]) -> dict:
    if df.empty:
        return {"periodo": None, "generado_el": None, "kpis": []}

    ultimo_periodo = sorted(df["periodo"].unique())[-1]

    kpis = []
    for metrica_id in KPI_METRICAS:
        fila = df[
            (df["metrica_id"] == metrica_id)
            & (df["agregacion"] == "mes")
            & (df["periodo"] == ultimo_periodo)
            & (df["dimension"].isna())
        ]
        valor = _clean(fila["valor"].iloc[0]) if not fila.empty else None
        var_pct = _clean(fila["var_pct_interanual"].iloc[0]) if not fila.empty else None
        kpis.append(
            {
                "metrica_id": metrica_id,
                "nombre": catalogo_idx.get(metrica_id, {}).get("nombre", metrica_id),
                "unidad": catalogo_idx.get(metrica_id, {}).get("unidad_canonica"),
                "valor": valor,
                "var_pct_interanual": var_pct,
                "sparkline": _serie_mensual(df, metrica_id),
            }
        )

    return {
        "periodo": ultimo_periodo,
        "generado_el": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ"),
        "kpis": kpis,
    }


def run() -> None:
    DOCS_DATA_DIR.mkdir(parents=True, exist_ok=True)
    catalogo = cargar_catalogo()
    catalogo_idx = {m["metrica_id"]: m for m in catalogo}

    with open(DOCS_DATA_DIR / "catalogo.json", "w", encoding="utf-8") as f:
        json.dump(catalogo, f, ensure_ascii=False, indent=2)
    print("catalogo.json generado")

    if not GAS_CSV_PATH.exists():
        df = pd.DataFrame(columns=SERIE_COLUMNS)
    else:
        df = pd.read_csv(GAS_CSV_PATH, dtype={"periodo": str})

    write_rows_json(DOCS_DATA_DIR / "serie.json", {"columns": SERIE_COLUMNS, "rows": build_serie_rows(df)})
    print(f"serie.json generado con {len(df)} filas")

    ultimo = build_ultimo(df, catalogo_idx)
    with open(DOCS_DATA_DIR / "ultimo.json", "w", encoding="utf-8") as f:
        json.dump(ultimo, f, ensure_ascii=False, indent=2)
    print(f"ultimo.json generado (periodo {ultimo['periodo']})")


def main() -> int:
    try:
        run()
    except Exception:
        print("ERROR generando datos del dashboard:", file=sys.stderr)
        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
