"""Test de integración: corre el pipeline completo de ingest_month.py
con --sin-llm sobre extracciones de ejemplo (sin llamar a la API ni
descargar nada) y comprueba el CSV resultante.

Se ejecuta con el directorio de trabajo apuntando a un directorio
temporal (todas las rutas de ingest_month.py son relativas a "data/",
así que basta con encadenar un chdir) y una copia del catálogo real,
para no depender de -- ni ensuciar -- el data/gas.csv del repo.
"""

from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from scripts import ingest_month

PERIODO = "2099-01"

# Cifras diseñadas para cuadrar exactamente las 4 comprobaciones de
# suma del validador y caer dentro de los rangos sanos calibrados
# sobre datos reales (ver src/extraccion/validar.py).
EXTRACCION_BOLETIN = {
    "extracciones": [
        {"metrica_id": "total_salidas", "dimension_valor": None, "pagina": 1, "valores": {"mes": "28.000"}, "var_pct_interanual": {}},
        {"metrica_id": "demanda_nacional", "dimension_valor": None, "pagina": 1, "valores": {"mes": "24.000"}, "var_pct_interanual": {}},
        {"metrica_id": "demanda_convencional", "dimension_valor": None, "pagina": 1, "valores": {"mes": "18.000"}, "var_pct_interanual": {}},
        {"metrica_id": "demanda_sector_electrico", "dimension_valor": None, "pagina": 1, "valores": {"mes": "6.000"}, "var_pct_interanual": {}},
        {"metrica_id": "demanda_internacional", "dimension_valor": None, "pagina": 1, "valores": {"mes": "4.000"}, "var_pct_interanual": {}},
        {"metrica_id": "salidas_conexiones_internacionales", "dimension_valor": None, "pagina": 1, "valores": {"mes": "3.000"}, "var_pct_interanual": {}},
        {"metrica_id": "cargas_buques", "dimension_valor": None, "pagina": 1, "valores": {"mes": "1.000"}, "var_pct_interanual": {}},
    ],
    "metricas_no_reconocidas": [],
}

# TWh en el PDF (unidad_pdf del catálogo para estas tres): 4+12+2 TWh
# = 18.000 GWh, exactamente demanda_convencional -- el cruce
# Boletín/Progreso más valioso del validador.
EXTRACCION_PROGRESO = {
    "extracciones": [
        {"metrica_id": "demanda_dc_pymes", "dimension_valor": None, "pagina": 3, "valores": {"mes": "4,0"}, "var_pct_interanual": {}},
        {"metrica_id": "demanda_industrial", "dimension_valor": None, "pagina": 3, "valores": {"mes": "12,0"}, "var_pct_interanual": {}},
        {"metrica_id": "demanda_cisternas", "dimension_valor": None, "pagina": 3, "valores": {"mes": "2,0"}, "var_pct_interanual": {}},
    ],
    "metricas_no_reconocidas": [],
}


@pytest.fixture
def repo_temporal(tmp_path, monkeypatch):
    """Copia el catálogo real y las extracciones de ejemplo a un repo
    temporal, y hace chdir ahí (las rutas de ingest_month.py son
    relativas a la raíz del proyecto)."""
    catalogo_real = Path(__file__).resolve().parents[1] / "data" / "metricas_catalogo.json"
    (tmp_path / "data" / "extracciones").mkdir(parents=True)
    shutil.copy(catalogo_real, tmp_path / "data" / "metricas_catalogo.json")

    with open(tmp_path / "data" / "extracciones" / f"{PERIODO}_boletin.json", "w", encoding="utf-8") as f:
        json.dump(EXTRACCION_BOLETIN, f)
    with open(tmp_path / "data" / "extracciones" / f"{PERIODO}_progreso.json", "w", encoding="utf-8") as f:
        json.dump(EXTRACCION_PROGRESO, f)

    monkeypatch.chdir(tmp_path)
    return tmp_path


class TestIngestMonthIntegracion:
    def test_pipeline_completo_con_sin_llm(self, repo_temporal):
        exit_code = ingest_month.main(["--periodo", PERIODO, "--sin-llm"])
        assert exit_code == 0

        csv_path = repo_temporal / "data" / "gas.csv"
        assert csv_path.exists()

        df = pd.read_csv(csv_path, dtype={"periodo": str})
        assert set(df["periodo"].unique()) == {PERIODO}
        assert len(df) == 10  # 7 filas del boletín + 3 del progreso

        fila = df[(df["metrica_id"] == "demanda_convencional") & (df["agregacion"] == "mes")].iloc[0]
        assert fila["valor"] == pytest.approx(18000.0)
        assert fila["unidad"] == "GWh"
        assert fila["extraido_el"] == date.today().isoformat()

        # unidad_pdf TWh -> unidad_canonica GWh: 4,0 TWh debe llegar como 4000.0 GWh
        fila_pymes = df[df["metrica_id"] == "demanda_dc_pymes"].iloc[0]
        assert fila_pymes["valor"] == pytest.approx(4000.0)
        assert fila_pymes["fuente_doc"] == "progreso"

        assert (repo_temporal / "data" / "manifiesto.json").exists()
        assert (repo_temporal / "data" / "metricas_desconocidas.json").exists()

    def test_periodo_ya_existente_no_se_reprocesa_sin_force(self, repo_temporal):
        ingest_month.main(["--periodo", PERIODO, "--sin-llm"])
        csv_path = repo_temporal / "data" / "gas.csv"
        mtime_antes = csv_path.stat().st_mtime

        exit_code = ingest_month.main(["--periodo", PERIODO, "--sin-llm"])
        assert exit_code == 0
        assert csv_path.stat().st_mtime == mtime_antes  # no se reescribió

    def test_periodo_ya_existente_se_reprocesa_con_force(self, repo_temporal):
        ingest_month.main(["--periodo", PERIODO, "--sin-llm"])
        exit_code = ingest_month.main(["--periodo", PERIODO, "--sin-llm", "--force"])
        assert exit_code == 0
        df = pd.read_csv(repo_temporal / "data" / "gas.csv")
        assert len(df) == 10  # upsert, no duplica filas

    def test_periodo_sin_extraccion_guardada_no_escribe_nada(self, repo_temporal):
        exit_code = ingest_month.main(["--periodo", "2099-02", "--sin-llm"])
        assert exit_code == 0
        assert not (repo_temporal / "data" / "gas.csv").exists()

    def test_dry_run_no_escribe_csv(self, repo_temporal):
        exit_code = ingest_month.main(["--periodo", PERIODO, "--sin-llm", "--dry-run"])
        assert exit_code == 0
        assert not (repo_temporal / "data" / "gas.csv").exists()

    def test_cruce_boletin_progreso_roto_no_escribe_csv(self, repo_temporal):
        # Rompe el cruce: la demanda_convencional del Boletín deja de
        # coincidir con dc_pymes+industrial+cisternas del Progreso.
        extraccion_rota = json.loads(json.dumps(EXTRACCION_BOLETIN))
        for e in extraccion_rota["extracciones"]:
            if e["metrica_id"] == "demanda_convencional":
                e["valores"]["mes"] = "99.999"
        with open(repo_temporal / "data" / "extracciones" / f"{PERIODO}_boletin.json", "w", encoding="utf-8") as f:
            json.dump(extraccion_rota, f)

        exit_code = ingest_month.main(["--periodo", PERIODO, "--sin-llm"])
        assert exit_code == 1
        assert not (repo_temporal / "data" / "gas.csv").exists()
