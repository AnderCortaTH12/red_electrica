"""Cliente para la REData API de Red Eléctrica de España (apidatos.ree.es).

API pública, sin autenticación. Documentación de referencia:
https://www.ree.es/es/apidatos
"""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://apidatos.ree.es"
DEFAULT_TIMEOUT = 30
MAX_RETRIES = 4
BACKOFF_SECONDS = 2.0


class REDataAPIError(Exception):
    """Error irrecuperable al consultar la REData API."""


def get_widget_data(
    category: str,
    widget: str,
    start_date: str,
    end_date: str,
    time_trunc: str = "day",
    lang: str = "es",
    geo_trunc: str | None = None,
    geo_limit: str | None = None,
    geo_ids: list[int] | None = None,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    """Llama a un endpoint de la REData API y devuelve el JSON:API crudo.

    Parameters
    ----------
    category: p.ej. "balance", "demanda", "generacion"
    widget: p.ej. "balance-electrico", "ire-general", "estructura-generacion"
    start_date / end_date: ISO 8601, "YYYY-MM-DDTHH:MM"
    time_trunc: "hour" | "day" | "month" | "year"
    geo_trunc: p.ej. "electric_system" (opcional)
    geo_limit: p.ej. "peninsular" | "canarias" | "baleares" | "ceuta" | "melilla" | "ccaa" (opcional)
    geo_ids: lista de ids geográficos, depende de geo_limit (opcional)
    """
    url = f"{BASE_URL}/{lang}/datos/{category}/{widget}"
    params: dict[str, Any] = {
        "start_date": start_date,
        "end_date": end_date,
        "time_trunc": time_trunc,
    }
    if geo_trunc:
        params["geo_trunc"] = geo_trunc
    if geo_limit:
        params["geo_limit"] = geo_limit
    if geo_ids:
        params["geo_ids"] = ",".join(str(g) for g in geo_ids)

    http = session or requests

    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = http.get(url, params=params, timeout=DEFAULT_TIMEOUT)
        except requests.RequestException as exc:
            last_error = exc
            logger.warning(
                "Fallo de red en intento %d/%d para %s: %s",
                attempt,
                MAX_RETRIES,
                widget,
                exc,
            )
            _sleep_backoff(attempt)
            continue

        if response.status_code == 429:
            retry_after = float(response.headers.get("Retry-After", BACKOFF_SECONDS * attempt))
            logger.warning(
                "Rate limit (429) en %s, esperando %.1fs (intento %d/%d)",
                widget,
                retry_after,
                attempt,
                MAX_RETRIES,
            )
            time.sleep(retry_after)
            continue

        if response.status_code >= 500:
            last_error = REDataAPIError(f"HTTP {response.status_code} en {widget}")
            logger.warning(
                "Error de servidor %d en %s (intento %d/%d)",
                response.status_code,
                widget,
                attempt,
                MAX_RETRIES,
            )
            _sleep_backoff(attempt)
            continue

        if response.status_code >= 400:
            raise REDataAPIError(
                f"HTTP {response.status_code} en {widget}: {response.text[:500]}"
            )

        try:
            return response.json()
        except ValueError as exc:
            raise REDataAPIError(f"Respuesta no-JSON de {widget}: {exc}") from exc

    raise REDataAPIError(
        f"Agotados los {MAX_RETRIES} intentos para {widget} ({start_date} - {end_date})"
    ) from last_error


def _sleep_backoff(attempt: int) -> None:
    time.sleep(BACKOFF_SECONDS * attempt)
