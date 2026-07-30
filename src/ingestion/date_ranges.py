"""Utilidades para trocear un rango de fechas largo en ventanas pequeñas,
para no pedir años de histórico de golpe a una API.
"""

from __future__ import annotations

from datetime import datetime

from dateutil.relativedelta import relativedelta


def chunk_range(
    start_ym: str, end_date: datetime, months_per_chunk: int = 3
) -> list[tuple[datetime, datetime]]:
    """Trocea [start_ym, end_date] en ventanas de `months_per_chunk` meses.

    start_ym: "YYYY-MM" (p.ej. cobertura_desde del catálogo)
    end_date: datetime hasta el que trocear (normalmente "hoy")

    Devuelve lista de (chunk_start, chunk_end), ambos datetime, sin
    solaparse y cubriendo todo el rango.
    """
    year, month = (int(x) for x in start_ym.split("-"))
    cursor = datetime(year, month, 1)

    chunks: list[tuple[datetime, datetime]] = []
    while cursor <= end_date:
        chunk_end = cursor + relativedelta(months=months_per_chunk) - relativedelta(days=1)
        chunks.append((cursor, min(chunk_end, end_date)))
        cursor = cursor + relativedelta(months=months_per_chunk)
    return chunks
