"""Capa LLM: mapea el contenido de un PDF de Enagás al catálogo de
métricas.

Decisión de diseño 1.2: la extracción numérica es determinista, el LLM
solo mapea. Claude no calcula ni infiere nada -- copia literalmente el
número que ve y decide a qué `metrica_id` del catálogo corresponde. La
conversión de unidades y el parseo del formato español los hace
después `src/extraccion/normalizar.py`; la comprobación de que los
agregados cuadran la hace `src/extraccion/validar.py`. Una llamada por
PDF, con las páginas como imágenes (ver el docstring de
`src/extraccion/pdf.py` para por qué imágenes y no solo texto).
"""

from __future__ import annotations

import json
import logging
import time

import anthropic

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 32000
MAX_REINTENTOS = 3
BACKOFF_SECONDS = 5

_SYSTEM_PROMPT_TEMPLATE = """\
Eres un extractor de datos determinista. Tu única tarea es leer las páginas \
de un documento PDF de Enagás (te las paso como imágenes, una por página) y \
devolver, para cada cifra que veas, a qué métrica del catálogo corresponde.

REGLAS ESTRICTAS:
1. NO calcules ni infieras ningún valor. Copia literalmente el número tal \
como aparece impreso (con su formato español: "15.267", "-2,8%", "1.065,3"). \
No lo conviertas de unidad, no lo redondees, no lo reformatees.
2. Si un valor de la tabla no aparece en la imagen o no lo puedes leer con \
confianza, devuelve null para ese campo. Nunca inventes ni "rellenes" un \
hueco con un cero o una estimación.
3. Solo devuelve extracciones para métricas del catálogo que te paso abajo. \
Si ves una cifra relevante que no encaja en ninguna métrica del catálogo, \
descríbela en "metricas_no_reconocidas" en vez de forzarla en una métrica \
que no le corresponde.
4. Cada extracción debe indicar la página (1-indexada) donde la viste.
5. `agregacion` es "mes" (columna "Acumulado mensual" / valor del mes en \
curso), "acumulado_anual" (columna "Acumulado anual", enero hasta el mes \
en curso) o "tam" (columna "Total Anual Móvil" / TAM). Si una métrica solo \
tiene una cifra puntual del mes (no una serie de 3 columnas), usa "mes".
6. `var_pct_interanual` es la variación % que publica el propio documento \
junto al valor (columna "%Δ" o similar), tal cual, en el mismo formato \
español. Si no hay variación publicada para esa celda, null.
7. Para métricas con dimensión (CCAA, país, tecnología, planta, conexión, \
destino), `dimension_valor` es el nombre tal como aparece impreso (no lo \
normalices, eso lo hace un paso posterior). Para métricas sin dimensión, \
`dimension_valor` es null.
8. UNA sola entrada por (metrica_id, dimension_valor): agrupa las tres \
columnas ("Acumulado mensual", "Acumulado anual", "Total anual móvil") \
dentro de "valores" y "var_pct_interanual", en vez de repetir metrica_id \
tres veces. Si una cifra solo tiene una columna (sin desglose mensual/ \
acumulado/TAM), rellena solo la clave "mes" y omite las demás (no \
inventes un acumulado que el documento no publica).
9. GRÁFICOS DE TARTA/DONUT CON LEYENDA DE COLORES: no asumas que el orden \
de las porciones (p.ej. en el sentido del reloj empezando arriba) coincide \
con el orden de las categorías en la leyenda. Identifica el COLOR exacto \
de cada porción y empareja ese mismo color con su cuadradito en la \
leyenda antes de asignar el porcentaje a la categoría -- es el error más \
fácil de cometer en este tipo de gráfico y produce un número plausible \
pero cruzado con otra categoría.
10. TABLAS CON FILA/COLUMNA "Total": para una métrica con dimensión (CCAA, \
país, planta, conexión, tecnología...), NO devuelvas una extracción con \
`dimension_valor` = "Total" (o "TOTAL", "Total general", etc.) aunque la \
tabla del PDF traiga esa fila/columna de suma. El total lo calcula el \
propio pipeline sumando las filas individuales que sí extraigas; una fila \
"Total" adicional no es una categoría real y descuadra la validación de \
rangos y las sumas cruzadas. Extrae únicamente las filas con un nombre de \
categoría real (BARCELONA, Argelia, Almería...).

CATÁLOGO DE MÉTRICAS PARA ESTE DOCUMENTO (fuente: {fuente}):
{catalogo_json}

FORMATO DE SALIDA: responde EXCLUSIVAMENTE con JSON estricto, sin markdown, \
sin bloques de código, sin texto antes ni después, y SIN espacios de \
indentación extra (JSON compacto, para ahorrar tokens de salida).
Estructura exacta:

{{
  "extracciones": [
    {{
      "metrica_id": "demanda_convencional",
      "dimension_valor": null,
      "pagina": 3,
      "valores": {{"mes": "15.267", "acumulado_anual": "117.818", "tam": "228.076"}},
      "var_pct_interanual": {{"mes": "-2,8%", "acumulado_anual": "-3,1%", "tam": "-1,6%"}}
    }},
    {{
      "metrica_id": "tvb_capacidad_regasificacion_total",
      "dimension_valor": null,
      "pagina": 15,
      "valores": {{"mes": "58.350"}},
      "var_pct_interanual": {{}}
    }}
  ],
  "metricas_no_reconocidas": [
    {{"descripcion": "texto que describe la cifra", "valor_aprox": "texto tal cual", "pagina": 7}}
  ]
}}
"""


