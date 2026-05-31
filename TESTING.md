# Documentación de Pruebas Automatizadas (ForenSys)

Esta guía explica cómo ejecutar, entender y extender la suite de pruebas automatizadas del proyecto ForenSys. Las pruebas están diseñadas para ejecutarse en cualquier entorno sin necesidad de tener el hardware físico conectado, garantizando así que no habrá pérdida de datos ni modificaciones reales en el sistema durante el testeo.

---

## 1. Instalación y Requisitos

Para poder ejecutar la suite de pruebas, asegúrate de estar dentro de tu entorno virtual y de haber instalado las dependencias necesarias.

```bash
# Navegar al proyecto y activar el entorno virtual
cd ForenSys_Project
source venv/bin/activate

# Instalar los requerimientos de test
pip install -r requirements-test.txt
```

---

## 2. Ejecutar las Pruebas

La herramienta principal que utilizamos es `pytest`. A continuación, se detallan los comandos más útiles según lo que necesites verificar:

### Ejecutar todas las pruebas (Rápido y Seguro)
```bash
pytest tests/ --ignore=tests/performance -v
```

### Ejecutar pruebas por categoría
- **Seguridad**: `pytest tests/security/ -v`
- **Cumplimiento Normativo**: `pytest tests/compliance/ -v`
- **Integración**: `pytest tests/integration/ -v`
- **Rendimiento** *(Peligro: requiere hardware real)*: `pytest tests/performance/ -m slow -v`

---

## 3. ¿Qué son los Mocks y por qué los usamos?

Un **Mock** (objeto simulado) actúa como un "doble de acción" para las partes peligrosas o dependencias externas del código. 
- Evitan que ejecutemos accidentalmente un clonado de disco real sobre `/dev/sda`.
- Evitan la necesidad de conectar un móvil físico para probar la lógica de extracción.
- Reemplazan peticiones de red pesadas (como a la IA de Ollama o búsquedas OSINT) por respuestas inmediatas de prueba.

*(Si deseas crear nuevos Mocks en el futuro, revisa el código fuente en la carpeta `/tests` donde utilizamos `@patch` y `responses`).*

---

## 4. Guía de Auditoría: Catálogo e Interpretación de Resultados

Esta es la sección más importante para auditores y desarrolladores. A continuación se detallan todas las pruebas implementadas (124 en total), qué significan, y cómo interpretar si una prueba **PASA** o **FALLA**.

### A. Pruebas de Cumplimiento Normativo (Compliance - `test_iso27037.py`)
Estas pruebas garantizan que el software cumple legalmente con los estándares forenses internacionales.

- **`test_all_mandatory_fields_present` (ISO 27037)**: 
  - **Qué hace:** Verifica que cada acta generada contenga: ID de Caso, Perito, Fecha, Hash PRE, Hash POST, y constancia del Write-Blocker.
  - **Si PASA:** El acta tiene validez legal básica.
  - **Si FALLA:** El sistema generó un acta incompleta. *Consecuencia de auditoría:* Evidencia inadmisible en corte.
- **`test_integrity_chain_maintained` (ISO 27037)**: 
  - **Qué hace:** Confirma que el Hash SHA-256 PRE-adquisición es matemáticamente idéntico al Hash POST-adquisición.
  - **Si FALLA:** Hubo alteración de la evidencia durante la copia. *Consecuencia de auditoría:* Cadena de custodia rota.
- **`test_all_nist_fields_present` (NIST SP 800-101)**: 
  - **Qué hace:** Para extracciones móviles, exige Modelo, Número de Serie, y Método de extracción lógica.
  - **Si FALLA:** El reporte móvil no cumple los estándares NIST para análisis de celulares.
- **`test_disclaimer_present_in_synthesis` (Auditoría de IA)**: 
  - **Qué hace:** Exige que toda síntesis generada por la IA incluya el texto: *"AVISO LEGAL — DOCUMENTO DE ASISTENCIA..."*.
  - **Si FALLA:** La IA generó un reporte sin la advertencia legal. *Consecuencia:* Un juez podría interpretar erróneamente que la IA tomó la decisión pericial final.

### B. Pruebas de Seguridad (`test_security.py`)
Garantizan que el sistema no puede ser hackeado o manipulado de forma maliciosa.

- **`test_explore_endpoint_path_traversal`**:
  - **Qué hace:** Intenta enviar rutas maliciosas (ej. `../../../etc/passwd`) a la API de exploración de archivos.
  - **Si PASA:** La API rechaza el intento con un error 400/403.
  - **Si FALLA:** ¡Peligro crítico! Un atacante puede leer archivos secretos del sistema operativo.
