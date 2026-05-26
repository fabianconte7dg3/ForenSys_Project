import os
import re
import json
import sys
import requests
from datetime import datetime

# ==========================================
# CONFIGURACIÓN DEL LLM (Valores default — sobreescribibles por args)
# ==========================================
OLLAMA_BASE_URL   = "http://localhost:11434"   # Host Ollama (local o remoto)
OLLAMA_URL        = OLLAMA_BASE_URL + "/api/generate"
MODELO_LLM        = "gemma3:4b"               # Modelo por defecto (RPi5)
DIRECTORIO_DEFAULT = "/mnt/Destino_ForenSys"

# --- PERFIL: Raspberry Pi 5 (8 GB RAM) ---
RPI_CTX     = 2048   # Ventana de contexto conservadora
RPI_THREAD  = 4      # 4 cores físicos
RPI_TIMEOUT = 900    # 15 minutos

# --- PERFIL: PC Escritorio (Ryzen 5600G + RX 6600 XT) ---
PC_CTX     = 4096   # Ventana de contexto amplia
PC_THREAD  = 12     # 6c/12t del 5600G
PC_TIMEOUT = 300    # 5 minutos (GPU/CPU más rápida)

# Valores activos (se sobrescriben en main según el motor elegido)
NUM_CTX    = RPI_CTX
NUM_THREAD = RPI_THREAD
KEEP_ALIVE = "0"     # Descargar modelo tras responder
TIMEOUT_SOLICITUD = RPI_TIMEOUT

