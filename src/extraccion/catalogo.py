"""Carga del catálogo de métricas (`data/metricas_catalogo.json`), el
contrato del proyecto."""

from __future__ import annotations

import json
from pathlib import Path

CATALOGO_PATH = Path("data/metricas_catalogo.json")


def cargar_catalogo(path: Path = CATALOGO_PATH) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def indexar_catalogo(catalogo: list[dict]) -> dict[str, dict]:
    """`metrica_id` -> definición completa, para lookups O(1)."""
    return {m["metrica_id"]: m for m in catalogo}
