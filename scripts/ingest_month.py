"""Ingesta de un periodo (o de todos los pendientes): descarga los dos
PDF de Enagás, los manda a Claude para mapear sus cifras al catálogo,
normaliza, valida y escribe en `data/gas.csv`.

Uso:
    python -m scripts.ingest_month                    # todos los periodos pendientes
    python -m scripts.ingest_month --periodo 2026-06   # solo ese mes
    python -m scripts.ingest_month --periodo 2026-06 --force     # reprocesa aunque ya exista (revisión de Enagás)
    python -m scripts.ingest_month --periodo 2026-06 --sin-llm   # reusa data/extracciones/*.json, no llama a la API
    python -m scripts.ingest_month --dry-run           # no escribe nada, solo informa

Cada periodo se procesa de forma atómica: si falla la validación de un
mes, ese mes no se escribe en el CSV (o todo o nada), pero el resto de
periodos pendientes en la misma ejecución sí se procesan -- un mes malo
no debe bloquear los demás. El exit code es 1 si algún periodo falló.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from calendar import monthrange
from datetime import date
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from src.extraccion.catalogo import cargar_catalogo, indexar_catalogo
from src.extraccion.llm import extraer_documento
from src.extraccion.normalizar import convertir_unidad, normalizar_dimension, parse_numero_es
from src.extraccion.pdf import download_pdf, extract_pdf, sha256_file
from src.extraccion.validar import validar_periodo
from src.ingestion.enagas_source import BoletinSource, ProgresoSource

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("ingest_month")

CSV_PATH = Path("data/gas.csv")
RAW_DIR = Path("data/raw")
EXTRACCIONES_DIR = Path("data/extracciones")
MANIFIESTO_PATH = Path("data/manifiesto.json")
DESCONOCIDAS_PATH = Path("data/metricas_desconocidas.json")

CSV_COLUMNS = [
    "periodo",
    "metrica_id",
    "dimension",
    "agregacion",
    "valor",
    "unidad",
    "var_pct_interanual",
    "fuente_doc",
    "pagina",
    "extraido_el",
]

FUENTES = [BoletinSource(), ProgresoSource()]
PRIMER_PERIODO = (2026, 1)


def mes_anterior(hoy: date) -> tuple[int, int]:
    primero_del_mes = hoy.replace(day=1)
    ultimo_dia_mes_anterior = primero_del_mes.fromordinal(primero_del_mes.toordinal() - 1)
    return ultimo_dia_mes_anterior.year, ultimo_dia_mes_anterior.month


def periodos_en_rango(inicio: tuple[int, int], fin: tuple[int, int]) -> list[str]:
    y, m = inicio
    periodos = []
    while (y, m) <= fin:
        periodos.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return periodos


def periodos_pendientes(csv_path: Path = CSV_PATH, hoy: date | None = None) -> list[str]:
    hoy = hoy or date.today()
    fin = mes_anterior(hoy)
    todos = periodos_en_rango(PRIMER_PERIODO, fin)

    existentes: set[str] = set()
    if csv_path.exists():
        df = pd.read_csv(csv_path)
        if not df.empty:
            existentes = set(df["periodo"].astype(str).unique())
    return [p for p in todos if p not in existentes]


def _cargar_json(path: Path, default):
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _guardar_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def normalizar_extraccion(
    extraccion: dict,
    fuente: str,
    periodo: str,
    catalogo_idx: dict[str, dict],
    hoy: date,
    desconocidas: list[dict],
) -> list[dict]:
    """Convierte la respuesta cruda del LLM en filas listas para
    `data/gas.csv`. Nunca calcula ni infiere: solo parsea el número
    literal (parse_numero_es), convierte de unidad (convertir_unidad)
    y normaliza el nombre de la dimensión (normalizar_dimension)."""
    filas = []
    for entrada in extraccion.get("extracciones", []):
        metrica_id = entrada.get("metrica_id")
        metrica = catalogo_idx.get(metrica_id)
        if metrica is None:
            logger.warning("::warning::El modelo devolvió un metrica_id fuera del catálogo: %s", metrica_id)
            desconocidas.append(
                {
                    "periodo": periodo,
                    "fuente": fuente,
                    "descripcion": f"metrica_id inventado por el modelo: {metrica_id}",
                    "valor_aprox": entrada.get("valores"),
                    "pagina": entrada.get("pagina"),
                }
            )
            continue

        dimension_valor = None
        if metrica["dimension"]:
            dimension_valor = normalizar_dimension(entrada.get("dimension_valor"), metrica["dimension"])

        valores = entrada.get("valores") or {}
        variaciones = entrada.get("var_pct_interanual") or {}
        for agregacion, valor_crudo in valores.items():
            valor = parse_numero_es(valor_crudo)
            valor = convertir_unidad(valor, metrica["unidad_pdf"], metrica["unidad_canonica"])
            filas.append(
                {
                    "periodo": periodo,
                    "metrica_id": metrica_id,
                    "dimension": dimension_valor or "",
                    "agregacion": agregacion,
                    "valor": valor,
                    "unidad": metrica["unidad_canonica"],
                    "var_pct_interanual": parse_numero_es(variaciones.get(agregacion)),
                    "fuente_doc": fuente,
                    "pagina": entrada.get("pagina"),
                    "extraido_el": hoy.isoformat(),
                }
            )

    for no_reconocida in extraccion.get("metricas_no_reconocidas", []):
        logger.warning("::warning::Cifra no reconocida en %s %s: %s", periodo, fuente, no_reconocida)
        desconocidas.append({"periodo": periodo, "fuente": fuente, **no_reconocida})

    return filas


def procesar_periodo(
    periodo: str,
    catalogo: list[dict],
    catalogo_idx: dict[str, dict],
    manifiesto: dict,
    desconocidas: list[dict],
    force: bool,
    sin_llm: bool,
    dry_run: bool,
    hoy: date,
) -> tuple[list[dict], bool]:
    """Devuelve (filas_del_periodo, hubo_algun_pdf_publicado). Si
    hubo_algun_pdf_publicado es False, el periodo simplemente no está
    publicado todavía -- no es un error."""
    year, month = (int(x) for x in periodo.split("-"))
    todas_las_filas: list[dict] = []
    algun_pdf = False

    for source in FUENTES:
        pdf_path = RAW_DIR / f"{periodo}_{source.name}.pdf"
        extraccion_path = EXTRACCIONES_DIR / f"{periodo}_{source.name}.json"

        if sin_llm:
            extraccion = _cargar_json(extraccion_path, None)
            if extraccion is None:
                logger.info("--sin-llm: no hay extracción guardada para %s (%s), se omite", periodo, source.name)
                continue
            algun_pdf = True
        else:
            url = source.find_url(year, month)
            if url is None:
                logger.info("PDF de %s todavía no publicado para %s", source.name, periodo)
                continue
            algun_pdf = True
            download_pdf(url, pdf_path, force=force)
            sha256 = sha256_file(pdf_path)
            pages = extract_pdf(pdf_path)
            extraccion = extraer_documento(pages, source.name, catalogo)

            if not dry_run:
                _guardar_json(extraccion_path, extraccion)
                manifiesto.setdefault(periodo, {})[source.name] = {
                    "url": url,
                    "sha256": sha256,
                    "descargado_el": hoy.isoformat(),
                    "extraido_el": hoy.isoformat(),
                }

        filas = normalizar_extraccion(extraccion, source.name, periodo, catalogo_idx, hoy, desconocidas)
        todas_las_filas.extend(filas)

    return todas_las_filas, algun_pdf


def escribir_csv(filas_nuevas: list[dict], csv_path: Path = CSV_PATH) -> None:
    """Upsert por periodo: sustituye las filas de los periodos tocados
    y conserva el resto tal cual, ordenado como pide el diseño
    (periodo, metrica_id, dimension, agregacion)."""
    periodos_tocados = {f["periodo"] for f in filas_nuevas}

    if csv_path.exists():
        existente = pd.read_csv(csv_path, dtype={"periodo": str})
        existente = existente[~existente["periodo"].isin(periodos_tocados)]
    else:
        existente = pd.DataFrame(columns=CSV_COLUMNS)

    nuevas_df = pd.DataFrame(filas_nuevas, columns=CSV_COLUMNS)
    combinado = pd.concat([existente, nuevas_df], ignore_index=True)
    combinado = combinado.sort_values(["periodo", "metrica_id", "dimension", "agregacion"], na_position="first")
    combinado.to_csv(csv_path, index=False)


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--periodo", help="YYYY-MM; si se omite, procesa todos los pendientes")
    parser.add_argument("--force", action="store_true", help="reprocesa aunque ya exista en el CSV")
    parser.add_argument("--sin-llm", action="store_true", help="reusa data/extracciones/*.json, no llama a la API")
    parser.add_argument("--dry-run", action="store_true", help="no escribe nada, solo informa")
    args = parser.parse_args(argv)

    hoy = date.today()
    catalogo = cargar_catalogo()
    catalogo_idx = indexar_catalogo(catalogo)
    manifiesto = _cargar_json(MANIFIESTO_PATH, {})
    desconocidas = _cargar_json(DESCONOCIDAS_PATH, [])

    if args.periodo:
        periodos = [args.periodo]
        if not args.force and CSV_PATH.exists():
            existentes = set(pd.read_csv(CSV_PATH)["periodo"].astype(str).unique())
            if args.periodo in existentes:
                logger.info("%s ya está en el CSV; usa --force para reprocesarlo", args.periodo)
                periodos = []
    else:
        periodos = periodos_pendientes(hoy=hoy)

    if not periodos:
        logger.info("No hay periodos pendientes que procesar")
        return 0

    hubo_error = False
    filas_para_escribir: list[dict] = []

    for periodo in periodos:
        logger.info("Procesando %s...", periodo)
        filas, algun_pdf = procesar_periodo(
            periodo, catalogo, catalogo_idx, manifiesto, desconocidas,
            force=args.force, sin_llm=args.sin_llm, dry_run=args.dry_run, hoy=hoy,
        )
        if not algun_pdf:
            logger.info("%s: ningún PDF publicado todavía, se omite (no es un error)", periodo)
            continue

        resultado = validar_periodo(filas, catalogo)
        for aviso in resultado.avisos:
            logger.warning("::warning::%s: %s", periodo, aviso)

        if not resultado.es_valido:
            hubo_error = True
            logger.error("%s: la validación falló, NO se escribe en el CSV:", periodo)
            for error in resultado.errores:
                logger.error("  - %s", error)
            continue

        logger.info("%s: validación OK (%d filas)", periodo, len(filas))
        filas_para_escribir.extend(filas)

    if args.dry_run:
        logger.info("--dry-run: %d filas se habrían escrito en total, nada se ha guardado", len(filas_para_escribir))
        return 1 if hubo_error else 0

    if filas_para_escribir:
        escribir_csv(filas_para_escribir)
        logger.info("gas.csv actualizado con %d filas nuevas", len(filas_para_escribir))
    _guardar_json(MANIFIESTO_PATH, manifiesto)
    _guardar_json(DESCONOCIDAS_PATH, desconocidas)

    return 1 if hubo_error else 0


if __name__ == "__main__":
    sys.exit(main())
