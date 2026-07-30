"""Interfaz común para fuentes de datos del pipeline.

Hoy solo hay una fuente (ESIOS), pero el proyecto va a incorporar más
(MIBGAS para precio del gas, Open-Meteo para meteorología, reserva
hidráulica...). Definir el contrato ahora evita migrar el esquema de
almacenamiento cuando llegue la segunda fuente.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

# Columnas que TODA fuente debe devolver en fetch(), en este orden.
OBSERVATION_COLUMNS = ["source", "indicator_id", "datetime_utc", "geo_id", "value"]


class DataSource(ABC):
    """Contrato que debe cumplir cualquier fuente de datos del pipeline.

    `name` identifica la fuente en la columna `source` de la tabla
    `observations` (p.ej. "esios", "mibgas", "open-meteo").
    """

    name: str

    @abstractmethod
    def fetch(
        self,
        indicator_id: int | str,
        start_date: str,
        end_date: str,
        **kwargs,
    ) -> pd.DataFrame:
        """Descarga un indicador en un rango de fechas.

        Debe devolver un DataFrame con exactamente las columnas de
        OBSERVATION_COLUMNS (aunque esté vacío), listo para insertar
        en la tabla `observations` sin transformación adicional.
        """
        raise NotImplementedError
