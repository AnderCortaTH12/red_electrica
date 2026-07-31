import json

import pandas as pd

from src.storage.predictions_log import append_predictions_log, load_predictions_log


def test_load_missing_file_returns_empty_dataframe(tmp_path):
    df = load_predictions_log(tmp_path / "no_existe.json")
    assert df.empty
    assert list(df.columns) == ["target_datetime_utc", "predicted_price", "model_version", "made_at"]


def test_append_creates_file_with_row_per_line(tmp_path):
    path = tmp_path / "predictions_log.json"
    preds = pd.DataFrame(
        {"datetime_utc": ["2026-07-31T10:00:00Z", "2026-07-31T11:00:00Z"], "predicted_price": [50.1, 55.2]}
    )

    append_predictions_log(path, preds, model_version="v1")

    raw = path.read_text(encoding="utf-8")
    # cada fila en su propia linea (git-friendly), no todo en una linea
    assert raw.count("\n") > 3
    data = json.loads(raw)
    assert data["columns"] == ["target_datetime_utc", "predicted_price", "model_version", "made_at"]
    assert len(data["rows"]) == 2


def test_append_persists_across_calls_like_across_hourly_runs(tmp_path):
    """El escenario real: una ejecucion horaria predice unas horas, la
    siguiente predice otras (o las mismas, refinadas) -- el log
    acumulado debe conservar el historico completo, no solo lo ultimo."""
    path = tmp_path / "predictions_log.json"

    append_predictions_log(
        path,
        pd.DataFrame({"datetime_utc": ["2026-07-31T10:00:00Z"], "predicted_price": [50.0]}),
        model_version="v1",
    )
    append_predictions_log(
        path,
        pd.DataFrame({"datetime_utc": ["2026-07-31T11:00:00Z"], "predicted_price": [60.0]}),
        model_version="v1",
    )

    log = load_predictions_log(path)
    assert len(log) == 2
    assert set(log["target_datetime_utc"]) == {"2026-07-31T10:00:00Z", "2026-07-31T11:00:00Z"}


def test_append_keeps_latest_value_when_same_hour_predicted_again(tmp_path):
    """Una hora que sigue sin publicarse se vuelve a predecir en runs
    sucesivos -- se debe quedar con el valor mas reciente (la prevision
    mas informada), no duplicar la fila."""
    path = tmp_path / "predictions_log.json"
    t = "2026-07-31T10:00:00Z"

    append_predictions_log(path, pd.DataFrame({"datetime_utc": [t], "predicted_price": [50.0]}), "v1")
    append_predictions_log(path, pd.DataFrame({"datetime_utc": [t], "predicted_price": [53.5]}), "v1")

    log = load_predictions_log(path)
    assert len(log) == 1
    assert log.iloc[0]["predicted_price"] == 53.5


def test_append_freezes_hour_once_no_longer_predicted():
    """Una vez una hora deja de aparecer en preds_df (porque ya se
    publico su precio), su fila queda tal cual en el log -- no se
    borra ni se toca en runs posteriores."""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "predictions_log.json"
        t1, t2 = "2026-07-31T10:00:00Z", "2026-07-31T11:00:00Z"

        append_predictions_log(
            path, pd.DataFrame({"datetime_utc": [t1, t2], "predicted_price": [50.0, 60.0]}), "v1"
        )
        # el siguiente run: t1 ya se publico y no se vuelve a predecir, solo t2
        append_predictions_log(path, pd.DataFrame({"datetime_utc": [t2], "predicted_price": [61.0]}), "v1")

        log = load_predictions_log(path).set_index("target_datetime_utc")
        assert log.loc[t1, "predicted_price"] == 50.0  # intacta
        assert log.loc[t2, "predicted_price"] == 61.0  # actualizada
