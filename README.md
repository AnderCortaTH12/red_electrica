# Forecasting Eléctrico

[![daily pipeline](https://github.com/AnderCortaTH12/red_electrica/actions/workflows/daily.yml/badge.svg)](https://github.com/AnderCortaTH12/red_electrica/actions/workflows/daily.yml)
[![docker build](https://github.com/AnderCortaTH12/red_electrica/actions/workflows/docker-build.yml/badge.svg)](https://github.com/AnderCortaTH12/red_electrica/actions/workflows/docker-build.yml)

Sistema de predicción del precio eléctrico español (mercado diario/spot) en
producción continua: ingesta automatizada de datos de la API de ESIOS (Red
Eléctrica de España), almacenamiento en SQLite, modelo de forecasting con
validación temporal honesta, servido vía API, y monitorización del error
real fuera de muestra.

El objetivo no es solo entrenar un modelo, sino **productivizarlo**: que
corra solo, se pueda reproducir, y se vigile a sí mismo.

## Estado del proyecto

En construcción, fase por fase. Ver `Proyecto_Forecasting_Electrico_Guia.md`
para el plan completo.

- [x] Fase 0 — Estructura y verificación de acceso a la API
- [x] Fase 1 — Catálogo de indicadores
- [x] Fase 2 — Cliente robusto de la API
- [x] Fase 3 — Ingesta histórica a SQLite
- [x] Fase 4 — Exploración y features
- [x] Fase 5 — Modelo (baseline + LightGBM) — pipeline completo; el modelo
      (tendencia lineal + LightGBM sobre el residuo, `src/model/detrend.py`)
      supera al baseline tras corregir dos bugs de agregación de datos
      (ver Limitaciones conocidas)
- [x] Fase 6 — Servir el modelo (FastAPI + Docker) — API verificada en
      local; el `Dockerfile` se verifica vía GitHub Actions (Docker
      Desktop no instalado en este entorno de desarrollo), ver
      pestaña "Actions" del repo
- [x] Fase 7 — Automatización y monitorización — job diario en GitHub
      Actions (ingesta incremental, reentreno, predicción, monitorización);
      badge arriba muestra el estado del último run
- [x] Fase 8 — Dashboard público en GitHub Pages

## Dashboard (Fase 8)

Página estática en GitHub Pages, servida desde **`main:/docs`** (no una
rama `gh-pages` separada — menos piezas que gestionar en un proyecto en
solitario): **https://andercortath12.github.io/red_electrica/**

Sin build step (HTML + CSS + JS vanilla con ES modules nativos,
[Apache ECharts](https://echarts.apache.org/) vía CDN) — cero
dependencias que puedan romper el Action dentro de seis meses. GitHub
Pages es estático (sin Python en runtime), así que todo lo que se
muestra viene precalculado por `scripts/export_dashboard_data.py`
(último paso del job diario, con `continue-on-error` para no tumbar el
resto del pipeline si falla):

- `docs/data/latest.json` (~16KB, se carga siempre): últimas 72h de
  precio real/modelo/baseline + generación, predicción de las próximas
  horas, KPIs del día, estado del sistema (semáforo verde/ámbar según
  los flags de `src/monitoring/`), y MAE rolling 7/30 días.
- `docs/data/monthly/YYYY-MM.json` (91 ficheros, ~78KB cada uno,
  2019-01 → hoy): cargado bajo demanda al navegar a una fecha. Los
  meses **pasados son inmutables** — solo se regenera el mes en curso
  en cada ejecución, para no inflar el historial de git.
- `docs/data/summary.json` (~350KB, series diarias 2019-hoy): formato
  `{columns, rows}` con cada fila en su propia línea de texto (no
  `json.dumps` con indent normal), para que el diff diario sean 1-2
  líneas, no el fichero entero.
- `docs/data/model_performance.json`: MAE por año (2014-hoy) del
  baseline y del modelo, y el scatter predicho-vs-real de las
  predicciones ya verificadas — crece día a día.

Probar en local (sirve `docs/` con un servidor estático simple; abrir
`index.html` directamente con `file://` NO funciona por las
restricciones CORS de los ES modules):

```powershell
cd docs
python -m http.server 8000
# abrir http://localhost:8000
```

Para regenerar los datos a mano sin lanzar todo el pipeline:

```powershell
python -m scripts.export_dashboard_data
```

## Estructura

```
Forecasting-Electrico/
├── .github/workflows/  # docker-build.yml (CI) y daily.yml (cron diario)
├── src/
│   ├── ingestion/  # cliente ESIOS, DataSource abstracta, backfill + incremental
│   ├── storage/    # esquema y acceso a SQLite (observations, predictions...)
│   ├── features/   # carga wide-format + feature engineering leakage-safe
│   ├── model/      # baseline, LightGBM, metricas, regimenes, artefacto agnostico
│   ├── monitoring/ # calidad de datos + tracking de error real
│   └── serving/    # API FastAPI (src/serving/api.py)
├── scripts/        # scripts ejecutables (ingesta, entrenamiento, predicción, monitor...)
├── data/           # bbdd SQLite y datos crudos (ignorado por git, se regenera)
├── models/         # modelo activo + historial de versiones + métricas de experimentos
├── notebooks/      # notebooks de exploración (EDA, análisis de resultados)
├── tests/          # tests con pytest
├── requirements.txt
├── Dockerfile
└── .env.example    # plantilla de variables de entorno (copiar a .env)
```

## Puesta en marcha

```powershell
# Crear y activar entorno virtual (si no existe ya)
python -m venv venv
.\venv\Scripts\Activate.ps1

# Instalar dependencias
pip install -r requirements.txt

# Configurar credenciales
copy .env.example .env
# Editar .env y rellenar ESIOS_API_KEY con tu token personal
```

Verificar que la autenticación contra la API de ESIOS funciona:

```powershell
python -m scripts.test_esios_auth
```

> Los scripts de `scripts/` se ejecutan como módulo (`python -m scripts.nombre`,
> no `python scripts\nombre.py`) porque importan código de `src/`, y `-m`
> añade la raíz del proyecto al `sys.path` automáticamente.

Descargar el histórico completo (2014 → hoy) de los indicadores del catálogo
a `data/electricidad.db`. Es idempotente: si se corta a mitad, al
relanzarlo continúa donde estaba sin duplicar datos ni repetir ventanas
ya descargadas:

```powershell
python -m scripts.ingest_historical
```

Traer solo los datos nuevos desde el último dato ya guardado (lo que
ejecuta el job diario; también válido para actualizar manualmente):

```powershell
python -m scripts.ingest_incremental
```

Entrenar el modelo actual (baseline naive + LightGBM sobre el régimen
`post_tope`) y guardar el artefacto que sirve la API:

```powershell
python -m scripts.train_baseline
python -m scripts.train_lightgbm
```

Generar la predicción con el modelo activo y guardarla (para poder
comparar más tarde contra el precio real), y correr la monitorización:

```powershell
python -m scripts.predict_and_log
python -m scripts.monitor
```

## Servir el modelo (API)

Arranque local (recarga automática al cambiar código):

```powershell
uvicorn src.serving.api:app --reload
```

```powershell
curl http://localhost:8000/health
curl "http://localhost:8000/predict?hours=24"
```

`/health` expone `model_type`/`model_version`/`trained_at` para saber a
simple vista qué modelo está sirviendo sin mirar el código. La API es
agnóstica al algoritmo (`src/model/artifact.py`): solo espera un
`models/model.joblib` + `models/model_metadata.json` con esa forma, así
que cambiar de modelo no requiere tocar `src/serving/api.py`.

**Resuelto (Fase 8)**: `/predict` ya devuelve previsión real de horas
futuras, no solo "las horas más recientes con dato completo" como en
la Fase 6 original. `scripts/ingest_incremental.py` pide las 3
previsiones D+1 de ESIOS (`demanda_prevista`, `prevision_eolica`,
`prevision_fv`) hasta ahora+48h en vez de solo hasta ahora
(`FORECAST_HORIZON_HOURS`). El horizonte real varía día a día: está
acotado por la previsión con el horizonte publicado más corto en ese
momento (normalmente `demanda_prevista`, que ESIOS suele publicar con
menos antelación que eólica/fotovoltaica). Bug relacionado corregido
de paso en `src/model/predict.py`: el `dropna()` exigía el target
(`precio_spot`) además de las features, lo que descartaba siempre las
horas futuras (el precio real, por definición, no existe todavía para
ellas); y las columnas derivadas de indicadores reales (lags/medias
móviles) se "congelan" hacia adelante (forward-fill) más allá de la
última hora con dato real, porque no se pueden recalcular de verdad
para el futuro.

Con Docker (`Dockerfile` en la raíz). La imagen NO incluye `data/` ni
`models/` — son estado que cambia con cada ingesta/reentrenamiento, no
código, así que se montan como volúmenes en tiempo de ejecución (así no
hay que reconstruir la imagen cada vez que se reentrena):

```powershell
docker build -t forecasting-electrico .
docker run -d -p 8000:8000 `
  -v ${PWD}/data:/app/data `
  -v ${PWD}/models:/app/models `
  --name forecasting-electrico forecasting-electrico
```

> El `Dockerfile` no se ha podido verificar en este entorno de
> desarrollo (Docker Desktop no instalado), pero sí se verifica
> automáticamente en cada push a GitHub vía
> `.github/workflows/docker-build.yml`: construye la imagen y hace un
> smoke-test real de `/health` en el runner. Revisa la pestaña
> "Actions" del repo para ver el resultado.

## Automatización (job diario)

`.github/workflows/daily.yml` corre cada día a las 06:00 UTC (y también
manualmente desde la pestaña "Actions" → "daily-pipeline" → "Run workflow"):

1. **Ingesta incremental** (`scripts/ingest_incremental.py`): trae solo
   los datos nuevos de cada indicador desde el último dato ya guardado
   (una petición por indicador, no re-descarga el histórico). Si un
   indicador no tiene datos previos o lleva >30 días sin actualizar
   (p.ej. porque se perdió el estado persistido), hace backfill
   completo para ese indicador en su lugar — se autorrepara solo.
2. **Reentrena el modelo** (`scripts/train_lightgbm.py`) con los datos
   actualizados.
3. **Genera y guarda la predicción** (`scripts/predict_and_log.py`) en
   la tabla `predictions` de la bbdd, para poder comparar más tarde
   contra el precio real.
4. **Monitorización** (`scripts/monitor.py`): calidad de datos + error
   real, ver abajo.
5. Comitea `models/model_metadata.json`, `models/lightgbm_metrics.json`
   y `data/monitoring_report.json` de vuelta al repo (`[skip ci]` para
   no disparar el resto de workflows).

**Configuración necesaria** (una sola vez): añade tu token de ESIOS
como secret del repo en *Settings → Secrets and variables → Actions →
New repository secret*, nombre `ESIOS_API_KEY`. Sin esto la ingesta
incremental fallará con 401.

**Versionado del modelo**: cada vez que `save_model_artifact()`
(`src/model/artifact.py`) guarda un modelo nuevo, archiva primero el
anterior en `models/history/model_<version>.joblib` +
`model_metadata_<version>.json` — no se pierde el rastro de versiones
previas al sobrescribir `models/model.joblib`.

> **Limitación conocida y asumida a propósito**: los runners de GitHub
> Actions no tienen estado propio entre ejecuciones, y
> `electricidad.db` (~230MB) es demasiado grande para versionar en git
> sin Git LFS. Se usa `actions/cache` (con una clave que incluye el
> `run_id`, para que cada ejecución guarde un cache nuevo) para
> persistir `data/` y `models/` entre días. No es almacenamiento
> "de verdad" — GitHub puede evictar el cache (más de 7 días sin usar,
> o si se supera el límite de 10GB del repo). Por eso
> `ingest_incremental.py` está preparado para autorepararse con un
> backfill completo si detecta que el cache se perdió, en vez de
> fallar en silencio. Una mejora futura razonable sería mover el
> almacenamiento a algo persistente de verdad (un bucket, una bbdd
> gestionada) en vez de abusar de `actions/cache`.

## Monitorización

`scripts/monitor.py` (parte del job diario) revisa tres cosas y escribe
`data/monitoring_report.json`:

- **Huecos**: ¿faltan muchas horas de las últimas 72h para algún
  indicador?
- **Valores fuera de rango**: ¿hay precios/demandas fuera de un rango
  "sano" (pensado para pillar errores groseros, no validación de
  negocio estricta)?
- **Indicador obsoleto**: ¿algún indicador lleva más de 48h sin traer
  un dato nuevo (o no tiene ninguno)?
- **Error real (7 días)**: compara las predicciones guardadas en la
  tabla `predictions` contra el precio real ya conocido (tabla
  `observations`) y calcula el MAE/RMSE de los últimos 7 días. **Esto
  es la pieza más valiosa, no decorativa**: la Fase 5 ya estableció que
  el error del modelo crece de forma estructural (régimen regulatorio
  + tendencia de volatilidad) — esta métrica es lo que avisa si el
  modelo placeholder actual se degrada MÁS de lo esperable, no solo lo
  esperado.

Si algo destaca, el script imprime `::warning::...` (sintaxis de
GitHub Actions: marca un aviso visible en la UI del workflow, en
amarillo, **sin fallar el job** — un error alto es una señal a
vigilar, no necesariamente un fallo del pipeline). Si el propio job
falla (ingesta o reentrenamiento con error real), eso ya lo marca
GitHub Actions como fallo del workflow — visible en el badge de arriba
y en la pestaña "Actions".

## Fuente de datos

[API de ESIOS](https://api.esios.ree.es/) — API pública de Red Eléctrica de
España para indicadores del sistema eléctrico (precio del mercado diario,
demanda, generación por tecnología...). Requiere un token personal gratuito
en el header `x-api-key`. Nunca se hardcodea: se carga desde `.env` mediante
`python-dotenv`.

El diseño es multi-fuente desde el principio (`src/ingestion/base.py`,
clase abstracta `DataSource`): ESIOS es la primera implementación, pero el
esquema de `observations` ya incluye una columna `source`, así que añadir
MIBGAS (gas) u Open-Meteo (meteorología) más adelante no requerirá migrar
la base de datos.

## Almacenamiento

`data/electricidad.db` (SQLite, no versionado en git). Datos **horarios**,
2014 → hoy, para los 13 indicadores del catálogo: ~1.78M filas. Ver
`src/storage/db.py` para el esquema (`observations`, `indicators_catalog`,
`ingestion_log`).

10 de esos 13 indicadores (precio spot, demanda, generación T.Real) se
piden en resolución **nativa** y se promedian a hora en cliente
(`ESIOSClient.fetch_hourly_mean`), no con `time_trunc=hour` directo —
ver "Corregido (2026-07-31)" en Limitaciones conocidas para el motivo.

## Limitaciones conocidas

- Varios indicadores no tienen histórico hasta 2014: PVPC 2.0TD empieza en
  2021-06 (coincide con la reforma de tarifas), generación solar
  FV/térmica en 2015-07, y ciclo combinado + previsiones D+1 eólica/FV en
  2019-01. Ver `cobertura_desde` en `data/esios_indicators_catalog.json`.
- La ingesta trocea las peticiones en ventanas mensuales, no trimestrales:
  con ventanas de 3 meses, el indicador de precio spot (600) en 2025 supera
  los 60s de timeout (~3.7MB de respuesta por mes). No afecta a la
  granularidad de los datos, que sigue siendo horaria.
- Varios indicadores devuelven varios ámbitos geográficos por hora (p.ej.
  el precio spot trae también Portugal/Francia/Alemania/Bélgica/Países
  Bajos; el PVPC trae Canarias/Baleares/Ceuta/Melilla además de
  Península). `geo_id_objetivo` en el catálogo fija cuál se usa; el resto
  se descarta al pivotar a formato ancho (`src/features/load.py`).
- **Decisión tomada (Fase 5)**: `pvpc` se excluye del todo del dataset
  de features (`DEFAULT_EXCLUDE_COLUMNS` en `src/features/build.py`),
  no solo del lag 0 — es casi una derivada regulatoria del propio
  precio spot (riesgo de leakage conceptual) y su cobertura desde
  2021-06 habría recortado la ventana de entrenamiento a solo la
  crisis energética 2021-2022. Aun así, la ventana de features usable
  hoy es **2019-01 → hoy** (~62.300 filas), no el histórico completo
  desde 2014: `gen_ciclo_combinado`, `prevision_eolica` y
  `prevision_fv` tampoco tienen datos antes de 2019-01. El **baseline**
  sí usa el histórico completo desde 2014 (solo necesita `precio_spot`).
- **El error del baseline naive se ha multiplicado por ~7 desde 2020**:
  MAE ~5 EUR/MWh en 2014-2020, pero 27.7 en 2022, 36.6 en 2025 y 66.8
  en 2026 (ver `models/baseline_metrics.json`, generado por
  `python -m scripts.train_baseline`). El mercado se ha vuelto mucho
  más volátil — cualquier modelo hay que evaluarlo con esto en mente,
  y probablemente conviene evaluar/entrenar por separado el periodo
  reciente frente al histórico "tranquilo" 2014-2020.
- **El salto de error SÍ coincide con un cambio de régimen regulatorio
  real**, no es solo volatilidad acumulada: la std del precio en
  `post_tope` (desde 2024-01-01, fin del tope al gas) es ~2.8x la de
  `normal`. Ver `src/model/regimes.py`, `evaluate_by_regime()` en
  `src/model/evaluate.py`, y la sección de régimen en
  `notebooks/01_eda.ipynb`.
- **Corregido (2026-07-31): ESIOS suma en vez de promediar cuando se pide
  `time_trunc=hour` sobre un indicador con resolución nativa más fina —
  bug real de la fuente, no de nuestro pipeline, pero que estuvo
  corrompiendo tanto features como el target.** Dos casos, encontrados
  al investigar por qué la demanda no cuadraba con la escala real de
  España (aviso del usuario) y por qué el modelo perdía cada vez peor
  contra el baseline en 2025-2026:
  - **Demanda y generación T.Real** (9 indicadores) tienen resolución
    nativa de 5 minutos. Pedir `time_trunc=hour` no promedia las ~12
    muestras de esa hora: las suma. Una demanda media real de ~21.500 MW
    se guardaba como ~250.000 (~6-10x según cuántas muestras hubiera esa
    hora — de ahí que en la investigación anterior pareciera "solo una
    escala distinta, consistente"; en realidad el multiplicador variaba
    con el número de muestras nativas disponibles, que a su vez cambió
    con los años, imitando una falsa tendencia temporal).
  - **El precio spot (indicador 600, el TARGET a predecir)** pasó de
    resolución nativa horaria a nativa de 15 minutos en algún punto
    entre 2024-06 y 2025-01 — el cambio real de mercado europeo a
    "15-minute market time units". Desde entonces, `time_trunc=hour`
    sumaba las 4 muestras de 15 min en vez de promediarlas: un precio
    real de ~105 €/MWh se guardaba como ~422 €/MWh. Esto producía un
    salto artificial de ~4x en el precio justo a partir de esa fecha,
    que en un primer análisis parecía un cambio estructural de mercado
    sin precedente — en realidad era este bug.

  **Fix**: `ESIOSClient.fetch_hourly_mean()` (`src/ingestion/esios_client.py`)
  pide resolución nativa (sin fijar `time_trunc`, sea la que sea en cada
  momento) y promedia a hora en cliente, por geo_id. Se aplica a los 10
  indicadores afectados (ver `promediar_desde_nativo` en
  `data/esios_indicators_catalog.json`). Todo el histórico de estos 10
  indicadores se ha vuelto a descargar desde 2014/cobertura_desde con el
  fix aplicado (no solo hacia adelante). Umbrales de
  `src/monitoring/data_quality.py` revertidos a escala real de MW
  (demanda hasta 60.000, generación hasta 40.000).

- **El modelo ahora supera al baseline** (MAE 16.8 vs 18.2 €/MWh en el
  holdout `2025-08-01 → hoy`, antes 128 vs 63 con los datos corrompidos).
  El diagnóstico anterior ("los árboles no pueden extrapolar más allá
  del precio máximo visto en entrenamiento") seguía siendo cierto en
  teoría pero **no era la causa principal del mal resultado**: la mayor
  parte del salto de error en 2025-2026 era el bug de agregación del
  precio de arriba, que fabricaba un salto de precio de ~4x sin
  precedente real que ningún modelo podía haber anticipado. Se mantiene
  igualmente `src/model/detrend.py` (tendencia lineal sobre
  `dias_desde_referencia` + LightGBM sobre el residuo) porque la
  limitación de extrapolación de los árboles es real y documentable
  aunque ya no sea el cuello de botella dominante — más robusto de cara
  a que el precio siga una tendencia genuina en el futuro.

- **Corregido (2026-07-31, tras revisar el dashboard ya publicado): dos
  restos del bug de agregación de arriba seguían contaminando la
  visualización aunque los datos ya estaban arreglados.**
  1. `models/baseline_metrics.json` no se había regenerado tras el fix
     del precio — sus cifras de 2025/2026 venían del precio ~4x
     inflado (MAE baseline 2026 mostraba ~67 en vez de ~17). El gráfico
     "MAE por año" del dashboard lo lee directo del fichero, así que
     comparaba el modelo (ya corregido) contra un baseline todavía
     corrompido. Se regeneró con `python -m scripts.train_baseline`.
  2. La tabla `predictions` conservaba 24 filas de un `model_version`
     anterior al fix (entrenado con datos corrompidos), con predicciones
     de hasta 847 €/MWh para horas ya pasadas — el gráfico de precio
     las mostraba tal cual junto a las del modelo nuevo, porque
     `load_all_predictions()` (`scripts/export_dashboard_data.py`) no
     distingue `model_version`, solo deduplica por hora quedándose con
     la más reciente. Se borraron esas filas directamente de la bbdd
     (no había nada que preservar: solo 2 ejecuciones del cron diario
     desde que existe la tabla). El diseño de "no distinguir
     model_version" se mantiene tal cual para el futuro — es correcto
     una vez el pipeline es estable, el problema era solo esta
     contaminación puntual de la migración.
