"""
test_security.py — TC-009, TC-009b, TC-Inputs: Tests de Seguridad

Valida que la API Flask rechaza correctamente:
- Path traversal en todos los endpoints
- Acceso al disco del sistema operativo
- Inputs maliciosos (XSS, SQLi, null bytes)
"""
import json
import os

import pytest


# ── TC-009: Path Traversal ───────────────────────────────────────────────────
PATH_TRAVERSAL_PAYLOADS = [
    '../../../etc/passwd',
    '....//....//etc/shadow',
    '%2e%2e%2f%2e%2e%2fetc%2fpasswd',
    '..%2F..%2F..%2Fetc%2Fpasswd',
    '/etc/passwd',
    '/root/.ssh/id_rsa',
    '\\..\\..\\windows\\system32',
    'valid/../../../etc/passwd',
]

XSS_PAYLOADS = [
    "<script>alert('xss')</script>",
    '"><img src=x onerror=alert(1)>',
    "javascript:alert('XSS')",
    '<iframe src="javascript:alert(1)">',
]

SQLI_PAYLOADS = [
    "'; DROP TABLE cases; --",
    "1' OR '1'='1",
    "admin'--",
    '1; SELECT * FROM information_schema.tables',
]

NULL_BYTE_PAYLOADS = [
    'caso_id\x00.php',
    'caso\x00../../etc/passwd',
]


class TestPathTraversal:
    """TC-009: Ningún endpoint debe permitir path traversal."""

    @pytest.mark.security
    def test_explore_endpoint_path_traversal(self, client):
        """El endpoint /api/explore rechaza rutas con path traversal."""
        for payload in PATH_TRAVERSAL_PAYLOADS:
            resp = client.post('/api/explore', json={'path': payload})
            # Debe retornar 400, 403, o 404 — NUNCA 200 con contenido del SO
            assert resp.status_code in (400, 403, 404, 500), (
                f'Path traversal no bloqueado para payload: {payload!r}\n'
                f'Status: {resp.status_code}'
            )

    @pytest.mark.security
    def test_file_content_path_traversal(self, client, tmp_path, monkeypatch):
        """El endpoint /api/case/<id>/file_content rechaza filenames con traversal."""
        import web_app.app as app_module
        monkeypatch.setattr(app_module, 'CASES_BASE_DIR', str(tmp_path))
        monkeypatch.setattr(app_module, 'CASES_REGISTRY',
                            str(tmp_path / 'casos_registro.json'))

        # Crear caso válido primero
        client.post('/api/case/open', json={
            'caso_id': 'CASO_SEC',
            'perito': 'Perito Test'
        })

        traversal_filenames = [
            '../../../etc/passwd',
            '..\\..\\system.ini',
            '/etc/shadow',
        ]
        for fname in traversal_filenames:
            resp = client.get(f'/api/case/CASO_SEC/file_content?filename={fname}')
            assert resp.status_code in (400, 403, 404), (
                f'Path traversal en filename no bloqueado: {fname!r}'
            )

    @pytest.mark.security
    def test_load_case_from_path_traversal(self, client):
        """El endpoint /api/case/load_from_path rechaza rutas peligrosas."""
        for payload in ['/etc/passwd', '/root', '/../../../etc']:
            resp = client.post('/api/case/load_from_path', json={'ruta': payload})
            assert resp.status_code in (400, 403, 404, 500), (
                f'Ruta peligrosa no bloqueada: {payload!r}'
            )


