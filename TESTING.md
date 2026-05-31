# Documentación de Pruebas Automatizadas (ForenSys)

Esta guía explica cómo ejecutar, entender y extender la suite de pruebas automatizadas del proyecto ForenSys. Las pruebas están diseñadas para ejecutarse en cualquier entorno sin necesidad de tener el hardware físico conectado (discos duros, móviles) ni dependencias externas corriendo (como Ollama o conexión a Internet), garantizando así que no habrá pérdida de datos ni modificaciones reales en el sistema durante el testeo.

## 1. Instalación y Requisitos

Para poder ejecutar la suite de pruebas, asegúrate de estar dentro de tu entorno virtual y de haber instalado las dependencias necesarias.

```bash
# Navegar al proyecto y activar el entorno virtual
cd ForenSys_Project
source venv/bin/activate

# Instalar los requerimientos de test
pip install -r requirements-test.txt
```

## 2. Ejecutar las Pruebas

La herramienta principal que utilizamos es `pytest`. A continuación, se detallan los comandos más útiles según lo que necesites verificar:

### Ejecutar todas las pruebas (Rápido y Seguro)
Este comando ejecutará todas las pruebas unitarias, de integración, cumplimiento (ISO/NIST) y seguridad. Ignorará las pruebas de rendimiento que requieren hardware real.
```bash
pytest tests/ --ignore=tests/performance -v
```

### Ejecutar pruebas por categoría
- **Pruebas de Seguridad** (Ej. inyecciones SQL, XSS, Path Traversal):
  ```bash
  pytest tests/security/ -v
  ```
- **Pruebas de Cumplimiento Normativo** (ISO/IEC 27037 y NIST SP 800-101):
  ```bash
  pytest tests/compliance/ -v
  ```
- **Pruebas de Integración** (Simulación completa de apertura/cierre de casos):
  ```bash
  pytest tests/integration/ -v
  ```

### Pruebas de Rendimiento (Precaución)
Las pruebas de rendimiento (`tests/performance`) **NO** usan mocks de hardware y medirán la velocidad real de la Raspberry Pi y el uso de RAM. Solo se recomienda ejecutarlas manualmente:
```bash
pytest tests/performance/ -m slow -v
```

## 3. ¿Qué son los Mocks y por qué los usamos?

Un **Mock** (objeto simulado) actúa como un "doble de acción" para las partes peligrosas o dependencias externas del código. 
- Evitan que ejecutemos accidentalmente un clonado de disco real sobre `/dev/sda`.
- Evitan la necesidad de conectar un iPhone (`ideviceinfo`) para probar el código del módulo móvil.
- Reemplazan peticiones HTTP pesadas o lentas (Ollama) por respuestas instantáneas simuladas.

## 4. ¿Cómo crear nuevos Tests con Mocks?

Si agregas un nuevo módulo al proyecto ForenSys y necesitas probar un comando de la terminal de Linux sin que realmente se ejecute, usa el decorador `@patch` de Python.

### Ejemplo: Mockear un comando de la Terminal (Subprocess)
Crea un archivo llamado `test_nuevo.py` dentro de `tests/unit/`:

```python
from unittest.mock import patch, MagicMock
import subprocess

@patch('subprocess.run') 
def test_nuevo_hardware(mock_run):
    # 1. Configuramos el comportamiento falso (Mock)
    mock_run.return_value = MagicMock(
        stdout="Dispositivo clonado exitosamente", 
        returncode=0
    )
    
    # 2. Ejecutamos nuestra lógica (Creerá que el comando corrió de verdad)
    resultado = subprocess.run(["comando_peligroso", "/dev/sdb"], capture_output=True, text=True)
    
    # 3. Validamos
    assert "exitosamente" in resultado.stdout
```

### Ejemplo: Mockear una petición de Red / API (Requests)
Si tu módulo necesita acceder a Internet o a una API local (como Ollama) utilizamos la librería `responses`.

```python
import responses
import requests

@responses.activate
def test_peticion_ia():
    # 1. Le decimos al mock qué debe responder cuando alguien consulte esta URL
    responses.add(
        responses.POST, 
        'http://localhost:11434/api/generate', 
        json={"response": "Analisis de IA completado"}, 
        status=200
    )
    
    # 2. Tu programa hace la petición como si nada
    respuesta = requests.post('http://localhost:11434/api/generate')
    
    # 3. Validamos el resultado
    assert respuesta.json()['response'] == "Analisis de IA completado"
```

## 5. Reporte de Cobertura (Coverage)
Si deseas saber qué porcentaje de tu código real está siendo validado por las pruebas automatizadas, puedes generar un reporte de cobertura con el siguiente comando:

```bash
pytest tests/ --ignore=tests/performance --cov=web_app --cov=scripts --cov-report=term-missing
```
Esto te mostrará en consola qué líneas exactas de tus scripts aún no tienen una prueba que las verifique.
