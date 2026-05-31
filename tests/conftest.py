"""
conftest.py — Fixtures globales para ForenSys Test Suite

PRINCIPIO: Ningún fixture toca hardware real, discos reales ni el sistema de
producción. Todo se ejecuta en directorios temporales destruidos al finalizar.
"""
import hashlib
import json
import os
import sys
import pytest

# ── Asegurar que la web_app y scripts sean importables ──────────────────────
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
WEBAPP_DIR   = os.path.join(PROJECT_ROOT, 'web_app')
SCRIPTS_DIR  = os.path.join(PROJECT_ROOT, 'scripts')

sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, WEBAPP_DIR)
sys.path.insert(0, SCRIPTS_DIR)


# ── Fixture: Flask Test Client ───────────────────────────────────────────────
@pytest.fixture(scope='session')
def flask_app(tmp_path_factory):
    """
    Instancia de Flask en modo test.
    - CASES_BASE_DIR apunta a un directorio temporal (no al proyecto real)
    - SYSTEM_DISK_NAMES mockeado para no depender del hardware de la máquina
    """
    # Directorio temporal para casos durante los tests
    test_cases_dir = tmp_path_factory.mktemp('ForenSys_TestCases')

    # Parchear variables de entorno ANTES de importar app
    import web_app.app as app_module
    original_cases   = app_module.CASES_BASE_DIR
    original_registry = app_module.CASES_REGISTRY
    original_system  = app_module.SYSTEM_DISK_NAMES

    app_module.CASES_BASE_DIR  = str(test_cases_dir)
    app_module.CASES_REGISTRY  = str(test_cases_dir / 'casos_registro.json')
    app_module.SYSTEM_DISK_NAMES = {'sda', 'sda1', 'sda2'}  # Disco "del SO" simulado

    app_module.app.config['TESTING'] = True
    app_module.app.config['WTF_CSRF_ENABLED'] = False

    yield app_module.app

    # Restaurar estado original
    app_module.CASES_BASE_DIR   = original_cases
    app_module.CASES_REGISTRY   = original_registry
    app_module.SYSTEM_DISK_NAMES = original_system


@pytest.fixture
def client(flask_app):
    """Cliente HTTP de Flask para los tests (sin servidor real)."""
    with flask_app.test_client() as c:
        yield c


# ── Fixture: Imagen de disco ficticia ───────────────────────────────────────
@pytest.fixture
def tmp_disk_image(tmp_path):
    """
    Crea una imagen binaria temporal de 10 MB con bytes pseudo-aleatorios.
    Simula un disco de evidencia sin tocar /dev/ real.
    """
    import random
    image_path = tmp_path / 'evidence_disk.img'
    size = 10 * 1024 * 1024  # 10 MB
    # Seed fijo para reproducibilidad en los tests
    rng = random.Random(0xDEADBEEF)
    data = bytes(rng.getrandbits(8) for _ in range(size))
    image_path.write_bytes(data)
    return image_path


@pytest.fixture
def tmp_disk_image_small(tmp_path):
    """Imagen de disco de 1 KB para tests rápidos de hashing."""
    image_path = tmp_path / 'small_disk.img'
    image_path.write_bytes(b'\xAB\xCD\xEF' * 341 + b'\x00')  # 1024 bytes
    return image_path


# ── Fixture: Estructura de caso forense ─────────────────────────────────────
@pytest.fixture
def tmp_caso(tmp_path):
    """
    Crea una estructura de carpetas de caso forense completa en tmp_path.
    Incluye contexto_incidente.json y cadena_custodia.log iniciales.
    Útil para tests que necesitan un caso ya existente.
    """
    caso_id = 'TEST_CASO_001'
    carpeta_caso = tmp_path / caso_id

    subcarpetas = [
        carpeta_caso / '01_Images_(Fuentes_de_datos)',
        carpeta_caso / '02_Views_(Vistas)',
        carpeta_caso / '03_Results_(Resultados_Extraidos)',
        carpeta_caso / '04_Archivos_Borrados_Recuperados',
    ]
    for sub in subcarpetas:
        sub.mkdir(parents=True, exist_ok=True)

    # contexto_incidente.json
    contexto = {
        'caso_id': caso_id,
        'perito': 'Perito Test',
        'clasificacion': 'Prueba automatizada',
        'timestamp': '2025-01-01T00:00:00+00:00',
        'notas': 'Caso generado automáticamente por pytest.',
    }
    ruta_contexto = carpeta_caso / '03_Results_(Resultados_Extraidos)' / 'contexto_incidente.json'
    ruta_contexto.write_text(json.dumps(contexto, indent=2), encoding='utf-8')

    # cadena_custodia.log inicial
    ruta_custodia = carpeta_caso / 'cadena_custodia.log'
    ruta_custodia.write_text(
        f'[2025-01-01T00:00:00+00:00] [APERTURA] Caso {caso_id} abierto por perito Test\n'
        '[2025-01-01T00:00:00+00:00] [INTEGRIDAD] SHA-256 de contexto: ' + 'a' * 64 + '\n',
        encoding='utf-8'
    )

    return {
        'caso_id': caso_id,
        'carpeta': carpeta_caso,
        'ruta_contexto': ruta_contexto,
        'ruta_custodia': ruta_custodia,
    }


# ── Fixture: Mock de respuesta Ollama ───────────────────────────────────────
@pytest.fixture
def mock_ollama_response():
    """JSON que simula una respuesta exitosa de Ollama /api/generate."""
    return {
        'model': 'gemma3:4b',
        'response': (
            '## Resumen Ejecutivo\n'
            'El análisis revela patrones de acceso inusuales.\n\n'
            '## Hallazgos Principales\n'
            '- Actividad sospechosa detectada en logs del sistema.\n\n'
            '## AVISO LEGAL — DOCUMENTO DE ASISTENCIA\n'
            'Este documento no reemplaza el criterio del perito.\n'
        ),
        'done': True,
    }


# ── Fixture: Datos OSINT de ejemplo ─────────────────────────────────────────
@pytest.fixture
def mock_osint_data():
    """Simula resultados de Maigret con perfiles de alta y baja confianza."""
    return {
        'username': 'test_alias',
        'sites': {
            'Twitter': {'status': {'status': 'Claimed'}, 'url_user': 'https://twitter.com/test_alias'},
            'GitHub':  {'status': {'status': 'Claimed'}, 'url_user': 'https://github.com/test_alias'},
            'SitioFalso': {'status': {'status': 'Available'}, 'url_user': ''},
        }
    }


# ── Fixture: Reporte maestro ficticio ───────────────────────────────────────
@pytest.fixture
def tmp_reporte_maestro(tmp_path):
    """Crea un Reporte_Forense_Maestro.txt ficticio para tests de PDF."""
    content = (
        '============================\n'
        'REPORTE FORENSE MAESTRO\n'
        '============================\n'
        'Caso: TEST_CASO_001\n'
        'Perito: Perito Test\n'
        'Fecha: 2025-01-01\n\n'
        'HALLAZGOS:\n'
        '- Archivo sospechoso detectado: malware_sample.exe\n'
        '- Actividad USB registrada el 2025-01-01\n'
    )
    ruta = tmp_path / 'Reporte_Forense_Maestro.txt'
    ruta.write_text(content, encoding='utf-8')
    return ruta
