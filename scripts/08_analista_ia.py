import os
import json
import sys
import requests
from datetime import datetime

# ==========================================
# CONFIGURACIÓN DEL LLM LOCAL (OLLAMA)
# ==========================================
OLLAMA_URL = "http://localhost:11434/api/generate"
MODELO_LLM = "gemma3:4b"  # Cambia esto si usaste otro modelo en Ollama
DIRECTORIO_DEFAULT = "/mnt/Destino_ForenSys"

# --- CONFIGURACIÓN DE RENDIMIENTO (Raspberry Pi 5 - 8GB) ---
# Ventana de contexto: cuántos tokens puede procesar el modelo.
# Más bajo = menos RAM. 2048 es seguro para 8GB con un modelo 4B.
NUM_CTX = 2048

# Hilos de CPU: la RPi5 tiene 4 cores. 4 hilos es el máximo eficiente.
# Usar más causa context-switching y congelamiento.
NUM_THREAD = 4

# Cuánto tiempo mantener el modelo en memoria después de responder.
# "0" = descargarlo inmediatamente para liberar RAM.
KEEP_ALIVE = "0"

# Límite máximo de caracteres del prompt de evidencia.
# Esto evita que un caso enorme sature la ventana de contexto.
MAX_CARACTERES_EVIDENCIA = 6000

# Timeout de la solicitud HTTP (en segundos).
# Un modelo 4B en RPi5 puede tardar 5-15 minutos para generar un informe largo.
TIMEOUT_SOLICITUD = 900  # 15 minutos


def imprimir_banner():
    print("""
    ========================================================
      ███████╗███████╗███████╗████████╗███████╗███╗   ███╗
      ██╔════╝██╔════╝██╔════╝╚══██╔══╝██╔════╝████╗ ████║
      █████╗  █████╗  █████╗     ██║   █████╗  ██╔████╔██║
      ██╔══╝  ██╔══╝  ██╔══╝     ██║   ██╔══╝  ██║╚██╔╝██║
      ██║     ███████╗███████╗   ██║   ███████╗██║ ╚═╝ ██║
      ╚═╝     ╚══════╝╚══════╝   ╚═╝   ╚══════╝╚═╝     ╚═╝
     FOREN-SYS: CEREBRO DE INTELIGENCIA ARTIFICIAL (V3.0)
    * LLM Triage | Ollama Engine | Optimizado Raspberry Pi 5 *
    ========================================================
    """)

def comprobar_ollama():
    """Verifica si el servidor de Ollama está encendido y el modelo existe."""
    print(f"[*] Conectando con el motor de IA local ({MODELO_LLM}) en {OLLAMA_URL}...")
    try:
        respuesta = requests.get("http://localhost:11434/", timeout=10)
        if respuesta.status_code == 200:
            print("[+] Servidor Ollama: EN LÍNEA")
            # Verificar que el modelo existe
            try:
                modelos = requests.get("http://localhost:11434/api/tags", timeout=10).json()
                nombres = [m['name'] for m in modelos.get('models', [])]
                if MODELO_LLM in nombres or any(MODELO_LLM.split(':')[0] in n for n in nombres):
                    print(f"[+] Modelo '{MODELO_LLM}': DISPONIBLE")
                else:
                    print(f"[!] Advertencia: Modelo '{MODELO_LLM}' no encontrado en la lista local.")
                    print(f"    Modelos disponibles: {', '.join(nombres) if nombres else 'Ninguno'}")
                    print(f"    Ejecuta: ollama pull {MODELO_LLM}")
            except Exception:
                pass
            return True
    except requests.exceptions.ConnectionError:
        print("[-] ERROR: No se pudo conectar a Ollama. ¿Está encendido el servicio?")
        print("    Prueba ejecutar en otra terminal: sudo systemctl start ollama")
        return False
    return False

def _leer_csv_resumido(ruta, max_filas=20):
    """Lee un CSV y devuelve un resumen textual de sus primeras filas."""
    if not os.path.exists(ruta):
        return ""
    try:
        import csv
        with open(ruta, 'r', encoding='utf-8', errors='ignore') as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if not header:
                return ""
            filas = []
            for i, fila in enumerate(reader):
                if i >= max_filas:
                    break
                filas.append(fila)
        if not filas:
            return ""
        texto = " | ".join(header) + "\n"
        for fila in filas:
            texto += " | ".join(str(c)[:60] for c in fila) + "\n"
        return texto
    except Exception:
        return ""

