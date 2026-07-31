"""Cliente robusto para la API de ESIOS (Red Eléctrica de España).

https://api.esios.ree.es/ — requiere token personal en el header x-api-key.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import pandas as pd
import requests

from src.ingestion.base import OBSERVATION_COLUMNS, DataSource

logger = logging.getLogger(__name__)

BASE_URL = "https://api.esios.ree.es"
DEFAULT_TIMEOUT = 60
MAX_RETRIES = 5
BACKOFF_BASE_SECONDS = 2.0
MIN_REQUEST_INTERVAL_SECONDS = 1.0


class ESIOSAPIError(Exception):
    """Error irrecuperable al consultar la API de ESIOS."""


class ESIOSClient(DataSource):
    """Cliente HTTP para la API de ESIOS con reintentos y auto-throttling.

    Implementa la interfaz DataSource (método fetch()) además de
    get_indicator(), que expone la respuesta cruda de ESIOS con más
    detalle (datetime local, geo_name) para usos que no sean la
    ingesta genérica a la tabla observations.

    Uso:
        client = ESIOSClient()  # lee ESIOS_API_KEY de .env / entorno
        df = client.get_indicator(600, "2019-01-01T00:00", "2019-01-31T23:59")
        df = client.fetch(600, "2019-01-01T00:00", "2019-01-31T23:59")  # esquema estándar
    """

    name = "esios"

    def __init__(
        self,
        token: str | None = None,
        session: requests.Session | None = None,
        min_request_interval: float = MIN_REQUEST_INTERVAL_SECONDS,
    ) -> None:
        self.token = token or os.environ.get("ESIOS_API_KEY")
        if not self.token:
            raise ESIOSAPIError(
                "ESIOS_API_KEY no está definida. Cárgala con python-dotenv "
                "(load_dotenv()) antes de crear el cliente, o pásala explícitamente."
            )
        self.session = session or requests.Session()
        self.min_request_interval = min_request_interval
        self._last_request_ts: float = 0.0

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json; application/vnd.esios-api-v1+json",
            "Content-Type": "application/json",
            "x-api-key": self.token,
        }

    def get_indicator(
        self,
        indicator_id: int,
        start_date: str,
        end_date: str,
        time_trunc: str | None = "hour",
        geo_agg: str | None = None,
        geo_ids: list[int] | None = None,
    ) -> pd.DataFrame:
        """Descarga los valores de un indicador en un rango de fechas.

        Devuelve un DataFrame con columnas:
        indicator_id, datetime, datetime_utc, geo_id, geo_name, value
        (vacío, con esas columnas, si la API no devuelve valores).
        """
        params: dict[str, Any] = {
            "start_date": start_date,
            "end_date": end_date,
        }
        if time_trunc:
            params["time_trunc"] = time_trunc
        if geo_agg:
            params["geo_agg"] = geo_agg
        if geo_ids:
            params["geo_ids[]"] = geo_ids

        payload = self._get(f"/indicators/{indicator_id}", params)
        values = payload["indicator"]["values"]

        df = pd.DataFrame(
            values,
            columns=["datetime", "datetime_utc", "geo_id", "geo_name", "value"],
        )
        df.insert(0, "indicator_id", indicator_id)
        if not df.empty:
            # "datetime" viene en hora local (Europe/Madrid) con offset propio
            # por fila (+01:00 en invierno, +02:00 en verano). pandas 2.x no
            # deja vectorizar offsets mixtos en una sola columna sin forzar
            # utc=True (lo que perdería el offset local); se parsea fila a
            # fila para conservarlo tal cual.
            df["datetime"] = df["datetime"].apply(pd.Timestamp)
            df["datetime_utc"] = pd.to_datetime(df["datetime_utc"], utc=True)
        return df

    def fetch(
        self,
        indicator_id: int,
        start_date: str,
        end_date: str,
        time_trunc: str | None = "hour",
        geo_agg: str | None = None,
        geo_ids: list[int] | None = None,
        **kwargs,
    ) -> pd.DataFrame:
        """Implementación de DataSource.fetch(): esquema estándar para storage.

        Devuelve columnas: source, indicator_id, datetime_utc, geo_id, value.
        geo_id se normaliza a 0 cuando la API no da uno (evita NULLs en la
        clave primaria de la tabla observations).
        """
        raw = self.get_indicator(
            indicator_id, start_date, end_date, time_trunc, geo_agg, geo_ids
        )
        df = pd.DataFrame(columns=OBSERVATION_COLUMNS)
        if raw.empty:
            return df

        df["indicator_id"] = raw["indicator_id"]
        df["datetime_utc"] = raw["datetime_utc"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        df["geo_id"] = raw["geo_id"].fillna(0).astype(int)
        df["value"] = raw["value"]
        df["source"] = self.name
        return df[OBSERVATION_COLUMNS]

    def fetch_hourly_mean(
        self,
        indicator_id: int,
        start_date: str,
        end_date: str,
        geo_ids: list[int] | None = None,
        **kwargs,
    ) -> pd.DataFrame:
        """Como `fetch()`, pero para indicadores cuya resolución nativa es
        más fina que la hora (demanda/generación T.Real a 5 min; el precio
        spot -- indicador 600 -- pasó de nativo horario a nativo de 15 min
        en algún punto entre 2024-06 y 2025-01, el cambio real de mercado
        europeo a "15-minute market time units").

        ESIOS, al pedir `time_trunc=hour` para un indicador cuya
        resolución nativa es más fina, no promedia las muestras de esa
        hora: las SUMA. Verificado contra la API real en ambos casos:
        demanda (~21.500 MW de media -> guardado como ~250.000) y precio
        (~105 €/MWh de media en 15 min -> guardado como ~422 €/MWh, un
        salto de escala x4 justo desde que el precio pasó a granularidad
        de 15 min, que parecía -y se documentó como- un cambio estructural
        de mercado sin precedente cuando en realidad era este bug).

        No se fija un `time_trunc` concreto: se pide resolución NATIVA
        (lo que sea que ESIOS use para ese indicador en ese rango de
        fechas) y se promedia a hora en cliente, por geo_id. Esto es
        correcto tanto si la resolución nativa es de 5 min, 15 min, o ya
        horaria (promediar una única muestra por hora es un no-op).
        """
        raw = self.get_indicator(
            indicator_id, start_date, end_date, time_trunc=None, geo_ids=geo_ids
        )
        df = pd.DataFrame(columns=OBSERVATION_COLUMNS)
        if raw.empty:
            return df

        raw = raw.copy()
        raw["geo_id"] = raw["geo_id"].fillna(0).astype(int)
        raw["hora_utc"] = raw["datetime_utc"].dt.floor("h")
        hourly = raw.groupby(["hora_utc", "geo_id"], as_index=False)["value"].mean()

        df["datetime_utc"] = hourly["hora_utc"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        df["geo_id"] = hourly["geo_id"]
        df["value"] = hourly["value"]
        df["indicator_id"] = indicator_id
        df["source"] = self.name
        return df[OBSERVATION_COLUMNS]

    def search_indicators(self, text: str) -> pd.DataFrame:
        """Busca indicadores por texto libre. Útil para descubrir ids."""
        payload = self._get("/indicators", {"text": text})
        return pd.DataFrame(payload["indicators"])

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        url = f"{BASE_URL}{path}"
        last_error: Exception | None = None

        for attempt in range(1, MAX_RETRIES + 1):
            self._throttle()
            start_ts = time.monotonic()
            try:
                response = self.session.get(
                    url, headers=self._headers, params=params, timeout=DEFAULT_TIMEOUT
                )
            except requests.RequestException as exc:
                last_error = exc
                logger.warning(
                    "Fallo de red en intento %d/%d para %s: %s",
                    attempt,
                    MAX_RETRIES,
                    path,
                    exc,
                )
                self._sleep_backoff(attempt)
                continue

            elapsed = time.monotonic() - start_ts
            logger.info(
                "GET %s params=%s -> %d (%.2fs, intento %d/%d)",
                path,
                params,
                response.status_code,
                elapsed,
                attempt,
                MAX_RETRIES,
            )

            if response.status_code == 429:
                retry_after = float(
                    response.headers.get("Retry-After", BACKOFF_BASE_SECONDS * attempt)
                )
                logger.warning("Rate limit (429) en %s, esperando %.1fs", path, retry_after)
                time.sleep(retry_after)
                continue

            if response.status_code >= 500:
                last_error = ESIOSAPIError(f"HTTP {response.status_code} en {path}")
                self._sleep_backoff(attempt)
                continue

            if response.status_code == 401:
                raise ESIOSAPIError("HTTP 401 Unauthorized: el token de ESIOS no es válido.")

            if response.status_code >= 400:
                raise ESIOSAPIError(
                    f"HTTP {response.status_code} en {path}: {response.text[:500]}"
                )

            try:
                return response.json()
            except ValueError as exc:
                raise ESIOSAPIError(f"Respuesta no-JSON de {path}: {exc}") from exc

        raise ESIOSAPIError(
            f"Agotados los {MAX_RETRIES} intentos para {path} (params={params})"
        ) from last_error

    def _throttle(self) -> None:
        """Espera lo necesario para no pedir más rápido de min_request_interval."""
        elapsed = time.monotonic() - self._last_request_ts
        wait = self.min_request_interval - elapsed
        if wait > 0:
            time.sleep(wait)
        self._last_request_ts = time.monotonic()

    @staticmethod
    def _sleep_backoff(attempt: int) -> None:
        time.sleep(BACKOFF_BASE_SECONDS * attempt)
