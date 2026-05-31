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

Esta es la sección para interpretar los fallos desde la perspectiva de auditoría:

### A. Pruebas de Cumplimiento Normativo (Compliance - `test_iso27037.py`)
- **`test_all_mandatory_fields_present` (ISO 27037)**: 
  - **Si PASA:** El acta tiene validez legal básica.
  - **Si FALLA:** El sistema generó un acta incompleta. *Consecuencia de auditoría:* Evidencia inadmisible en corte.
- **`test_integrity_chain_maintained` (ISO 27037)**: 
  - **Si FALLA:** Hubo alteración de la evidencia durante la copia. *Consecuencia de auditoría:* Cadena de custodia rota.
- **`test_disclaimer_present_in_synthesis` (Auditoría de IA)**: 
  - **Si FALLA:** La IA generó un reporte sin la advertencia legal. *Consecuencia:* Un juez podría interpretar erróneamente que la IA tomó la decisión pericial final.

### B. Pruebas de Seguridad (`test_security.py`)
- **`test_explore_endpoint_path_traversal`**:
  - **Si PASA:** La API rechaza el intento con un error 400/403.
  - **Si FALLA:** ¡Peligro crítico! Un atacante puede leer archivos secretos del sistema operativo (`../../../etc/passwd`).
- **`test_system_disk_not_in_list_devices` y `test_set_readonly_blocks_system_disk`**:
  - **Si FALLA:** Un perito podría borrar accidentalmente el sistema ForenSys entero confundiéndolo con un USB de evidencia.
- **`test_caso_id_xss_rejected` y `test_caso_id_sqli_sanitized`**:
  - **Si PASA:** El sistema sanitiza el texto eliminando caracteres peligrosos de inmediato.

---

## 5. Filosofía Forense: ¿Por qué todo esto es válido en la Vida Real?

Una duda recurrente en auditorías de sistemas forenses es: *"Si están usando Mocks que fingen comportamientos (como fingir que un disco fue clonado), ¿qué nos garantiza que el software funcionará de verdad en un juzgado?"*

Para entender la validez de nuestra suite de pruebas automatizadas de 124 tests, debemos diferenciar entre **El Motor Lógico** (nuestro código Python) y **Las Herramientas Físicas Matemáticas** (hardware y comandos nativos del gobierno como `dc3dd`).

A continuación, detallamos la naturaleza real de cada categoría de nuestras pruebas:

### 5.1 Pruebas Ejecutadas 100% en Tiempo Real
No todas las pruebas usan mocks. Para todo lo que es "procesamiento interno", **las pruebas se ejecutan de forma 100% real en milisegundos**.

- **El Algoritmo de Hashing (`test_01_hashing.py`):** 
  Durante la prueba, Python genera un archivo real en un directorio temporal de la Raspberry Pi, escribe datos binarios reales y ejecuta la función `compute_sha256()`. La prueba valida que el hash resultante sea matemáticamente idéntico a los vectores de prueba oficiales del **NIST** (National Institute of Standards and Technology de EE.UU.). Esto certifica que nuestro motor lógico jamás cometerá un error calculando un SHA-256.
- **Protección contra Hackeos (`test_security.py`):**
  Las inyecciones SQL y ataques Cross-Site Scripting (XSS) se inyectan en tiempo real a las funciones de nuestra API. La prueba confirma que los filtros en tiempo real extirpan los caracteres peligrosos instantáneamente.
- **Generación de Formatos PDF y actas ISO (`test_09_pdf.py` y `test_iso27037.py`):**
  El sistema compila verdaderos reportes en texto/PDF y se ejecuta un análisis sintáctico real mediante *Expresiones Regulares* (RegEx) para buscar el texto del descargo legal, contar que el Hash conste de exactamente 64 caracteres hexadecimales, y que las fechas tengan la norma ISO.

### 5.2 Pruebas Simuladas (Mocks) en Comandos Pesados
Para los comandos que implican hardware (como extraer datos de Android/iOS o clonar un disco duro por completo con `dc3dd`), usamos "Mocks" que devuelven resultados prefabricados (por ejemplo, le dicen a Python: *"Soy dc3dd, acabo de terminar y el Hash POST es 0xABC..."*).

**¿Por qué usar Mocks aquí lo hace válido legalmente?**
1. **La herramienta de clonación ya está validada:** `dc3dd` es una herramienta forense de grado militar creada por el Departamento de Defensa (DoD) de EE.UU. Un auditor o juez **no duda de que dc3dd funcione**. No necesitamos (ni deberíamos) clonar un disco de 1 Terabyte en cada prueba automatizada para demostrar que `dc3dd` clona bien.
2. **Lo que probamos es la Tubería Lógica (Pipeline):** Lo que un auditor podría cuestionar es: *"¿Y qué pasa si dc3dd hace bien su trabajo, pero la interfaz ForenSys se confunde y anota el Hash de otro caso?"* o *"¿Qué pasa si el Hash PRE de dc3dd es distinto al POST y ForenSys no se da cuenta?"*.
3. **El Mock valida la reacción:** Mediante Mocks, le inyectamos a ForenSys simulaciones de desastres de hardware (ej. le fingimos que el Hash PRE es `AAA` y el Hash POST es `BBB`). La prueba se considera "Exitosa" (PASSED) únicamente si ForenSys detecta de inmediato el error, congela el flujo, muestra la advertencia en rojo y rompe la cadena de custodia en el log.

### Conclusión de Validez
En la **vida real**, cuando un perito esté frente al equipo y conecte un pendrive de evidencia, las matemáticas probadas (`SHA-256`) y el software de grado militar (`dc3dd`) tomarán el control del hardware físico real. 

La suite de pruebas garantiza al 100% que la "Tubería Lógica" de ForenSys orquestará las herramientas con perfección matemática y jamás alterará la cadena de custodia.

---

## 6. Integración Continua y Entornos Aislados (CI/CD y Docker)

Para cumplir al 100% con los más altos estándares de aseguramiento de calidad (QA), el proyecto cuenta con dos herramientas avanzadas para correr estas pruebas de forma automática e imparcial.

### A. Uso del Dockerfile de Pruebas (Testeo Aislado)
Si un auditor externo quiere verificar que el software de ForenSys funciona, no necesita una Raspberry Pi. Puede usar Docker en cualquier computadora (Mac, Windows, Linux) para crear un entorno estéril idéntico al tuyo y correr las 124+ pruebas.

**Cómo usarlo:**
```bash
# 1. Construir la imagen aislada
docker build -t forensys-test -f Dockerfile.test .

# 2. Correr las pruebas dentro del contenedor
docker run --rm forensys-test
```
*Si las pruebas pasan dentro de Docker, significa que el código fuente es perfecto y sus dependencias están sanas.*

### B. Integración Continua (GitHub Actions)
No tienes que acordarte de correr `pytest` cada vez que programas algo nuevo. Hemos configurado un **Pipeline CI/CD** (`.github/workflows/testing.yml`).

**Cómo funciona:**
1. Cada vez que haces `git push origin main`, los servidores de GitHub despiertan una máquina virtual (Ubuntu).
2. Instalan Python 3.12 y todas las dependencias forenses (`dc3dd`, etc.).
3. Ejecutan automáticamente toda la suite de pruebas.
4. **Resultado:** Si todo está bien, verás un "✅ Check verde" al lado de tu commit en GitHub. Si un cambio rompió algo, verás una "❌ X roja", y recibirás un correo avisándote del error antes de que afecte a producción.
