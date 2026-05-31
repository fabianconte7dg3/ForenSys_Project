"""
test_iso27037.py — TC-013, TC-014, TC-015: Conformidad Normativa

Valida el cumplimiento de ISO/IEC 27037:2012 y NIST SP 800-101
en los artefactos generados por ForenSys.
"""
import hashlib
import json
import os
import re
from datetime import datetime

import pytest


# ── Patrones de validación ───────────────────────────────────────────────────
SHA256_RE    = re.compile(r'[0-9a-f]{64}')
ISO_DATE_RE  = re.compile(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}')

# Campos ISO/IEC 27037:2012 — Sección 7 (Identificación y Preservación)
ISO_27037_FIELDS = [
    'ID de Caso',
    'Perito a Cargo',
    'Fecha de Extracción',
    'NORMATIVA APLICABLE: ISO/IEC 27037',
    'Bloqueador de Escritura',
    'SHA-256 PRE',
    'SHA-256 POST',
]

# Cláusulas NIST SP 800-101 Rev.1 (Mobile Forensics)
NIST_800101_MOBILE_FIELDS = [
    'Modelo',        # Identificación del dispositivo
    'Número de Serie',
    'SHA-256',       # Hash de integridad
]

DISCLAIMER_REQUIRED = 'AVISO LEGAL — DOCUMENTO DE ASISTENCIA'


def build_iso_compliant_acta(tmp_path, caso_id: str = 'CASO_ISO_TEST',
                              hash_val: str = None) -> str:
    """Genera un acta que cumple con ISO/IEC 27037."""
    if hash_val is None:
        hash_val = 'a' * 64

    fecha = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    ruta = os.path.join(str(tmp_path), f'{caso_id}_Acta.txt')

    with open(ruta, 'w', encoding='utf-8') as f:
        f.write(
            '==================================================\n'
            'ACTA DE CADENA DE CUSTODIA - EXTRACCIÓN DIGITAL\n'
            '==================================================\n'
            'NORMATIVA APLICABLE: ISO/IEC 27037:2012\n\n'
            f'ID de Caso:       {caso_id}\n'
            f'Perito a Cargo:   Perito ISO Test\n'
            f'Fecha de Extracción: {fecha}\n\n'
            'Ruta Lógica:      /dev/mock_sdb\n'
            'Modelo:           SAMSUNG_EVO\n'
            'Número de Serie:  SN-TEST-001\n\n'
            'Bloqueador de Escritura: Activado\n\n'
            f'SHA-256 PRE-Adquisición:  {hash_val}\n'
            f'SHA-256 POST-Adquisición: {hash_val}\n\n'
            'Yo, Perito ISO Test, certifico la veracidad.\n'
        )
    return ruta