- **`test_system_disk_not_in_list_devices` y `test_set_readonly_blocks_system_disk`**:
  - **Qué hace:** Asegura que el disco del sistema (`/dev/sda` o `mmcblk0`) NUNCA sea bloqueado ni listado como evidencia.
  - **Si PASA:** El sistema operativo está blindado.
  - **Si FALLA:** Un perito podría borrar accidentalmente el sistema ForenSys entero confundiéndolo con un USB.
- **`test_caso_id_xss_rejected` y `test_caso_id_sqli_sanitized`**:
  - **Qué hace:** Intenta crear casos usando código malicioso (ej. `<script>alert('xss')</script>` o `'; DROP TABLE;`).
  - **Si PASA:** El sistema "sanitiza" el texto eliminando los caracteres peligrosos de inmediato.
  - **Si FALLA:** El sistema es vulnerable a inyección de código.

### C. Pruebas Unitarias (Lógica Central)

**1. Hashing (`test_01_hashing.py`)**
- **`test_abc_string`**: 
  - **Qué hace:** Genera el SHA-256 de la cadena "abc" y valida que coincida exactamente con el vector oficial del NIST (`ba7816bf...`).
  - **Si FALLA:** El algoritmo de hashing central del sistema está corrupto. ¡Detener uso inmediatamente!

**2. Adquisición Dead-Box (`test_02_deadbox.py`)**
- **`test_write_blocker_activation_attempt`**:
  - **Qué hace:** Simula conectar un USB en modo lectura/escritura (RW) y verifica que el sistema lo fuerce a Solo Lectura (RO).
  - **Si FALLA:** El Write-Blocker por software falló. La evidencia está en riesgo de contaminación.

**3. Dispositivos Móviles (`test_04_mobile.py`)**
- **`test_unauthorized_device_excluded`**:
  - **Qué hace:** Conecta un Android virtual que no ha dado permisos USB ("unauthorized").
  - **Si PASA:** El sistema ignora el teléfono porque no se puede extraer nada de forma segura.
  - **Si FALLA:** El sistema intentará extraer un teléfono bloqueado, provocando que se congele.

**4. Inteligencia de Fuentes Abiertas (OSINT - `test_05_osint.py`)**
- **`test_available_profiles_excluded`**:
  - **Qué hace:** Maigret a veces reporta que una cuenta está "Available" (Disponible/No Registrada). La prueba verifica que estos se filtren.
  - **Si PASA:** El reporte OSINT solo incluye perfiles "Claimed" (Registrados reales).
  - **Si FALLA:** El reporte entregará "falsos positivos" (ej. dirá que el sospechoso tiene cuenta de Twitter, cuando en realidad el nombre de usuario simplemente está libre).

**5. Análisis de IA (`test_08_ia.py`)**
- **`test_unknown_model_rejected`**:
  - **Qué hace:** Intenta usar un modelo no autorizado (ej. `gpt-4`).
  - **Si PASA:** Se bloquea el uso, obligando a usar solo modelos locales pre-aprobados (ej. `gemma3:4b`).
  - **Si FALLA:** Riesgo de fuga de datos sensibles si se usara un modelo conectado a la nube en lugar de procesamiento 100% local.

### D. Pruebas de Integración (`test_case_lifecycle.py`)
Miden que todos los engranajes funcionen juntos sin atascarse.

- **`test_full_lifecycle_open_to_close`**:
  - **Qué hace:** Simula darle click a "Abrir Caso", crear las 4 subcarpetas, generar el log de custodia `contexto_incidente.json`, y finalmente darle a "Cerrar Caso" obteniendo el Hash Maestro final.
  - **Si PASA:** El flujo operativo (End-to-End) del sistema es perfecto y la base de datos registra los estados correctamente.
  - **Si FALLA:** Hay un error en la comunicación entre el front-end, la API de Flask y el disco de almacenamiento.

---

## 5. Reporte de Cobertura (Coverage)
Si deseas saber qué porcentaje de tu código real está siendo validado por las pruebas automatizadas, genera el reporte de cobertura:

```bash
pytest tests/ --ignore=tests/performance --cov=web_app --cov=scripts --cov-report=term-missing
```
Esto te mostrará en consola qué líneas exactas de tus scripts aún no tienen una prueba que las verifique.
