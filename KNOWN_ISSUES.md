# Problemas Conocidos (Known Issues)

Este documento sirve para rastrear errores y problemas persistentes que no bloquean la operación principal pero que deben ser solucionados en el futuro.

## Módulo de Wiping (01_wiping.py)

### 1. Barra de progreso congelada en 96%
- **Descripción:** Al ejecutar el borrado de disco (Wiping), el proceso finaliza correctamente y el disco es formateado y montado. Sin embargo, la interfaz de usuario en tiempo real (barra de progreso y terminal SSE) se queda atascada en el paso de "Montando disco..." (96%), y no renderiza el mensaje de `[PROGRESO:100]` ni el final de la cadena de texto de salida.
- **Impacto:** Menor (puramente visual). El borrado en sí se completa de forma exitosa y el reporte se genera.
- **Posible Causa:** Interacción asíncrona entre el pipe (`subprocess.Popen` de Python) y el buffer SSE de la interfaz web, o el script `app.py` que muere o no logra descargar los últimos bytes de `stdout` antes de que el proceso principal sea cerrado/desmontado.

### 2. Velocidad de escritura / Lectura (Telemetría)
- **Descripción:** En el PDF generado por `10_telemetry_logger.py`, el campo de Velocidad Promedio a veces continúa mostrando `0.00 MB/s` a pesar de que el proceso subyacente de `dd` genera y guarda el log con la velocidad real.
- **Impacto:** Menor. La velocidad aparece en los logs del sistema, pero no en el PDF automatizado.
- **Posible Causa:** Problemas de caché con el servidor Flask, o fallo de lectura del archivo temporal de telemetría (`/tmp/wiping_speed.txt`) debido a permisos o ciclo de vida del log de proceso que se adelanta a la escritura del archivo en el sistema de telemetría asíncrona.

*Nota: Ambos bugs deben ser investigados con sesiones de debug con captura de sockets locales y trazas de buffering profundo en Python.*