def _agregar_bloque(evidencia, presupuesto, titulo, contenido):
    """Agrega un bloque de evidencia respetando el presupuesto de caracteres."""
    if not contenido or not contenido.strip():
        return evidencia, presupuesto
    bloque = f"--- {titulo} ---\n{contenido}--- FIN {titulo} ---\n\n"
    if len(bloque) < presupuesto:
        return evidencia + bloque, presupuesto - len(bloque)
    elif presupuesto > 200:
        bloque_truncado = bloque[:presupuesto - 50] + "\n[...TRUNCADO...]\n\n"
        return evidencia + bloque_truncado, 0
    return evidencia, presupuesto

def recopilar_inteligencia(carpeta_resultados):
    """Filtra y empaqueta TODA la evidencia V11.0 para la ventana de contexto de la IA."""
    print("[*] Recopilando evidencia V11.0 (9 fuentes de datos)...")

    evidencia_texto = ""
    presupuesto = MAX_CARACTERES_EVIDENCIA
    fuentes_cargadas = []

    # 1. REPORTE MAESTRO (Prioridad MÁXIMA - contiene resumen ejecutivo)
    ruta_maestro = os.path.join(carpeta_resultados, "Reporte_Forense_Maestro.txt")
    if os.path.exists(ruta_maestro):
        with open(ruta_maestro, 'r', encoding='utf-8', errors='ignore') as f:
            contenido = f.read()
        idx = contenido.find("RESUMEN EJECUTIVO")
        fragmento = contenido[idx:][:1500] if idx != -1 else contenido[-1500:]
        # Incluir también sección de REGISTRY si existe
        idx_reg = contenido.find("[REGISTRY]")
        if idx_reg != -1:
            fragmento += "\n" + contenido[idx_reg:][:800]
        evidencia_texto, presupuesto = _agregar_bloque(evidencia_texto, presupuesto, "RESUMEN MAESTRO", fragmento)
        fuentes_cargadas.append("Reporte Maestro")

    # 2. USUARIOS DEL EQUIPO (Prioridad ALTA - identifica quién usaba la máquina)
    ruta_usuarios = os.path.join(carpeta_resultados, "Usuarios_Equipo.csv")
    texto_usuarios = _leer_csv_resumido(ruta_usuarios, 15)
    if texto_usuarios:
        evidencia_texto, presupuesto = _agregar_bloque(evidencia_texto, presupuesto, "USUARIOS DEL EQUIPO", texto_usuarios)
        fuentes_cargadas.append("Usuarios")

    # 3. HARDWARE Y USB (Prioridad ALTA - dispositivos conectados)
    ruta_hw = os.path.join(carpeta_resultados, "Hardware_y_USB.csv")
    texto_hw = _leer_csv_resumido(ruta_hw, 25)
    if texto_hw:
        evidencia_texto, presupuesto = _agregar_bloque(evidencia_texto, presupuesto, "HARDWARE Y DISPOSITIVOS USB", texto_hw)
        fuentes_cargadas.append("Hardware/USB")

    # 4. PERSISTENCIA (Prioridad ALTA - mecanismos de auto-arranque sospechosos)
    ruta_persist = os.path.join(carpeta_resultados, "Mecanismos_Persistencia.csv")
    texto_persist = _leer_csv_resumido(ruta_persist, 15)
    if texto_persist:
        evidencia_texto, presupuesto = _agregar_bloque(evidencia_texto, presupuesto, "MECANISMOS DE PERSISTENCIA", texto_persist)
        fuentes_cargadas.append("Persistencia")

    # 5. ALERTAS DE SEGURIDAD del JSONL (Entropía alta)
    ruta_jsonl = os.path.join(carpeta_resultados, "Master_Timeline.jsonl")
    alertas = []
    if os.path.exists(ruta_jsonl):
        with open(ruta_jsonl, 'r', encoding='utf-8', errors='ignore') as f:
            for linea in f:
                try:
                    evento = json.loads(linea)
                    if evento.get("sospechoso_entropia") or evento.get("alerta_evasion"):
                        alertas.append(
                            f"- {evento.get('descripcion','?')} | "
                            f"Entropía: {evento.get('entropia', 'N/A')} | "
                            f"Ext. falsa: {'SÍ' if evento.get('alerta_evasion') else 'NO'}"
                        )
                except (json.JSONDecodeError, KeyError):
                    continue
    if alertas:
        evidencia_texto, presupuesto = _agregar_bloque(
            evidencia_texto, presupuesto, "ALERTAS SEGURIDAD (ENTROPÍA/EVASIÓN)",
            "\n".join(alertas[:20]) + "\n")
        fuentes_cargadas.append(f"Alertas ({len(alertas)})")

    # 6. PROGRAMAS INSTALADOS
    ruta_prog = os.path.join(carpeta_resultados, "Lista_Programas_Instalados.csv")
    texto_prog = _leer_csv_resumido(ruta_prog, 25)
    if texto_prog:
        evidencia_texto, presupuesto = _agregar_bloque(evidencia_texto, presupuesto, "PROGRAMAS INSTALADOS", texto_prog)
        fuentes_cargadas.append("Programas")

    # 7. HISTORIAL WEB
    ruta_web = os.path.join(carpeta_resultados, "Web_History_and_Bookmarks.txt")
    if os.path.exists(ruta_web) and presupuesto > 300:
        with open(ruta_web, 'r', encoding='utf-8', errors='ignore') as f:
            lineas_web = f.readlines()
        lineas_utiles = [l for l in lineas_web[2:40] if l.strip()]
        if lineas_utiles:
            evidencia_texto, presupuesto = _agregar_bloque(
                evidencia_texto, presupuesto, "HISTORIAL WEB",
                "".join(lineas_utiles))
            fuentes_cargadas.append("Web History")

    # 8. DESCARGAS WEB
    ruta_desc = os.path.join(carpeta_resultados, "Descargas_Web.csv")
    texto_desc = _leer_csv_resumido(ruta_desc, 15)
    if texto_desc and presupuesto > 200:
        evidencia_texto, presupuesto = _agregar_bloque(evidencia_texto, presupuesto, "DESCARGAS WEB", texto_desc)
        fuentes_cargadas.append("Descargas")

    # 9. EVENTOS DEL SISTEMA
    ruta_evt = os.path.join(carpeta_resultados, "Eventos_Sistema.csv")
    texto_evt = _leer_csv_resumido(ruta_evt, 15)
    if texto_evt and presupuesto > 200:
        evidencia_texto, presupuesto = _agregar_bloque(evidencia_texto, presupuesto, "EVENTOS SISTEMA (EVTX)", texto_evt)
        fuentes_cargadas.append("Event Logs")

    # 10. MULTIMEDIA CON METADATOS (GPS, cámaras)
    ruta_multi = os.path.join(carpeta_resultados, "Metadatos_Multimedia.csv")
    texto_multi = _leer_csv_resumido(ruta_multi, 10)
    if texto_multi and presupuesto > 200:
        evidencia_texto, presupuesto = _agregar_bloque(evidencia_texto, presupuesto, "MULTIMEDIA (EXIF/GPS)", texto_multi)
        fuentes_cargadas.append("Multimedia")

    caracteres_total = len(evidencia_texto)
    print(f"    [+] Fuentes cargadas: {', '.join(fuentes_cargadas)}")
    print(f"    [+] Evidencia empaquetada: {caracteres_total} caracteres (límite: {MAX_CARACTERES_EVIDENCIA})")
    return evidencia_texto

