"""
test_benchmarks.py — TC-011, TC-Perf-IA: Benchmarks de Rendimiento

Tests de rendimiento marcados con @pytest.mark.slow.
Solo se ejecutan manualmente en la Raspberry Pi 5 real:
    pytest tests/performance/ -m slow -v

NO se ejecutan en el pipeline normal (pytest tests/).
"""
import hashlib
import os
import time

import psutil
import pytest


# ── TC-011: Uso de Memoria bajo Carga ────────────────────────────────────────
@pytest.mark.slow
class TestMemoryUsage:

    def test_sha256_1gb_under_120_seconds(self, tmp_path):
        """TC-011a: SHA-256 de imagen de 1 GB debe completarse en < 120s en RPi5."""
        # Crear archivo de 1 GB
        gb_file = tmp_path / 'test_1gb.img'
        chunk = b'\xAB\xCD' * (1024 * 512)  # 1 MB chunk
        with open(str(gb_file), 'wb') as f:
            for _ in range(1024):  # 1024 * 1 MB = 1 GB
                f.write(chunk)

        start = time.time()
        h = hashlib.sha256()
        with open(str(gb_file), 'rb') as f:
            for block in iter(lambda: f.read(65536), b''):
                h.update(block)
        elapsed = time.time() - start

        assert elapsed < 120.0, (
            f'SHA-256 de 1 GB tardó {elapsed:.1f}s — límite RPi5: 120s'
        )

    def test_flask_memory_under_500mb(self, flask_app):
        """TC-011b: La app Flask no debe superar 500 MB de RAM en reposo."""
        process = psutil.Process(os.getpid())
        mem_mb = process.memory_info().rss / (1024 * 1024)
        assert mem_mb < 500, (
            f'Uso de memoria actual: {mem_mb:.1f} MB — límite: 500 MB'
        )

    def test_flask_50_requests_response_time(self, client):
        """TC-011c: 50 requests GET al home deben completarse en < 10s."""
        start = time.time()
        for _ in range(50):
            resp = client.get('/')
            assert resp.status_code == 200
        elapsed = time.time() - start
        assert elapsed < 10.0, (
            f'50 requests tardaron {elapsed:.2f}s — límite: 10s'
        )


# ── Benchmarks de hashing (sin marca slow para CI normal) ───────────────────
class TestHashPerformance:
    """Benchmarks básicos que corren en CI normal (datos pequeños)."""

    def test_sha256_10mb_baseline(self, tmp_disk_image):
        """Benchmark baseline: 10 MB en menos de 5s (cualquier hardware moderno)."""
        start = time.time()
        h = hashlib.sha256()
        with open(str(tmp_disk_image), 'rb') as f:
            for block in iter(lambda: f.read(8192), b''):
                h.update(block)
        elapsed = time.time() - start
        throughput_mbps = 10 / elapsed
        assert elapsed < 5.0, (
            f'10 MB tardó {elapsed:.3f}s — throughput: {throughput_mbps:.1f} MB/s'
        )

    def test_sha256_throughput_above_50mbps(self, tmp_disk_image):
        """El throughput de hashing debe ser > 50 MB/s en cualquier hardware moderno."""
        start = time.time()
        h = hashlib.sha256()
        with open(str(tmp_disk_image), 'rb') as f:
            for block in iter(lambda: f.read(65536), b''):
                h.update(block)
        elapsed = time.time() - start
        throughput = 10 / elapsed  # MB/s (10 MB archivo)
        assert throughput > 50, (
            f'Throughput de SHA-256: {throughput:.1f} MB/s — mínimo esperado: 50 MB/s'
        )


# ── TC-Perf-IA: Rendimiento Inferencia IA (solo RPi5 manual) ─────────────────
@pytest.mark.slow
@pytest.mark.skipif(
    os.environ.get('OLLAMA_AVAILABLE') != 'true',
    reason='Requiere Ollama corriendo y OLLAMA_AVAILABLE=true'
)
class TestIAPerformance:

    def test_ollama_tokens_per_second_rpi5(self):
        """TC-Perf-IA: Ollama debe generar > 5 tokens/segundo en RPi5 con gemma3:4b."""
        import requests

        prompt = 'Analiza brevemente: archivo de log con 100 entradas de acceso SSH.'

        start = time.time()
        resp = requests.post(
            'http://localhost:11434/api/generate',
            json={'model': 'gemma3:4b', 'prompt': prompt, 'stream': False},
            timeout=300
        )
        elapsed = time.time() - start
        resp.raise_for_status()

        data = resp.json()
        response_text = data.get('response', '')
        token_count = len(response_text.split())  # Aproximación simple

        tokens_per_second = token_count / elapsed if elapsed > 0 else 0

        assert tokens_per_second > 5, (
            f'Velocidad de inferencia: {tokens_per_second:.1f} tok/s '
            f'— mínimo RPi5: 5 tok/s\n'
            f'Tiempo total: {elapsed:.1f}s, tokens: {token_count}'
        )
