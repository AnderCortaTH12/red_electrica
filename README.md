# Observatorio del Sistema Gasista Español

Datos mensuales del sistema gasista español, extraídos automáticamente de
las dos publicaciones PDF de Enagás (Boletín Estadístico del Gas y
Progreso mensual de la demanda), validados con reglas de cuadre cruzado,
y servidos en un dashboard estático en GitHub Pages.

**Dashboard:** https://andercortath12.github.io/red_electrica/

Este proyecto era antes un sistema de forecasting del precio eléctrico
(ver el historial de git para esa versión). Se reconvirtió por completo:
se conserva la infraestructura que funcionaba (patrón de automatización
con GitHub Actions, abstracción de fuentes de datos, capa `docs/` de
GitHub Pages sin build step), pero la lógica de negocio es enteramente
nueva.

## La idea en una frase

Cada mes, sin intervención manual: descarga los dos PDF que publica
Enagás, le pide a Claude que localice cada cifra y la mapee a un
catálogo de métricas fijo, valida que los agregados cuadran entre sí
(y entre las dos fuentes), y si todo cuadra lo escribe en un CSV
versionado en git que alimenta el dashboard.

## Por qué dos fuentes

- **Boletín Estadístico del Gas**: totales de demanda, demanda por
  CCAA, orígenes de suministro por país, conexiones internacionales,
  biometano, TVB, plantas de regasificación, mix de generación
  eléctrica. Es la fuente "ancha": muchas métricas, cada una a un solo
  nivel de detalle.
- **Progreso mensual de la demanda**: lo único que aporta y el Boletín
  no trae es el desglose de la demanda convencional en **D/C+PyMES ·
  Industrial · Cisternas**. Sin esta fuente, la jerarquía de demanda se
  quedaría coja en su nivel más fino.

Que ambas fuentes describan la misma demanda convencional total desde
ángulos distintos es, además, la validación cruzada más valiosa del
pipeline (ver más abajo).

## Decisiones de arquitectura

**Nada de SQLite.** El volumen es pequeño (12 meses × unos cientos de
métricas al año) y cabe de sobra en un CSV versionado en git
(`data/gas.csv`). Esto da historial y diff auditable de cada
extracción gratis, y elimina de raíz el problema del proyecto anterior
(la cache de GitHub Actions evictándose y haciendo desaparecer datos).

**La extracción numérica es determinista; el LLM solo mapea.** Claude
no calcula ni infiere ninguna cifra: copia literalmente el número que
ve en el PDF y decide a qué `metrica_id` del catálogo corresponde
(`src/extraccion/llm.py`). El parseo del formato español
(`parse_numero_es`), la conversión de unidades y la normalización de
nombres de dimensión los hace después código determinista
(`src/extraccion/normalizar.py`). Un validador (`src/extraccion/validar.py`)
comprueba que los agregados cuadran antes de escribir nada; si no
cuadran, el proceso falla en rojo y **no se escribe nada en el CSV**
(o todo o nada, para no dejar el dataset a medias).

**PDF → imagen, no PDF → texto.** La primera versión mandaba a Claude
el texto que extrae `pdfplumber`. Probado contra un PDF real, el texto
de las tablas con estilo (fondo de color, cabeceras rotadas) sale
desordenado carácter a carácter — inservible. La misma página
renderizada como imagen se lee perfectamente. `src/extraccion/pdf.py`
genera un PNG por página y `src/extraccion/llm.py` usa la API
multimodal de Claude. El texto/tablas de `pdfplumber` se conservan
igualmente como respaldo auditable barato en `data/extracciones/`.

**Idempotencia y reproceso.** Cualquier mes se puede volver a procesar
a mano con `--force`. Las revisiones de Enagás se sobrescriben en
silencio (sin versionado ni aviso) — pero si la revisión introduce un
sufijo distinto en el nombre del fichero (ver Limitaciones), hay que
tocar `src/ingestion/enagas_source.py`.

## Estructura