def _catalogo_para_prompt(catalogo: list[dict], fuente: str) -> list[dict]:
    """Filtra el catálogo a las métricas de esta fuente, con solo los
    campos que el modelo necesita para mapear (no le hace falta
    `unidad_canonica` ni `padre`, eso es normalización posterior)."""
    return [
        {
            "metrica_id": m["metrica_id"],
            "nombre": m["nombre"],
            "dimension": m["dimension"],
            "unidad_esperada_en_pdf": m["unidad_pdf"],
            "notas": m["notas"],
        }
        for m in catalogo
        if m["fuente"] == fuente
    ]


def _build_system_prompt(catalogo: list[dict], fuente: str) -> str:
    subset = _catalogo_para_prompt(catalogo, fuente)
    return _SYSTEM_PROMPT_TEMPLATE.format(
        fuente=fuente, catalogo_json=json.dumps(subset, ensure_ascii=False, indent=2)
    )


def _build_image_blocks(pages: list[dict]) -> list[dict]:
    blocks = []
    for page in pages:
        blocks.append({"type": "text", "text": f"Página {page['pagina']}:"})
        blocks.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": page["imagen_base64"],
                },
            }
        )
    return blocks


def _extraer_json(texto: str) -> dict:
    """Parsea la respuesta del modelo como JSON. Defensivo ante algún
    preámbulo/fence de markdown que el modelo pueda colar pese a la
    instrucción, para no perder una extracción cara por un detalle de
    formato."""
    limpio = texto.strip()
    if limpio.startswith("```"):
        limpio = limpio.strip("`")
        if limpio.startswith("json"):
            limpio = limpio[4:]
        limpio = limpio.strip()
    inicio = limpio.find("{")
    fin = limpio.rfind("}")
    if inicio == -1 or fin == -1:
        raise ValueError("La respuesta no contiene un objeto JSON")
    return json.loads(limpio[inicio : fin + 1])


def extraer_documento(
    pages: list[dict],
    fuente: str,
    catalogo: list[dict],
    client: anthropic.Anthropic | None = None,
) -> dict:
    """Llama a Claude una vez para extraer todas las cifras de un PDF
    (una lista de páginas ya renderizadas, ver `src/extraccion/pdf.py`)
    y mapearlas al catálogo de métricas de `fuente` ("boletin" |
    "progreso"). Reintenta con backoff si la respuesta no parsea como
    JSON válido. Temperature 0: queremos la lectura más literal posible,
    no creatividad.
    """
    client = client or anthropic.Anthropic()
    system_prompt = _build_system_prompt(catalogo, fuente)
    content = _build_image_blocks(pages)

    last_exc: Exception | None = None
    for intento in range(1, MAX_REINTENTOS + 1):
        # max_tokens es lo bastante grande (documentos con muchas métricas
        # dimensionadas) para que el SDK exija streaming en vez de una
        # llamada bloqueante (ver aviso de anthropic-sdk-python sobre
        # peticiones que pueden tardar más de 10 minutos).
        with client.messages.stream(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            temperature=0,
            system=system_prompt,
            messages=[{"role": "user", "content": content}],
        ) as stream:
            response = stream.get_final_message()
        texto = "".join(block.text for block in response.content if block.type == "text")
        try:
            resultado = _extraer_json(texto)
        except (ValueError, json.JSONDecodeError) as exc:
            last_exc = exc
            logger.warning(
                "Respuesta del modelo no parsea como JSON (intento %d/%d): %s",
                intento,
                MAX_REINTENTOS,
                exc,
            )
            if intento < MAX_REINTENTOS:
                time.sleep(BACKOFF_SECONDS * intento)
            continue

        resultado.setdefault("extracciones", [])
        resultado.setdefault("metricas_no_reconocidas", [])
        resultado["_meta"] = {
            "modelo": MODEL,
            "fuente": fuente,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }
        return resultado

    raise RuntimeError(
        f"El modelo no devolvió JSON válido tras {MAX_REINTENTOS} intentos"
    ) from last_exc
