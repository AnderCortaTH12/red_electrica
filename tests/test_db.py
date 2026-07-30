"""Tests del almacenamiento SQLite: idempotencia de observations y
del tracking de ingestion_log (reanudabilidad).
"""

import pandas as pd
import pytest

from src.storage.db import (
    get_connection,
    init_db,
    insert_observations,
    is_period_done,
    mark_period,
    upsert_catalog,
)


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "test.db"
    connection = get_connection(str(db_path))
    init_db(connection)
    yield connection
    connection.close()


def make_df(n=3, source="esios", indicator_id=600):
    return pd.DataFrame(
        {
            "source": [source] * n,
            "indicator_id": [indicator_id] * n,
            "datetime_utc": [f"2019-01-01T0{i}:00:00Z" for i in range(n)],
            "geo_id": [3] * n,
            "value": [10.0 + i for i in range(n)],
        }
    )


def test_insert_observations_inserts_rows(conn):
    df = make_df(3)
    n_new = insert_observations(conn, df)

    assert n_new == 3
    count = conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
    assert count == 3


def test_insert_observations_is_idempotent(conn):
    df = make_df(3)
    insert_observations(conn, df)
    n_new_second_time = insert_observations(conn, df)

    assert n_new_second_time == 0
    count = conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
    assert count == 3


def test_insert_observations_empty_df_is_noop(conn):
    empty = pd.DataFrame(columns=["source", "indicator_id", "datetime_utc", "geo_id", "value"])
    n_new = insert_observations(conn, empty)
    assert n_new == 0


def test_different_sources_same_indicator_id_dont_collide(conn):
    df_esios = make_df(2, source="esios", indicator_id=600)
    df_other = make_df(2, source="otra-fuente", indicator_id=600)

    insert_observations(conn, df_esios)
    insert_observations(conn, df_other)

    count = conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
    assert count == 4


def test_is_period_done_roundtrip(conn):
    assert is_period_done(conn, "esios", 600, "2019-01-01", "2019-03-31") is False

    mark_period(conn, "esios", 600, "2019-01-01", "2019-03-31", "done", rows_fetched=100)

    assert is_period_done(conn, "esios", 600, "2019-01-01", "2019-03-31") is True


def test_failed_period_is_not_done(conn):
    mark_period(conn, "esios", 600, "2019-01-01", "2019-03-31", "failed", rows_fetched=0)
    assert is_period_done(conn, "esios", 600, "2019-01-01", "2019-03-31") is False


def test_mark_period_upgrades_failed_to_done(conn):
    mark_period(conn, "esios", 600, "2019-01-01", "2019-03-31", "failed", rows_fetched=0)
    mark_period(conn, "esios", 600, "2019-01-01", "2019-03-31", "done", rows_fetched=100)

    assert is_period_done(conn, "esios", 600, "2019-01-01", "2019-03-31") is True
    row = conn.execute(
        "SELECT COUNT(*) FROM ingestion_log WHERE indicator_id = 600"
    ).fetchone()
    assert row[0] == 1  # ON CONFLICT actualiza, no duplica fila


def test_upsert_catalog(conn):
    entries = [
        {
            "source": "esios",
            "id": 600,
            "name": "Precio SPOT",
            "categoria": "precio",
            "rol": "target",
            "cobertura_desde": "2014-01",
        }
    ]
    upsert_catalog(conn, entries)

    row = conn.execute(
        "SELECT name FROM indicators_catalog WHERE source = 'esios' AND indicator_id = 600"
    ).fetchone()
    assert row[0] == "Precio SPOT"
