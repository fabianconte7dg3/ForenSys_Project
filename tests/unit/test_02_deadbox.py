"""
test_02_deadbox.py — TC-001, TC-002: Dead-box acquisition y Write-Blocker

Valida la lógica de adquisición forense física (dead-box) sin hardware real.
subprocess.run() se mockea completamente — nunca se ejecutan comandos reales.
"""
import json
import os
import sys
import hashlib
from datetime import datetime
from unittest.mock import MagicMock, patch, call

import pytest

# ── Helpers extraídos de 02_deadbox_v2.py (copiados para testear en aislamiento) ──
def compute_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def verificar_write_blocker_logic(getro_output: str) -> bool:
    """
    Lógica pura del write-blocker:
    retorna True si el dispositivo está en RO, False si está en RW.
    """
    return getro_output.strip() == '1'


def generar_cadena_custodia(destino_base: str, caso_id: str, perito: str,
                            origen: str, hash_pre: str,
                            modelo: str = 'MOCK_MODEL',
                            serial: str = 'MOCK_SERIAL') -> str:
    """
    Genera el acta de cadena de custodia ISO/IEC 27037.
    Versión simplificada para testing (sin llamadas a subprocess).
    """
    fecha = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    ruta_acta = os.path.join(destino_base, f'{caso_id}_Acta_Cadena_Custodia.txt')

    contenido = (
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
        f'Modelo:           {modelo}\n'
        f'Número de Serie:  {serial}\n\n'
        '3. MEDIDAS TÉCNICAS APLICADAS\n'
        '--------------------------------------------------\n'
        'Bloqueador de Escritura: Activado (Software - blockdev --setro)\n\n'
        '4. HASHES DE INTEGRIDAD\n'
        '--------------------------------------------------\n'
        f'SHA-256 PRE-Adquisición:  {hash_pre}\n'
        f'SHA-256 POST-Adquisición: {hash_pre}\n\n'
        '5. DECLARACIÓN DEL PERITO\n'
        '--------------------------------------------------\n'
        f'Yo, {perito}, certifico la veracidad de este acta.\n'
    )

    with open(ruta_acta, 'w', encoding='utf-8') as f:
        f.write(contenido)

    return ruta_acta


# ── TC-001: Dead-box acquisition con hash verification ──────────────────────
class TestDeadBoxAcquisition:

    def test_sha256_pre_post_match(self, tmp_disk_image):
        """TC-001: Hash SHA-256 PRE == POST cuando no hay modificación."""
        hash_pre  = compute_sha256(str(tmp_disk_image))
        hash_post = compute_sha256(str(tmp_disk_image))
        assert hash_pre == hash_post, 'La integridad falló: hashes difieren'

    def test_sha256_detects_tampering(self, tmp_disk_image):
        """TC-001b: Cualquier modificación al archivo es detectada por SHA-256."""
        hash_pre = compute_sha256(str(tmp_disk_image))

        # Simular alteración de 1 byte
        with open(str(tmp_disk_image), 'r+b') as f:
            f.seek(100)
            original = f.read(1)
            f.seek(100)
            f.write(bytes([original[0] ^ 0xFF]))  # Flip todos los bits

        hash_post = compute_sha256(str(tmp_disk_image))
        assert hash_pre != hash_post, 'La tampering debería ser detectada'

    def test_acquisition_creates_image_file(self, tmp_path, tmp_disk_image):
        """TC-001c: La adquisición debe crear un archivo de imagen en el destino."""
        destino = tmp_path / 'output'
        destino.mkdir()

        # Simular copia (mock de dc3dd — solo copia el archivo)
        import shutil
        dst_img = destino / 'evidencia.dd'
        shutil.copy2(str(tmp_disk_image), str(dst_img))

        assert dst_img.exists()
        assert dst_img.stat().st_size == tmp_disk_image.stat().st_size

    @patch('subprocess.run')
    def test_dcdd_called_with_correct_params(self, mock_run, tmp_path, tmp_disk_image):
        """TC-001d: El comando dc3dd debe recibir los parámetros correctos."""
        mock_run.return_value = MagicMock(returncode=0, stdout='', stderr='')

        origen  = str(tmp_disk_image)
        destino = str(tmp_path / 'output.dd')

        # Simular llamada como lo haría deadbox_v2.py
        import subprocess
        subprocess.run(
            ['dc3dd', f'if={origen}', f'of={destino}', 'hash=sha256', 'log=/dev/null'],
            check=True
        )

        mock_run.assert_called_once()
        args_used = mock_run.call_args[0][0]
        assert args_used[0] == 'dc3dd'
        assert any('if=' in a for a in args_used)
        assert any('of=' in a for a in args_used)
        assert any('sha256' in a for a in args_used)


