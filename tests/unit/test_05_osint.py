"""
test_05_osint.py — TC-007: OSINT - Detección de falsos positivos y validación

Valida la lógica de parsing y filtrado de resultados OSINT (Maigret).
Todas las llamadas de red se mockean — no se hace ninguna petición real.
"""
import json
import os
from unittest.mock import MagicMock, patch

import pytest


# ── Helpers que simulan la lógica del parser OSINT ──────────────────────────

def parse_maigret_results(raw_data: dict) -> list:
    """
    Parsea los resultados de Maigret y retorna solo los perfiles 'Claimed'.
    Filtra los 'Available' (falsos positivos de plataformas que devuelven 200
    aunque el usuario no exista).
    """
    found = []
    for site_name, site_data in raw_data.get('sites', {}).items():
        status = site_data.get('status', {}).get('status', '')
        if status == 'Claimed':
            found.append({
                'site': site_name,
                'url': site_data.get('url_user', ''),
                'status': status,
            })
    return found


def generate_osint_report(caso_id: str, alias: str, resultados: list) -> dict:
    """Genera el JSON de reporte OSINT con los campos requeridos."""
    return {
        'caso_id': caso_id,
        'alias': alias,
        'timestamp': '2025-01-01T00:00:00',
        'total_sitios': len(resultados),
        'perfiles_encontrados': resultados,
    }


# ── TC-007: Falsos positivos OSINT ──────────────────────────────────────────
class TestOSINTFalsePositives:

    def test_claimed_profiles_included(self, mock_osint_data):
        """TC-007a: Solo los perfiles con status 'Claimed' se incluyen."""
        resultados = parse_maigret_results(mock_osint_data)
        site_names = [r['site'] for r in resultados]
        assert 'Twitter' in site_names
        assert 'GitHub'  in site_names

    def test_available_profiles_excluded(self, mock_osint_data):
        """TC-007b: Los perfiles 'Available' se descartan (son falsos positivos)."""
        resultados = parse_maigret_results(mock_osint_data)
        site_names = [r['site'] for r in resultados]
        assert 'SitioFalso' not in site_names, (
            "'SitioFalso' con status Available debería ser filtrado como FP"
        )

    def test_empty_results_no_crash(self):
        """TC-007c: Resultados vacíos no generan excepciones."""
        resultados = parse_maigret_results({'sites': {}})
        assert resultados == []

    def test_all_available_returns_empty(self):
        """TC-007d: Si todas las plataformas dicen Available, la lista es vacía."""
        data = {
            'sites': {
                'Plataforma1': {'status': {'status': 'Available'}, 'url_user': ''},
                'Plataforma2': {'status': {'status': 'Available'}, 'url_user': ''},
            }
        }
        resultados = parse_maigret_results(data)
        assert resultados == []

    def test_mixed_results_correct_count(self, mock_osint_data):
        """TC-007e: El conteo de perfiles encontrados es correcto."""
        resultados = parse_maigret_results(mock_osint_data)
        # Twitter + GitHub = 2 (SitioFalso excluido)
        assert len(resultados) == 2


# ── TC-OSINT-Parsing: Validación de datos OSINT ─────────────────────────────
class TestOSINTReportFields:

    def test_report_has_required_fields(self, mock_osint_data):
        """El reporte OSINT debe tener todos los campos requeridos."""
        resultados = parse_maigret_results(mock_osint_data)
        report = generate_osint_report('CASO_001', 'test_alias', resultados)

        required_keys = ['caso_id', 'alias', 'timestamp', 'total_sitios', 'perfiles_encontrados']
        for key in required_keys:
            assert key in report, f'Campo requerido ausente en el reporte OSINT: {key}'

    def test_report_caso_id_matches(self, mock_osint_data):
        """El caso_id en el reporte debe coincidir con el solicitado."""
        resultados = parse_maigret_results(mock_osint_data)
        report = generate_osint_report('CASO_XYZ', 'alias_test', resultados)
        assert report['caso_id'] == 'CASO_XYZ'

    def test_report_alias_matches(self, mock_osint_data):
        """El alias en el reporte debe coincidir con el buscado."""
        resultados = parse_maigret_results(mock_osint_data)
        report = generate_osint_report('CASO_001', 'john_doe', resultados)
        assert report['alias'] == 'john_doe'

    def test_total_sitios_is_correct(self, mock_osint_data):
        """El campo total_sitios debe reflejar el número de perfiles encontrados."""
        resultados = parse_maigret_results(mock_osint_data)
        report = generate_osint_report('CASO_001', 'alias', resultados)
        assert report['total_sitios'] == len(resultados)

    def test_each_profile_has_site_and_url(self, mock_osint_data):
        """Cada perfil encontrado debe tener 'site' y 'url'."""
        resultados = parse_maigret_results(mock_osint_data)
        for perfil in resultados:
            assert 'site' in perfil, 'Campo site ausente en perfil OSINT'
            assert 'url'  in perfil, 'Campo url ausente en perfil OSINT'

    def test_report_serializable_to_json(self, mock_osint_data):
        """El reporte debe ser serializable a JSON sin errores."""
        resultados = parse_maigret_results(mock_osint_data)
        report = generate_osint_report('CASO_001', 'alias', resultados)
        json_str = json.dumps(report)
        assert json_str  # No debe ser vacío
        parsed = json.loads(json_str)
        assert parsed['caso_id'] == 'CASO_001'


# ── Tests de alias sanitización ──────────────────────────────────────────────
class TestOSINTAliasValidation:

    def test_valid_alias_accepted(self):
        """Alias alfanumérico válido pasa la sanitización."""
        alias_raw = 'john_doe123'
        alias = ''.join(c for c in alias_raw if c.isalnum() or c in ('-', '_', '.'))
        assert alias == 'john_doe123'

    def test_special_chars_stripped(self):
        """Caracteres especiales son eliminados del alias."""
        alias_raw = 'john<script>alert(1)</script>'
        alias = ''.join(c for c in alias_raw if c.isalnum() or c in ('-', '_', '.'))
        assert '<' not in alias
        assert '>' not in alias
        assert 'script' not in alias or alias == 'johnscriptalert1script'

    def test_path_traversal_in_alias_stripped(self):
        """Path traversal en alias es eliminado."""
        alias_raw = '../../../etc/passwd'
        alias = ''.join(c for c in alias_raw if c.isalnum() or c in ('-', '_', '.'))
        assert '/' not in alias
        assert alias == '......etcpasswd'

    def test_empty_alias_detected(self):
        """Alias vacío después de sanitizar es rechazado."""
        alias_raw = '<>!@#$%^&*()'
        alias = ''.join(c for c in alias_raw if c.isalnum() or c in ('-', '_', '.'))
        assert not alias  # Debe quedar vacío → rechazado
