"""Descarga de PDFs de Enagás y extracción de su contenido en crudo.

La extracción es puramente mecánica: no interpreta cifras ni decide a
qué métrica corresponde cada número -- eso lo hace la capa LLM en
`src/extraccion/llm.py`. Este módulo solo convierte un PDF en algo que
se le pueda pasar a Claude, por página.

**Decisión tomada al probar contra un PDF real (Progreso jun-2026,
página 3 "Sectores de Mercado")**: el texto que extrae `pdfplumber` de
las tablas con estilo (fondo de color, columnas con cabecera rotada)
sale desordenado carácter a carácter -- inservible para un LLM. La
misma página renderizada como imagen se lee perfectamente. Por eso
`extract_pdf` genera también un PNG por página (`page.to_image()` de
pdfplumber, sin dependencias nuevas) para que la capa LLM use la API
multimodal de Claude en vez de solo texto. El texto y las tablas se
siguen extrayendo y guardando igual, como respaldo auditable barato en
`data/extracciones/`, pero no son lo que se manda al modelo.
"""

from __future__ import annotations

import base64
import hashlib
import io
import logging
import time
from pathlib import Path

import pdfplumber
import requests

logger = logging.getLogger(__name__)

DOWNLOAD_TIMEOUT_SECONDS = 60
DOWNLOAD_RETRIES = 3
RETRY_BACKOFF_SECONDS = 5


def download_pdf(url: str, dest: Path, retries: int = DOWNLOAD_RETRIES, force: bool = False) -> Path:
    """Descarga un PDF a `dest`, con reintentos y timeout.

    Idempotente: si `dest` ya existe y `force` es False, no vuelve a
    descargar. `--force` en `ingest_month.py` debe borrar el fichero
    (o pasar `force=True`) antes de llamar a esto, para poder recoger
    revisiones de Enagás sobre un PDF ya descargado.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not force:
        logger.info("PDF ya descargado, se reutiliza: %s", dest)
        return dest

    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, timeout=DOWNLOAD_TIMEOUT_SECONDS)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
            return dest
        except requests.RequestException as exc:
            last_exc = exc
            logger.warning(
                "Descarga fallida (intento %d/%d) de %s: %s", attempt, retries, url, exc
            )
            if attempt < retries:
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)
    raise RuntimeError(f"No se pudo descargar {url} tras {retries} intentos") from last_exc


def sha256_file(path: Path) -> str:
    """Hash del PDF descargado, para `data/manifiesto.json` (permite
    detectar si Enagás ha revisado en silencio un PDF ya procesado)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


IMAGE_RESOLUTION_DPI = 150


def extract_pdf(path: Path, resolution: int = IMAGE_RESOLUTION_DPI) -> list[dict]:
    """Extrae texto, tablas e imagen de cada página del PDF.

    Devuelve una lista (una entrada por página, 1-indexada) de:
        {
            "pagina": int,
            "texto": str,
            "tablas": list[list[list[str | None]]],
            "imagen_base64": str,  # PNG de la página, para la capa LLM
        }

    Sin ninguna interpretación de las cifras: es la entrada cruda que
    recibe la capa LLM (que usa `imagen_base64`; `texto`/`tablas`
    quedan como respaldo auditable en `data/extracciones/`).
    """
    pages = []
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            texto = page.extract_text() or ""
            tablas = page.extract_tables() or []
            buf = io.BytesIO()
            page.to_image(resolution=resolution).original.save(buf, format="PNG")
            imagen_base64 = base64.b64encode(buf.getvalue()).decode("ascii")
            pages.append(
                {
                    "pagina": i,
                    "texto": texto,
                    "tablas": tablas,
                    "imagen_base64": imagen_base64,
                }
            )
    return pages
