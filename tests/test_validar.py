"""Tests de src/extraccion/validar.py: un caso que cuadra y uno por
cada regla que falla."""

from __future__ import annotations

from src.extraccion.validar import validar_periodo

CATALOGO_MINIMO = [
    {"metrica_id": "total_salidas", "obligatoria": True},
    {"metrica_id": "demanda_nacional", "obligatoria": True},
    {"metrica_id": "demanda_convencional", "obligatoria": True},
    {"metrica_id": "demanda_dc_pymes", "obligatoria": True},
    {"metrica_id": "demanda_industrial", "obligatoria": True},
    {"metrica_id": "demanda_cisternas", "obligatoria": True},
    {"metrica_id": "demanda_sector_electrico", "obligatoria": True},
    {"metrica_id": "demanda_internacional", "obligatoria": True},
    {"metrica_id": "salidas_conexiones_internacionales", "obligatoria": True},
    {"metrica_id": "cargas_buques", "obligatoria": True},
]


def _fila(metrica_id, valor, agregacion="mes", dimension="", unidad="GWh"):
    return {
        "periodo": "2026-06",
        "metrica_id": metrica_id,
        "dimension": dimension,
        "agregacion": agregacion,
        "valor": valor,
        "unidad": unidad,
        "var_pct_interanual": None,
        "fuente_doc": "boletin",
        "pagina": 1,
    }


def _filas_validas() -> list[dict]:
    """Un periodo que cuadra en todas las reglas (cifras reales de
    2026-06, ver data/gas.csv)."""
    return [
        _fila("total_salidas", 26231.0),
        _fila("demanda_nacional", 23840.0),
        _fila("demanda_internacional", 2391.0),
        _fila("demanda_convencional", 15267.0),
        _fila("demanda_sector_electrico", 8573.0),
        _fila("demanda_dc_pymes", 1300.0),
        _fila("demanda_industrial", 13000.0),
        _fila("demanda_cisternas", 900.0),
        _fila("salidas_conexiones_internacionales", 1372.0),
        _fila("cargas_buques", 1019.0),
    ]


class TestPeriodoValido:
    def test_sin_errores(self):
        resultado = validar_periodo(_filas_validas(), CATALOGO_MINIMO)
        assert resultado.es_valido
        assert resultado.errores == []

    def test_acumulado_anual_no_se_valida_contra_rango_de_mes(self):
        # tam/acumulado_anual son ~6-12x un mes por diseño; no deben
        # disparar el chequeo de rango sano calibrado sobre "mes".
        filas = _filas_validas() + [_fila("total_salidas", 186002.0, agregacion="acumulado_anual")]
        resultado = validar_periodo(filas, CATALOGO_MINIMO)
        assert resultado.es_valido


class TestComprobacionesDeSuma:
    def test_total_salidas_no_cuadra_con_nacional_mas_internacional(self):
        filas = _filas_validas()
        filas[0] = _fila("total_salidas", 99999.0)  # rompe la suma
        resultado = validar_periodo(filas, CATALOGO_MINIMO)
        assert not resultado.es_valido
        assert any("total_salidas" in e for e in resultado.errores)

    def test_demanda_nacional_no_cuadra_con_convencional_mas_electrico(self):
        filas = _filas_validas()
        for f in filas:
            if f["metrica_id"] == "demanda_nacional":
                f["valor"] = 1000.0
        resultado = validar_periodo(filas, CATALOGO_MINIMO)
        assert not resultado.es_valido
        assert any("demanda_nacional" in e for e in resultado.errores)

    def test_demanda_convencional_no_cuadra_cruce_boletin_progreso(self):
        filas = _filas_validas()
        for f in filas:
            if f["metrica_id"] == "demanda_dc_pymes":
                f["valor"] = 9999.0  # rompe el cruce con demanda_convencional
        resultado = validar_periodo(filas, CATALOGO_MINIMO)
        assert not resultado.es_valido
        assert any("demanda_convencional" in e for e in resultado.errores)

    def test_demanda_internacional_no_cuadra_con_conexiones_mas_buques(self):
        filas = _filas_validas()
        for f in filas:
            if f["metrica_id"] == "cargas_buques":
                f["valor"] = 9999.0
        resultado = validar_periodo(filas, CATALOGO_MINIMO)
        assert not resultado.es_valido
        assert any("demanda_internacional" in e for e in resultado.errores)


class TestObligatorias:
    def test_falta_una_metrica_obligatoria(self):
        filas = [f for f in _filas_validas() if f["metrica_id"] != "demanda_cisternas"]
        resultado = validar_periodo(filas, CATALOGO_MINIMO)
        assert not resultado.es_valido
        assert any("demanda_cisternas" in e for e in resultado.errores)


class TestRangoSano:
    def test_valor_negativo_donde_no_procede(self):
        filas = _filas_validas()
        for f in filas:
            if f["metrica_id"] == "demanda_nacional":
                f["valor"] = -23840.0
        resultado = validar_periodo(filas, CATALOGO_MINIMO)
        assert not resultado.es_valido
        assert any("fuera de rango" in e for e in resultado.errores)

    def test_valor_absurdamente_grande(self):
        filas = _filas_validas()
        for f in filas:
            if f["metrica_id"] == "total_salidas":
                f["valor"] = 5_000_000.0
        resultado = validar_periodo(filas, CATALOGO_MINIMO)
        assert not resultado.es_valido
        assert any("fuera de rango" in e for e in resultado.errores)


class TestAvisosCcaa:
    def test_ccaa_no_cuadra_con_nacional_es_aviso_no_error(self):
        filas = _filas_validas() + [
            _fila("demanda_ccaa_convencional", 100.0, dimension="Andalucía"),
            _fila("demanda_ccaa_convencional", 50.0, dimension="Aragón"),
        ]
        resultado = validar_periodo(filas, CATALOGO_MINIMO)
        assert resultado.es_valido  # no bloquea
        assert any("demanda_ccaa_convencional" in a for a in resultado.avisos)
