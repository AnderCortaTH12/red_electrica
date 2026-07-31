"""Tests de la logica de ingesta incremental/backfill. El cliente ESIOS
se mockea (sin peticiones reales); se prueba contra una bbdd sqlite
temporal real para verificar la interaccion con MAX(datetime_utc) y la
tabla ingestion_log.
"""

from unittest.mock import MagicMock

import pandas as pd
import pytest

from src.ingestion.esios_client import ESIOSAPIError
from src.ingestion.pipeline import backfill_indicator, update_indicator_incremental
from src.storage.db import get_connection, init_db, insert_observations


@pytest.fixture
def conn(tmp_path):
    connection = get_connection(str(tmp_path / "test.db"))
    init_db(connection)
    yield connection
    connection.close()


def make_entry(indicator_id=600, cobertura_desde="2024-01"):
    return {
        "id": indicator_id,
        "source": "esios",
        "name": "Precio mercado SPOT Diario",
        "cobertura_desde": cobertura_desde,
    }


def make_obs_df(n, source="esios", indicator_id=600, start="2024-06-01T00:00:00Z"):
    idx = pd.date_range(start, periods=n, freq="h", tz="UTC")
    return pd.DataFrame(
        {
            "source": [source] * n,
            "indicator_id": [indicator_id] * n,
            "datetime_utc": [t.strftime("%Y-%m-%dT%H:%M:%SZ") for t in idx],
            "geo_id": [3] * n,
            "value": [50.0 + i for i in range(n)],
        }
    )


def make_fake_client(fetch_return=None, fetch_side_effect=None):
    client = MagicMock()
    if fetch_side_effect is not None:
        client.fetch.side_effect = fetch_side_effect
    else:
        client.fetch.return_value = fetch_return if fetch_return is not None else make_obs_df(5)
    return client


def test_update_incremental_with_no_prior_data_falls_back_to_backfill(conn):
    client = make_fake_client(fetch_return=make_obs_df(3))
    entry = make_entry()

    result = update_indicator_incremental(client, conn, entry)

    assert result["modo"] == "backfill"
    assert client.fetch.called


def test_update_incremental_uses_last_known_datetime(conn):
    insert_observations(conn, make_obs_df(1, start="2026-07-01T00:00:00Z"))
    client = make_fake_client(fetch_return=make_obs_df(2, start="2026-07-01T00:00:00Z"))
    entry = make_entry()

    result = update_indicator_incremental(client, conn, entry, overlap_hours=2)

    assert result["modo"] == "incremental"
    call_args = client.fetch.call_args
    assert call_args[0][0] == 600  # indicator_id
    # el start pedido debe ser ANTERIOR al ultimo dato conocido (overlap)
    start_param = call_args[0][1]
    assert start_param < "2026-07-01T00:00"


def test_update_incremental_stale_data_falls_back_to_backfill(conn):
    insert_observations(conn, make_obs_df(1, start="2020-01-01T00:00:00Z"))
    client = make_fake_client(fetch_return=make_obs_df(1))
    entry = make_entry()

    result = update_indicator_incremental(client, conn, entry, stale_days=30)

    assert result["modo"] == "backfill"


def test_update_incremental_records_new_rows(conn):
    insert_observations(conn, make_obs_df(1, start="2026-07-29T00:00:00Z"))
    client = make_fake_client(fetch_return=make_obs_df(3, start="2026-07-29T00:00:00Z"))
    entry = make_entry()

    result = update_indicator_incremental(client, conn, entry)

    assert result["nuevas_filas"] == 2  # 1 ya existia, 2 son nuevas
    assert result["fallidas"] == 0


def test_update_incremental_handles_api_error_gracefully(conn):
    insert_observations(conn, make_obs_df(1, start="2026-07-29T00:00:00Z"))
    client = make_fake_client(fetch_side_effect=ESIOSAPIError("boom"))
    entry = make_entry()

    result = update_indicator_incremental(client, conn, entry)

    assert result["fallidas"] == 1
    assert result["nuevas_filas"] == 0


def test_backfill_indicator_skips_done_periods(conn):
    entry = make_entry(cobertura_desde="2026-06")
    client = make_fake_client(fetch_return=make_obs_df(1))

    first = backfill_indicator(client, conn, entry)
    calls_after_first = client.fetch.call_count

    second = backfill_indicator(client, conn, entry)

    assert second["skip"] == first["ventanas"]
    assert client.fetch.call_count == calls_after_first  # no se repiten peticiones


def test_update_incremental_with_end_offset_requests_future_end(conn):
    """Los indicadores de prevision (demanda_prevista, prevision_eolica,
    prevision_fv) se piden hasta ahora + end_offset_hours, no solo hasta
    ahora -- si no, nunca tendriamos en la bbdd el dato de manana que
    ESIOS publica con antelacion."""
    insert_observations(conn, make_obs_df(1, start="2026-07-29T00:00:00Z"))
    client = make_fake_client(fetch_return=make_obs_df(1))
    entry = make_entry()

    update_indicator_incremental(client, conn, entry, end_offset_hours=48)

    end_param = client.fetch.call_args[0][2]
    # "ahora" en el test es la fecha real de ejecucion, muy posterior a
    # 2026-07-29 (el ultimo dato conocido); basta con comprobar que el
    # end pedido es mayor que "ahora" sin offset para confirmar que se
    # aplico el desplazamiento hacia el futuro.
    now_no_offset = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M")
    assert end_param > now_no_offset


def test_backfill_uses_fetch_hourly_mean_when_marked_in_catalog(conn):
    entry = make_entry(cobertura_desde="2026-06")
    entry["promediar_desde_nativo"] = True
    client = make_fake_client()
    client.fetch_hourly_mean.return_value = make_obs_df(1)

    backfill_indicator(client, conn, entry)

    assert client.fetch_hourly_mean.called
    assert not client.fetch.called


def test_backfill_uses_plain_fetch_when_not_marked(conn):
    entry = make_entry(cobertura_desde="2026-06")
    client = make_fake_client(fetch_return=make_obs_df(1))

    backfill_indicator(client, conn, entry)

    assert client.fetch.called
    assert not client.fetch_hourly_mean.called


def test_update_incremental_uses_fetch_hourly_mean_when_marked_in_catalog(conn):
    insert_observations(conn, make_obs_df(1, start="2026-07-29T00:00:00Z"))
    entry = make_entry()
    entry["promediar_desde_nativo"] = True
    client = make_fake_client()
    client.fetch_hourly_mean.return_value = make_obs_df(1, start="2026-07-29T00:00:00Z")

    result = update_indicator_incremental(client, conn, entry)

    assert result["modo"] == "incremental"
    assert client.fetch_hourly_mean.called
    assert not client.fetch.called


def test_update_incremental_without_end_offset_does_not_request_future(conn):
    insert_observations(conn, make_obs_df(1, start="2026-07-29T00:00:00Z"))
    client = make_fake_client(fetch_return=make_obs_df(1))
    entry = make_entry()

    update_indicator_incremental(client, conn, entry, end_offset_hours=0)

    end_param = client.fetch.call_args[0][2]
    now_str = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M")
    assert end_param <= now_str
