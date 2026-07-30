# Sistema de predicción de precio eléctrico en producción — Guía completa

> Proyecto de portfolio para demostrar que sabes **productivizar** machine learning, no solo entrenar modelos en un notebook. Pensado para alguien que sabe Python y ML pero nunca ha montado un sistema que corra solo.

---

## 1. La idea en una frase

Un servicio que, **cada día y sin que tú toques nada**, descarga los datos eléctricos de España, reentrena/actualiza un modelo, publica la predicción del precio de las próximas 24 horas y **se vigila a sí mismo** comparando lo que predijo ayer con lo que pasó de verdad.

Lo interesante no es el modelo. Es que el modelo **vive**. En una entrevista para un puesto tipo QuantumBlack, poder decir *"lleva 3 meses corriendo solo y su error real fuera de muestra es X"* vale más que cualquier métrica de un backtest hecho una vez.

### Qué demuestra (mapeado a la oferta)

| Frase de la oferta | Dónde lo cubres en el proyecto |
|---|---|
| *applying ML to large, real-world datasets* | Años de datos horarios reales de REE, sucios de verdad |
| *translate business problems into analytical challenges* | "predecir el precio" → problema de forecasting con features y métricas |
| *build models... evaluated with relevant metrics* | Evaluación continua, no puntual |
| *lead and drive model development independently* | Lo haces tú solo, de principio a fin |
| *real-world application of ML methods* | Está en producción, no en un notebook |
| Sector *energy* | Es literalmente el sector eléctrico |

---

## 2. Arquitectura del sistema

No te agobies, son 6 piezas y las vas a construir de una en una:

```
   ┌─────────────┐     ┌──────────────┐     ┌───────────────┐
   │  INGESTA    │────▶│    ALMACÉN   │────▶│   FEATURES    │
   │ (ESIOS +    │     │  (SQLite/    │     │ (calendario,  │
   │  meteo)     │     │   DuckDB)    │     │  lags, meteo) │
   └─────────────┘     └──────────────┘     └───────┬───────┘
        ▲                                            │
        │ cada día                                   ▼
   ┌────┴────────┐                          ┌───────────────┐
   │ ORQUESTADOR │                          │ ENTRENAMIENTO │
   │ (GitHub     │                          │  (+ MLflow)   │
   │  Actions    │                          └───────┬───────┘
   │  cron)      │                                  │
   └────┬────────┘                                  ▼
        │                                   ┌───────────────┐
        │                                   │    SERVING    │
        │                                   │ (FastAPI +    │
        │                                   │   Docker)     │
        │                                   └───────┬───────┘
        │                                           │ predicción 24h
        ▼                                           ▼
   ┌──────────────────────────────────────────────────────┐
   │  MONITORIZACIÓN: predicción de ayer vs. real de hoy   │
   │  → error en el tiempo, drift, alertas (Evidently)     │
   └──────────────────────────────────────────────────────┘
```

---

## 3. Stack tecnológico y por qué cada pieza

Elijo herramientas que **enseñan el concepto sin distraerte con infraestructura pesada**. Todo gratis.

- **Python** — ya lo dominas.
- **Almacenamiento: SQLite** para empezar (un fichero, cero configuración; ya lo has usado en Polymarket). Si quieres subir de nivel luego, DuckDB (analítica más rápida) o Postgres. Para portfolio, SQLite es perfectamente honesto.
- **Modelo: LightGBM** — gradient boosting, el rey de datos tabulares con lags y calendario. Rápido, no necesitas GPU. *Antes*, un **baseline naïve** (ver sección 4).
- **Experimentos: MLflow** — registra cada entrenamiento (parámetros, métricas, versión del modelo). Es el "git para modelos". Aprendes qué es el *model registry* y el versionado de modelos.
- **API: FastAPI** — expones el modelo como un endpoint REST. Aprendes qué es servir un modelo detrás de una API.
- **Contenedor: Docker** — empaquetas todo para que corra igual en tu máquina y en cualquier servidor. Es *el* concepto de producción que más echa de menos la gente que viene de notebooks.
- **Orquestación/scheduling: GitHub Actions (cron)** — ejecuta tu job cada día **sin necesidad de un servidor encendido**. Coste cero. Alternativa si quieres tocar cloud: una instancia EC2 del *free tier* de AWS con `cron` (refuerza tu certificación de Cloud Practitioner).
- **Monitorización: Evidently** — librería open-source que genera informes de *data drift* y de rendimiento del modelo en HTML. Te enseña los conceptos de monitorización sin montarte nada complejo.
- **Tests + CI: pytest + GitHub Actions** — tests automáticos que corren en cada push.
- **Meteo: Open-Meteo** (sin token, gratis) y/o **AEMET OpenData** (token gratis). La temperatura, el viento y la irradiancia solar mueven demanda y precio.