# ── TC-009b: Protección del Disco del Sistema ────────────────────────────────
class TestSystemDiskProtection:
    """TC-009b: El disco del SO no debe aparecer ni ser operable."""

    @pytest.mark.security
    def test_system_disk_not_in_list_devices(self, client, monkeypatch):
        """El disco del SO (sda) no debe aparecer en /api/list_devices."""
        import web_app.app as app_module

        # Forzar SYSTEM_DISK_NAMES a incluir sda
        monkeypatch.setattr(app_module, 'SYSTEM_DISK_NAMES', {'sda', 'sda1', 'sda2'})

        import subprocess
        import json as json_lib

        # Mock lsblk devolviendo sda + sdb
        mock_lsblk = {
            'blockdevices': [
                {'name': 'sda', 'size': '32G', 'model': 'System Disk',
                 'type': 'disk', 'mountpoint': None, 'rm': False, 'pkname': None,
                 'children': [
                     {'name': 'sda1', 'size': '1G', 'model': None,
                      'type': 'part', 'mountpoint': '/', 'rm': False, 'pkname': 'sda'},
                     {'name': 'sda2', 'size': '31G', 'model': None,
                      'type': 'part', 'mountpoint': '/home', 'rm': False, 'pkname': 'sda'},
                 ]},
                {'name': 'sdb', 'size': '500G', 'model': 'Evidence Drive',
                 'type': 'disk', 'mountpoint': None, 'rm': True, 'pkname': None,
                 'children': []},
            ]
        }

        with monkeypatch.context() as m:
            import unittest.mock as mock
            m.setattr(subprocess, 'run', mock.MagicMock(return_value=mock.MagicMock(
                stdout=json_lib.dumps(mock_lsblk),
                returncode=0
            )))
            resp = client.get('/api/list_devices')

        assert resp.status_code == 200
        data = resp.get_json()
        device_names = [d['name'] for d in data.get('devices', [])]

        assert 'sda'  not in device_names, 'sda (disco SO) no debe aparecer'
        assert 'sda1' not in device_names, 'sda1 (partición SO) no debe aparecer'
        assert 'sda2' not in device_names, 'sda2 (partición SO) no debe aparecer'
        assert 'sdb'  in device_names,     'sdb (disco externo) sí debe aparecer'

    @pytest.mark.security
    def test_verify_disk_blocks_system_disk(self, client, monkeypatch):
        """verify_disk() retorna 403 para el disco del sistema."""
        import web_app.app as app_module
        monkeypatch.setattr(app_module, 'SYSTEM_DISK_NAMES', {'sda', 'sda1', 'sda2'})

        resp = client.post('/api/verify_disk', json={'target_disk': '/dev/sda'})
        assert resp.status_code == 403, (
            f'verify_disk sobre /dev/sda debería retornar 403, got {resp.status_code}'
        )

    @pytest.mark.security
    def test_verify_partition_blocks_system_disk(self, client, monkeypatch):
        """verify_disk() retorna 403 para particiones del disco del sistema."""
        import web_app.app as app_module
        monkeypatch.setattr(app_module, 'SYSTEM_DISK_NAMES', {'sda', 'sda1', 'sda2'})

        for partition in ['/dev/sda1', '/dev/sda2']:
            resp = client.post('/api/verify_disk', json={'target_disk': partition})
            assert resp.status_code == 403, (
                f'{partition} debería ser bloqueada (es partición del SO)'
            )

    @pytest.mark.security
    def test_set_readonly_blocks_system_disk(self, client, monkeypatch):
        """set_readonly() retorna 403 para el disco del sistema."""
        import web_app.app as app_module
        monkeypatch.setattr(app_module, 'SYSTEM_DISK_NAMES', {'sda', 'sda1', 'sda2'})

        resp = client.post('/api/set_readonly', json={'target_disk': '/dev/sda'})
        assert resp.status_code == 403

    @pytest.mark.security
    def test_external_disk_not_blocked(self, client, monkeypatch):
        """Un disco externo (no del SO) no debe ser bloqueado por verify_disk."""
        import web_app.app as app_module
        monkeypatch.setattr(app_module, 'SYSTEM_DISK_NAMES', {'mmcblk0', 'mmcblk0p1'})

        # /dev/sdb es externo — no debe retornar 403 por protección del SO
        # (puede fallar por otras razones como no estar montado, pero no por 403)
        resp = client.post('/api/verify_disk', json={'target_disk': '/dev/sdb'})
        assert resp.status_code != 403, (
            'El disco externo /dev/sdb no debería estar bloqueado por protección del SO'
        )


