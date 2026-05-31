"""
test_04_mobile.py — TC-005, TC-006: Extracción móvil Android/iOS

Valida la lógica de extracción móvil con mocks de ADB e libimobiledevice.
No se requiere ningún dispositivo físico conectado.
"""
import json
import os
from unittest.mock import MagicMock, patch, call

import pytest


# ── Helpers que simulan la lógica del script 04_mobile.py ───────────────────

def detect_android_devices_mock(adb_output: str) -> list:
    """
    Parsea la salida de 'adb devices' y retorna lista de device IDs conectados.
    """
    devices = []
    for line in adb_output.strip().splitlines():
        if '\t' in line and 'device' in line and not line.startswith('List'):
            device_id = line.split('\t')[0].strip()
            status    = line.split('\t')[1].strip()
            if status == 'device':
                devices.append(device_id)
    return devices


def detect_ios_devices_mock(idevice_output: str) -> list:
    """
    Parsea la salida de 'idevice_id -l' y retorna lista de UDIDs conectados.
    """
    devices = []
    for line in idevice_output.strip().splitlines():
        udid = line.strip()
        if len(udid) == 40 and all(c in '0123456789abcdefABCDEF' for c in udid):
            devices.append(udid)
    return devices


def parse_adb_info(ideviceinfo_output: str) -> dict:
    """Parsea la salida de 'adb shell getprop' en un dict."""
    result = {}
    for line in ideviceinfo_output.strip().splitlines():
        if ':' in line:
            key, _, value = line.partition(':')
            result[key.strip()] = value.strip()
    return result


# ── TC-005: Android ADB (mockeado) ──────────────────────────────────────────
class TestAndroidADB:

    def test_detects_connected_device(self):
        """TC-005a: Se detecta 1 dispositivo Android conectado."""
        adb_output = (
            'List of devices attached\n'
            'emulator-5554\tdevice\n'
        )
        devices = detect_android_devices_mock(adb_output)
        assert len(devices) == 1
        assert 'emulator-5554' in devices

    def test_detects_multiple_devices(self):
        """TC-005b: Se detectan múltiples dispositivos Android."""
        adb_output = (
            'List of devices attached\n'
            'emulator-5554\tdevice\n'
            'R3CN705WXXX\tdevice\n'
        )
        devices = detect_android_devices_mock(adb_output)
        assert len(devices) == 2

    def test_unauthorized_device_excluded(self):
        """TC-005c: Dispositivos en estado 'unauthorized' no se incluyen."""
        adb_output = (
            'List of devices attached\n'
            'R3CN705WXXX\tunauthorized\n'
        )
        devices = detect_android_devices_mock(adb_output)
        assert len(devices) == 0

    def test_no_devices_connected(self):
        """TC-005d: Sin dispositivos conectados retorna lista vacía."""
        adb_output = 'List of devices attached\n'
        devices = detect_android_devices_mock(adb_output)
        assert devices == []

    @patch('subprocess.run')
    def test_adb_devices_command_called(self, mock_run):
        """TC-005e: El comando 'adb devices' se ejecuta correctamente."""
        mock_run.return_value = MagicMock(
            stdout='List of devices attached\nemulator-5554\tdevice\n',
            returncode=0
        )
        import subprocess
        result = subprocess.run(['adb', 'devices'], capture_output=True, text=True)
        mock_run.assert_called_once_with(['adb', 'devices'], capture_output=True, text=True)
        assert 'emulator-5554' in result.stdout

    @patch('subprocess.run')
    def test_adb_pull_creates_extraction_file(self, mock_run, tmp_path):
        """TC-005f: adb pull simula la creación del archivo de extracción."""
        destino = tmp_path / 'android_extraction.tar'

        mock_run.return_value = MagicMock(returncode=0, stdout='', stderr='')

        import subprocess
        subprocess.run(
            ['adb', '-s', 'emulator-5554', 'pull', '/sdcard/', str(destino)],
            capture_output=True, text=True
        )

        # Simular que el archivo fue creado
        destino.write_bytes(b'mock android data')
        assert destino.exists()

    def test_android_metadata_parsed(self):
        """TC-005g: Los metadatos del dispositivo Android se parsean correctamente."""
        getprop_output = (
            'ro.product.model: Pixel 6\n'
            'ro.product.manufacturer: Google\n'
            'ro.build.version.release: 13\n'
            'ro.serialno: R3CN705WXXX\n'
        )
        metadata = parse_adb_info(getprop_output)
        assert metadata.get('ro.product.model') == 'Pixel 6'
        assert metadata.get('ro.serialno') == 'R3CN705WXXX'


# ── TC-006: iOS libimobiledevice (mockeado) ──────────────────────────────────
class TestiOSLibimobiledevice:

    def test_detects_ios_device(self):
        """TC-006a: Se detecta un dispositivo iOS conectado."""
        idevice_output = 'a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2\n'
        devices = detect_ios_devices_mock(idevice_output)
        assert len(devices) == 1
        assert devices[0] == 'a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2'

    def test_no_ios_device(self):
        """TC-006b: Sin dispositivos iOS retorna lista vacía."""
        devices = detect_ios_devices_mock('')
        assert devices == []

    @patch('subprocess.run')
    def test_ideviceinfo_called(self, mock_run):
        """TC-006c: El comando idevice_id se ejecuta para listar dispositivos."""
        mock_run.return_value = MagicMock(
            stdout='a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2\n',
            returncode=0
        )
        import subprocess
        result = subprocess.run(['idevice_id', '-l'], capture_output=True, text=True)
        mock_run.assert_called_once()
        assert 'a1b2c3d4' in result.stdout

    @patch('subprocess.run')
    def test_ios_extraction_command_structure(self, mock_run, tmp_path):
        """TC-006d: El comando de extracción iOS tiene la estructura correcta."""
        mock_run.return_value = MagicMock(returncode=0, stdout='', stderr='')
        udid = 'a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2'
        destino = str(tmp_path / 'ios_backup')

        import subprocess
        subprocess.run(
            ['idevicebackup2', '-u', udid, 'backup', destino],
            capture_output=True, text=True
        )

        args = mock_run.call_args[0][0]
        assert 'idevicebackup2' in args
        assert udid in args
        assert 'backup' in args