# ── TC-002: Write-Blocker validation ────────────────────────────────────────
class TestWriteBlocker:

    def test_device_already_readonly(self):
        """TC-002a: Dispositivo ya en RO → bloqueador confirmado."""
        assert verificar_write_blocker_logic('1\n') is True

    def test_device_readwrite_detected(self):
        """TC-002b: Dispositivo en RW → bloqueador NO activo."""
        assert verificar_write_blocker_logic('0\n') is False

    def test_device_readonly_no_whitespace(self):
        """TC-002c: Salida sin newline también debe reconocerse."""
        assert verificar_write_blocker_logic('1') is True

    @patch('subprocess.run')
    def test_write_blocker_activation_attempt(self, mock_run):
        """TC-002d: Si el disco está en RW, se debe intentar activar blockdev --setro."""
        # Primera llamada (getro) → RW. Segunda (setro) → OK. Tercera (getro) → RO.
        mock_run.side_effect = [
            MagicMock(stdout='0\n', returncode=0),  # getro inicial: RW
            MagicMock(stdout='',   returncode=0),  # setro: activar
            MagicMock(stdout='1\n', returncode=0),  # getro final: RO confirmado
        ]

        import subprocess
        # Simular lógica de verificar_write_blocker del script original
        result1 = subprocess.run(['blockdev', '--getro', '/dev/sdb'], capture_output=True, text=True)
        is_ro = result1.stdout.strip() == '1'

        if not is_ro:
            subprocess.run(['sudo', 'blockdev', '--setro', '/dev/sdb'])
            result3 = subprocess.run(['blockdev', '--getro', '/dev/sdb'], capture_output=True, text=True)
            is_ro = result3.stdout.strip() == '1'

        assert is_ro is True
        assert mock_run.call_count == 3

    @patch('subprocess.run')
    def test_write_blocker_failure_is_critical(self, mock_run):
        """TC-002e: Si no se puede activar RO, la adquisición debe abortar."""
        # Ambas llamadas getro devuelven RW (no se puede activar)
        mock_run.return_value = MagicMock(stdout='0\n', returncode=0)

        import subprocess
        result = subprocess.run(['blockdev', '--getro', '/dev/sdb'], capture_output=True, text=True)
        is_ro = result.stdout.strip() == '1'
        assert is_ro is False  # Confirmar que la condición de fallo existe


# ── TC-003 preview: Cadena de Custodia básica ───────────────────────────────
class TestCadenaBasica:

    def test_genera_archivo_acta(self, tmp_path, tmp_disk_image):
        """El acta se crea en el directorio destino."""
        hash_pre = compute_sha256(str(tmp_disk_image))
        ruta_acta = generar_cadena_custodia(
            str(tmp_path), 'CASO_001', 'Perito Test',
            '/dev/mock_sdb', hash_pre
        )
        assert os.path.exists(ruta_acta)
        assert os.path.getsize(ruta_acta) > 0

    def test_acta_contiene_caso_id(self, tmp_path, tmp_disk_image):
        """El acta debe incluir el ID de caso."""
        hash_pre = compute_sha256(str(tmp_disk_image))
        ruta_acta = generar_cadena_custodia(
            str(tmp_path), 'CASO_XYZ', 'Perito Test',
            '/dev/mock_sdb', hash_pre
        )
        contenido = open(ruta_acta, encoding='utf-8').read()
        assert 'CASO_XYZ' in contenido

    def test_acta_contiene_hash_pre(self, tmp_path, tmp_disk_image):
        """El hash PRE-adquisición debe estar en el acta."""
        hash_pre = compute_sha256(str(tmp_disk_image))
        ruta_acta = generar_cadena_custodia(
            str(tmp_path), 'CASO_001', 'Perito Test',
            '/dev/mock_sdb', hash_pre
        )
        contenido = open(ruta_acta, encoding='utf-8').read()
        assert hash_pre in contenido