---

## 4. Decisiones de datos y modelado (léelo dos veces: aquí es donde la gente se equivoca)

### Qué predecir

El **precio horario del mercado diario español** (mercado *spot*) para el día siguiente: 24 valores, uno por hora. Es volátil e interesante. (Alternativa más fácil si te atascas: la **demanda**, que es más suave y predecible.)

### Los datos que necesitas de ESIOS

- Precio del mercado diario (€/MWh, horario)
- Demanda real (MW, horario)
- Generación por tecnología (eólica, solar, nuclear, hidráulica, ciclo combinado…)

Y de meteo: temperatura, viento e irradiancia por zonas.

### Las 4 trampas que tienes que evitar

1. **Fuga de datos temporal (data leakage).** Cuando predices el día D, solo puedes usar información disponible el día D-1. Nunca metas como feature algo que "ya sabe el futuro". El error clásico: usar la meteo **real** de mañana como feature. En producción no la tendrás; tendrás la **previsión** meteorológica. Solución honesta: usa *forecast* de meteo, y **documenta** la diferencia. Este matiz, contado bien, te hace parecer sénior.

2. **Split temporal, nunca aleatorio.** Es una serie temporal. Entrenas con el pasado, validas con el futuro (**walk-forward / backtesting**). Si haces `train_test_split` aleatorio, estás haciendo trampa y tu error será mentira.

3. **Precios negativos y cero.** En el mercado eléctrico español el precio puede ser 0 o negativo (exceso de renovables). Eso **rompe el MAPE** (divides por cero). Usa **MAE** como métrica principal, y añade RMSE. El MAPE, si acaso, como secundario y con cuidado.

4. **Ten un baseline y ten la humildad de compararte con él.** El baseline *seasonal naïve* — "mañana a las 15h costará lo mismo que hoy a las 15h" (o lo mismo que el mismo día la semana pasada) — es sorprendentemente bueno. **Tu modelo tiene que batirlo o no vale nada.** Poder decir *"mi modelo mejora el baseline naïve un 18% en MAE"* es una frase de entrevista mucho más creíble que un número absoluto suelto.

### Features típicas

- **Calendario:** hora, día de la semana, mes, festivo (paquete `holidays` de Python para festivos españoles), findes.
- **Lags:** precio/demanda de hace 24h, 48h, 168h (una semana).
- **Meteo:** temperatura, viento, sol (previsión para el día objetivo).
- **Generación renovable prevista** si te animas.

---

## 5. Plan por fases

Filosofía: **primero un hilo fino de punta a punta que funcione, luego engordas cada capa.** No construyas la ingesta perfecta antes de haber entrenado tu primer modelo. Cada fase es aproximadamente "un fin de semana", pero ve a tu ritmo.

### Fase 0 — Cimientos (medio día)

**Qué construyes:** el esqueleto del repo y tu entorno.

- Crea el repo en GitHub, entorno virtual (`venv` o `conda`), `requirements.txt`.
- Solicita el **token de ESIOS** (formulario "Personal token request" o correo a consultasios@ree.es). Tarda uno o pocos días — pídelo **ahora**, hoy, antes de nada.
- Guarda el token como variable de entorno / GitHub Secret, **nunca** en el código.
- Estructura de carpetas (ver sección 6).

**Qué aprendes:** higiene de proyecto, gestión de secretos.
**Hecho cuando:** el repo existe y puedes hacer `import` de tus módulos vacíos.

---

### Fase 1 — Datos fluyendo (1 fin de semana)

**Qué construyes:** un script que descarga datos de ESIOS + meteo, los **valida** y los guarda en SQLite.

- Primera llamada a la API (ver esqueleto en sección 7). Descárgate primero un histórico largo de golpe (años) para tener con qué entrenar.
- **Validación de datos:** ¿faltan horas? ¿hay nulos? ¿valores absurdos (demanda negativa)? Si algo falla, que el script avise, no que guarde basura en silencio. Esto es lo que separa un pipeline de un `pd.read_csv`.
- Guarda en tablas SQLite con una clave temporal limpia (timestamp en UTC + zona Europe/Madrid; ojo con los cambios de hora).

**Qué aprendes:** pipelines de ingesta, validación de datos, el infierno de las zonas horarias (bienvenido a la ingeniería de datos real).
**Hecho cuando:** tienes años de datos horarios limpios en tu base de datos y un script que puedes volver a ejecutar sin duplicar filas (idempotencia).

---

### Fase 2 — Modelo baseline y honesto (1 fin de semana)

**Qué construyes:** el baseline naïve, luego LightGBM, evaluados con walk-forward.

