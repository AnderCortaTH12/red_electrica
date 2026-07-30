"""Genera los JSON estáticos que consume el dashboard (docs/index.html).

GitHub Pages es estático: no hay Python en runtime, así que todo lo que
el navegador necesita mostrar tiene que estar precalculado aquí.

Tres ficheros:
- docs/data/latest.json: siempre se carga al abrir. Últimas 72h,
  predicción próximas horas, KPIs del día, estado del sistema, error
  rolling del modelo y del baseline.
- docs/data/monthly/YYYY-MM.json: uno por mes, cargado bajo demanda al
  navegar a una fecha. Los meses PASADOS son inmutables -- solo se
  regenera el mes en curso en cada ejecución, para no inflar el
  historial de git con ~90 ficheros reescritos cada día.
- docs/data/summary.json: series diarias 2019-hoy. Formato particular
  (objeto {columns, rows} con cada fila en su propia línea) para que
  el diff diario sean 1-2 líneas, no el fichero entero (~200KB).
- docs/data/model_performance.json: MAE por año (2014-hoy) del baseline
  y del modelo, más el scatter predicho-vs-real de las predicciones ya
  verificadas -- crece día a día según se conocen los precios reales.

Reutilizable a mano:
    python -m scripts.export_dashboard_data

También es el último paso de .github/workflows/daily.yml, con
continue-on-error para no tumbar el resto del pipeline si falla.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import traceback
from pathlib import Path

import pandas as pd

from src.features.load import load_catalog, load_wide_dataframe
from src.model.artifact import load_model_artifact
from src.model.baseline import naive_forecast
from src.model.metrics import mae, rmse
from src.model.predict import latest_predictions
from src.monitoring.error_tracking import recent_error

DB_PATH = "data/electricidad.db"
DOCS_DATA_DIR = Path("docs/data")
MONITORING_REPORT_PATH = Path("data/monitoring_report.json")

GEN_COLUMNS = [
    "gen_eolica",
    "gen_solar_fv",
    "gen_solar_termica",
    "gen_nuclear",
    "gen_hidraulica",
    "gen_ciclo_combinado",
    "gen_carbon",
]
RENEWABLE_COLUMNS = ["gen_eolica", "gen_solar_fv", "gen_solar_termica", "gen_hidraulica"]

SUMMARY_START = "2019-01-01"
SUMMARY_COLUMNS = [
    "date",
    "precio_medio",
    "precio_min",
    "precio_max",
    "demanda_media",
    "gen_eolica",
    "gen_solar_fv",
    "gen_solar_termica",
    "gen_nuclear",
    "gen_hidraulica",
    "gen_ciclo_combinado",
    "gen_carbon",
    "ratio_renovable",
]

PREDICTION_HORIZON_HOURS = 24
LATEST_WINDOW_HOURS = 72


def _round(value, ndigits: int = 2):
    if value is None or pd.isna(value):
        return None
    return round(float(value), ndigits)


def _iso_z(ts: pd.Timestamp) -> str:
    """Formatea como 'YYYY-MM-DDTHH:MM:SSZ', igual que el resto del
    proyecto (observations.datetime_utc), en vez de '+00:00'."""
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def load_all_predictions(conn: sqlite3.Connection) -> pd.Series:
    """Predicciones logueadas por hora objetivo, quedándose con la más
    reciente si una misma hora se predijo más de una vez (el horizonte
    de predicción se solapa día a día)."""
    query = "SELECT target_datetime_utc, predicted_price, made_at FROM predictions ORDER BY made_at"
    df = pd.read_sql_query(query, conn)
    if df.empty:
        return pd.Series(dtype=float)
    df = df.drop_duplicates(subset="target_datetime_utc", keep="last")
    idx = pd.to_datetime(df["target_datetime_utc"], utc=True)
    return pd.Series(df["predicted_price"].values, index=idx)


def build_status(metadata: dict | None, generated_at: str) -> dict:
    quality_flags = []
    if MONITORING_REPORT_PATH.exists():
        with open(MONITORING_REPORT_PATH, encoding="utf-8") as f:
            report = json.load(f)
        for p in report.get("gaps", []):
            quality_flags.append(
                {
                    "tipo": "hueco",
                    "indicator_id": p["indicator_id"],
                    "nombre": p["nombre"],
                    "detalle": f"{p['filas_encontradas']}/{p['filas_esperadas_aprox']} filas en 72h",
                }
            )
        for p in report.get("stale_indicators", []):
            quality_flags.append(
                {
                    "tipo": "obsoleto",
                    "indicator_id": p["indicator_id"],
                    "nombre": p["nombre"],
                    "detalle": str(p.get("horas_sin_actualizar", "sin datos")),
                }
            )
        for p in report.get("out_of_range", []):
            quality_flags.append(
                {
                    "tipo": "fuera_de_rango",
                    "indicator_id": p["indicator_id"],
                    "nombre": p["nombre"],
                    "detalle": f"{p['filas_fuera_de_rango']} filas",
                }
            )
        error_7d = report.get("error_ultimos_7_dias", {})
        mae_alert, threshold = error_7d.get("mae"), report.get("mae_alert_threshold_eur_mwh")
        if mae_alert is not None and threshold is not None and mae_alert > threshold:
            quality_flags.append(
                {
                    "tipo": "error_alto",
                    "detalle": f"MAE 7d {mae_alert:.2f} EUR/MWh > umbral {threshold}",
                }
            )

    health = "amber" if quality_flags else "green"

    return {
        "model_type": metadata.get("model_type") if metadata else None,
        "model_version": metadata.get("model_version") if metadata else None,
        "trained_at": metadata.get("trained_at") if metadata else None,
        "last_run_at": generated_at,
        "last_run_status": "ok",
        "health": health,
        "quality_flags": quality_flags,
    }


def build_kpis(df: pd.DataFrame, now_utc: pd.Timestamp) -> dict:
    """KPIs del día en curso. Día = día natural en UTC (todo el backend
    trabaja en UTC; el frontend convierte a Europe/Madrid al mostrar)."""
    today_start = pd.Timestamp(now_utc.date(), tz="UTC")
    today_end = today_start + pd.Timedelta(days=1)
    todays = df.loc[(df.index >= today_start) & (df.index < today_end), "precio_spot"].dropna()

    empty = {
        "precio_actual": None,
        "precio_actual_datetime_utc": None,
        "precio_min_hoy": None,
        "precio_max_hoy": None,
        "precio_medio_hoy": None,
        "delta_vs_ayer_pct": None,
        "hora_mas_cara_utc": None,
        "hora_mas_barata_utc": None,
    }
    if todays.empty:
        return empty

    precio_actual_ts = todays.index.max()
    precio_actual = todays.loc[precio_actual_ts]

    delta_pct = None
    yesterday_ts = precio_actual_ts - pd.Timedelta(days=1)
    if yesterday_ts in df.index:
        ayer_val = df.loc[yesterday_ts, "precio_spot"]
        if pd.notna(ayer_val) and ayer_val != 0:
            delta_pct = (precio_actual - ayer_val) / abs(ayer_val) * 100

    return {
        "precio_actual": _round(precio_actual),
        "precio_actual_datetime_utc": _iso_z(precio_actual_ts),
        "precio_min_hoy": _round(todays.min()),
        "precio_max_hoy": _round(todays.max()),
        "precio_medio_hoy": _round(todays.mean()),
        "delta_vs_ayer_pct": _round(delta_pct, 1),
        "hora_mas_cara_utc": _iso_z(todays.idxmax()),
        "hora_mas_barata_utc": _iso_z(todays.idxmin()),
    }


def build_horas_72h(
    df: pd.DataFrame, baseline: pd.Series, model_preds: pd.Series, now_utc: pd.Timestamp
) -> dict:
    start = now_utc - pd.Timedelta(hours=LATEST_WINDOW_HOURS)
    window = df.loc[(df.index >= start) & (df.index <= now_utc)]
    idx = window.index

    out = {
        "datetime_utc": [_iso_z(t) for t in idx],
        "precio_real": [_round(v) for v in window["precio_spot"]],
        "precio_modelo": [_round(model_preds.get(t)) for t in idx],
        "precio_baseline": [_round(baseline.get(t)) for t in idx],
    }
    for col in GEN_COLUMNS:
        out[col] = [_round(v) for v in window[col]]
    return out


def build_prediccion_24h(df, catalog, model, metadata, baseline: pd.Series) -> dict:
    if model is None:
        return {"datetime_utc": [], "precio_modelo": [], "precio_baseline": []}

    preds = latest_predictions(
        df, catalog, model, metadata["feature_columns"], hours=PREDICTION_HORIZON_HOURS
    )
    if preds.empty:
        return {"datetime_utc": [], "precio_modelo": [], "precio_baseline": []}

    return {
        "datetime_utc": [_iso_z(t) for t in preds["datetime_utc"]],
        "precio_modelo": [_round(v) for v in preds["predicted_price"]],
        "precio_baseline": [_round(baseline.get(t)) for t in preds["datetime_utc"]],
    }


def build_error_rolling(conn: sqlite3.Connection, df: pd.DataFrame, baseline: pd.Series) -> dict:
    model_7d = recent_error(conn, days=7)
    model_30d = recent_error(conn, days=30)

    y_true = df["precio_spot"]
    now = pd.Timestamp.now(tz="UTC")

    def baseline_error(days: int) -> tuple[float | None, float | None]:
        cutoff = now - pd.Timedelta(days=days)
        mask = (y_true.index >= cutoff) & y_true.notna() & baseline.notna()
        yt, yp = y_true[mask], baseline[mask]
        if len(yt) == 0:
            return None, None
        return mae(yt, yp), rmse(yt, yp)

    baseline_mae_7d, _ = baseline_error(7)
    baseline_mae_30d, _ = baseline_error(30)

    return {
        "mae_modelo_7d": _round(model_7d["mae"]),
        "mae_baseline_7d": _round(baseline_mae_7d),
        "mae_modelo_30d": _round(model_30d["mae"]),
        "mae_baseline_30d": _round(baseline_mae_30d),
        "n_7d": model_7d["n"],
        "n_30d": model_30d["n"],
    }


def build_monthly_payload(
    df: pd.DataFrame, baseline: pd.Series, model_preds: pd.Series, year: int, month: int
) -> dict:
    start = pd.Timestamp(year=year, month=month, day=1, tz="UTC")
    end = start + pd.DateOffset(months=1)
    window = df.loc[(df.index >= start) & (df.index < end)]
    idx = window.index

    payload = {
        "year_month": f"{year:04d}-{month:02d}",
        "datetime_utc": [_iso_z(t) for t in idx],
        "precio_real": [_round(v) for v in window["precio_spot"]],
        "precio_modelo": [_round(model_preds.get(t)) for t in idx],
        "precio_baseline": [_round(baseline.get(t)) for t in idx],
        "demanda_real": [_round(v) for v in window["demanda_real"]],
    }
    for col in GEN_COLUMNS:
        payload[col] = [_round(v) for v in window[col]]
    return payload


def export_monthly_files(
    df: pd.DataFrame, baseline: pd.Series, model_preds: pd.Series, now_utc: pd.Timestamp
) -> list[str]:
    """Escribe un fichero por mes desde SUMMARY_START hasta el mes en
    curso. Los meses PASADOS solo se escriben si el fichero no existe
    todavía (inmutables); el mes en curso se regenera siempre."""
    monthly_dir = DOCS_DATA_DIR / "monthly"
    monthly_dir.mkdir(parents=True, exist_ok=True)

    current = (now_utc.year, now_utc.month)
    start_ts = pd.Timestamp(SUMMARY_START, tz="UTC")
    cursor = pd.Timestamp(year=start_ts.year, month=start_ts.month, day=1, tz="UTC")
    end_ts = pd.Timestamp(year=now_utc.year, month=now_utc.month, day=1, tz="UTC")

    written = []
    while cursor <= end_ts:
        year, month = cursor.year, cursor.month
        path = monthly_dir / f"{year:04d}-{month:02d}.json"
        is_current = (year, month) == current
        if path.exists() and not is_current:
            cursor = cursor + pd.DateOffset(months=1)
            continue
        payload = build_monthly_payload(df, baseline, model_preds, year, month)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
        written.append(path.name)
        cursor = cursor + pd.DateOffset(months=1)
    return written


BASELINE_METRICS_PATH = Path("models/baseline_metrics.json")
LIGHTGBM_METRICS_PATH = Path("models/lightgbm_metrics.json")
MAX_SCATTER_POINTS = 500


def build_model_performance(conn: sqlite3.Connection) -> dict:
    """Rendimiento del modelo a lo largo del tiempo: MAE por año (2014-hoy
    para el baseline, régimen post_tope para el modelo -- ver Fase 5) y
    el scatter predicho-vs-real de las predicciones ya verificadas
    (crece día a día según se van conociendo los precios reales).
    """
    baseline_por_anio, lightgbm_por_anio, holdout = [], [], {}

    if BASELINE_METRICS_PATH.exists():
        with open(BASELINE_METRICS_PATH, encoding="utf-8") as f:
            baseline_metrics = json.load(f)
        baseline_por_anio = [
            {"periodo": r["periodo"], "mae": _round(r["mae"]), "n": r["n"]}
            for r in baseline_metrics.get("por_anio", [])
            if r["periodo"] != "total"
        ]

    if LIGHTGBM_METRICS_PATH.exists():
        with open(LIGHTGBM_METRICS_PATH, encoding="utf-8") as f:
            lgbm_metrics = json.load(f)
        lightgbm_por_anio = [
            {"periodo": r["periodo"], "mae": _round(r["mae"]), "n": r["n"]}
            for r in lgbm_metrics.get("lightgbm_por_anio", [])
            if r["periodo"] != "total"
        ]
        holdout = {
            "modelo_tipo": lgbm_metrics.get("modelo"),
            "regimen": lgbm_metrics.get("regimen"),
            "test_start": lgbm_metrics.get("test_start"),
            "mae_modelo": _round(lgbm_metrics.get("lightgbm_mae")),
            "mae_baseline": _round(lgbm_metrics.get("baseline_mae")),
        }

    query = """
        SELECT o.value AS actual, p.predicted_price AS predicted, p.target_datetime_utc
        FROM predictions p
        JOIN observations o
          ON o.source = 'esios' AND o.indicator_id = 600 AND o.geo_id = 3
             AND o.datetime_utc = p.target_datetime_utc
        ORDER BY p.target_datetime_utc DESC
        LIMIT ?
    """
    scatter_df = pd.read_sql_query(query, conn, params=(MAX_SCATTER_POINTS,))
    scatter = [
        {"actual": _round(row.actual), "predicted": _round(row.predicted)}
        for row in scatter_df.itertuples()
    ]

    return {
        "baseline_por_anio": baseline_por_anio,
        "modelo_por_anio": lightgbm_por_anio,
        "holdout": holdout,
        "scatter": scatter,
    }


def build_summary_rows(df: pd.DataFrame) -> list[list]:
    start_ts = pd.Timestamp(SUMMARY_START, tz="UTC")
    window = df.loc[df.index >= start_ts]

    price_stats = window["precio_spot"].resample("D").agg(["mean", "min", "max"])
    daily_means = window[["demanda_real"] + GEN_COLUMNS].resample("D").mean()

    rows = []
    for date in price_stats.index:
        precio_medio = price_stats.loc[date, "mean"]
        if pd.isna(precio_medio):
            continue
        demanda_media = daily_means.loc[date, "demanda_real"]
        gen_values = {col: daily_means.loc[date, col] for col in GEN_COLUMNS}
        renewable_sum = sum(gen_values[c] for c in RENEWABLE_COLUMNS if pd.notna(gen_values[c]))
        ratio_renovable = (
            renewable_sum / demanda_media
            if pd.notna(demanda_media) and demanda_media != 0
            else None
        )
        rows.append(
            [
                date.strftime("%Y-%m-%d"),
                _round(precio_medio),
                _round(price_stats.loc[date, "min"]),
                _round(price_stats.loc[date, "max"]),
                _round(demanda_media),
                _round(gen_values["gen_eolica"]),
                _round(gen_values["gen_solar_fv"]),
                _round(gen_values["gen_solar_termica"]),
                _round(gen_values["gen_nuclear"]),
                _round(gen_values["gen_hidraulica"]),
                _round(gen_values["gen_ciclo_combinado"]),
                _round(gen_values["gen_carbon"]),
                _round(ratio_renovable, 3),
            ]
        )
    return rows


def write_summary_json(rows: list[list]) -> Path:
    """Cada fila en su propia línea a propósito: se regenera entero
    cada día, y con esto el diff diario son 1-2 líneas nuevas/cambiadas,
    no el fichero completo (~200KB)."""
    path = DOCS_DATA_DIR / "summary.json"
    with open(path, "w", encoding="utf-8") as f:
        f.write("{\n")
        f.write('  "columns": ' + json.dumps(SUMMARY_COLUMNS, ensure_ascii=False) + ",\n")
        f.write('  "rows": [\n')
        for i, row in enumerate(rows):
            comma = "," if i < len(rows) - 1 else ""
            f.write("    " + json.dumps(row, ensure_ascii=False) + comma + "\n")
        f.write("  ]\n")
        f.write("}\n")
    return path


def run() -> None:
    DOCS_DATA_DIR.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    catalog = load_catalog()
    df = load_wide_dataframe(conn, catalog)

    try:
        model, metadata = load_model_artifact()
    except FileNotFoundError:
        model, metadata = None, None

    now_utc = pd.Timestamp.now(tz="UTC")
    generated_at = _iso_z(now_utc)

    baseline = naive_forecast(df, lag_hours=24)
    all_predictions = load_all_predictions(conn)

    latest_payload = {
        "generated_at": generated_at,
        "status": build_status(metadata, generated_at),
        "kpis": build_kpis(df, now_utc),
        "horas_72h": build_horas_72h(df, baseline, all_predictions, now_utc),
        "prediccion_24h": build_prediccion_24h(df, catalog, model, metadata, baseline),
        "error_rolling": build_error_rolling(conn, df, baseline),
    }
    with open(DOCS_DATA_DIR / "latest.json", "w", encoding="utf-8") as f:
        json.dump(latest_payload, f, ensure_ascii=False, indent=2)
    print(f"latest.json generado ({generated_at})")

    written_months = export_monthly_files(df, baseline, all_predictions, now_utc)
    print(f"{len(written_months)} ficheros mensuales escritos: {written_months}")

    summary_rows = build_summary_rows(df)
    write_summary_json(summary_rows)
    print(f"summary.json generado con {len(summary_rows)} días")

    performance_payload = build_model_performance(conn)
    with open(DOCS_DATA_DIR / "model_performance.json", "w", encoding="utf-8") as f:
        json.dump(performance_payload, f, ensure_ascii=False, indent=2)
    print(f"model_performance.json generado ({len(performance_payload['scatter'])} puntos de scatter)")

    conn.close()


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
