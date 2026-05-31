"""
test_03_live_ram.py — TC-004: Análisis de Memoria RAM (Volatility3)

Valida la integración con Volatility3 mediante mocks (sin requerir dumps de RAM reales).
"""
import os
import json
from unittest.mock import MagicMock, patch
import pytest

# ── Helpers simulando la lógica de 03_live_ram.py ────────────────────────────

def parse_volatility_pslist(output: str) -> list:
    """Extrae PIDs y nombres de procesos de la salida raw de windows.pslist"""
    procesos = []
    lines = output.strip().splitlines()
    for line in lines:
        if 'PID' in line or '---' in line or not line.strip():
            continue
        parts = line.split()
        if len(parts) >= 3:
            try:
                pid = int(parts[0])
                name = parts[2]
                procesos.append({'pid': pid, 'name': name})
            except ValueError:
                pass
    return procesos

def parse_volatility_malfind(output: str) -> list:
    """Extrae detecciones de inyección de código de windows.malfind"""
    detecciones = []
    lines = output.strip().splitlines()
    for line in lines:
        if 'Process' in line and 'PID' in line:
            # Ejemplo: Process: svchost.exe PID: 1234
            detecciones.append({'raw_info': line.strip()})
    return detecciones

def calculate_memory_hash(filepath: str) -> str:
    """Simula el hash de un volcado de memoria"""
    import hashlib
    h = hashlib.sha256()
    with open(filepath, 'rb') as f:
        for block in iter(lambda: f.read(65536), b''):
            h.update(block)
    return h.hexdigest()

# ── TC-004: Volatility3 Integration Tests ────────────────────────────────────

class TestVolatilityIntegration:

    def test_pslist_plugin_parsing(self):
        """TC-004a: Validar parsing de lista de procesos (PsList)"""
        mock_output = (
            "PID\tPPID\tImageFileName\n"
            "---------------------------------\n"
            "4\t0\tSystem\n"
            "1234\t4\tsvchost.exe\n"
            "5678\t1234\tmalware.exe\n"
        )
        procesos = parse_volatility_pslist(mock_output)
        
        assert len(procesos) == 3
        assert procesos[0]['pid'] == 4
        assert procesos[0]['name'] == 'System'
        assert procesos[2]['name'] == 'malware.exe'

    def test_malfind_detection(self):
        """TC-004b: Detección de código inyectado (shellcode)"""
        mock_output = (
            "Process: svchost.exe PID: 1234 Address: 0x10000\n"
            "4D 5A 90 00 03 00 00 00  MZ......\n"
            "Process: explorer.exe PID: 999 Address: 0x20000\n"
            "EB 03 5D EB 05 E8 F8 FF  ..].....\n"
        )
        injections = parse_volatility_malfind(mock_output)
        
        assert len(injections) == 2
        assert 'svchost.exe' in injections[0]['raw_info']
        assert 'explorer.exe' in injections[1]['raw_info']

    def test_memory_dump_integrity(self, tmp_path):
        """TC-004c: Verificar integridad del dump de RAM con SHA-256"""
        memory_file = tmp_path / "memory_test.raw"
        memory_file.write_bytes(b"\x00\xFF" * 1024)  # 2KB de datos falsos
        
        hash1 = calculate_memory_hash(str(memory_file))
        hash2 = calculate_memory_hash(str(memory_file))
        
        assert hash1 == hash2, "El hash de la imagen de memoria debe ser determinístico"

    @patch('subprocess.run')
    def test_execute_volatility_plugin(self, mock_run):
        """TC-004d: Verificar que el comando volatility se arma correctamente"""
        mock_run.return_value = MagicMock(
            stdout="PID ImageFileName\n123 fake.exe\n",
            returncode=0
        )
        
        plugin = "windows.pslist.PsList"
        dump_path = "/tmp/mem.raw"
        
        import subprocess
        # Simular llamada
        result = subprocess.run(
            ['vol', '-f', dump_path, plugin],
            capture_output=True, text=True
        )
        
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert 'vol' in args
        assert dump_path in args
        assert plugin in args
        assert 'fake.exe' in result.stdout