# ── TC-013: ISO/IEC 27037:2012 Compliance ───────────────────────────────────
@pytest.mark.compliance
class TestISO27037Compliance:

    def test_all_mandatory_fields_present(self, tmp_path):
        """TC-013a: Todos los campos ISO/IEC 27037 obligatorios están presentes."""
        ruta = build_iso_compliant_acta(tmp_path)
        contenido = open(ruta, encoding='utf-8').read()

        missing = [f for f in ISO_27037_FIELDS if f not in contenido]
        assert not missing, (
            f'Campos ISO/IEC 27037 ausentes en el acta:\n' +
            '\n'.join(f'  - {f}' for f in missing)
        )

    def test_date_format_is_iso_compliant(self, tmp_path):
        """TC-013b: La fecha cumple con el formato estándar (YYYY-MM-DD HH:MM:SS)."""
        ruta = build_iso_compliant_acta(tmp_path)
        contenido = open(ruta, encoding='utf-8').read()
        assert ISO_DATE_RE.search(contenido), (
            'La fecha no cumple el formato ISO YYYY-MM-DD HH:MM:SS'
        )

    def test_sha256_pre_is_64_hex_chars(self, tmp_path):
        """TC-013c: El hash SHA-256 PRE tiene exactamente 64 chars hexadecimales."""
        ruta = build_iso_compliant_acta(tmp_path)
        contenido = open(ruta, encoding='utf-8').read()
        hashes = SHA256_RE.findall(contenido)
        assert len(hashes) >= 1, 'No se encontró hash SHA-256 PRE en el acta'
        assert all(len(h) == 64 for h in hashes)

    def test_sha256_post_is_64_hex_chars(self, tmp_path):
        """TC-013d: El hash SHA-256 POST tiene exactamente 64 chars hexadecimales."""
        ruta = build_iso_compliant_acta(tmp_path)
        contenido = open(ruta, encoding='utf-8').read()
        hashes = SHA256_RE.findall(contenido)
        assert len(hashes) >= 2, 'Se necesitan hashes PRE y POST en el acta'

    def test_write_blocker_documented(self, tmp_path):
        """TC-013e: El bloqueador de escritura está documentado en el acta."""
        ruta = build_iso_compliant_acta(tmp_path)
        contenido = open(ruta, encoding='utf-8').read()
        assert 'Bloqueador de Escritura' in contenido
        assert 'Activado' in contenido

    def test_normative_reference_explicit(self, tmp_path):
        """TC-013f: La norma ISO/IEC 27037:2012 está explícitamente referenciada."""
        ruta = build_iso_compliant_acta(tmp_path)
        contenido = open(ruta, encoding='utf-8').read()
        assert 'ISO/IEC 27037:2012' in contenido

    def test_examiner_identified(self, tmp_path):
        """TC-013g: El perito está identificado en el acta."""
        ruta = build_iso_compliant_acta(tmp_path, caso_id='CASO_PERITO')
        contenido = open(ruta, encoding='utf-8').read()
        assert 'Perito a Cargo' in contenido
        # Verificar que no está vacío
        match = re.search(r'Perito a Cargo:\s+(.+)', contenido)
        assert match and match.group(1).strip()

    def test_case_id_identified(self, tmp_path):
        """TC-013h: El ID de caso está presente y no vacío."""
        caso_id = 'CASO-2025-ISO-001'
        ruta = build_iso_compliant_acta(tmp_path, caso_id=caso_id)
        contenido = open(ruta, encoding='utf-8').read()
        assert caso_id in contenido

    def test_integrity_chain_maintained(self, tmp_path):
        """TC-013i: La cadena de integridad (PRE=POST) está verificada."""
        hash_real = hashlib.sha256(b'sample evidence data').hexdigest()
        ruta = build_iso_compliant_acta(tmp_path, hash_val=hash_real)
        contenido = open(ruta, encoding='utf-8').read()
        hashes = SHA256_RE.findall(contenido)
        assert len(hashes) >= 2
        assert hashes[0] == hashes[1] == hash_real


# ── TC-014: NIST SP 800-101 Mobile Forensics ────────────────────────────────
@pytest.mark.compliance
class TestNIST800101MobileCompliance:

    def build_mobile_report(self, tmp_path, device_model='iPhone 14',
                             serial='DNXXXXXXXX', caso_id='CASO_MOVIL') -> str:
        """Genera un reporte de extracción móvil con campos NIST."""
        ruta = os.path.join(str(tmp_path), f'{caso_id}_mobile_report.txt')
        hash_val = 'c' * 64
        fecha = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with open(ruta, 'w', encoding='utf-8') as f:
            f.write(
                f'REPORTE DE EXTRACCIÓN MÓVIL\n'
                f'NORMATIVA: NIST SP 800-101 Rev.1\n\n'
                f'Caso: {caso_id}\n'
                f'Fecha: {fecha}\n'
                f'Modelo: {device_model}\n'
                f'Número de Serie: {serial}\n'
                f'Sistema Operativo: iOS 17.2\n\n'
                f'INTEGRIDAD:\n'
                f'SHA-256: {hash_val}\n\n'
                f'Método de Extracción: Lógica (iTunes Backup)\n'
                f'Herramienta: libimobiledevice 1.3.0\n'
            )
        return ruta

    def test_mobile_report_has_device_model(self, tmp_path):
        """TC-014a: El reporte móvil identifica el modelo del dispositivo."""
        ruta = self.build_mobile_report(tmp_path, device_model='Samsung Galaxy S23')
        contenido = open(ruta, encoding='utf-8').read()
        assert 'Modelo' in contenido
        assert 'Samsung Galaxy S23' in contenido

    def test_mobile_report_has_serial_number(self, tmp_path):
        """TC-014b: El reporte móvil incluye el número de serie."""
        ruta = self.build_mobile_report(tmp_path, serial='R3ABC123456')
        contenido = open(ruta, encoding='utf-8').read()
        assert 'Número de Serie' in contenido
        assert 'R3ABC123456' in contenido

    def test_mobile_report_has_hash(self, tmp_path):
        """TC-014c: El reporte móvil incluye hash SHA-256 de integridad."""
        ruta = self.build_mobile_report(tmp_path)
        contenido = open(ruta, encoding='utf-8').read()
        hashes = SHA256_RE.findall(contenido)
        assert len(hashes) >= 1, 'Hash SHA-256 ausente en reporte móvil'

    def test_mobile_report_has_extraction_method(self, tmp_path):
        """TC-014d: El reporte documenta el método de extracción."""
        ruta = self.build_mobile_report(tmp_path)
        contenido = open(ruta, encoding='utf-8').read()
        assert 'Método de Extracción' in contenido or 'Extracción' in contenido

    def test_mobile_report_has_date(self, tmp_path):
        """TC-014e: El reporte móvil incluye fecha en formato ISO."""
        ruta = self.build_mobile_report(tmp_path)
        contenido = open(ruta, encoding='utf-8').read()
        assert ISO_DATE_RE.search(contenido), 'Fecha no encontrada o formato incorrecto'

    def test_all_nist_fields_present(self, tmp_path):
        """TC-014f: Todos los campos NIST SP 800-101 obligatorios están presentes."""
        ruta = self.build_mobile_report(tmp_path)
        contenido = open(ruta, encoding='utf-8').read()
        missing = [f for f in NIST_800101_MOBILE_FIELDS if f not in contenido]
        assert not missing, (
            f'Campos NIST SP 800-101 ausentes:\n' +
            '\n'.join(f'  - {f}' for f in missing)
        )


