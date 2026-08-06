"""Interfaz común para las fuentes de datos del observatorio.

El proyecto tiene dos fuentes, ambas publicaciones PDF mensuales de
Enagás (no hay API): el Boletín Estadístico del Gas y el Progreso
mensual de la demanda. Cada una sabe construir sus URLs candidatas
para un periodo y localizar cuál existe de verdad; la descarga y la
extracción de texto/tablas son mecánicas y están compartidas en
`src/extraccion/pdf.py`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class DataSource(ABC):
    """Contrato que debe cumplir cualquier fuente de datos del pipeline.

    `name` identifica la fuente en la columna `fuente_doc` del CSV
    canónico (`data/gas.csv`) y en `data/manifiesto.json` (p.ej.
    "boletin", "progreso").
    """

    name: str

    @abstractmethod
    def candidate_urls(self, year: int, month: int) -> list[str]:
        """URLs candidatas para el PDF de un periodo, en orden de
        probabilidad. Separado de `find_url` para poder testear la
        construcción de URLs sin hacer peticiones HTTP.
        """
        raise NotImplementedError

    @abstractmethod
    def find_url(self, year: int, month: int) -> str | None:
        """Prueba las URLs candidatas con HEAD y devuelve la primera
        que responde 200, o None si Enagás todavía no ha publicado el
        PDF de ese periodo (no es un error: simplemente aún no toca).
        """
        raise NotImplementedError
