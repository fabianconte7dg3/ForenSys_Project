"""
test_01_hashing.py — TC-010: Consistencia SHA-256 PRE/POST adquisición

Valida la función de hashing pura contra vectores NIST FIPS 180-4 conocidos
y contra archivos temporales.
Sin hardware, sin discos reales.
"""
import hashlib
import os
import sys

import pytest

# ── Helper local (mismo algoritmo que usa deadbox_v2.py) ────────────────────
def compute_sha256(filepath: str) -> str:
    """Calcula SHA-256 de un archivo en bloques de 8 KB."""
    h = hashlib.sha256()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


# ── TC-010a: Vectores conocidos NIST ────────────────────────────────────────
class TestSHA256KnownVectors:
    """Valida el algoritmo contra valores de referencia NIST FIPS 180-4."""

    def test_empty_string(self, tmp_path):
        """SHA-256 de archivo vacío debe ser el hash conocido del string vacío."""
        f = tmp_path / 'empty.bin'
        f.write_bytes(b'')
        result = compute_sha256(str(f))
        assert result == 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'

    def test_single_byte_0x61(self, tmp_path):
        """SHA-256 del byte 'a' (0x61) — vector NIST conocido."""
        f = tmp_path / 'single.bin'
        f.write_bytes(b'a')
        result = compute_sha256(str(f))
        assert result == 'ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb'

    def test_abc_string(self, tmp_path):
        """SHA-256 de 'abc' — vector NIST más utilizado."""
        f = tmp_path / 'abc.bin'
        f.write_bytes(b'abc')
        result = compute_sha256(str(f))
        assert result == 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'

    def test_null_bytes(self, tmp_path):
        """SHA-256 de 1024 bytes nulos — simula sector vacío de disco."""
        f = tmp_path / 'nulls.bin'
        f.write_bytes(b'\x00' * 1024)
        result = compute_sha256(str(f))
        assert result == hashlib.sha256(b'\x00' * 1024).hexdigest()

    def test_output_is_64_hex_chars(self, tmp_disk_image):
        """SHA-256 siempre produce exactamente 64 caracteres hexadecimales."""
        result = compute_sha256(str(tmp_disk_image))
        assert len(result) == 64
        assert all(c in '0123456789abcdef' for c in result)


# ── TC-010b: Consistencia PRE/POST ──────────────────────────────────────────
class TestSHA256Consistency:
    """El hash de un archivo NO debe cambiar entre dos lecturas consecutivas."""

    def test_pre_post_identical(self, tmp_disk_image):
        """Hash PRE == Hash POST cuando el archivo no se modifica."""
        hash_pre  = compute_sha256(str(tmp_disk_image))
        hash_post = compute_sha256(str(tmp_disk_image))
        assert hash_pre == hash_post, (
            f'FALLO DE INTEGRIDAD: hash cambió entre lecturas\n'
            f'  PRE:  {hash_pre}\n'
            f'  POST: {hash_post}'
        )

    def test_modification_detected(self, tmp_disk_image):
        """Un solo byte modificado DEBE producir un hash diferente."""
        hash_pre = compute_sha256(str(tmp_disk_image))

        # Modificar 1 byte en el medio del archivo
        with open(str(tmp_disk_image), 'r+b') as f:
            f.seek(5 * 1024 * 1024)  # Posición 5 MB
            f.write(b'\xFF')

        hash_post = compute_sha256(str(tmp_disk_image))
        assert hash_pre != hash_post, (
            'El hash NO debería ser igual después de modificar el archivo'
        )

    def test_small_file_consistency(self, tmp_disk_image_small):
        """Consistencia con archivo pequeño (1 KB)."""
        hashes = [compute_sha256(str(tmp_disk_image_small)) for _ in range(5)]
        assert len(set(hashes)) == 1, 'Hashes inconsistentes en lecturas repetidas'

    def test_hash_is_deterministic_across_instances(self, tmp_path):
        """Dos instancias independientes de la función producen el mismo hash."""
        data = b'ForenSys deterministic test data 12345'
        f = tmp_path / 'det.bin'
        f.write_bytes(data)

        h1 = compute_sha256(str(f))
        h2 = hashlib.sha256(data).hexdigest()
        assert h1 == h2


# ── TC-010c: Rendimiento básico ──────────────────────────────────────────────
class TestSHA256Performance:
    """Hash de 10 MB debe completarse en tiempo razonable."""

    def test_10mb_under_5_seconds(self, tmp_disk_image):
        """10 MB de datos deben hashearse en menos de 5 segundos."""
        import time
        start = time.time()
        compute_sha256(str(tmp_disk_image))
        elapsed = time.time() - start
        assert elapsed < 5.0, f'SHA-256 de 10 MB tardó {elapsed:.2f}s (límite: 5s)'
