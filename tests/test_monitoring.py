from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from src.monitoring.data_quality import check_gaps, check_out_of_range, check_stale_indicators
from src.monitoring.error_tracking import recent_error
from src.storage.db import get_connection, init_db, insert_observations
from src.storage.predictions_log import append_predictions_log


@pytest.fixture
def conn(tmp_path):
    connection = get_connection(str(tmp_path / "test.db"))
    init_db(connection)
    yield connection
    connection.close()


def make_catalog_entry(indicator_id=600, columna="precio_spot", geo_id=3):
    return {
        "id": indicator_id,
        "source": "esios",
        "name": f"Indicador {indicator_id}",
        "columna": columna,
        "geo_id_objetivo": geo_id,
    }


def make_obs_df(n, indicator_id=600, geo_id=3, values=None, start=None):
    if start is None:
        start = datetime.now(timezone.utc) - timedelta(hours=n)
    idx = pd.date_range(start, periods=n, freq="h", tz="UTC")
    return pd.DataFrame(
        {
            "source": ["esios"] * n,
            "indicator_id": [indicator_id] * n,
            "datetime_utc": [t.strftime("%Y-%m-%dT%H:%M:%SZ") for t in idx],
            "geo_id": [geo_id] * n,
            "value": values if values is not None else [50.0] * n,
        }
    )


# ---- check_gaps ----


def test_check_gaps_flags_indicator_with_few_recent_rows(conn):
    insert_observations(conn, make_obs_df(5))  # muy pocas filas en las ultimas 72h
    catalog = [make_catalog_entry()]

    problems = check_gaps(conn, catalog, window_hours=72)

    assert len(problems) == 1
    assert problems[0]["tipo"] == "hueco"
    assert problems[0]["indicator_id"] == 600


def test_check_gaps_no_problem_when_well_covered(conn):
    insert_observations(conn, make_obs_df(72))
    catalog = [make_catalog_entry()]

    problems = check_gaps(conn, catalog, window_hours=72)

    assert problems == []


# ---- check_stale_indicators ----


def test_check_stale_indicators_flags_no_data(conn):
    catalog = [make_catalog_entry()]
    problems = check_stale_indicators(conn, catalog)

    assert len(problems) == 1
    assert problems[0]["tipo"] == "sin_datos"


def test_check_stale_indicators_flags_old_last_value(conn):
    old_start = datetime.now(timezone.utc) - timedelta(days=5)
    insert_observations(conn, make_obs_df(3, start=old_start))
    catalog = [make_catalog_entry()]

    problems = check_stale_indicators(conn, catalog, stale_hours=48)

    assert len(problems) == 1
    assert problems[0]["tipo"] == "obsoleto"


def test_check_stale_indicators_ok_when_recent(conn):
    insert_observations(conn, make_obs_df(3))
    catalog = [make_catalog_entry()]

    problems = check_stale_indicators(conn, catalog, stale_hours=48)

    assert problems == []


# ---- check_out_of_range ----


def test_check_out_of_range_flags_values_outside_bounds(conn):
    insert_observations(conn, make_obs_df(3, values=[50.0, 50.0, 99999.0]))
    catalog = [make_catalog_entry()]

    problems = check_out_of_range(conn, catalog)

    assert len(problems) == 1
    assert problems[0]["filas_fuera_de_rango"] == 1


def test_check_out_of_range_ok_within_bounds(conn):
    insert_observations(conn, make_obs_df(3, values=[10.0, 50.0, 90.0]))
    catalog = [make_catalog_entry()]

    problems = check_out_of_range(conn, catalog)

    assert problems == []


# ---- recent_error ----


def test_recent_error_no_predictions_returns_none(conn, tmp_path):
    log_path = tmp_path / "predictions_log.json"
    result = recent_error(conn, log_path, days=7)
    assert result == {"n": 0, "mae": None, "rmse": None, "dias": 7}


def test_recent_error_computes_mae_against_actuals(conn, tmp_path):
    now = datetime.now(timezone.utc)
    target_hour = (now - timedelta(hours=2)).replace(minute=0, second=0, microsecond=0)
    target_str = target_hour.strftime("%Y-%m-%dT%H:%M:%SZ")
    log_path = tmp_path / "predictions_log.json"

    insert_observations(
        conn,
        pd.DataFrame(
            {
                "source": ["esios"],
                "indicator_id": [600],
                "datetime_utc": [target_str],
                "geo_id": [3],
                "value": [100.0],
            }
        ),
    )
    append_predictions_log(
        log_path,
        pd.DataFrame({"datetime_utc": [target_str], "predicted_price": [90.0]}),
        model_version="v1",
    )

    result = recent_error(conn, log_path, days=7)

    assert result["n"] == 1
    assert result["mae"] == pytest.approx(10.0)


def test_recent_error_ignores_predictions_outside_window(conn, tmp_path):
    old_target = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    log_path = tmp_path / "predictions_log.json"
    insert_observations(
        conn,
        pd.DataFrame(
            {
                "source": ["esios"], "indicator_id": [600], "datetime_utc": [old_target],
                "geo_id": [3], "value": [100.0],
            }
        ),
    )
    append_predictions_log(
        log_path,
        pd.DataFrame({"datetime_utc": [old_target], "predicted_price": [90.0]}),
        model_version="v1",
    )

    result = recent_error(conn, log_path, days=7)

    assert result["n"] == 0
