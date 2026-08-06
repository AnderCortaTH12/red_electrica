"""Normalización de cifras y nombres de dimensión extraídos de los PDF.

Esta es la pieza determinista del pipeline: el LLM solo mapea texto a
`metrica_id`, pero el número en sí y su unidad los procesa este
módulo, no el modelo (ver decisión 1.2 del diseño). `parse_numero_es`
es probablemente la fuente de error más probable de todo el proyecto
-- de ahí que tenga tests dedicados con casos reales del PDF.
"""

from __future__ import annotations

# Valores que Enagás usa para "no hay dato" o "no publicable".
_SIN_DATO = {"", "-", "–", "—", "n/d", "n.d.", "nd"}

# Variación interanual fuera del rango que Enagás publica como cifra
# exacta: aparece como ">100%" o "<-100%" en el PDF. No es un valor
# real, es un texto que indica "más de" / "menos de" -- se guarda como
# null, nunca como 100/-100 (eso falsearía la cifra).
_SIGNOS_FUERA_DE_RANGO = (">", "<")


def parse_numero_es(raw: str | float | int | None) -> float | None:
    """Parsea un número en formato español tal como lo publica Enagás.

    - Punto = separador de miles, coma = separador decimal:
      "15.267" -> 15267.0, "-2,8%" -> -2.8, "1.065" -> 1065.0
    - ">100%" / "<-100%" -> None (Enagás trunca la variación fuera de
      rango, no publica la cifra exacta)
    - "", "-", None -> None (dato no publicado)
    """
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw)

    s = str(raw).strip()
    if s.lower() in _SIN_DATO:
        return None
    if s.startswith(_SIGNOS_FUERA_DE_RANGO):
        return None

    negativo = s.startswith("-")
    s = s.lstrip("+-").strip()
    s = s.replace("%", "").strip()
    if s in _SIN_DATO:
        return None

    # Formato español -> formato parseable por float()
    s = s.replace(".", "").replace(",", ".")

    try:
        valor = float(s)
    except ValueError:
        return None
    return -valor if negativo else valor


# Factores de conversión soportados. Se amplía según haga falta, no se
# intenta cubrir unidades arbitrarias.
_FACTORES_CONVERSION: dict[tuple[str, str], float] = {
    ("TWh", "GWh"): 1000.0,
    ("GWh", "TWh"): 0.001,
}


def convertir_unidad(valor: float | None, unidad_origen: str, unidad_destino: str) -> float | None:
    """Convierte `valor` de `unidad_origen` a `unidad_destino`.

    El CSV canónico (`data/gas.csv`) nunca mezcla unidades para la
    misma métrica: todo se normaliza a `unidad_canonica` del catálogo
    antes de escribirse (p.ej. el Progreso viene en TWh, se multiplica
    por 1000 para guardarse en GWh).
    """
    if valor is None:
        return None
    if unidad_origen == unidad_destino:
        return valor
    factor = _FACTORES_CONVERSION.get((unidad_origen, unidad_destino))
    if factor is None:
        raise ValueError(f"Conversión de unidad no soportada: {unidad_origen} -> {unidad_destino}")
    return valor * factor


# Variantes de nombre vistas en los PDF -> forma canónica. Se amplía
# según aparezcan variantes reales al procesar más meses; no pretende
# ser exhaustivo desde el día uno.
DIMENSION_ALIASES: dict[str, dict[str, str]] = {
    "ccaa": {
        "castilla - la mancha": "Castilla-La Mancha",
        "castilla-la mancha": "Castilla-La Mancha",
        "castilla la mancha": "Castilla-La Mancha",
        "castilla y leon": "Castilla y León",
        "castilla y león": "Castilla y León",
        "pais vasco": "País Vasco",
        "país vasco": "País Vasco",
        "comunidad valenciana": "Comunidad Valenciana",
        "c. valenciana": "Comunidad Valenciana",
        "la rioja": "La Rioja",
        "madrid": "Madrid",
        "comunidad de madrid": "Madrid",
    },
    "tecnologia": {
        # "Hidraúlica" (sic) es un error tipográfico real de Enagás en
        # el PDF, no un error nuestro -- se normaliza igual.
        "hidraúlica": "Hidráulica",
        "hidraulica": "Hidráulica",
        "hidráulica": "Hidráulica",
        "eolica": "Eólica",
        "eólica": "Eólica",
        "solar fv": "Solar fotovoltaica",
        "solar fotovoltaica": "Solar fotovoltaica",
        "solar termica": "Solar térmica",
        "solar térmica": "Solar térmica",
        "ciclo combinado": "Ciclo combinado",
        "nuclear": "Nuclear",
        "carbon": "Carbón",
        "carbón": "Carbón",
        "cogeneracion": "Cogeneración",
        "cogeneración": "Cogeneración",
    },
}


def normalizar_dimension(valor: str | None, dimension: str) -> str | None:
    """Mapea una variante de nombre (CCAA, tecnología, país...) a su
    forma canónica, usando `DIMENSION_ALIASES`. Si no hay alias
    conocido, devuelve el valor tal cual (recortado de espacios), en
    vez de fallar -- lo nuevo se detecta luego al no cuadrar en el
    validador, no aquí.
    """
    if valor is None:
        return None
    limpio = valor.strip()
    alias = DIMENSION_ALIASES.get(dimension, {})
    return alias.get(limpio.lower(), limpio)
