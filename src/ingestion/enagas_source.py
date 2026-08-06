"""Las dos fuentes de datos de Enagás: publicaciones PDF mensuales.

No se scrapea la página de listado de publicaciones de Enagás: se
renderiza con JavaScript y el HTML estático no contiene los enlaces a
los PDF. En vez de eso, cada fuente construye el patrón de URL
directamente a partir del periodo (año, mes) y prueba las variantes
plausibles con HEAD hasta encontrar la que existe de verdad.
"""

from __future__ import annotations

import logging
from urllib.parse import quote

import requests

from src.ingestion.base import DataSource

logger = logging.getLogger(__name__)

MESES_ABREV = [
    "ene", "feb", "mar", "abr", "may", "jun",
    "jul", "ago", "sep", "oct", "nov", "dic",
]
MESES_COMPLETOS = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]

HEAD_TIMEOUT_SECONDS = 15


def _first_existing_url(urls: list[str]) -> str | None:
    """Prueba las URLs candidatas en orden y devuelve la primera que
    responde 200. Registra en el log cuál acertó, tal como pide el
    diseño (para poder auditar por qué variante de nombrado se coló
    un mes concreto)."""
    for url in urls:
        try:
            resp = requests.head(url, timeout=HEAD_TIMEOUT_SECONDS, allow_redirects=True)
        except requests.RequestException as exc:
            logger.warning("HEAD falló para %s: %s", url, exc)
            continue
        if resp.status_code == 200:
            logger.info("URL encontrada: %s", url)
            return url
    return None


class BoletinSource(DataSource):
    """Boletín Estadístico del Gas: totales de demanda, demanda por
    CCAA, orígenes de suministro por país, conexiones internacionales,
    biometano, TVB, plantas de regasificación, almacenamientos
    subterráneos, mix de generación eléctrica.

    Patrón de nombrado verificado estable (jun26, may26, abr26): un
    único nombre de fichero por periodo, sin variantes históricas
    conocidas (a diferencia del Progreso).
    """

    name = "boletin"
    BASE_URL = (
        "https://www.enagas.es/content/dam/enagas/es/ficheros/"
        "gestion-tecnica-sistema/energy-data/publicaciones/"
        "boletin-estadistico-del-gas/"
    )

    def candidate_urls(self, year: int, month: int) -> list[str]:
        mmm = MESES_ABREV[month - 1]
        yy = f"{year % 100:02d}"
        # Verificado sobre datos reales (2026-01/02/03): cuando Enagás
        # revisa un Boletín ya publicado, el fichero se renombra con un
        # sufijo "rev" -- e inconsistente en el propio formato del
        # sufijo (visto "ene26rev.pdf" sin guion bajo, "feb26_rev.pdf"
        # y "mar26_rev.pdf" con guion bajo). Se prueban las tres formas;
        # el nombre sin "rev" va primero por ser el caso normal.
        nombres = [
            f"Boletín Estadístico_{mmm}{yy}.pdf",
            f"Boletín Estadístico_{mmm}{yy}_rev.pdf",
            f"Boletín Estadístico_{mmm}{yy}rev.pdf",
        ]
        # quote() codifica el espacio como %20 y la í como %C3%AD,
        # igual que la URL real publicada por Enagás.
        return [self.BASE_URL + quote(nombre) for nombre in nombres]

    def find_url(self, year: int, month: int) -> str | None:
        return _first_existing_url(self.candidate_urls(year, month))


class ProgresoSource(DataSource):
    """Progreso mensual de la demanda: desglose de la demanda
    convencional en D/C+PyMES, Industrial y Cisternas (que el Boletín
    no trae), y comparativa europea. Cifras en TWh en el PDF.

    El nombrado histórico es inconsistente (se han visto
    `Progreso_Ene22.pdf`, `Progreso_Septiembre22.pdf`,
    `Progreso_febrero25.pdf`), así que se prueban varias variantes de
    capitalización y longitud del nombre del mes.
    """

    name = "progreso"
    BASE_URL = (
        "https://www.enagas.es/content/dam/enagas/es/ficheros/"
        "gestion-tecnica-sistema/energy-data/publicaciones/"
        "demanda-de-gas/demanda-mensual/"
    )

    def candidate_urls(self, year: int, month: int) -> list[str]:
        mes_completo = MESES_COMPLETOS[month - 1]
        mes_abrev = MESES_ABREV[month - 1]
        yy = f"{year % 100:02d}"

        nombres = [
            f"Progreso_{mes_completo}{yy}.pdf",
            f"Progreso_{mes_completo.capitalize()}{yy}.pdf",
            f"Progreso_{mes_abrev.capitalize()}{yy}.pdf",
            f"Progreso_{mes_abrev}{yy}.pdf",
        ]
        # dedupe conservando el orden (algunos meses no distinguen
        # mayúscula/minúscula tras capitalize())
        vistos: list[str] = []
        for nombre in nombres:
            if nombre not in vistos:
                vistos.append(nombre)
        return [self.BASE_URL + quote(nombre) for nombre in vistos]

    def find_url(self, year: int, month: int) -> str | None:
        return _first_existing_url(self.candidate_urls(year, month))
