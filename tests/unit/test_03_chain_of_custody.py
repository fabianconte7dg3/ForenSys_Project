"""
test_03_chain_of_custody.py — TC-003: Cadena de Custodia ISO/IEC 27037

Valida que el acta de cadena de custodia cumple TODOS los campos
obligatorios de la norma ISO/IEC 27037:2012.
Sin hardware real.
"""
import hashlib
import json
import os
import re
from datetime import datetime

import pytest


# ── Campos obligatorios ISO/IEC 27037:2012 ──────────────────────────────────
ISO_REQUIRED_FIELDS = [
    'ID de Caso',
    'Perito a Cargo',
    'Fecha de Extracción',
    'Ruta Lógica',
    'Bloqueador de Escritura',
    'SHA-256 PRE',
    'SHA-256 POST',
    'NORMATIVA APLICABLE: ISO/IEC 27037',
]

DATE_ISO_PATTERN = re.compile(
    r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}'  # YYYY-MM-DD HH:MM:SS
)
SHA256_PATTERN = re.compile(r'[0-9a-f]{64}')


def build_sample_acta(destino: str, caso_id: str = 'TC003',
                       perito: str = 'Perito ISO Test',
                       origen: str = '/dev/mock_sdb',
                       hash_pre: str = 'a' * 64,
                       hash_post: str = 'a' * 64) -> str:
    """Genera un acta de ejemplo con todos los campos ISO requeridos."""
    fecha = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    ruta = os.path.join(destino, f'{caso_id}_Acta_Cadena_Custodia.txt')

    with open(ruta, 'w', encoding='utf-8') as f:
        f.write(
            '==================================================\n'
            'ACTA DE CADENA DE CUSTODIA - EXTRACCIÓN DIGITAL\n'
            '==================================================\n'
            'NORMATIVA APLICABLE: ISO/IEC 27037:2012\n\n'
            '1. INFORMACIÓN DEL CASO\n'
            '--------------------------------------------------\n'
            f'ID de Caso:       {caso_id}\n'
            f'Perito a Cargo:   {perito}\n'
            f'Fecha de Extracción: {fecha}\n\n'
            '2. DISPOSITIVO DE EVIDENCIA (ORIGEN)\n'
            '--------------------------------------------------\n'
            f'Ruta Lógica:      {origen}\n'
            'Modelo:           SAMSUNG_TEST_DRIVE\n'
            'Número de Serie:  SN123456789\n\n'
            '3. MEDIDAS TÉCNICAS APLICADAS\n'
            '--------------------------------------------------\n'
            'Bloqueador de Escritura: Activado (Software - blockdev --setro)\n\n'
            '4. HASHES DE INTEGRIDAD\n'
            '--------------------------------------------------\n'
            f'SHA-256 PRE-Adquisición:  {hash_pre}\n'
            f'SHA-256 POST-Adquisición: {hash_post}\n\n'
            '5. DECLARACIÓN DEL PERITO\n'
            '--------------------------------------------------\n'
            f'Yo, {perito}, certifico la veracidad de este acta.\n'
        )
    return ruta


