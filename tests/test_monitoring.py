"""Tests de src/monitoring/informe.py, en particular
check_periodo_desactualizado: la métrica correcta es días desde la
última ingesta exitosa (extraido_el), no días desde el mes calendario
del periodo -- ver el docstring del módulo para el porqué."""

from __future__ import annotations

from datetime import date

import pandas as pd

from src.monitoring.informe import check_periodo_desactualizado


def _df(periodo: str, extraido_el: str) -> pd.DataFrame:
    return pd.DataFrame(
        [{"periodo": periodo, "metrica_id": "total_salidas", "extraido_el": extraido_el, "valor": 26231.0}]
    )


class TestCheckPeriodoDesactualizado:
    def test_csv_vacio_da_aviso(self):
        aviso = check_periodo_desactualizado(pd.DataFrame(), hoy=date(2026, 8, 6))
        assert aviso is not None
        assert aviso["tipo"] == "sin_datos"

    def test_ingesta_reciente_no_avisa(self):
        df = _df("2026-06", "2026-08-06")
        assert check_periodo_desactualizado(df, hoy=date(2026, 8, 6)) is None

    def test_periodo_antiguo_pero_ingesta_reciente_no_avisa(self):
        # Esto es lo que falla si se mide mal: el periodo (2026-06)
        # cubre un mes de hace 66 días, pero el pipeline SÍ consiguió
        # ingerirlo hoy mismo -- no es una señal de alarma.
        df = _df("2026-06", "2026-08-06")
        assert check_periodo_desactualizado(df, hoy=date(2026, 8, 6), umbral_dias=45) is None

    def test_ingesta_antigua_avisa(self):
        df = _df("2026-06", "2026-06-10")
        aviso = check_periodo_desactualizado(df, hoy=date(2026, 8, 6), umbral_dias=45)
        assert aviso is not None
        assert aviso["tipo"] == "periodo_desactualizado"
        assert aviso["dias_desde_ultima_ingesta"] == 57

    def test_justo_en_el_umbral_no_avisa(self):
        df = _df("2026-06", "2026-06-22")
        assert check_periodo_desactualizado(df, hoy=date(2026, 8, 6), umbral_dias=45) is None
