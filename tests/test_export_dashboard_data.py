import json

import numpy as np
import pandas as pd
import pytest

from src.storage.db import get_connection, init_db, insert_observations, insert_predictions

from scripts.export_dashboard_data import (
    GEN_COLUMNS,
    _iso_z,
    _round,
    build_horas_72h,
    build_kpis,
    build_model_performance,
    build_status,
    build_summary_rows,
    export_monthly_files,
    write_summary_json,
)


def test_round_handles_none_and_nan():
    assert _round(None) is None
    assert _round(float("nan")) is None
    assert _round(3.14159, 2) == 3.14


def test_iso_z_format():
    ts = pd.Timestamp("2026-07-30T18:00:00", tz="UTC")
    assert _iso_z(ts) == "2026-07-30T18:00:00Z"


def synthetic_df(n=400, start="2024-02-01"):
    idx = pd.date_range(start, periods=n, freq="h", tz="UTC")
    rng = np.random.default_rng(0)
    cols = ["precio_spot", "demanda_real"] + GEN_COLUMNS
    return pd.DataFrame({c: rng.uniform(10, 100, n) for c in cols}, index=idx)


def test_build_kpis_uses_madrid_day_window():
    df = synthetic_df()
    now = df.index.max()
    kpis = build_kpis(df, now)

    assert kpis["precio_actual"] is not None
    assert kpis["precio_min_hoy"] <= kpis["precio_actual"] <= kpis["precio_max_hoy"]
    assert kpis["hora_mas_cara_utc"].endswith("Z")


def test_build_kpis_day_boundary_is_madrid_not_utc():
    """En verano Madrid va +2h: el dia natural espanol empieza a las
    22:00Z del dia anterior. Un dato de las 22:30Z del dia D-1 pertenece
    ya al dia D espanol y debe entrar en los KPIs de 'hoy'; con el corte
    en UTC quedaba fuera."""
    idx = pd.date_range("2026-07-29T21:00:00Z", periods=6, freq="h", tz="UTC")
    df = pd.DataFrame(
        {c: [50.0] * len(idx) for c in ["precio_spot", "demanda_real"] + GEN_COLUMNS},
        index=idx,
    )
    # 2026-07-29T22:00Z == 2026-07-30 00:00 en Madrid -> dia espanol 30
    df.loc["2026-07-29T22:00:00Z", "precio_spot"] = 999.0
    # 2026-07-29T21:00Z == 2026-07-29 23:00 en Madrid -> dia espanol 29
    df.loc["2026-07-29T21:00:00Z", "precio_spot"] = -999.0

    kpis = build_kpis(df, pd.Timestamp("2026-07-30T02:00:00Z"))

    assert kpis["precio_max_hoy"] == 999.0  # la hora de las 22:00Z SI cuenta
    assert kpis["precio_min_hoy"] != -999.0  # la de las 21:00Z NO


def test_build_summary_rows_aggregates_by_madrid_day():
    """Regresion del desajuste con OMIE: agregando por dia UTC la media
    del 30-jul-2026 salia 129.05 en vez de los 128.55 que publica OMIE,
    porque el dia UTC va desplazado 2h respecto al dia espanol."""
    idx = pd.date_range("2026-06-30T22:00:00Z", periods=24, freq="h", tz="UTC")
    df = pd.DataFrame(
        {c: [1000.0] * 24 for c in ["demanda_real"] + GEN_COLUMNS}, index=idx
    )
    # las 24h del dia espanol 1-jul valen 100; se anaden vecinas distintas
    df["precio_spot"] = 100.0

    rows = build_summary_rows(df)
    by_date = {r[0]: r for r in rows}

    assert "2026-07-01" in by_date
    fila = by_date["2026-07-01"]
    assert fila[1] == 100.0  # media exacta del dia espanol completo
    # y ese dia agrupa las 24 horas, no 22 ni 26
    assert fila[2] == 100.0 and fila[3] == 100.0


