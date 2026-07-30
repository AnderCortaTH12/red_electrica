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
- [ ] Fase 1 — Catálogo de indicadores
- [ ] Fase 2 — Cliente robusto de la API
- [ ] Fase 3 — Ingesta histórica a SQLite
- [ ] Fase 4 — Exploración y features
- [ ] Fase 5 — Modelo (baseline + LightGBM)
- [ ] Fase 6 — Servir el modelo (FastAPI + Docker)
- [ ] Fase 7 — Automatización y monitorización

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

## Limitaciones conocidas

Se irán documentando aquí a medida que aparezcan (huecos de datos, cambios
de hora, indicadores discontinuados, etc.).