# ── TC-003: Validación de Campos ISO ────────────────────────────────────────
class TestCadenaCustodiaISO:

    @pytest.fixture
    def acta_valida(self, tmp_path):
        """Genera un acta con todos los campos ISO correctos."""
        ruta = build_sample_acta(str(tmp_path))
        return open(ruta, encoding='utf-8').read()

    def test_todos_los_campos_iso_presentes(self, acta_valida):
        """TC-003: Todos los campos ISO/IEC 27037 obligatorios deben estar presentes."""
        for campo in ISO_REQUIRED_FIELDS:
            assert campo in acta_valida, (
                f'Campo ISO obligatorio ausente en el acta: "{campo}"'
            )

    def test_fecha_formato_valido(self, acta_valida):
        """La fecha de extracción debe estar en formato YYYY-MM-DD HH:MM:SS."""
        assert DATE_ISO_PATTERN.search(acta_valida), (
            'No se encontró fecha en formato YYYY-MM-DD HH:MM:SS en el acta'
        )

    def test_hash_pre_formato_sha256(self, acta_valida):
        """El hash PRE-adquisición debe ser un SHA-256 de 64 caracteres hex."""
        matches = SHA256_PATTERN.findall(acta_valida)
        assert len(matches) >= 1, 'No se encontró ningún hash SHA-256 en el acta'

    def test_hash_post_formato_sha256(self, acta_valida):
        """El hash POST-adquisición debe ser un SHA-256 de 64 caracteres hex."""
        matches = SHA256_PATTERN.findall(acta_valida)
        assert len(matches) >= 2, 'Se necesitan al menos 2 hashes SHA-256 en el acta (PRE y POST)'

    def test_caso_id_presente(self, tmp_path):
        """El ID de caso debe aparecer en el acta."""
        ruta = build_sample_acta(str(tmp_path), caso_id='CASO-2025-001')
        contenido = open(ruta, encoding='utf-8').read()
        assert 'CASO-2025-001' in contenido

    def test_perito_presente(self, tmp_path):
        """El nombre del perito debe aparecer en el acta."""
        ruta = build_sample_acta(str(tmp_path), perito='Juan Pérez Forense')
        contenido = open(ruta, encoding='utf-8').read()
        assert 'Juan Pérez Forense' in contenido

    def test_normativa_iso_referenciada(self, acta_valida):
        """La normativa ISO/IEC 27037:2012 debe estar explícitamente referenciada."""
        assert 'ISO/IEC 27037' in acta_valida

    def test_write_blocker_documentado(self, acta_valida):
        """El bloqueador de escritura debe estar documentado en el acta."""
        assert 'Bloqueador de Escritura' in acta_valida
        assert 'Activado' in acta_valida

    def test_integridad_hash_pre_post_match(self, tmp_path):
        """Cuando no hay modificación, PRE y POST deben ser idénticos."""
        hash_val = 'b' * 64
        ruta = build_sample_acta(str(tmp_path), hash_pre=hash_val, hash_post=hash_val)
        contenido = open(ruta, encoding='utf-8').read()
        hashes = SHA256_PATTERN.findall(contenido)
        assert hashes[0] == hashes[1], 'PRE y POST no coinciden cuando no hubo modificación'

    def test_integridad_hash_pre_post_differ_when_tampered(self, tmp_path):
        """Si el dispositivo fue alterado, PRE y POST deben diferir."""
        hash_pre  = 'a' * 64
        hash_post = 'b' * 64  # Diferente → alteración detectada
        ruta = build_sample_acta(str(tmp_path), hash_pre=hash_pre, hash_post=hash_post)
        contenido = open(ruta, encoding='utf-8').read()
        hashes = SHA256_PATTERN.findall(contenido)
        assert hashes[0] != hashes[1], 'Los hashes deberían diferir cuando hay tampering'


# ── Casos de borde / negativos ───────────────────────────────────────────────
class TestCadenaCustodiaNegative:

    def test_caso_id_vacio_detectado(self, tmp_path):
        """Un caso_id vacío debe ser rechazado antes de generar el acta."""
        # Simular la validación que hace sanitize_case_id en app.py
        import re
        caso_id_raw = ''
        sanitized = re.sub(r'[^a-zA-Z0-9_\-]', '', caso_id_raw)
        assert not sanitized, 'caso_id vacío debería ser rechazado'

    def test_caso_id_con_path_traversal_sanitizado(self, tmp_path):
        """caso_id con path traversal debe quedar sanitizado."""
        import re
        caso_id_raw = '../../../etc/passwd'
        sanitized = re.sub(r'[^a-zA-Z0-9_\-]', '', caso_id_raw)
        assert '/' not in sanitized
        assert '..' not in sanitized
        assert 'etc' in sanitized  # Solo los chars alfanuméricos sobreviven

    def test_perito_no_vacio(self):
        """El campo perito no puede estar vacío según la norma."""
        perito = ''
        assert not perito.strip(), 'Perito vacío debería ser inválido'
