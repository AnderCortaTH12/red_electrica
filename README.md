# Forecasting Eléctrico

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
- [ ] Fase 5 — Modelo (baseline + LightGBM)
- [ ] Fase 6 — Servir el modelo (FastAPI + Docker)
- [ ] Fase 7 — Automatización y monitorización

### Diseño planeado: dashboard público (Fase 6/7)

Aún no implementado; documentado aquí para no perder el diseño acordado.

Página estática en GitHub Pages, servida desde **`main:/docs`** (carpeta
`docs/` en la rama `main`, no una rama `gh-pages` separada — menos piezas
que gestionar en un proyecto en solitario), en
`https://andercortath12.github.io/red_electrica/`.

Flujo diario (GitHub Actions cron, ver Fase 7):
1. El Action ejecuta el pipeline: ingesta del día → predicción 24h →
   métricas de error reciente (MAE 7 días, comparativa vs demanda
   prevista oficial de ESIOS).
2. Exporta el resultado a un **JSON pequeño y estable** en `docs/` (no la
   base de datos entera): precio real reciente, predicción, métricas.
3. `docs/index.html` (HTML + Chart.js vía CDN, sin build tool) lee ese
   JSON y pinta: precio real vs. predicho (últimas 48-72h), predicción
   próximas 24h, MAE 7 días, generación por tecnología del día, y fecha
   de última actualización.
4. El propio Action hace commit y push de `docs/` (HTML + JSON) a `main`
   tras generarlos.

## Estructura

```
Forecasting-Electrico/
├── src/            # código fuente (cliente API, storage, features, modelo...)
├── scripts/        # scripts ejecutables puntuales (verificación, ingesta histórica...)
├── data/           # bbdd SQLite y datos crudos (ignorado por git, se regenera)
├── notebooks/       # notebooks de exploración (EDA, análisis de resultados)
├── tests/          # tests con pytest
├── requirements.txt
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

`data/electricidad.db` (SQLite, no versionado en git). Datos **horarios**
(`time_trunc=hour`), 2014 → hoy, para los 13 indicadores del catálogo:
~1.78M filas. Ver `src/storage/db.py` para el esquema (`observations`,
`indicators_catalog`, `ingestion_log`).

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
- **Primer intento de LightGBM: pierde contra el baseline con claridad**
  (MAE 131.97 vs 63.26 en el holdout, entrenado solo sobre el régimen
  `post_tope`). Causa raíz identificada: los modelos de árboles no
  pueden extrapolar más allá del rango del target visto en
  entrenamiento (precio máximo en train: 240 EUR/MWh; en test llega a
  1020). Las predicciones quedan ancladas cerca de ese techo mientras
  el precio real sigue subiendo. No es un problema de la feature de
  tendencia (se probó sin ella, mismo resultado) — es una limitación
  estructural de los árboles de decisión ante una serie con tendencia
  fuerte. Pendiente de decidir cómo abordarlo (predecir un residual/
  ratio en vez del precio absoluto, reentrenamiento periódico con
  ventana móvil, o un modelo que sí extrapole). Ver
  `models/lightgbm_metrics.json`.