# Presupuesto de caracteres del prompt
MAX_CARACTERES_EVIDENCIA = 6000


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
    print(f"[*] Conectando con el motor de IA en {OLLAMA_BASE_URL} (modelo: {MODELO_LLM})...")
    try:
        respuesta = requests.get(OLLAMA_BASE_URL + "/", timeout=10)
        if respuesta.status_code == 200:
            print("[+] Servidor Ollama: EN LÍNEA")
            # Verificar que el modelo existe
            try:
                modelos = requests.get(OLLAMA_BASE_URL + "/api/tags", timeout=10).json()
                nombres = [m['name'] for m in modelos.get('models', [])]
                if MODELO_LLM in nombres or any(MODELO_LLM.split(':')[0] in n for n in nombres):
                    print(f"[+] Modelo '{MODELO_LLM}': DISPONIBLE")
                else:
                    print(f"[!] Advertencia: Modelo '{MODELO_LLM}' no encontrado.")
                    print(f"    Modelos disponibles: {', '.join(nombres) if nombres else 'Ninguno'}")
                    print(f"    Ejecuta en el motor remoto: ollama pull {MODELO_LLM}")
            except Exception:
                pass
            return True
    except requests.exceptions.ConnectionError:
        print(f"[-] ERROR: No se pudo conectar a Ollama en {OLLAMA_BASE_URL}.")
        print("    • Motor local (RPi5): sudo systemctl start ollama")
        print("    • Motor remoto (PC):  Asegúrate de que Ollama está corriendo con OLLAMA_HOST=0.0.0.0")
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
    print(f"[*] Motor: {OLLAMA_BASE_URL} | Modelo: {MODELO_LLM} | ctx: {NUM_CTX} | threads: {NUM_THREAD}")
    print("[*] La respuesta aparece en tiempo real. Ctrl+C para cancelar.\n")
    print("=" * 60)
    
    try:
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
# INICIO — Modo no interactivo (para Web o CLI)
# ==========================================
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Analizador IA Forense (Ollama) — Foren-Sys")
    parser.add_argument("--caso",   required=True,  help="ID del caso (Ej: TEST-123)")
    parser.add_argument("--dest",   required=False, default=DIRECTORIO_DEFAULT,
                        help=f"Ruta base donde vive el caso (default: {DIRECTORIO_DEFAULT})")
    parser.add_argument("--motor",  required=False, default="local",
                        choices=["local", "remoto"],
                        help="Motor Ollama: 'local' = RPi5, 'remoto' = PC Escritorio (default: local)")
    parser.add_argument("--host",   required=False, default=None,
                        help="URL del servidor Ollama remoto (Ej: http://192.168.1.50:11434). Sobreescribe --motor.")
    parser.add_argument("--model",  required=False, default=None,
                        help="Nombre del modelo a usar (Ej: gemma3:4b, llama3.2:3b, mistral:7b)")
    parser.add_argument("--ctx",    required=False, type=int, default=None,
                        help="Ventana de contexto en tokens (sobreescribe el perfil del motor)")
    parser.add_argument("--threads",required=False, type=int, default=None,
                        help="Número de hilos CPU (sobreescribe el perfil del motor)")
    args = parser.parse_args()

    # ── Limpiar inputs ───────────────────────────────────────
    caso_id               = re.sub(r'[^a-zA-Z0-9_\-]', '', args.caso.strip())
    directorio_base_actual = args.dest.strip()

    # ── Aplicar perfil de motor ──────────────────────────────
    if args.host:
        # Host explícito — tiene precedencia total sobre --motor
        OLLAMA_BASE_URL   = args.host.rstrip('/')
        OLLAMA_URL        = OLLAMA_BASE_URL + "/api/generate"
        NUM_CTX           = args.ctx     or PC_CTX      # Perfil desktop si no se especifica
        NUM_THREAD        = args.threads or PC_THREAD
        TIMEOUT_SOLICITUD = PC_TIMEOUT
        perfil_nombre     = f"Personalizado ({OLLAMA_BASE_URL})"
    elif args.motor == "remoto":
        # El host remoto está guardado en la config; si no, error
        config_path = os.path.join(directorio_base_actual, ".ia_config.json")
        if not os.path.exists(config_path):
            print("[-] ERROR: Motor remoto seleccionado pero no hay host configurado.")
            print(f"    Crea {config_path} con la IP de tu PC de escritorio,")
            print("    o usa: --host http://192.168.X.X:11434")
            sys.exit(1)
        with open(config_path, 'r') as f:
            ia_cfg = json.load(f)
        host_remoto = ia_cfg.get('remote_host', '').rstrip('/')
        if not host_remoto:
            print("[-] ERROR: 'remote_host' está vacío en la configuración.")
            sys.exit(1)
        OLLAMA_BASE_URL   = host_remoto
        OLLAMA_URL        = OLLAMA_BASE_URL + "/api/generate"
        NUM_CTX           = args.ctx     or ia_cfg.get('ctx',     PC_CTX)
        NUM_THREAD        = args.threads or ia_cfg.get('threads', PC_THREAD)
        TIMEOUT_SOLICITUD = ia_cfg.get('timeout', PC_TIMEOUT)
        perfil_nombre     = f"PC Escritorio Remoto ({OLLAMA_BASE_URL})"
    else:
        # Motor local (RPi5) — default
        OLLAMA_BASE_URL   = "http://localhost:11434"
        OLLAMA_URL        = OLLAMA_BASE_URL + "/api/generate"
        NUM_CTX           = args.ctx     or RPI_CTX
        NUM_THREAD        = args.threads or RPI_THREAD
        TIMEOUT_SOLICITUD = RPI_TIMEOUT
        perfil_nombre     = "Raspberry Pi 5 (Local)"

    # Modelo: argumento explícito tiene precedencia
    if args.model:
        MODELO_LLM = args.model.strip()

    print(f"[PROGRESO:5] Iniciando Triaje IA para el caso: {caso_id}")
    print(f"    Motor:   {perfil_nombre}")
    print(f"    Modelo:  {MODELO_LLM}")
    print(f"    Config:  ctx={NUM_CTX} | threads={NUM_THREAD} | timeout={TIMEOUT_SOLICITUD}s")
    print(f"    Evidencia máx.: {MAX_CARACTERES_EVIDENCIA} caracteres")

    # ── Verificar Ollama ─────────────────────────────────────
    print(f"[PROGRESO:10] Verificando motor Ollama...")
    if not comprobar_ollama():
        print("[-] ERROR: Motor Ollama no disponible.")
        sys.exit(1)

    # ── Localizar carpeta de resultados ───────────────────────
    carpeta_resultados = os.path.join(directorio_base_actual, caso_id, "03_Results_(Resultados_Extraidos)")
    if not os.path.exists(carpeta_resultados):
        print(f"[-] ERROR: No se encontró la carpeta de resultados en: {carpeta_resultados}")
        print("    Asegúrate de haber ejecutado el Módulo 7 (Normalización) primero.")
        sys.exit(1)

    ruta_informe_ia = os.path.join(carpeta_resultados, f"Dictamen_Pericial_IA_{caso_id}.md")

    # ── Recopilar evidencia ─────────────────────────────────
    print("[PROGRESO:30] Recopilando y filtrando evidencia de los módulos anteriores...")
    evidencia_filtrada = recopilar_inteligencia(carpeta_resultados)
    if len(evidencia_filtrada) < 50:
        print("[-] Advertencia: Poca evidencia disponible. ¿Ejecutaste el Módulo 7?")
        print("[-] Continuando con la evidencia disponible...")

    # ── Análisis IA ─────────────────────────────────────────
    print(f"[PROGRESO:60] Transmitiendo evidencia al LLM (motor: {perfil_nombre})...")
    analizar_con_ia(evidencia_filtrada, ruta_informe_ia)

    if os.path.exists(ruta_informe_ia):
        print(f"[PROGRESO:100] Dictamen Pericial guardado en: {ruta_informe_ia}")
    else:
        print("[-] ERROR: No se generó el informe final.")
        sys.exit(1)