```
Forecasting-Electrico/
├── .github/workflows/mensual.yml  # cron diario: ingesta + monitorización + dashboard
├── data/
│   ├── metricas_catalogo.json     # el contrato del proyecto
│   ├── gas.csv                    # el dataset canónico, formato largo (tidy)
│   ├── manifiesto.json            # URL/sha256/fechas de cada PDF procesado
│   ├── extracciones/              # respuesta cruda del LLM por periodo+fuente (auditable)
│   ├── metricas_desconocidas.json # cifras vistas pero no mapeadas a ninguna métrica
│   ├── informe_monitorizacion.json
│   └── raw/                       # PDFs descargados (gitignored, se recuperan de la URL)
├── src/
│   ├── ingestion/                 # DataSource abstracta + BoletinSource/ProgresoSource
│   ├── extraccion/                # pdf.py, llm.py, normalizar.py, validar.py, catalogo.py
│   └── monitoring/                # informe.py (periodo desactualizado + última validación)
├── scripts/                       # ingest_month.py, backfill.py, validar_dataset.py,
│                                   # monitor.py, export_dashboard.py
├── docs/                          # dashboard estático (GitHub Pages, sirve desde main:/docs)
├── tests/
├── requirements.txt
└── .env.example
```

## Puesta en marcha

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