- Implementa el **baseline seasonal naïve** primero. Mide su MAE. Ese es el número a batir.
- Ingeniería de features (sección 4).
- Entrena LightGBM. Evalúa con **backtesting walk-forward**, no con split aleatorio.
- Compara contra el baseline. Si no lo bates, no pasa nada: iteras features. (Esto *es* el trabajo real.)

**Qué aprendes:** evaluación honesta de series temporales, la disciplina de tener un baseline.
**Hecho cuando:** tienes un número creíble del tipo *"MAE de X €/MWh, un Y% mejor que el naïve"*.

---

### Fase 3 — Servir el modelo (1 fin de semana)

**Qué construyes:** el modelo detrás de una API, dentro de un contenedor.

- **FastAPI:** un endpoint `GET /predict` que devuelve las 24 predicciones de mañana en JSON. Y un `GET /health` (buena práctica).
- Guarda el modelo entrenado en disco (`joblib`) y que la API lo cargue al arrancar.
- **Docker:** escribe un `Dockerfile`, construye la imagen, arráncala. Cuando veas tu API respondiendo desde dentro de un contenedor, has cruzado la línea de "notebook" a "producción".

**Qué aprendes:** servir modelos, REST, contenedores. **Esta es la fase que más te va a diferenciar.**
**Hecho cuando:** `docker run` levanta tu API y `curl localhost:8000/predict` devuelve la predicción de mañana.

---

### Fase 4 — Que corra solo (1 fin de semana)

**Qué construyes:** el orquestador que ejecuta el ciclo diario sin ti.

- Un **GitHub Actions con `schedule` (cron)** que cada mañana: descarga datos nuevos → genera la predicción del día → guarda esa predicción (en la BD o en un fichero commiteado al repo).
- El truco elegante: **no necesitas servidor**. GitHub te ejecuta el job gratis.
- Alternativa "quiero tocar cloud": instancia EC2 *free tier* + `cron`. Más realista, más curro. Tú decides.

**Qué aprendes:** orquestación, scheduling, ejecución desatendida.
**Hecho cuando:** te despiertas, no has tocado nada, y hay una predicción nueva de hoy esperándote.

---

### Fase 5 — La joya: monitorización (1 fin de semana)

**Qué construyes:** el sistema que compara predicción vs. realidad y se vigila.

- Cada día, cuando llega el precio **real**, guárdalo junto a la predicción que hiciste **ayer** para ese día. Ahora tienes error real fuera de muestra, acumulándose.
- Traza **MAE/RMSE en el tiempo**. Si sube, algo va mal.
- **Detección de drift con Evidently:** ¿han cambiado las distribuciones de tus features respecto a cuando entrenaste? (Un invierno frío, una crisis de gas… el mundo cambia y tu modelo envejece.) Evidently te genera informes HTML preciosos.
- **Alerta simple:** si el MAE de los últimos 7 días supera un umbral, que te mande un aviso (un email, un mensaje). Esto es *observabilidad*, y casi nadie lo tiene en su portfolio.

**Qué aprendes:** monitorización de modelos, drift, degradación, alertas. **Este es el diferenciador nº1 de todo el proyecto.**
**Hecho cuando:** tienes una gráfica de "error real a lo largo del tiempo" que puedes enseñar en una entrevista.

---

### Fase 6 — Pulido y venta (repartido)

**Qué construyes:** lo que convierte un proyecto en un proyecto que impresiona.

- **MLflow:** cada reentrenamiento queda registrado y versionado. Aprendes *model registry*.
- **Tests con pytest + CI:** GitHub Actions corre los tests en cada push. Aprendes CI/CD.
- **README que vende:** el diagrama de arriba, cómo arrancarlo, la gráfica de error real, y una sección honesta de "limitaciones y siguientes pasos".
- **Dashboard opcional:** los informes HTML de Evidently servidos con **GitHub Pages** (estático, gratis, elegante). Si quieres algo interactivo, aquí *sí* encaja un dashboard, aunque no lo destaques en el CV.

**Hecho cuando:** un desconocido puede clonar el repo, leer el README y entender qué hace y por qué es bueno en 2 minutos.

---

## 6. Estructura del repositorio

```
electricity-forecast/
├── README.md
├── requirements.txt
├── Dockerfile
├── .github/
│   └── workflows/
│       ├── daily.yml        # cron: ingesta + predicción diaria
│       └── ci.yml           # tests en cada push
├── src/
│   ├── ingestion/
│   │   ├── esios.py         # cliente de la API de ESIOS
│   │   ├── weather.py       # cliente meteo
│   │   └── validate.py      # validaciones de calidad de datos
│   ├── storage/
│   │   └── db.py            # lectura/escritura en SQLite
│   ├── features/
│   │   └── build.py         # calendario, lags, meteo
│   ├── model/
│   │   ├── baseline.py      # seasonal naïve
│   │   ├── train.py         # LightGBM + MLflow + walk-forward
│   │   └── predict.py
│   ├── serving/
│   │   └── api.py           # FastAPI
│   └── monitoring/
│       └── monitor.py       # predicción vs real, Evidently, alertas
├── tests/
│   └── test_*.py
└── data/
    └── electricity.db       # (o en .gitignore si pesa)
```

