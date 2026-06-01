# 🚀 Ideas y Desarrollos Futuros para ForenSys

Este documento recopila propuestas, mejoras y nuevas características planeadas para futuras versiones de ForenSys, manteniendo siempre la rigurosidad forense y la eficiencia en recursos limitados.

---

## 1. Integración de IA Multimodal (Análisis de Imágenes)

**Contexto:**
Actualmente, el Módulo 8 (Triaje IA) de ForenSys analiza texto y metadatos estructurados utilizando Modelos de Lenguaje Grandes (LLMs). Sin embargo, gran parte de la evidencia clave en una investigación reside en archivos multimedia (fotografías, capturas de pantalla, diagramas).

**La Propuesta:**
Aprovechar modelos de Visión-Lenguaje (VLM) como `minicpm-v:8b` o `llava` (ejecutados en el motor remoto de PC) para permitir a la IA "ver" e interpretar imágenes forenses.

### 1.1 Flujo Técnico Propuesto
1. La API de Ollama soporta el envío de imágenes nativamente mediante codificación en **Base64**.
2. Al invocar el endpoint `/api/generate`, el payload JSON se expandiría para incluir las imágenes:
   ```json
   {
     "model": "minicpm-v:8b-2.6",
     "prompt": "Analiza esta evidencia gráfica recuperada del disco. Describe cualquier texto o elemento sospechoso.",
     "images": ["<string_base64_de_la_imagen>"]
   }
   ```
3. El motor remoto decodificará la imagen, la procesará junto con el prompt y devolverá la descripción forense.

### 1.2 Implementación Lógica en la Interfaz
Dado que un disco clonado puede contener decenas de miles de imágenes basura (íconos, caché de navegadores), automatizar el envío de *todas* las imágenes saturaría la RAM y la ventana de contexto de la IA. La estrategia será:

- **Triaje Dirigido (Humano-IA):** En el "Explorador de Evidencia" del Dashboard, se añadirá un botón `[👁️ Análisis Visual IA]` junto a los archivos multimedia recuperados. El perito seleccionará manualmente imágenes sospechosas (ej. una captura de pantalla de un chat o un pasaporte escaneado) y ForenSys enviará únicamente esa imagen al motor de IA.
- **Detección de Anomalías (Auto-trigger):** Si el Módulo 7 detecta una anomalía severa (ej. una imagen con alta entropía o con *steganography* sospechoso en los metadatos EXIF), el sistema podría pre-seleccionar automáticamente esa imagen para su revisión visual.

---

## 2. Barra de Progreso en Cálculo de Hash Pre-Adquisición

**Contexto:**
Durante la extracción estática (Módulo 2), el sistema realiza un hashing inicial leyendo todo el disco crudo (ej. `/dev/sdb`) usando bloques en Python puro. Este proceso demora considerablemente para discos de gran capacidad y no reporta su avance.

**La Propuesta:**
- Optimizar el cálculo de hash, posiblemente delegándolo a herramientas nativas o ajustando el tamaño del buffer en Python para mayor velocidad.
- Implementar y reportar el progreso fraccionado (porcentaje de I/O) para que este sea transmitido en vivo al frontend (Live Console) usando Server-Sent Events (SSE). De esta manera el perito sabrá el porcentaje exacto y el sistema dejará de parecer "trabado" antes de que inicie `dc3dd`.

---

*(Añadir nuevas ideas debajo de esta línea a medida que el proyecto evolucione)*
