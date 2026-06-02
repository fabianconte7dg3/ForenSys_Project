# Problemas Conocidos (Known Issues)

Este documento sirve para rastrear errores y problemas persistentes que no bloquean la operación principal pero que deben ser solucionados en el futuro.

## Módulo de Wiping (01_wiping.py)

### 1. Barra de progreso congelada en 96% (RESUELTO)
- **Descripción:** Al ejecutar el borrado de disco (Wiping), el proceso finaliza correctamente y el disco es formateado y montado. Sin embargo, la interfaz de usuario en tiempo real (barra de progreso y terminal SSE) se queda atascada en el paso de "Montando disco..." (96%), y no renderiza el mensaje de `[PROGRESO:100]` ni el final de la cadena de texto de salida.
- **Impacto:** Menor (puramente visual). El borrado en sí se completa de forma exitosa y el reporte se genera.
- **Causa/Solución:** Se descubrió un defecto de arquitectura asíncrona ("robo de mensajes" o race condition) en el buffer original de Flask (SSE). Al existir múltiples conexiones inactivas o si el usuario recargaba la página a medio proceso (F5), los mensajes de fin de proceso (como el `[PROGRESO:100]`) se balanceaban accidentalmente a conexiones huérfanas o se perdían. Se implementó un modelo "PubSub" completo, lo cual garantiza la entrega limpia de todo el output del proceso sin bloqueos asíncronos.

### 2. Velocidad de escritura / Lectura (Telemetría) (RESUELTO)
- **Descripción:** En el PDF generado por `10_telemetry_logger.py`, el campo de Velocidad Promedio a veces continúa mostrando `0.00 MB/s` a pesar de que el proceso subyacente de `dd` genera y guarda el log con la velocidad real.
- **Impacto:** Menor. La velocidad aparece en los logs del sistema, pero no en el PDF automatizado.
- **Causa/Solución:** El subproceso `dd` corría en un namespace o contexto donde `psutil` no era capaz de rastrear dinámicamente sus contadores de lectura/escritura (`io_counters`). Se solucionó inyectando un paso intermedio donde el script principal de Python extrae el log puro del binario, lo vuelca a un archivo en `/tmp/wiping_speed.txt`, y el logger de telemetría lo ingiere y calcula los promedios justos antes de construir el PDF.

### 3. Falta de barra de progreso en Hash Pre-Adquisición y telemetría de Hash
- **Descripción:** Al iniciar la Extracción de Disco (Módulo Deadbox), el sistema comienza a calcular el Hash SHA-256 original antes de clonar. Este proceso es síncrono y no emite actualizaciones, haciendo que parezca que la interfaz o el comando se han "congelado". Además, no hay registro de telemetría específico para esta etapa intensiva de lectura.
- **Causa/Solución:** Se necesita refactorizar la función `calcular_hash` para que imprima el progreso actual basándose en el tamaño total del disco (`os.path.getsize` o `blockdev --getsize64`) y crear un wrapper que invoque `10_telemetry_logger.py` específicamente para la fase de Hashing. (Pendiente para futura versión).