---

## 7. Esqueletos de código clave

Solo los puntos donde la gente se atasca. El resto lo escribes tú (es parte de aprender).

**Primera llamada a ESIOS** (`src/ingestion/esios.py`):

```python
import os
import requests

TOKEN = os.environ["ESIOS_TOKEN"]  # nunca hardcodeado

def get_indicator(indicator_id: int, start: str, end: str):
    url = f"https://api.esios.ree.es/indicators/{indicator_id}"
    headers = {
        "x-api-key": TOKEN,
        "Accept": "application/json",
    }
    params = {
        "start_date": start,   # "2020-01-01T00:00:00"
        "end_date": end,
        "time_trunc": "hour",
    }
    r = requests.get(url, headers=headers, params=params, timeout=30)
    r.raise_for_status()
    return r.json()["indicator"]["values"]
```

> Los `indicator_id` los sacas de la lista de indicadores de ESIOS (precio del mercado diario, demanda real, etc.). Empieza descargando esa lista una vez y anota los IDs que te interesan.

**Validación mínima** (`src/ingestion/validate.py`):

```python
def validate(df):
    problems = []
    expected_hours = 24
    for day, group in df.groupby(df.timestamp.dt.date):
        if len(group) != expected_hours:
            problems.append(f"{day}: {len(group)} horas, esperadas {expected_hours}")
    if df.value.isna().any():
        problems.append(f"{df.value.isna().sum()} valores nulos")
    if problems:
        raise ValueError("Datos inválidos:\n" + "\n".join(problems))
    return df
```

**Dockerfile** (esqueleto):

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ ./src/
COPY models/ ./models/
CMD ["uvicorn", "src.serving.api:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Cron de GitHub Actions** (`.github/workflows/daily.yml`):

```yaml
name: daily-forecast
on:
  schedule:
    - cron: "0 6 * * *"   # cada día a las 06:00 UTC
  workflow_dispatch:       # y botón para lanzarlo a mano
jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -r requirements.txt
      - name: Ingesta + predicción
        env:
          ESIOS_TOKEN: ${{ secrets.ESIOS_TOKEN }}
        run: python -m src.pipeline.daily
```

---

## 8. Cómo presentarlo (esto es lo que te da el puesto)

El proyecto vale por cómo lo cuentas. Prepara **tres versiones** de la historia:

- **Una frase (CV):** *"Sistema de forecasting de precio eléctrico en producción continua: ingesta automatizada de datos de REE, modelo LightGBM servido vía API en Docker, con monitorización diaria de error real y detección de drift (Python, SQL, FastAPI, MLflow)."*
- **Un minuto (entrevista):** el problema de negocio (por qué importa predecir el precio: comercializadoras, industria electrointensiva, baterías) → la arquitectura → **la parte de monitorización** → una limitación honesta que descubriste.
- **Diez minutos (technical deep-dive):** las 4 trampas de la sección 4. Que sepas explicar por qué usas walk-forward, por qué MAE y no MAPE, y el matiz de la meteo prevista vs. real. **Eso** es lo que buscan.

Regla de oro: **habla de las limitaciones tú primero.** *"El modelo se degrada cuando hay un shock de precio del gas, y por eso monté el drift detection"* suena diez veces mejor que fingir que todo es perfecto. Me pediste no venderte como el mesías; esta es la forma correcta de no hacerlo y aun así impresionar.

---

## 9. Coste y siguientes pasos opcionales

**Coste: 0 €.** ESIOS gratis, Open-Meteo gratis, GitHub Actions gratis, SQLite gratis. Solo pagarías si te empeñas en una instancia cloud siempre encendida (y aun así, *free tier* de AWS).

Si quieres seguir subiendo de nivel después:

- Intervalos de predicción (cuantiles), no solo el valor central — muy valorado en energía.
- Comparar tu modelo con uno de deep learning para series (por curiosidad, no porque haga falta).
- Migrar de SQLite a Postgres y el scheduling a Airflow o Prefect (orquestadores "de verdad").
- Desplegar en cloud de verdad y añadir *infrastructure as code*.

Pero **no empieces por aquí.** Empieza por la Fase 0 hoy, pide el token, y ten el hilo fino de punta a punta funcionando antes de adornar nada. El valor del proyecto crece con cada día que lleva corriendo solo — así que cuanto antes arranque, mejor.
