"""Validación determinista de un periodo ya normalizado. Esto es lo
que hace que el proyecto sea fiable (decisión 1.2 del diseño): el LLM
puede leer mal una cifra, pero estas comprobaciones cruzadas lo pillan
antes de que llegue a `data/gas.csv`.

Si `validar_periodo` devuelve algún error, el periodo entero no se
escribe en el CSV -- o todo o nada, para no dejar el dataset a medias.
Los avisos (CCAA que no cuadran con el nacional, etc.) no bloquean la
escritura: se imprimen como `::warning::` y siguen adelante.
"""

from __future__ import annotations

from dataclasses import dataclass, field

TOLERANCIA_SUMA_PCT = 0.5  # cuadres exigidos (misma fuente o cruce de fuentes)
TOLERANCIA_CCAA_PCT = 5.0  # aviso, no error: Enagás no cubre todas las CCAA

# Rangos "sanos" en GWh (o la unidad canónica de la métrica) para pillar
# errores groseros de lectura del PDF -- no es validación de negocio
# estricta, deja margen amplio por encima/debajo de lo observado en
# 2026. Se amplía según se procesen más meses y aparezcan valores
# legítimos fuera de este rango inicial.
RANGOS_SANOS: dict[str, tuple[float, float]] = {
    "total_salidas": (5_000, 60_000),
    "demanda_nacional": (5_000, 55_000),
    "demanda_convencional": (5_000, 40_000),
    "demanda_sector_electrico": (0, 25_000),
    "demanda_internacional": (0, 15_000),
    "salidas_conexiones_internacionales": (-5_000, 15_000),
    "cargas_buques": (0, 8_000),
    # Ensanchado tras backfill de enero-2026 (mes de mayor demanda por
    # calefacción del año, ~1.8x junio): dc_pymes/industrial/cisternas
    # escalan con la demanda convencional total, que en enero casi
    # dobla la de junio.
    "demanda_dc_pymes": (0, 20_000),
    "demanda_industrial": (0, 30_000),
    "demanda_cisternas": (0, 2_000),
    # Ensanchado tras backfill de enero-2026 (mes de mayor demanda por
    # calefacción del año): Cataluña llegó a 5.159 GWh de convencional,
    # por encima del límite inicial calibrado sobre junio.
    "demanda_ccaa_convencional": (0, 6_500),
    "demanda_ccaa_sector_electrico": (0, 6_000),
    "demanda_ccaa_cisternas": (0, 1_200),
    "aprovisionamiento_gn": (0, 20_000),
    "aprovisionamiento_gnl": (0, 20_000),
    "conexion_internacional_saldo": (-15_000, 15_000),
    "planta_descargas_buques": (0, 10_000),
    "planta_n_buques_descargados": (0, 30),
    "planta_cargas_buques": (0, 5_000),
    "planta_carga_cisternas": (0, 500),
    "generacion_electrica": (0, 30_000),
    "destino_cargas_pct": (0, 100),
    "biometano_transporte": (0, 500),
    "biometano_distribucion": (0, 500),
    "tvb_capacidad_regasificacion_total": (0, 100_000),
    "tvb_capacidad_regasificacion_contratada": (0, 100_000),
    "tvb_capacidad_regasificacion_disponible": (0, 100_000),
    "tvb_regasificacion_comercial": (0, 50_000),
    "correccion_laboralidad": (-50, 50),
    "correccion_temperatura": (-50, 50),
    "demanda_convencional_corregida": (-50, 50),
    "delta_temperatura": (-10, 10),
    "pct_total_gn": (0, 100),
    "pct_total_gnl": (0, 100),
}

# Comprobaciones de suma: (nombre, métrica total, [métricas parte]).
# Todas se validan para agregacion="mes" -- es la que se puede cruzar
# con más confianza; acumulado_anual y tam se dejan para una iteración
# futura si hace falta (ver limitación en el README).
COMPROBACIONES_SUMA = [
    ("total_salidas = nacional + internacional", "total_salidas", ["demanda_nacional", "demanda_internacional"]),
    (
        "demanda_nacional = convencional + sector_electrico",
        "demanda_nacional",
        ["demanda_convencional", "demanda_sector_electrico"],
    ),
    (
        "demanda_convencional = dc_pymes + industrial + cisternas (cruce Boletín/Progreso)",
        "demanda_convencional",
        ["demanda_dc_pymes", "demanda_industrial", "demanda_cisternas"],
    ),
    (
        "demanda_internacional = conexiones_internacionales + cargas_buques",
        "demanda_internacional",
        ["salidas_conexiones_internacionales", "cargas_buques"],
    ),
]