def test_build_kpis_empty_when_no_data_today():
    df = synthetic_df()
    far_future = df.index.max() + pd.Timedelta(days=5)
    kpis = build_kpis(df, far_future)
    assert kpis["precio_actual"] is None


def test_build_horas_72h_length_and_keys():
    df = synthetic_df()
    now = df.index.max()
    baseline = pd.Series(dtype=float)
    model_preds = pd.Series(dtype=float)

    out = build_horas_72h(df, baseline, model_preds, now)

    assert len(out["datetime_utc"]) == 73  # 72h + la hora actual
    for col in GEN_COLUMNS:
        assert col in out
        assert len(out[col]) == len(out["datetime_utc"])


def test_build_status_no_report_file(tmp_path, monkeypatch):
    import scripts.export_dashboard_data as mod

    monkeypatch.setattr(mod, "MONITORING_REPORT_PATH", tmp_path / "nope.json")
    status = build_status(None, "2026-07-30T18:00:00Z")

    assert status["health"] == "green"
    assert status["quality_flags"] == []
    assert status["model_type"] is None


def test_build_status_with_flags_is_amber(tmp_path, monkeypatch):
    import scripts.export_dashboard_data as mod

    report_path = tmp_path / "monitoring_report.json"
    report_path.write_text(
        json.dumps(
            {
                "gaps": [{"indicator_id": 600, "nombre": "Precio", "filas_encontradas": 10, "filas_esperadas_aprox": 72}],
                "stale_indicators": [],
                "out_of_range": [],
                "error_ultimos_7_dias": {"mae": None},
                "mae_alert_threshold_eur_mwh": 150.0,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(mod, "MONITORING_REPORT_PATH", report_path)

    metadata = {"model_type": "lightgbm", "model_version": "v1", "trained_at": "v1"}
    status = build_status(metadata, "2026-07-30T18:00:00Z")

    assert status["health"] == "amber"
    assert len(status["quality_flags"]) == 1
    assert status["quality_flags"][0]["tipo"] == "hueco"


def test_build_status_high_error_is_amber(tmp_path, monkeypatch):
    import scripts.export_dashboard_data as mod

    report_path = tmp_path / "monitoring_report.json"
    report_path.write_text(
        json.dumps(
            {
                "gaps": [],
                "stale_indicators": [],
                "out_of_range": [],
                "error_ultimos_7_dias": {"mae": 200.0},
                "mae_alert_threshold_eur_mwh": 150.0,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(mod, "MONITORING_REPORT_PATH", report_path)

    status = build_status(None, "2026-07-30T18:00:00Z")

    assert status["health"] == "amber"
    assert status["quality_flags"][0]["tipo"] == "error_alto"


def test_build_summary_rows_skips_days_without_price():
    # arranca a las 23:00Z = 00:00 del 1-ene en Madrid (invierno, +1h),
    # para que las 24 horas con precio sean exactamente un dia espanol
    idx = pd.date_range("2018-12-31T23:00:00Z", periods=48, freq="h", tz="UTC")
    df = pd.DataFrame(
        {
            "precio_spot": [50.0] * 24 + [np.nan] * 24,
            "demanda_real": [1000.0] * 48,
            **{col: [100.0] * 48 for col in GEN_COLUMNS},
        },
        index=idx,
    )

    rows = build_summary_rows(df)

    assert len(rows) == 1  # solo el primer dia tiene precio
    assert rows[0][0] == "2019-01-01"


def test_build_summary_rows_computes_ratio_renovable():
    idx = pd.date_range("2019-01-01", periods=24, freq="h", tz="UTC")
    gen = {col: [100.0] * 24 for col in GEN_COLUMNS}
    gen["gen_nuclear"] = [0.0] * 24  # no renovable, no debe contar
    gen["gen_carbon"] = [0.0] * 24
    gen["gen_ciclo_combinado"] = [0.0] * 24
    df = pd.DataFrame(
        {"precio_spot": [50.0] * 24, "demanda_real": [400.0] * 24, **gen}, index=idx
    )

    rows = build_summary_rows(df)

    # 4 tecnologias renovables x 100 = 400 renovable / 400 demanda = 1.0
    assert rows[0][-1] == 1.0


def test_write_summary_json_one_row_per_line(tmp_path, monkeypatch):
    import scripts.export_dashboard_data as mod

    monkeypatch.setattr(mod, "DOCS_DATA_DIR", tmp_path)
    rows = [["2019-01-01", 1.0], ["2019-01-02", 2.0]]

    path = write_summary_json(rows)
    lines = path.read_text(encoding="utf-8").splitlines()

    row_lines = [l for l in lines if l.strip().startswith("[")]
    assert len(row_lines) == 2
    assert '"2019-01-01"' in row_lines[0]


def test_export_monthly_files_does_not_overwrite_past_months(tmp_path, monkeypatch):
    import scripts.export_dashboard_data as mod

    monkeypatch.setattr(mod, "DOCS_DATA_DIR", tmp_path)
    monkeypatch.setattr(mod, "SUMMARY_START", "2024-01-01")

    df = synthetic_df(n=24 * 40, start="2024-01-01")  # ~40 dias, cruza a febrero
    baseline = pd.Series(dtype=float)
    model_preds = pd.Series(dtype=float)
    now = df.index.max()

    export_monthly_files(df, baseline, model_preds, now)
    current_month_path = tmp_path / "monthly" / f"{now.year:04d}-{now.month:02d}.json"
    past_month_path = tmp_path / "monthly" / "2024-01.json"

    assert past_month_path.exists()
    original_mtime = past_month_path.stat().st_mtime
    original_content = past_month_path.read_text(encoding="utf-8")

    # segunda ejecucion: el mes pasado no debe reescribirse
    export_monthly_files(df, baseline, model_preds, now)

    assert past_month_path.stat().st_mtime == original_mtime
    assert past_month_path.read_text(encoding="utf-8") == original_content
    assert current_month_path.exists()


def test_build_model_performance_without_metrics_files(tmp_path, monkeypatch):
    import scripts.export_dashboard_data as mod

    monkeypatch.setattr(mod, "BASELINE_METRICS_PATH", tmp_path / "nope1.json")
    monkeypatch.setattr(mod, "LIGHTGBM_METRICS_PATH", tmp_path / "nope2.json")

    conn = get_connection(str(tmp_path / "test.db"))
    init_db(conn)

    result = build_model_performance(conn)

    assert result["baseline_por_anio"] == []
    assert result["modelo_por_anio"] == []
    assert result["scatter"] == []
    conn.close()


def test_build_model_performance_scatter_from_verified_predictions(tmp_path, monkeypatch):
    import scripts.export_dashboard_data as mod

    monkeypatch.setattr(mod, "BASELINE_METRICS_PATH", tmp_path / "nope1.json")
    monkeypatch.setattr(mod, "LIGHTGBM_METRICS_PATH", tmp_path / "nope2.json")

    conn = get_connection(str(tmp_path / "test.db"))
    init_db(conn)

    target = "2026-07-01T10:00:00Z"
    insert_observations(
        conn,
        pd.DataFrame(
            {
                "source": ["esios"], "indicator_id": [600], "datetime_utc": [target],
                "geo_id": [3], "value": [55.5],
            }
        ),
    )
    insert_predictions(
        conn,
        pd.DataFrame(
            {
                "model_version": ["v1"], "target_datetime_utc": [target],
                "predicted_price": [50.0], "made_at": [target],
            }
        ),
    )

    result = build_model_performance(conn)

    assert len(result["scatter"]) == 1
    assert result["scatter"][0] == {"actual": 55.5, "predicted": 50.0}
    conn.close()
