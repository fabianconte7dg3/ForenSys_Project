# Reporte de Configuración y Rendimiento IA - ForenSys_Project

**Fecha:** Junio 2026
**Propósito:** Detallar la arquitectura, parámetros y configuración del entorno de Inteligencia Artificial desplegado en el Servidor PC para soportar las consultas forenses desde la Raspberry Pi.

---

## 1. El Modelo de Lenguaje: `gemma4-forense`
Se ha creado un modelo especializado basado en `gemma4:e4b` (8 Billones de parámetros). Para evitar alucinaciones y garantizar que se comporte de forma rigurosamente científica, se han inyectado los siguientes parámetros en su `Modelfile`:

*   **Temperatura (`0.0`):** Elimina cualquier ápice de creatividad. El modelo siempre dará la respuesta más matemática y lógica posible.
*   **Prompt de Sistema Estricto:** Se le instruyó bajo una serie de directrices irrompibles donde tiene expresamente prohibido inventar hashes, rutas, o asumir datos. Si un cálculo matemático o una pregunta no corresponde a evidencia digital, el modelo responderá automáticamente: *"Evidencia insuficiente para determinar"*.

## 2. Configuración Extrema de Hardware (Servidor Host)
Dado que la computadora anfitriona (CachyOS Linux) funcionará como un Servidor IA dedicado, se ajustaron las tuercas al máximo absoluto del hardware para procesar gigantescos archivos de logs lo más rápido posible.

*   **VRAM de la Tarjeta Gráfica (Radeon RX 6600 - 8GB):**
    *   **Parámetro:** `num_gpu 42`
    *   **Resultado:** El 100% de las capas neuronales del modelo se introducen directamente en la tarjeta gráfica.
    *   **Consumo:** Abarca exactamente el **69% de la VRAM**. Deja libre el resto de la memoria gráfica para evitar que el entorno de escritorio del PC colapse.
*   **Memoria RAM (32GB Total):**
    *   **Parámetro:** `num_ctx 98304`
    *   **Resultado:** La ventana de contexto ("memoria a corto plazo" de la IA) se elevó a casi 100,000 tokens. Esto permite enviarle volcados enteros de servidores en un solo bloque.
    *   **Consumo:** Reserva un espacio enorme que garantiza dejar tu sistema con unos ~9 a 19 GB de RAM libres fluctuantes, asegurando máxima retención de datos sin usar la memoria Swap (disco duro).
*   **Velocidad Resultante:** **23.44 tokens por segundo**. Rendimiento extraordinario que procesa textos muy largos en fracción de minutos.

## 3. Integración y Configuración para la Raspberry Pi
La comunicación entre la Raspberry Pi (Cliente) y la Computadora (Servidor) está lista y totalmente automatizada mediante el script local `raspberry-ai`.

### Funcionamiento del comando `raspberry-ai on`
Cuando se ejecuta el comando de inicio en la computadora anfitriona:
1.  Se levanta el túnel VPN de forma silenciosa.
2.  Se enciende el servicio `ollama`.
3.  Se abren los puertos del Firewall (11434).
4.  **(NUEVO):** Se **precarga automáticamente** el modelo `gemma4-forense` directamente a la GPU sin intervención del usuario. Esto hace que cuando la Raspberry envíe su primer escaneo, la IA responda instantáneamente en lugar de tardar segundos en despertar.

### Consideración Técnica Vital para ForenSys (Importante)
El modelo recibe nativamente tres tipos de entradas:
*   Texto plano (`.txt`, `.log`, `.md`, fragmentos de código).
*   Imágenes (`.jpg`, `.png`).
*   Audio (`.wav`).

**Regla de Oro:** Para que ForenSys analice archivos complejos (PDFs, documentos de Word, bases de datos SQLite, binarios o volcados de memoria RAM), el código Python dentro de tu Raspberry Pi **debe parsear y extraer el texto o convertir las hojas a imágenes** antes de enviarlas por la API al servidor IA. Enviar un archivo binario directamente causará fallas en el análisis.

---
*Configuración implementada con éxito. El servidor está listo para recibir operaciones periciales en caliente.*
