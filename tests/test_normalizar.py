"""Tests de src/extraccion/normalizar.py. parse_numero_es() es la
fuente de error más probable de todo el proyecto (ver docstring del
módulo), así que se cubre con los casos reales que aparecen en los PDF
de Enagás."""

from __future__ import annotations

import pytest

from src.extraccion.normalizar import (
    convertir_unidad,
    normalizar_dimension,
    parse_numero_es,
)


class TestParseNumeroEs:
    def test_miles_con_punto(self):
        assert parse_numero_es("15.267") == 15267.0

    def test_miles_con_punto_otro_valor(self):
        assert parse_numero_es("1.065") == 1065.0

    def test_decimal_con_coma_negativo_y_porcentaje(self):
        assert parse_numero_es("-2,8%") == pytest.approx(-2.8)

    def test_decimal_cero_con_porcentaje(self):
        assert parse_numero_es("0,0%") == pytest.approx(0.0)

    def test_variacion_mayor_que_100_es_none(self):
        assert parse_numero_es(">100%") is None

    def test_variacion_menor_que_menos_100_es_none(self):
        assert parse_numero_es("<-100%") is None

    def test_cadena_vacia_es_none(self):
        assert parse_numero_es("") is None

    def test_guion_es_none(self):
        assert parse_numero_es("-") is None

    def test_none_es_none(self):
        assert parse_numero_es(None) is None

    def test_numero_ya_float_pasa_tal_cual(self):
        assert parse_numero_es(123.45) == 123.45

    def test_numero_ya_int_se_convierte_a_float(self):
        assert parse_numero_es(42) == 42.0

    def test_positivo_con_signo_explicito(self):
        assert parse_numero_es("+3,2%") == pytest.approx(3.2)

    def test_miles_y_decimales_combinados(self):
        assert parse_numero_es("1.234,56") == pytest.approx(1234.56)

    def test_no_numerico_es_none(self):
        assert parse_numero_es("abc") is None


class TestConvertirUnidad:
    def test_twh_a_gwh(self):
        assert convertir_unidad(1.5, "TWh", "GWh") == pytest.approx(1500.0)

    def test_gwh_a_twh(self):
        assert convertir_unidad(1500.0, "GWh", "TWh") == pytest.approx(1.5)

    def test_misma_unidad_no_cambia(self):
        assert convertir_unidad(42.0, "GWh", "GWh") == 42.0

    def test_valor_none_pasa_tal_cual(self):
        assert convertir_unidad(None, "TWh", "GWh") is None

    def test_conversion_no_soportada_lanza(self):
        with pytest.raises(ValueError):
            convertir_unidad(1.0, "GWh", "MW")


class TestNormalizarDimension:
    def test_castilla_la_mancha_con_espacios_y_guion(self):
        assert normalizar_dimension("Castilla - La Mancha", "ccaa") == "Castilla-La Mancha"

    def test_castilla_la_mancha_sin_espacios(self):
        assert normalizar_dimension("Castilla-La Mancha", "ccaa") == "Castilla-La Mancha"

    def test_hidraulica_typo_real_del_pdf(self):
        # "Hidraúlica" (sic) es un error tipográfico real de Enagás.
        assert normalizar_dimension("Hidraúlica", "tecnologia") == "Hidráulica"

    def test_hidraulica_sin_tilde(self):
        assert normalizar_dimension("hidraulica", "tecnologia") == "Hidráulica"

    def test_valor_desconocido_pasa_tal_cual_recortado(self):
        assert normalizar_dimension("  Alguna Región Nueva  ", "ccaa") == "Alguna Región Nueva"

    def test_none_pasa_tal_cual(self):
        assert normalizar_dimension(None, "ccaa") is None
