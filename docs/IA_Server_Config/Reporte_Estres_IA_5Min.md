# Reporte de Estrés y Rendimiento Sostenido - ForenSys_Project

**Fecha del Análisis:** Junio 2026
**Objetivo:** Evaluar la estabilidad térmica, consumo de memoria y velocidad de inferencia de la Inteligencia Artificial anfitriona (`gemma4-forense`) bajo una carga de trabajo constante de 5 minutos proveniente del cliente Raspberry Pi.

---

## 1. Parámetros de Hardware Activos
Durante la prueba, el modelo de 8 Billones de parámetros se sometió al máximo rendimiento mediante la siguiente configuración extrema en el `Modelfile`:
*   `num_gpu 42`: 100% de las capas físicas delegadas a la GPU.
*   `num_ctx 98304`: ~100,000 tokens de contexto para retención de logs forenses masivos.

## 2. Métricas de Rendimiento (Tokens)
La velocidad de procesamiento es un factor crítico en el análisis pericial. Gracias a la delegación total del modelo a la GPU, se lograron las siguientes métricas:
*   **Velocidad Promedio:** **23.44 tokens por segundo**.
*   **Capacidad Estimada:** El servidor es capaz de generar aproximadamente 1,400 tokens (unas 1,000 palabras) por minuto.
*   **Eficiencia:** El tiempo de "Time-to-First-Token" (TTFT) se redujo al mínimo posible para la red local, ofreciendo una respuesta prácticamente instantánea a las peticiones remotas.

## 3. Análisis de Estrés Sostenido (Prueba de 5 Minutos)

Se desplegó una sonda de monitorización capturando métricas cada 20 segundos durante un intervalo continuo de 5 minutos de procesamiento ininterrumpido.

### A. Estabilidad Térmica (GPU AMD Radeon RX 6600)
*   La temperatura base operativa inició en **56°C**.
*   Bajo estrés prolongado, la curva térmica se mantuvo estable gracias a los ventiladores dinámicos operando a un ~20% de su capacidad, logrando enfriar el núcleo a **58°C - 61°C** durante la mayor parte de la prueba.
*   Se detectaron picos saludables de hasta **74°C** coincidiendo con bloques pesados de procesamiento. El sistema nunca alcanzó estados de sobrecalentamiento crítico (*thermal throttling*).

### B. Consumo de Memoria de Video (VRAM)
*   El uso de VRAM se afianzó en el objetivo preestablecido: el bloque alcanzó un límite de consumo cercano al **70%**.
*   Esto asegura que el modelo cabalga sobre el procesador gráfico a máxima velocidad, dejando un 30% reservado para prevenir el colapso del gestor de ventanas del sistema operativo (Hyprland).

### C. Retención en Memoria RAM
*   La memoria total consumida por el modelo y el sistema osciló rígidamente entre **12 GB y 13 GB**.
*   Se confirmó una disponibilidad constante e inamovible de **18 GB a 19 GB de RAM Libre/Disponible** a lo largo de toda la prueba. No se detectaron fugas de memoria (*memory leaks*) asociadas a la acumulación del contexto de 98K tokens.

### D. Consolidación de Procesamiento (CPU)
*   El subproceso de Ollama requirió el uso sostenido de aproximadamente **3 núcleos completos** (fluctuando entre el 284% y el 306% de uso de CPU).
*   La carga de trabajo se distribuyó de forma equitativa y no se vio afectada por tareas secundarias del sistema anfitrión (ej. navegadores web).

---

## 4. Veredicto Técnico
El entorno anfitrión (Host PC) cuenta con la calificación **Grado Producción (A+)** para tareas forenses. El sistema está perfectamente equilibrado, garantizando que el modelo `gemma4-forense` opere a su máxima capacidad lógica y de velocidad sin comprometer la integridad térmica ni la estabilidad de red necesaria para dar soporte ininterrumpido a la Raspberry Pi.
