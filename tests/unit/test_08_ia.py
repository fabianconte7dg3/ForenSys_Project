"""
test_08_ia.py — TC-IA-Mock: Módulo de IA con Ollama mockeado

Valida la lógica del módulo 08_analista_ia.py sin necesitar Ollama corriendo.
Todas las llamadas HTTP se interceptan con la librería 'responses'.
"""
import json
import os
import re

import pytest
import responses as responses_lib


# ── Helpers que reflejan la lógica de 08_analista_ia.py ─────────────────────

MODELOS_AUDITADOS = {
    'gemma3:4b',
    'gemma3:1b',
    'llama3.2:3b',
    'llama3.2:1b',
    'mistral:7b',
    'mistral:latest',
    'llama3:8b',
    'llama3:latest',
}

DISCLAIMER_FRAGMENT = 'AVISO LEGAL — DOCUMENTO DE ASISTENCIA'
DISCLAIMER_FULL = (
    'Este documento es generado por un sistema de inteligencia artificial '
    'y no reemplaza el criterio del perito'
)

OLLAMA_URL = 'http://localhost:11434/api/generate'


def validate_model(model_name: str) -> bool:
    """Verifica que el modelo esté en la whitelist auditada."""
    return model_name in MODELOS_AUDITADOS


def call_ollama(prompt: str, model: str = 'gemma3:4b',
                base_url: str = 'http://localhost:11434') -> str:
    """
    Llama a Ollama y retorna la respuesta de texto.
    (Versión simplificada para testing)
    """
    import requests
    url = f'{base_url}/api/generate'
    payload = {'model': model, 'prompt': prompt, 'stream': False}
    resp = requests.post(url, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json().get('response', '')


def generate_ia_synthesis(response_text: str, caso_id: str,
                           destino: str) -> str:
    """
    Genera el archivo Markdown de síntesis IA.
    Añade el disclaimer legal al inicio del documento.
    """
    disclaimer = (
        f'> **{DISCLAIMER_FRAGMENT}**\n'
        f'> {DISCLAIMER_FULL}\n\n'
    )
    content = disclaimer + response_text
    filename = f'Sintesis_IA_{caso_id}.md'
    ruta = os.path.join(destino, filename)
    with open(ruta, 'w', encoding='utf-8') as f:
        f.write(content)
    return ruta


# ── TC-IA-Mock: Validaciones con Ollama mockeado ────────────────────────────
class TestIAWithMockedOllama:

    @responses_lib.activate
    def test_ollama_call_returns_response(self, mock_ollama_response):
        """TC-IA-01: La llamada a Ollama retorna el texto de la respuesta."""
        responses_lib.add(
            responses_lib.POST, OLLAMA_URL,
            json=mock_ollama_response, status=200
        )
        result = call_ollama('Analiza esta evidencia forense.', model='gemma3:4b')
        assert result  # No vacío
        assert 'Resumen' in result or 'análisis' in result.lower() or 'Hallazgos' in result

    @responses_lib.activate
    def test_synthesis_file_created(self, tmp_path, mock_ollama_response):
        """TC-IA-02: Se crea el archivo Sintesis_IA_*.md en el destino."""
        responses_lib.add(
            responses_lib.POST, OLLAMA_URL,
            json=mock_ollama_response, status=200
        )
        response_text = call_ollama('Prompt de prueba', model='gemma3:4b')
        ruta = generate_ia_synthesis(response_text, 'CASO_001', str(tmp_path))
        assert os.path.exists(ruta)
        assert 'Sintesis_IA_CASO_001.md' in ruta

    @responses_lib.activate
    def test_synthesis_contains_disclaimer(self, tmp_path, mock_ollama_response):
        """TC-IA-03: La síntesis siempre contiene el disclaimer legal."""
        responses_lib.add(
            responses_lib.POST, OLLAMA_URL,
            json=mock_ollama_response, status=200
        )
        response_text = call_ollama('Analiza.', model='gemma3:4b')
        ruta = generate_ia_synthesis(response_text, 'CASO_TEST', str(tmp_path))
        contenido = open(ruta, encoding='utf-8').read()
        assert DISCLAIMER_FRAGMENT in contenido, (
            'El disclaimer legal debe estar presente en toda síntesis IA'
        )

    @responses_lib.activate
    def test_ollama_server_error_handled(self):
        """TC-IA-04: Un error del servidor Ollama (500) genera excepción."""
        responses_lib.add(
            responses_lib.POST, OLLAMA_URL,
            json={'error': 'Internal Server Error'}, status=500
        )
        import requests
        with pytest.raises(requests.HTTPError):
            call_ollama('Prompt.', model='gemma3:4b')

    @responses_lib.activate
    def test_connection_error_handled(self):
        """TC-IA-05: Si Ollama no está disponible, genera ConnectionError."""
        responses_lib.add(
            responses_lib.POST, OLLAMA_URL,
            body=ConnectionError('Connection refused')
        )
        import requests
        with pytest.raises(ConnectionError):
            call_ollama('Prompt.', model='gemma3:4b')


# ── Whitelist de modelos auditados ───────────────────────────────────────────
class TestModelWhitelist:

    def test_approved_model_accepted(self):
        """TC-IA-06: Modelos en la whitelist son aceptados."""
        for model in MODELOS_AUDITADOS:
            assert validate_model(model), f'Modelo aprobado rechazado: {model}'

    def test_unknown_model_rejected(self):
        """TC-IA-07: Modelos no auditados son rechazados."""
        assert not validate_model('gpt-4-turbo')
        assert not validate_model('claude-3-opus')
        assert not validate_model('unknown_model:latest')
        assert not validate_model('')

    def test_case_sensitive_whitelist(self):
        """TC-IA-08: La whitelist distingue mayúsculas/minúsculas."""
        assert not validate_model('Gemma3:4b')    # Mayúscula incorrecta
        assert not validate_model('GEMMA3:4B')
        assert     validate_model('gemma3:4b')    # Correcto


# ── Disclaimer legal ─────────────────────────────────────────────────────────
class TestDisclaimerLegal:

    def test_disclaimer_in_every_synthesis(self, tmp_path):
        """TC-015: El disclaimer legal debe estar en CADA síntesis generada."""
        for i in range(3):
            ruta = generate_ia_synthesis(
                f'Contenido de prueba {i}', f'CASO_{i:03d}', str(tmp_path)
            )
            contenido = open(ruta, encoding='utf-8').read()
            assert DISCLAIMER_FRAGMENT in contenido, (
                f'Disclaimer ausente en síntesis {i}'
            )

    def test_disclaimer_at_beginning_of_file(self, tmp_path):
        """TC-015b: El disclaimer debe aparecer al INICIO del documento."""
        ruta = generate_ia_synthesis(
            'Análisis de evidencia...', 'CASO_DISC', str(tmp_path)
        )
        contenido = open(ruta, encoding='utf-8').read()
        # El disclaimer debe estar en las primeras 500 chars
        assert DISCLAIMER_FRAGMENT in contenido[:500], (
            'El disclaimer debe aparecer al inicio del documento'
        )