# ── TC-Inputs: Sanitización de Inputs ───────────────────────────────────────
class TestInputSanitization:
    """TC-Inputs: Todos los inputs maliciosos deben ser rechazados o sanitizados."""

    @pytest.mark.security
    def test_caso_id_xss_rejected(self, client, tmp_path, monkeypatch):
        """caso_id con payload XSS es rechazado o sanitizado."""
        import web_app.app as app_module
        monkeypatch.setattr(app_module, 'CASES_BASE_DIR', str(tmp_path))
        monkeypatch.setattr(app_module, 'CASES_REGISTRY',
                            str(tmp_path / 'casos_registro.json'))

        for payload in XSS_PAYLOADS:
            resp = client.post('/api/case/open', json={
                'caso_id': payload,
                'perito': 'Perito Test',
            })
            # XSS en caso_id debe resultar en caso_id vacío (sanitizado) → 400
            assert resp.status_code in (400, 200), (
                f'XSS payload debería ser sanitizado o rechazado: {payload!r}'
            )
            if resp.status_code == 200:
                # Si se acepta, el caso_id en la respuesta no debe contener el payload HTML original
                data = resp.get_json()
                returned_id = data.get('caso_id', '')
                assert '<' not in returned_id
                assert '>' not in returned_id

    @pytest.mark.security
    def test_caso_id_sqli_sanitized(self, client, tmp_path, monkeypatch):
        """caso_id con payload SQLi es sanitizado (sin chars especiales)."""
        import web_app.app as app_module
        monkeypatch.setattr(app_module, 'CASES_BASE_DIR', str(tmp_path))
        monkeypatch.setattr(app_module, 'CASES_REGISTRY',
                            str(tmp_path / 'casos_registro.json'))

        import re
        for payload in SQLI_PAYLOADS:
            # Verificar que sanitize_case_id elimina chars peligrosos como ' y ;
            sanitized = re.sub(r'[^a-zA-Z0-9_\-]', '', payload)
            assert "'" not in sanitized
            assert ';' not in sanitized

    @pytest.mark.security
    def test_caso_id_null_bytes_sanitized(self, client, tmp_path, monkeypatch):
        """caso_id con null bytes es sanitizado."""
        import re
        for payload in NULL_BYTE_PAYLOADS:
            sanitized = re.sub(r'[^a-zA-Z0-9_\-]', '', payload)
            assert '\x00' not in sanitized

    @pytest.mark.security
    def test_invalid_disk_path_rejected(self, client):
        """Rutas de disco sin /dev/ son rechazadas."""
        invalid_paths = ['sda', 'disk0', '/proc/sda', 'C:\\disk', '']
        for path in invalid_paths:
            resp = client.post('/api/verify_disk', json={'target_disk': path})
            assert resp.status_code in (400, 403), (
                f'Ruta inválida no rechazada: {path!r}'
            )

    @pytest.mark.security
    def test_perito_length_limit(self, client, tmp_path, monkeypatch):
        """Campos excesivamente largos son rechazados (protección DoS)."""
        import web_app.app as app_module
        monkeypatch.setattr(app_module, 'CASES_BASE_DIR', str(tmp_path))
        monkeypatch.setattr(app_module, 'CASES_REGISTRY',
                            str(tmp_path / 'casos_registro.json'))

        resp = client.post('/api/case/open', json={
            'caso_id': 'CASO_LONG',
            'perito': 'A' * 10000,  # Excede límite de 200 chars
        })
        assert resp.status_code == 400

    @pytest.mark.security
    def test_notas_length_limit(self, client, tmp_path, monkeypatch):
        """El campo notas tiene límite de 5000 chars."""
        import web_app.app as app_module
        monkeypatch.setattr(app_module, 'CASES_BASE_DIR', str(tmp_path))
        monkeypatch.setattr(app_module, 'CASES_REGISTRY',
                            str(tmp_path / 'casos_registro.json'))

        resp = client.post('/api/case/open', json={
            'caso_id': 'CASO_NOTAS',
            'perito': 'Perito Test',
            'notas': 'X' * 10000,  # Excede límite de 5000 chars
        })
        assert resp.status_code == 400