# CCAA: se avisa si no cuadra, nunca se falla (ver nota en el catálogo).
COMPROBACIONES_CCAA = [
    ("demanda_ccaa_convencional", "demanda_convencional"),
    ("demanda_ccaa_sector_electrico", "demanda_sector_electrico"),
    ("demanda_ccaa_cisternas", "demanda_cisternas"),
]


@dataclass
class ResultadoValidacion:
    errores: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    @property
    def es_valido(self) -> bool:
        return not self.errores


def _aproximadamente_igual(a: float, b: float, tolerancia_pct: float) -> bool:
    if b == 0:
        return abs(a - b) < 1e-6
    return abs(a - b) / abs(b) * 100 <= tolerancia_pct


def _indexar_filas(filas: list[dict]) -> dict[tuple[str, str, str], float]:
    """(metrica_id, dimension, agregacion) -> valor. `dimension` es ""
    para las métricas escalares (así se guarda en el CSV)."""
    return {(f["metrica_id"], f.get("dimension") or "", f["agregacion"]): f["valor"] for f in filas}


def validar_periodo(filas: list[dict], catalogo: list[dict]) -> ResultadoValidacion:
    resultado = ResultadoValidacion()
    idx = _indexar_filas(filas)

    for nombre, total_id, partes_ids in COMPROBACIONES_SUMA:
        total = idx.get((total_id, "", "mes"))
        partes = [idx.get((pid, "", "mes")) for pid in partes_ids]
        if total is None or any(p is None for p in partes):
            faltantes = [pid for pid, p in zip([total_id, *partes_ids], [total, *partes]) if p is None]
            resultado.errores.append(
                f"{nombre}: no se puede validar, faltan valores para {faltantes}"
            )
            continue
        suma = sum(partes)
        if not _aproximadamente_igual(suma, total, TOLERANCIA_SUMA_PCT):
            resultado.errores.append(
                f"{nombre}: {total_id}={total:g} pero suma de partes={suma:g} "
                f"(diferencia {abs(suma - total):g}, tolerancia {TOLERANCIA_SUMA_PCT}%)"
            )

    for m in catalogo:
        if m["obligatoria"] and idx.get((m["metrica_id"], "", "mes")) is None:
            resultado.errores.append(f"Métrica obligatoria ausente: {m['metrica_id']} (agregacion=mes)")

    for f in filas:
        # Los rangos están calibrados sobre la escala mensual. acumulado_anual
        # (hasta 12x un mes) y tam (12 meses) se salen de esa escala por
        # diseño, no por un error de lectura -- no tiene sentido validarlos
        # contra el mismo rango.
        if f["agregacion"] != "mes":
            continue
        rango = RANGOS_SANOS.get(f["metrica_id"])
        if rango is None or f["valor"] is None:
            continue
        lo, hi = rango
        if not (lo <= f["valor"] <= hi):
            resultado.errores.append(
                f"Valor fuera de rango sano: {f['metrica_id']}"
                f"{' [' + f['dimension'] + ']' if f.get('dimension') else ''} "
                f"= {f['valor']:g} {f.get('unidad')}, esperado [{lo}, {hi}] "
                f"(página {f.get('pagina')})"
            )

    for metrica_ccaa, metrica_nacional in COMPROBACIONES_CCAA:
        valores_ccaa = [
            v for (mid, dim, agg), v in idx.items() if mid == metrica_ccaa and agg == "mes" and dim and v is not None
        ]
        nacional = idx.get((metrica_nacional, "", "mes"))
        if valores_ccaa and nacional is not None:
            suma_ccaa = sum(valores_ccaa)
            if not _aproximadamente_igual(suma_ccaa, nacional, TOLERANCIA_CCAA_PCT):
                resultado.avisos.append(
                    f"{metrica_ccaa}: suma CCAA={suma_ccaa:g} no cuadra con {metrica_nacional}={nacional:g} "
                    "(esperado: Enagás no incluye todas las CCAA ni todos los consumos)"
                )

    return resultado