def analizar_con_ia(evidencia_cruda, ruta_salida):
    """Envía el prompt y evidencia al LLM con streaming para evitar congelamiento."""

    prompt_maestro = f"""Eres un Perito Informático Forense certificado. Analiza la siguiente evidencia digital extraída de un equipo y redacta un Dictamen Pericial en ESPAÑOL.

EVIDENCIA RECOPILADA:
{evidencia_cruda}

INSTRUCCIONES (máximo 1000 palabras, formato Markdown):

## 1. Identificación del Equipo
- Nombre del equipo, zona horaria, sistema operativo detectado.
- Dispositivos USB que fueron conectados (marca, serial).

## 2. Usuarios del Sistema
- Lista de usuarios detectados con su nivel de actividad.
- Documentos recientes, comandos ejecutados, programas usados por cada uno.

## 3. Perfil de Uso
- Deduce el perfil del usuario principal (programador, oficinista, gamer, etc.).
- Basado en: programas instalados, historial web, tipos de archivos.

## 4. Cronología de Actividad Sospechosa
- Las 5-10 acciones más relevantes en orden cronológico.
- Incluye: URLs visitadas, programas ejecutados, archivos descargados.

## 5. Alertas de Seguridad
- Archivos con alta entropía (posible ransomware/cifrado).
- Mecanismos de persistencia sospechosos (auto-arranque fuera de rutas confiables).
- Extensiones falsas o técnicas antiforenses detectadas.

## 6. Evidencia Multimedia
- Archivos con coordenadas GPS embebidas.
- Cámaras/dispositivos detectados en metadatos EXIF.

## 7. Conclusión Pericial
- Párrafo final indicando hallazgos principales y nivel de riesgo.

REGLAS: No inventes datos. Solo analiza lo proporcionado. Tono formal y pericial."""

    carga_util = {
        "model": MODELO_LLM,
        "prompt": prompt_maestro,
        "stream": True,  # CRÍTICO: streaming evita que la RPi acumule toda la respuesta en RAM
        "options": {
            "temperature": 0.2,      # Baja para análisis preciso
            "num_ctx": NUM_CTX,      # Ventana de contexto reducida para ahorrar RAM
            "num_thread": NUM_THREAD # Hilos limitados a los cores físicos del RPi5
        },
        "keep_alive": KEEP_ALIVE    # Descargar modelo tras responder para liberar RAM
    }

    print("[*] Transmitiendo datos a la IA (streaming activado)...")
    print("[*] La respuesta aparecerá en tiempo real. Ctrl+C para cancelar.\n")
    print("=" * 60)
    
    try:
        # stream=True en requests = recibir la respuesta chunk por chunk
        # Esto evita que requests acumule toda la respuesta en memoria
        respuesta = requests.post(OLLAMA_URL, json=carga_util, stream=True, timeout=TIMEOUT_SOLICITUD)
        respuesta.raise_for_status()
        
        texto_completo = []
        
        for linea in respuesta.iter_lines():
            if linea:
                try:
                    fragmento = json.loads(linea)
                    token = fragmento.get("response", "")
                    texto_completo.append(token)
                    # Imprimir cada token en tiempo real (sin salto de línea)
                    sys.stdout.write(token)
                    sys.stdout.flush()
                    
                    # Si el modelo indica que terminó
                    if fragmento.get("done", False):
                        break
                except json.JSONDecodeError:
                    continue
        
        print("\n" + "=" * 60)
        
        # Guardar el informe completo
        informe_final = "".join(texto_completo)
        
        if informe_final.strip():
            with open(ruta_salida, 'w', encoding='utf-8') as f:
                f.write(f"<!-- Generado por Foren-Sys IA | Modelo: {MODELO_LLM} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} -->\n\n")
                f.write(informe_final)
            print(f"\n[+] ¡Análisis completado! Informe guardado en:")
            print(f"    -> {ruta_salida}")
        else:
            print("[-] La IA no generó contenido. Verifica que el modelo esté correctamente instalado.")
        
    except requests.exceptions.Timeout:
        print(f"\n[-] TIMEOUT: La IA tardó más de {TIMEOUT_SOLICITUD // 60} minutos. Intenta con un modelo más pequeño.")
    except requests.exceptions.ConnectionError:
        print("\n[-] Se perdió la conexión con Ollama durante la generación.")
        print("    Posible causa: Ollama se quedó sin memoria RAM y fue terminado por el kernel (OOM Killer).")
        print("    Solución: Reduce NUM_CTX o usa un modelo más pequeño (Ej. gemma3:1b)")
    except KeyboardInterrupt:
        print("\n\n[!] Generación cancelada por el usuario.")
        # Guardar lo que se haya generado hasta ahora
        parcial = "".join(texto_completo)
        if parcial.strip():
            ruta_parcial = ruta_salida.replace(".md", "_PARCIAL.md")
            with open(ruta_parcial, 'w', encoding='utf-8') as f:
                f.write(f"<!-- INFORME PARCIAL - Cancelado por usuario -->\n\n{parcial}")
            print(f"    Informe parcial guardado en: {ruta_parcial}")
    except requests.exceptions.RequestException as e:
        print(f"[-] Error de comunicación con la IA: {e}")