copy .env.example .env
# Editar .env y rellenar ANTHROPIC_API_KEY (console.anthropic.com/settings/keys)
```

```powershell
python -m pytest tests/ -q
```

## Esquema del CSV (`data/gas.csv`)

Formato largo (tidy), una fila por observación, ordenado por
`periodo, metrica_id, dimension, agregacion`:

```
periodo,metrica_id,dimension,agregacion,valor,unidad,var_pct_interanual,fuente_doc,pagina,extraido_el
2026-06,demanda_convencional,,mes,15267.0,GWh,-2.8,boletin,3,2026-08-06
2026-06,demanda_convencional,,acumulado_anual,117818.0,GWh,-3.1,boletin,3,2026-08-06
2026-06,aprovisionamiento_gn,Argelia,mes,9978.0,GWh,40.3,boletin,9,2026-08-06
```

- `periodo`: `YYYY-MM`, el mes al que se refiere el dato (no el de publicación).
- `dimension`: vacío para métricas escalares; el valor del eje (p.ej.
  `Argelia`, `Cataluña`) para las dimensionadas.
- `agregacion`: `mes` | `acumulado_anual` | `tam` (Total Anual Móvil).
  **Ojo**: no todas las métricas traen las tres. El desglose por CCAA,
  las plantas de regasificación, el TVB y la mezcla GN/GNL solo vienen
  en columna mensual en el PDF fuente — ver Limitaciones.
- `var_pct_interanual`: tal cual la publica Enagás (ver por qué en
  Limitaciones). `>100%`/`<-100%` se guardan como `null`, nunca como
  `100`/`-100`.
- Todo normalizado a la `unidad_canonica` del catálogo (TWh → GWh × 1000
  cuando aplica). El CSV nunca mezcla unidades para la misma métrica.

## Catálogo de métricas (`data/metricas_catalogo.json`)

Es el contrato del proyecto. Cada métrica define `metrica_id`,
`nombre`, `padre` (para la jerarquía de demanda), `unidad_canonica`,
`unidad_pdf` (la unidad tal como aparece en el PDF, para saber cuándo
convertir), `dimension`, `fuente` (`boletin`|`progreso`) y `obligatoria`
(si su ausencia debe hacer fallar la validación).

**Para añadir una métrica nueva:**

1. Añade la entrada al catálogo con su `metrica_id`, `padre` (o `null`
   si es raíz o no forma parte de la jerarquía de demanda),
   `unidad_canonica`, `unidad_pdf`, `dimension` y `fuente`.
2. Si quieres que bloquee la validación cuando falte, márcala
   `obligatoria: true` — con cuidado, solo tiene sentido para métricas
   que Enagás publica todos los meses sin falta.
3. Reprocesa un mes con `--force` para comprobar que el modelo la
   encuentra: `python -m scripts.ingest_month --periodo 2026-06 --force`.
4. Si el modelo no la encuentra, revisa `data/metricas_desconocidas.json`
   de ese periodo — puede que la esté describiendo con otro nombre.

## Reprocesar un mes

```powershell
python -m scripts.ingest_month --periodo 2026-06 --force   # revisión de Enagás
python -m scripts.ingest_month --periodo 2026-06 --sin-llm  # reusa data/extracciones/, no llama a la API
python -m scripts.ingest_month --dry-run                    # no escribe nada, solo informa
python -m scripts.backfill                                  # todos los periodos pendientes desde 2026-01
python -m scripts.validar_dataset                            # revalida gas.csv entero sin tocar PDFs
```

## Automatización

`.github/workflows/mensual.yml` corre cada día a las 07:00 UTC (cron
diario pese al nombre "mensual": probar dos URLs con `HEAD` no cuesta
nada y es más robusto que adivinar el día exacto de publicación de
Enagás, que varía). Solo se llama a la API de Claude cuando aparece un
PDF nuevo — un día sin publicación cuesta cero. También se puede
lanzar a mano desde la pestaña *Actions* → *mensual-pipeline* → *Run
workflow*, con inputs `periodo` y `force` para reprocesar un mes
concreto.

**Configuración necesaria** (una sola vez): añade tu clave de la API
de Anthropic como secret del repo en *Settings → Secrets and variables
→ Actions → New repository secret*, nombre exacto `ANTHROPIC_API_KEY`
(sin espacios ni comillas). Sin esto el job falla pronto con un mensaje
claro en vez de un traceback.

**GitHub Pages**: *Settings → Pages → Build and deployment → Source:
"Deploy from a branch"* → rama `main`, carpeta `/docs`. No uses el modo
"GitHub Actions" — genera un workflow de Pages aparte
(`actions/deploy-pages`) que no forma parte de este proyecto y que se
ha visto quedarse colgado en `deployment_queued`.

Si la ingesta o la validación fallan, el job se pone en rojo (sin
`continue-on-error`). Si no hay PDF nuevo, termina en verde sin commit.
El paso de exportar el dashboard sí tiene `continue-on-error`: un fallo
ahí no debe tumbar el pipeline de datos, que es la fuente de verdad.

## Monitorización

`scripts/monitor.py` (parte del workflow) escribe
`data/informe_monitorizacion.json` con dos chequeos:

- **¿Más de 45 días sin conseguir ingerir un periodo nuevo?** Medido
  contra la fecha de la última ingesta exitosa (`extraido_el`), no
  contra el mes calendario del periodo — Enagás publica con ~1 mes de
  retraso, así que medirlo mal dispararía el aviso todos los días
  aunque el pipeline funcione perfectamente (bug real que se detectó
  y corrigió antes de llegar a producción, ver tests en
  `tests/test_monitoring.py`). Un aviso aquí sugiere que el patrón de
  URL de Enagás ha cambiado.
- **Resumen de la última validación** del periodo más reciente en el CSV.

Nunca falla el job: un aviso (`::warning::`) es una señal a revisar,
no un fallo del pipeline.

## Dashboard

Estático en `docs/`, servido por GitHub Pages desde `main:/docs`. HTML
+ CSS + JS vanilla con ES modules nativos, sin build step, [Apache
ECharts](https://echarts.apache.org/) por CDN. `scripts/export_dashboard.py`
genera `docs/data/{catalogo,serie,ultimo}.json`; `serie.json` con el
patrón "una fila por línea" para que el diff de cada ejecución mensual
sean unas pocas líneas.

Seis vistas (Resumen, Desglose de la demanda, Comparativa, Territorio,
Aprovisionamiento, Infraestructuras) con un control global de
agregación (Mes / Acumulado del año / Total anual móvil). Territorio,
Infraestructuras y la mezcla GN/GNL de Aprovisionamiento ignoran ese
control a propósito y se quedan fijos en "Mes" con un aviso explícito
— ver Limitaciones, esas tablas del PDF fuente no traen columna
acumulado/TAM.

Probar en local:

```powershell
cd docs
python -m http.server 8000
# abrir http://localhost:8000 (file:// no funciona, lo bloquean los ES modules por CORS)
```

## Limitaciones conocidas

- **Los datos de Enagás son un AVANCE provisional**, sujeto a revisión
  en publicaciones posteriores. El pipeline sobrescribe en silencio si
  se reprocesa con `--force`; no versiona revisiones distintas del
  mismo mes.
- **No hay histórico antes de 2026-01**, así que las variaciones
  interanuales se toman tal como las publica Enagás y no se pueden
  recalcular de forma independiente hasta 2027, cuando haya un año
  completo propio.
- **La ingesta depende de un patrón de URL, no de una API.** Si Enagás
  cambia el nombrado de los ficheros, el pipeline deja de encontrar
  meses nuevos en silencio (no es un error: "PDF no publicado todavía"
  es un estado válido). Por eso existe el aviso de monitorización de
  "45 días sin periodo nuevo". Ya ha pasado una vez en producción: ver
  el punto siguiente.
- **Corregido durante el backfill: el Boletín renombra el fichero con
  un sufijo "rev" cuando revisa un mes ya publicado**, y de forma
  inconsistente — visto `ene26rev.pdf` (sin guion) y `feb26_rev.pdf` /
  `mar26_rev.pdf` (con guion). `BoletinSource.candidate_urls` prueba
  las tres variantes; el nombrado del Progreso ya era conocido por
  inconsistente desde el diseño original.
- **Los desgloses por CCAA no cuadran con el total nacional** (Enagás
  no incluye todas las comunidades ni todos los consumos). Es un
  `::warning::`, no un error — comprobado en los 6 meses del backfill,
  la diferencia ronda el 5-10%.
- **CCAA, plantas de regasificación, TVB y la mezcla GN/GNL solo
  traen columna mensual** en el PDF fuente, sin desglose
  acumulado/TAM. El validador no las comprueba fuera de `agregacion=mes`,
  y el dashboard fija esas vistas a "Mes" con un aviso en vez de
  mostrar una tabla vacía cuando se cambia el control de agregación.
- **Los gráficos de tarta/donut son el punto más frágil de la
  extracción por visión.** Se encontró un caso real: en
  `destino_cargas_pct` de junio-2026, el modelo leyó bien los tres
  porcentajes pero cruzó **Bunkering ↔ EU** (emparejó mal el color de
  cada porción con su leyenda). Corregido a mano contrastando contra
  el PDF, con nota de auditoría en
  `data/extracciones/2026-06_boletin.json`, y reforzada la instrucción
  del prompt (`src/extraccion/llm.py`) para que el modelo empareje por
  color exacto, no por posición.
- **`pct_total_gn`/`pct_total_gnl` faltaron para 2026-06**: el modelo
  vio la cifra (registrada en `metricas_no_reconocidas`) pero no la
  mapeó a la métrica del catálogo — un fallo de recall puntual, no
  sistemático (los otros 5 meses del backfill sí lo mapearon bien).
  Añadido a mano con el valor verificado contra el PDF.
- **Almacenamientos subterráneos (AASS) no están en el catálogo.**
  Decisión tomada al ver que esa sección del Boletín (página 20) es
  solo gráficos, sin tabla de cifras — nada fiable que extraer por
  ahora. Pendiente si Enagás cambia el formato de esa sección.
- **Los rangos "sanos" del validador se calibraron sobre junio**
  (mes de baja demanda) y hubo que ensancharlos tras procesar enero
  (pico de demanda por calefacción, ~1,8x junio) — ver el historial de
  `src/extraccion/validar.py`. Es plausible que haga falta ensancharlos
  más al acumular más inviernos.
- **Sin histórico real de rendimiento**: a diferencia del proyecto de
  forecasting anterior, este observatorio no predice nada — es
  puramente descriptivo. No hay MAE ni modelo que monitorizar, solo la
  fiabilidad de la extracción.

## Tests

```powershell
python -m pytest tests/ -q
```

Cubren: parseo de números en formato español (`parse_numero_es`, con
los casos reales del PDF que rompen más fácil), conversión de
unidades, normalización de nombres de dimensión, construcción de URLs
candidatas (incluidas las variantes "rev"), el validador (un caso que
cuadra y uno por cada regla que falla), y el chequeo de periodo
desactualizado de la monitorización.
