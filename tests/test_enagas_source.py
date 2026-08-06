"""Tests de construcción de URLs candidatas (src/ingestion/enagas_source.py).

Sin peticiones HTTP: solo se verifica que el patrón de URL y la
codificación se construyen bien para varios meses y años. `find_url`
(que sí hace HEAD) se cubre por separado mockeando `requests.head`.
"""

from __future__ import annotations

import requests

from src.ingestion.enagas_source import BoletinSource, ProgresoSource


class TestBoletinSource:
    def test_url_junio_2026(self):
        urls = BoletinSource().candidate_urls(2026, 6)
        assert urls[0].endswith("Bolet%C3%ADn%20Estad%C3%ADstico_jun26.pdf")

    def test_incluye_variantes_de_revision(self):
        # Verificado sobre datos reales: Enagás renombra el fichero con
        # sufijo "rev" cuando revisa un Boletín ya publicado, de forma
        # inconsistente (con y sin guion bajo).
        urls = BoletinSource().candidate_urls(2026, 1)
        assert any(u.endswith("_ene26.pdf") for u in urls)
        assert any(u.endswith("_ene26_rev.pdf") for u in urls)
        assert any(u.endswith("_ene26rev.pdf") for u in urls)

    def test_el_nombre_sin_revisar_va_primero(self):
        urls = BoletinSource().candidate_urls(2026, 1)
        assert urls[0].endswith("_ene26.pdf")

    def test_url_enero_de_dos_digitos(self):
        urls = BoletinSource().candidate_urls(2025, 1)
        assert urls[0].endswith("_ene25.pdf")

    def test_url_diciembre(self):
        urls = BoletinSource().candidate_urls(2024, 12)
        assert urls[0].endswith("_dic24.pdf")

    def test_espacio_y_tilde_van_url_encoded(self):
        url = BoletinSource().candidate_urls(2026, 6)[0]
        assert " " not in url
        assert "í" not in url
        assert "%20" in url
        assert "%C3%AD" in url


class TestProgresoSource:
    def test_incluye_variante_completa_minuscula(self):
        urls = ProgresoSource().candidate_urls(2025, 2)
        assert any(u.endswith("Progreso_febrero25.pdf") for u in urls)

    def test_incluye_variante_completa_capitalizada(self):
        urls = ProgresoSource().candidate_urls(2022, 9)
        assert any(u.endswith("Progreso_Septiembre22.pdf") for u in urls)

    def test_incluye_variante_abreviada_capitalizada(self):
        urls = ProgresoSource().candidate_urls(2022, 1)
        assert any(u.endswith("Progreso_Ene22.pdf") for u in urls)

    def test_incluye_variante_abreviada_minuscula(self):
        urls = ProgresoSource().candidate_urls(2026, 6)
        assert any(u.endswith("Progreso_jun26.pdf") for u in urls)

    def test_no_hay_duplicados(self):
        urls = ProgresoSource().candidate_urls(2026, 6)
        assert len(urls) == len(set(urls))


class TestFindUrl:
    def test_devuelve_la_primera_url_que_responde_200(self, monkeypatch):
        source = BoletinSource()
        candidatas = source.candidate_urls(2026, 6)

        class FakeResponse:
            status_code = 200

        monkeypatch.setattr(requests, "head", lambda url, timeout, allow_redirects: FakeResponse())
        assert source.find_url(2026, 6) == candidatas[0]

    def test_devuelve_none_si_ninguna_candidata_existe(self, monkeypatch):
        source = ProgresoSource()

        class FakeResponse:
            status_code = 404

        monkeypatch.setattr(requests, "head", lambda url, timeout, allow_redirects: FakeResponse())
        assert source.find_url(2099, 1) is None

    def test_no_falla_si_una_peticion_lanza_excepcion(self, monkeypatch):
        source = ProgresoSource()
        calls = {"n": 0}

        def fake_head(url, timeout, allow_redirects):
            calls["n"] += 1
            if calls["n"] == 1:
                raise requests.ConnectionError("boom")
            return type("R", (), {"status_code": 200})()

        monkeypatch.setattr(requests, "head", fake_head)
        assert source.find_url(2026, 6) is not None