# ==========================================
# INICIO
# ==========================================
if __name__ == "__main__":
    imprimir_banner()

    # Mostrar configuración de rendimiento
    print(f"    Configuración RPi5: ctx={NUM_CTX} | threads={NUM_THREAD} | keep_alive={KEEP_ALIVE}")
    print(f"    Límite evidencia: {MAX_CARACTERES_EVIDENCIA} caracteres\n")

    if not comprobar_ollama():
        exit()

    caso_id = input("[?] ID del Caso a analizar por la IA (Ej. CASONORMA): ").strip()
    dest_input = input(f"[?] Ruta base del caso (Presiona Enter para usar {DIRECTORIO_DEFAULT}): ").strip()
    directorio_base_actual = dest_input if dest_input else DIRECTORIO_DEFAULT

    carpeta_resultados = os.path.join(directorio_base_actual, caso_id, "03_Results_(Resultados_Extraidos)")
    
    if not os.path.exists(carpeta_resultados):
        print(f"[-] ERROR: No se encontró la carpeta de resultados en: {carpeta_resultados}")
        print("    Asegúrate de haber ejecutado 06_normalizacion.py primero.")
        exit()

    ruta_informe_ia = os.path.join(carpeta_resultados, f"Dictamen_Pericial_IA_{caso_id}.md")

    # 1. Filtramos y preparamos la evidencia (con presupuesto de caracteres)
    evidencia_filtrada = recopilar_inteligencia(carpeta_resultados)
    
    if len(evidencia_filtrada) < 100:
        print("[-] Advertencia: Se encontró muy poca evidencia para analizar.")
        confirmar = input("    ¿Continuar de todos modos? (S/N): ").strip().lower()
        if confirmar != 's':
            exit()
    
    # 2. Análisis con streaming (token por token, sin acumular en RAM)
    analizar_con_ia(evidencia_filtrada, ruta_informe_ia)
