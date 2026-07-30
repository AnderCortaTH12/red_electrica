"""Tests del ESIOSClient, todos con la respuesta HTTP mockeada.
No gastan peticiones reales contra la API.
"""

from unittest.mock import MagicMock

import pytest

from src.ingestion.esios_client import ESIOSAPIError, ESIOSClient

SAMPLE_INDICATOR_PAYLOAD = {
    "indicator": {
        "id": 600,
        "name": "Precio mercado SPOT Diario",
        "values": [
            {
                "value": 45.32,
                "datetime": "2019-01-01T00:00:00.000+01:00",
                "datetime_utc": "2018-12-31T23:00:00Z",
                "geo_id": 3,
                "geo_name": "España",
            },
            {
                "value": 46.10,
                "datetime": "2019-01-01T01:00:00.000+01:00",
                "datetime_utc": "2019-01-01T00:00:00Z",
                "geo_id": 3,
                "geo_name": "España",
            },
        ],
    }
}


def make_client() -> ESIOSClient:
    return ESIOSClient(token="fake-token", min_request_interval=0)


def make_response(status_code: int, json_body: dict | None = None, headers: dict | None = None):
    response = MagicMock()
    response.status_code = status_code
    response.headers = headers or {}
    if json_body is not None:
        response.json.return_value = json_body
    response.text = "error body"
    return response


def test_get_indicator_happy_path():
    client = make_client()
    client.session.get = MagicMock(return_value=make_response(200, SAMPLE_INDICATOR_PAYLOAD))

    df = client.get_indicator(600, "2019-01-01T00:00", "2019-01-01T23:59")

    assert len(df) == 2
    assert list(df["value"]) == [45.32, 46.10]
    assert (df["indicator_id"] == 600).all()
    client.session.get.assert_called_once()


def test_get_indicator_empty_values_returns_empty_dataframe():
    client = make_client()
    empty_payload = {"indicator": {"id": 600, "name": "x", "values": []}}
    client.session.get = MagicMock(return_value=make_response(200, empty_payload))

    df = client.get_indicator(600, "2019-01-01T00:00", "2019-01-01T23:59")

    assert df.empty
    assert list(df.columns) == [
        "indicator_id",
        "datetime",
        "datetime_utc",
        "geo_id",
        "geo_name",
        "value",
    ]


def test_retries_on_429_then_succeeds():
    client = make_client()
    responses = [
        make_response(429, headers={"Retry-After": "0"}),
        make_response(200, SAMPLE_INDICATOR_PAYLOAD),
    ]
    client.session.get = MagicMock(side_effect=responses)

    df = client.get_indicator(600, "2019-01-01T00:00", "2019-01-01T23:59")

    assert len(df) == 2
    assert client.session.get.call_count == 2


def test_retries_on_500_then_succeeds():
    client = make_client()
    responses = [
        make_response(500),
        make_response(200, SAMPLE_INDICATOR_PAYLOAD),
    ]
    client.session.get = MagicMock(side_effect=responses)

    df = client.get_indicator(600, "2019-01-01T00:00", "2019-01-01T23:59")

    assert len(df) == 2
    assert client.session.get.call_count == 2


def test_401_raises_immediately_without_retry():
    client = make_client()
    client.session.get = MagicMock(return_value=make_response(401))

    with pytest.raises(ESIOSAPIError, match="401"):
        client.get_indicator(600, "2019-01-01T00:00", "2019-01-01T23:59")

    client.session.get.assert_called_once()


def test_exhausts_retries_and_raises():
    client = make_client()
    client.session.get = MagicMock(return_value=make_response(500))

    with pytest.raises(ESIOSAPIError, match="Agotados"):
        client.get_indicator(600, "2019-01-01T00:00", "2019-01-01T23:59")

    assert client.session.get.call_count == 5  # MAX_RETRIES


def test_missing_token_raises():
    import os

    old = os.environ.pop("ESIOS_API_KEY", None)
    try:
        with pytest.raises(ESIOSAPIError, match="ESIOS_API_KEY"):
            ESIOSClient()
    finally:
        if old is not None:
            os.environ["ESIOS_API_KEY"] = old


def test_get_indicator_handles_dst_offset_change():
    """Regresión: un rango que cruza el cambio de hora tiene filas con
    offset +01:00 (invierno) y +02:00 (verano) en 'datetime'. pandas 2.x
    no vectoriza offsets mixtos sin utc=True; get_indicator no debe romper."""
    client = make_client()
    payload = {
        "indicator": {
            "id": 600,
            "name": "Precio mercado SPOT Diario",
            "values": [
                {
                    "value": 45.0,
                    "datetime": "2019-03-31T01:00:00.000+01:00",
                    "datetime_utc": "2019-03-31T00:00:00Z",
                    "geo_id": 3,
                    "geo_name": "España",
                },
                {
                    "value": 46.0,
                    "datetime": "2019-03-31T03:00:00.000+02:00",
                    "datetime_utc": "2019-03-31T01:00:00Z",
                    "geo_id": 3,
                    "geo_name": "España",
                },
            ],
        }
    }
    client.session.get = MagicMock(return_value=make_response(200, payload))

    df = client.get_indicator(600, "2019-03-31T00:00", "2019-03-31T23:59")

    assert len(df) == 2
    assert str(df["datetime"].iloc[0].tzinfo) == "UTC+01:00"
    assert str(df["datetime"].iloc[1].tzinfo) == "UTC+02:00"


def test_search_indicators():
    client = make_client()
    payload = {"indicators": [{"id": 600, "name": "Precio mercado SPOT Diario"}]}
    client.session.get = MagicMock(return_value=make_response(200, payload))

    df = client.search_indicators("Precio")

    assert len(df) == 1
    assert df.iloc[0]["id"] == 600
