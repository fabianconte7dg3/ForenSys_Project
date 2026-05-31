"""
test_case_lifecycle.py — TC-Lifecycle: Ciclo completo de un Caso Forense

Prueba el flujo completo: Abrir → Verificar estructura → Cerrar caso
usando el Flask Test Client. Todo en directorios temporales.
"""
import json
import os

import pytest


class TestCaseLifecycle:
    """Ciclo completo de vida de un caso forense vía API REST."""

    def test_open_case_success(self, client, tmp_path, monkeypatch):
        """Abrir un caso retorna HTTP 200 con caso_id y ruta."""
        import web_app.app as app_module
        monkeypatch.setattr(app_module, 'CASES_BASE_DIR', str(tmp_path))
        monkeypatch.setattr(app_module, 'CASES_REGISTRY',
                            str(tmp_path / 'casos_registro.json'))

        resp = client.post('/api/case/open', json={
            'caso_id': 'CASO_LIFECYCLE_001',
            'perito': 'Perito Automatizado',
            'clasificacion': 'Prueba de integración',
            'notas': 'Test lifecycle automatizado',
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'success'
        assert data['caso_id'] == 'CASO_LIFECYCLE_001'

    def test_open_case_creates_folders(self, client, tmp_path, monkeypatch):
        """Al abrir un caso se crean las 4 subcarpetas forenses."""
        import web_app.app as app_module
        monkeypatch.setattr(app_module, 'CASES_BASE_DIR', str(tmp_path))
        monkeypatch.setattr(app_module, 'CASES_REGISTRY',
                            str(tmp_path / 'casos_registro.json'))

        client.post('/api/case/open', json={
            'caso_id': 'CASO_FOLDERS',
            'perito': 'Perito Test',
        })

        carpeta_caso = tmp_path / 'CASO_FOLDERS'
        assert (carpeta_caso / '01_Images_(Fuentes_de_datos)').exists()
        assert (carpeta_caso / '02_Views_(Vistas)').exists()
        assert (carpeta_caso / '03_Results_(Resultados_Extraidos)').exists()
        assert (carpeta_caso / '04_Archivos_Borrados_Recuperados').exists()

    def test_open_case_creates_context_json(self, client, tmp_path, monkeypatch):
        """Al abrir un caso se crea contexto_incidente.json."""
        import web_app.app as app_module
        monkeypatch.setattr(app_module, 'CASES_BASE_DIR', str(tmp_path))
        monkeypatch.setattr(app_module, 'CASES_REGISTRY',
                            str(tmp_path / 'casos_registro.json'))

        client.post('/api/case/open', json={
            'caso_id': 'CASO_CTX',
            'perito': 'Perito Test',
        })

        ctx_path = (tmp_path / 'CASO_CTX' /
                    '03_Results_(Resultados_Extraidos)' / 'contexto_incidente.json')
        assert ctx_path.exists()
        ctx = json.loads(ctx_path.read_text())
        assert ctx['caso_id'] == 'CASO_CTX'
        assert ctx['perito'] == 'Perito Test'

    def test_open_case_creates_custody_log(self, client, tmp_path, monkeypatch):
        """Al abrir un caso se crea cadena_custodia.log."""
        import web_app.app as app_module
        monkeypatch.setattr(app_module, 'CASES_BASE_DIR', str(tmp_path))
        monkeypatch.setattr(app_module, 'CASES_REGISTRY',
                            str(tmp_path / 'casos_registro.json'))

        client.post('/api/case/open', json={
            'caso_id': 'CASO_LOG',
            'perito': 'Perito Test',
        })

        log_path = tmp_path / 'CASO_LOG' / 'cadena_custodia.log'
        assert log_path.exists()
        contenido = log_path.read_text()
        assert '[APERTURA]' in contenido
        assert 'CASO_LOG' in contenido

    def test_duplicate_case_rejected(self, client, tmp_path, monkeypatch):
        """Intentar abrir un caso con ID ya existente retorna error 409."""
        import web_app.app as app_module
        monkeypatch.setattr(app_module, 'CASES_BASE_DIR', str(tmp_path))
        monkeypatch.setattr(app_module, 'CASES_REGISTRY',
                            str(tmp_path / 'casos_registro.json'))

        payload = {'caso_id': 'CASO_DUP', 'perito': 'Perito Test'}
        client.post('/api/case/open', json=payload)
        resp2 = client.post('/api/case/open', json=payload)
        assert resp2.status_code == 409

    def test_close_case_success(self, client, tmp_path, monkeypatch):
        """Cerrar un caso retorna HTTP 200 con hash maestro."""
        import web_app.app as app_module
        monkeypatch.setattr(app_module, 'CASES_BASE_DIR', str(tmp_path))
        monkeypatch.setattr(app_module, 'CASES_REGISTRY',
                            str(tmp_path / 'casos_registro.json'))

        # Abrir primero
        client.post('/api/case/open', json={
            'caso_id': 'CASO_CLOSE',
            'perito': 'Perito Test',
        })

        # Cerrar
        resp = client.post('/api/case/close', json={'caso_id': 'CASO_CLOSE'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'success'
        assert 'hash_maestro' in data
        assert len(data['hash_maestro']) == 64  # SHA-256

    def test_close_nonexistent_case_returns_404(self, client, tmp_path, monkeypatch):
        """Intentar cerrar un caso inexistente retorna 404."""
        import web_app.app as app_module
        monkeypatch.setattr(app_module, 'CASES_BASE_DIR', str(tmp_path))
        monkeypatch.setattr(app_module, 'CASES_REGISTRY',
                            str(tmp_path / 'casos_registro.json'))

        resp = client.post('/api/case/close', json={'caso_id': 'CASO_NO_EXISTE'})
        assert resp.status_code == 404

    def test_list_cases_returns_opened_case(self, client, tmp_path, monkeypatch):
        """El endpoint /api/case/list incluye el caso recién abierto."""
        import web_app.app as app_module
        monkeypatch.setattr(app_module, 'CASES_BASE_DIR', str(tmp_path))
        monkeypatch.setattr(app_module, 'CASES_REGISTRY',
                            str(tmp_path / 'casos_registro.json'))

        client.post('/api/case/open', json={
            'caso_id': 'CASO_LIST',
            'perito': 'Perito Test',
        })

        resp = client.get('/api/case/list')
        assert resp.status_code == 200
        data = resp.get_json()
        caso_ids = [c['caso_id'] for c in data['cases']]
        assert 'CASO_LIST' in caso_ids

    def test_full_lifecycle_open_to_close(self, client, tmp_path, monkeypatch):
        """
        TC-Lifecycle completo:
        Abrir → Verificar estructura → Verificar log → Cerrar → Verificar estado cerrado
        """
        import web_app.app as app_module
        monkeypatch.setattr(app_module, 'CASES_BASE_DIR', str(tmp_path))
        monkeypatch.setattr(app_module, 'CASES_REGISTRY',
                            str(tmp_path / 'casos_registro.json'))

        caso_id = 'CASO_FULL_LIFECYCLE'

        # 1. Abrir
        r1 = client.post('/api/case/open', json={
            'caso_id': caso_id,
            'perito': 'Perito Lifecycle',
            'clasificacion': 'Homicidio',
            'notas': 'Test de ciclo completo.',
        })
        assert r1.status_code == 200

        # 2. Verificar estructura
        carpeta = tmp_path / caso_id
        assert carpeta.exists()
        assert (carpeta / '01_Images_(Fuentes_de_datos)').exists()
        assert (carpeta / 'cadena_custodia.log').exists()

        # 3. Verificar log de apertura
        log = (carpeta / 'cadena_custodia.log').read_text()
        assert '[APERTURA]' in log
        assert caso_id in log

        # 4. Cerrar caso
        r2 = client.post('/api/case/close', json={'caso_id': caso_id})
        assert r2.status_code == 200
        assert r2.get_json()['status'] == 'success'

        # 5. Verificar log de cierre
        log_post = (carpeta / 'cadena_custodia.log').read_text()
        assert '[CIERRE]' in log_post
        assert '[HASH MAESTRO]' in log_post

        # 6. Verificar estado en registro
        r3 = client.get('/api/case/list')
        casos = r3.get_json()['cases']
        caso_cerrado = next((c for c in casos if c['caso_id'] == caso_id), None)
        assert caso_cerrado is not None
        assert caso_cerrado['estado'] == 'cerrado'
        assert caso_cerrado['hash_cierre'] is not None