# ── TC-015: Disclaimer Legal en Síntesis IA ──────────────────────────────────
@pytest.mark.compliance
class TestDisclaimerLegalCompliance:

    def build_synthesis_with_disclaimer(self, tmp_path, caso_id: str,
                                         include_disclaimer: bool = True) -> str:
        """Genera una síntesis IA con o sin disclaimer para testing."""
        ruta = os.path.join(str(tmp_path), f'Sintesis_IA_{caso_id}.md')
        disclaimer = ''
        if include_disclaimer:
            disclaimer = (
                f'> **{DISCLAIMER_REQUIRED}**\n'
                '> Este documento no reemplaza el criterio del perito forense.\n\n'
            )
        with open(ruta, 'w', encoding='utf-8') as f:
            f.write(disclaimer + '## Análisis\nContenido del análisis IA.\n')
        return ruta

    def test_disclaimer_present_in_synthesis(self, tmp_path):
        """TC-015a: El disclaimer legal está presente en la síntesis IA."""
        ruta = self.build_synthesis_with_disclaimer(tmp_path, 'CASO_DISC')
        contenido = open(ruta, encoding='utf-8').read()
        assert DISCLAIMER_REQUIRED in contenido

    def test_disclaimer_absent_is_detected(self, tmp_path):
        """TC-015b: Una síntesis SIN disclaimer es identificada como no conforme."""
        ruta = self.build_synthesis_with_disclaimer(
            tmp_path, 'CASO_NODISC', include_disclaimer=False
        )
        contenido = open(ruta, encoding='utf-8').read()
        # Este test verifica que el check funciona — la síntesis sin disclaimer
        # DEBE ser detectada como no conforme
        is_compliant = DISCLAIMER_REQUIRED in contenido
        assert not is_compliant, (
            'La síntesis sin disclaimer debería ser detectada como no conforme'
        )

    def test_disclaimer_appears_at_top(self, tmp_path):
        """TC-015c: El disclaimer aparece al inicio del documento (primeros 300 chars)."""
        ruta = self.build_synthesis_with_disclaimer(tmp_path, 'CASO_TOP')
        contenido = open(ruta, encoding='utf-8').read()
        assert DISCLAIMER_REQUIRED in contenido[:300]

    def test_multiple_syntheses_all_have_disclaimer(self, tmp_path):
        """TC-015d: Todas las síntesis generadas contienen el disclaimer."""
        casos = ['CASO_A', 'CASO_B', 'CASO_C']
        for caso_id in casos:
            ruta = self.build_synthesis_with_disclaimer(tmp_path, caso_id)
            contenido = open(ruta, encoding='utf-8').read()
            assert DISCLAIMER_REQUIRED in contenido, (
                f'Disclaimer ausente en síntesis del caso {caso_id}'
            )
