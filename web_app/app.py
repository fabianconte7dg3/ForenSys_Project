import os
import subprocess
import psutil
import shutil
import hashlib
import json
import re
import queue
import threading
import time
from datetime import datetime, timezone
from flask import Flask, render_template, jsonify, request, Response, stream_with_context

app = Flask(__name__)

# ── Real-time Log Stream via SSE ──────────────────────────────────
# Global queue: worker threads push lines, SSE endpoint pops them
log_queue = queue.Queue(maxsize=500)

# Currently running process (for signal/kill support)
running_proc = None
running_proc_lock = threading.Lock()

def push_log(message: str, level: str = 'info'):
    """Thread-safe helper to push a log line into the SSE queue."""
    ts = datetime.now().strftime('%H:%M:%S.') + f"{datetime.now().microsecond // 1000:03d}"
    entry = json.dumps({'ts': ts, 'msg': message, 'level': level})
    try:
        log_queue.put_nowait(entry)
    except queue.Full:
        pass  # Drop when queue is full (shouldn't happen in normal use)


# Definir la ruta base de tus scripts
SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts'))

# Ruta base donde se almacenan los casos forenses
CASES_BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'Casos_ForenSys'))
# Registro centralizado de casos
CASES_REGISTRY = os.path.join(CASES_BASE_DIR, 'casos_registro.json')

# --- Utilidades de Seguridad ---

def sanitize_case_id(caso_id):
    """Sanitiza el ID de caso para prevenir path traversal.
    Solo permite letras, números, guiones y guiones bajos."""
    sanitized = re.sub(r'[^a-zA-Z0-9_\-]', '', caso_id)
    if not sanitized:
        return None
    return sanitized

def sha256_file(filepath):
    """Calcula SHA-256 de un archivo individual."""
    h = hashlib.sha256()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()

def sha256_directory(dirpath):
    """Calcula SHA-256 recursivo de toda una carpeta (cadena de custodia)."""
    h = hashlib.sha256()
    for root, dirs, files in sorted(os.walk(dirpath)):
        dirs.sort()
        for filename in sorted(files):
            filepath = os.path.join(root, filename)
            # Incluir ruta relativa + contenido del archivo en el hash
            rel_path = os.path.relpath(filepath, dirpath)
            h.update(rel_path.encode('utf-8'))
            try:
                with open(filepath, 'rb') as f:
                    for chunk in iter(lambda: f.read(8192), b''):
                        h.update(chunk)
            except (PermissionError, OSError):
                h.update(b'UNREADABLE')
    return h.hexdigest()

def load_registry():
    """Carga el registro de casos desde disco."""
    if not os.path.exists(CASES_REGISTRY):
        return []
    try:
        with open(CASES_REGISTRY, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []

def save_registry(registry):
    """Guarda el registro de casos a disco."""
    os.makedirs(os.path.dirname(CASES_REGISTRY), exist_ok=True)
    with open(CASES_REGISTRY, 'w', encoding='utf-8') as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)

# --- Rutas de Gestión de Casos ---

@app.route('/api/case/open', methods=['POST'])
def open_case():
    """Abre un caso: crea carpetas, contexto_incidente.json y cadena de custodia."""
    data = request.json or {}
    raw_caso_id = data.get('caso_id', '').strip()
    perito = data.get('perito', '').strip()
    clasificacion = data.get('clasificacion', '').strip() or 'No especificada'
    notas = data.get('notas', '').strip() or 'Sin notas del incidente.'

    # Validación de entrada
    caso_id = sanitize_case_id(raw_caso_id)
    if not caso_id or not perito:
        return jsonify({"status": "error", "message": "caso_id y perito son obligatorios."}), 400

    if len(perito) > 200 or len(clasificacion) > 200 or len(notas) > 5000:
        return jsonify({"status": "error", "message": "Longitud de campos excede el límite permitido."}), 400

    # Verificar que no exista ya un caso abierto con ese ID
    registry = load_registry()
    for caso in registry:
        if caso['caso_id'] == caso_id and caso['estado'] == 'abierto':
            return jsonify({"status": "error", "message": f"El caso {caso_id} ya está abierto."}), 409

    now_iso = datetime.now(timezone.utc).isoformat()
    now_local = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Crear estructura de carpetas forense
    carpeta_caso = os.path.join(CASES_BASE_DIR, caso_id)
    subcarpetas = [
        os.path.join(carpeta_caso, '01_Images_(Fuentes_de_datos)'),
        os.path.join(carpeta_caso, '02_Views_(Vistas)'),
        os.path.join(carpeta_caso, '03_Results_(Resultados_Extraidos)'),
        os.path.join(carpeta_caso, '04_Archivos_Borrados_Recuperados'),
    ]
    try:
        for carpeta in subcarpetas:
            os.makedirs(carpeta, exist_ok=True)
    except OSError as e:
        return jsonify({"status": "error", "message": f"No se pudo crear estructura de carpetas: {e}"}), 500

    # Generar contexto_incidente.json para la IA
    contexto = {
        "caso_id": caso_id,
        "perito": perito,
        "clasificacion": clasificacion,
        "timestamp": now_iso,
        "notas": notas
    }
    ruta_contexto = os.path.join(carpeta_caso, '03_Results_(Resultados_Extraidos)', 'contexto_incidente.json')
    try:
        with open(ruta_contexto, 'w', encoding='utf-8') as f:
            json.dump(contexto, f, ensure_ascii=False, indent=2)
    except IOError as e:
        return jsonify({"status": "error", "message": f"No se pudo escribir contexto_incidente.json: {e}"}), 500

    # Hash de integridad del contexto
    hash_contexto = sha256_file(ruta_contexto)

    # Iniciar cadena de custodia (log append-only)
    ruta_custodia = os.path.join(carpeta_caso, 'cadena_custodia.log')
    try:
        with open(ruta_custodia, 'a', encoding='utf-8') as f:
            f.write(f"[{now_iso}] [APERTURA] Caso '{caso_id}' abierto por perito '{perito}'\n")
            f.write(f"[{now_iso}] [CLASIFICACIÓN] {clasificacion}\n")
            f.write(f"[{now_iso}] [INTEGRIDAD] SHA-256 de contexto_incidente.json: {hash_contexto}\n")
            f.write(f"[{now_iso}] [NOTAS] {notas}\n")
            f.write("-" * 80 + "\n")
    except IOError as e:
        return jsonify({"status": "error", "message": f"No se pudo escribir cadena de custodia: {e}"}), 500

    # Registrar en el índice maestro
    registro_caso = {
        "caso_id": caso_id,
        "perito": perito,
        "clasificacion": clasificacion,
        "fecha_apertura": now_iso,
        "estado": "abierto",
        "ruta": carpeta_caso,
        "hash_contexto": hash_contexto,
        "hash_cierre": None,
        "fecha_cierre": None
    }
    registry.append(registro_caso)
    save_registry(registry)

    return jsonify({
        "status": "success",
        "message": f"Caso {caso_id} registrado exitosamente.",
        "caso_id": caso_id,
        "ruta_caso": carpeta_caso,
        "hash_contexto": hash_contexto
    })

@app.route('/api/case/list', methods=['GET'])
def list_cases():
    """Lista todos los casos registrados."""
    registry = load_registry()
    return jsonify({"status": "success", "cases": registry})

@app.route('/api/case/close', methods=['POST'])
def close_case():
    """Cierra un caso: calcula hash maestro y sella la cadena de custodia."""
    data = request.json or {}
    raw_caso_id = data.get('caso_id', '').strip()

    caso_id = sanitize_case_id(raw_caso_id)
    if not caso_id:
        return jsonify({"status": "error", "message": "caso_id es obligatorio."}), 400

    registry = load_registry()
    caso_encontrado = None
    for caso in registry:
        if caso['caso_id'] == caso_id and caso['estado'] == 'abierto':
            caso_encontrado = caso
            break

    if not caso_encontrado:
        return jsonify({"status": "error", "message": f"No se encontró un caso abierto con ID: {caso_id}"}), 404

    carpeta_caso = caso_encontrado['ruta']
    # Validar que la ruta del caso está dentro de CASES_BASE_DIR
    resolved = os.path.realpath(carpeta_caso)
    if not resolved.startswith(os.path.realpath(CASES_BASE_DIR) + os.sep):
        return jsonify({"status": "error", "message": "Ruta del caso inválida."}), 403

    if not os.path.exists(carpeta_caso):
        return jsonify({"status": "error", "message": "La carpeta del caso no existe en disco."}), 404

    now_iso = datetime.now(timezone.utc).isoformat()

    # Calcular hash maestro SHA-256 de toda la carpeta
    hash_maestro = sha256_directory(carpeta_caso)

    # Sellar cadena de custodia
    ruta_custodia = os.path.join(carpeta_caso, 'cadena_custodia.log')
    try:
        with open(ruta_custodia, 'a', encoding='utf-8') as f:
            f.write(f"[{now_iso}] [CIERRE] Caso cerrado.\n")
            f.write(f"[{now_iso}] [HASH MAESTRO] SHA-256 de carpeta completa: {hash_maestro}\n")
            f.write("=" * 80 + "\n")
    except IOError:
        pass

    # Actualizar registro
    caso_encontrado['estado'] = 'cerrado'
    caso_encontrado['hash_cierre'] = hash_maestro
    caso_encontrado['fecha_cierre'] = now_iso
    save_registry(registry)

    return jsonify({
        "status": "success",
        "message": f"Caso {caso_id} cerrado y sellado.",
        "hash_maestro": hash_maestro,
        "fecha_cierre": now_iso
    })

@app.route('/api/case/load_from_path', methods=['POST'])
def load_case_from_path():
    """Carga un caso existente desde una ruta específica."""
    data = request.json or {}
    ruta_caso = data.get('ruta', '').strip()

    if not ruta_caso or not os.path.exists(ruta_caso):
        return jsonify({"status": "error", "message": "Ruta inválida o no existe."}), 404

    # Verificar si es una carpeta de caso válida comprobando contexto_incidente.json
    ruta_contexto = os.path.join(ruta_caso, '03_Results_(Resultados_Extraidos)', 'contexto_incidente.json')
    if not os.path.exists(ruta_contexto):
        return jsonify({"status": "error", "message": "No se encontró contexto_incidente.json en la ruta especificada."}), 400

    try:
        with open(ruta_contexto, 'r', encoding='utf-8') as f:
            contexto = json.load(f)
    except Exception as e:
        return jsonify({"status": "error", "message": f"Error al leer contexto: {e}"}), 500

    caso_id = contexto.get('caso_id')
    if not caso_id:
        return jsonify({"status": "error", "message": "El archivo de contexto está corrupto (falta caso_id)."}), 400

    # Calcular hash actual del contexto
    hash_contexto = sha256_file(ruta_contexto)

    # Verificar cadena de custodia para determinar estado
    ruta_custodia = os.path.join(ruta_caso, 'cadena_custodia.log')
    estado = "abierto"
    hash_cierre = None
    fecha_cierre = None
    if os.path.exists(ruta_custodia):
        try:
            with open(ruta_custodia, 'r', encoding='utf-8') as f:
                contenido_custodia = f.read()
                if "[CIERRE]" in contenido_custodia:
                    estado = "cerrado"
                    # Intentar extraer el hash de cierre (última línea relevante)
                    lineas = contenido_custodia.splitlines()
                    for linea in reversed(lineas):
                        if "[HASH MAESTRO]" in linea:
                            partes = linea.split(":")
                            if len(partes) > 1:
                                hash_cierre = partes[-1].strip()
                            break
        except Exception:
            pass

    # Agregar o actualizar el registro en casos_registro.json
    registry = load_registry()
    caso_existente = next((c for c in registry if c['caso_id'] == caso_id), None)
    
    registro_actualizado = {
        "caso_id": caso_id,
        "perito": contexto.get('perito', 'Desconocido'),
        "clasificacion": contexto.get('clasificacion', 'No especificada'),
        "fecha_apertura": contexto.get('timestamp', ''),
        "estado": estado,
        "ruta": ruta_caso,
        "hash_contexto": hash_contexto,
        "hash_cierre": hash_cierre,
        "fecha_cierre": fecha_cierre
    }

    if caso_existente:
        caso_existente.update(registro_actualizado)
    else:
        registry.append(registro_actualizado)
        
    save_registry(registry)

    return jsonify({
        "status": "success",
        "message": f"Caso {caso_id} importado exitosamente.",
        "caso": registro_actualizado,
        "notas": contexto.get('notas', '')
    })

@app.route('/')
def home():
    """Sirve el panel principal (index.html)"""
    return render_template('index.html')

@app.route('/api/explore', methods=['POST'])
def explore_files():
    """Explorador de archivos para el frontend"""
    data = request.json or {}
    # Directorio base por defecto: la raíz o el punto de montaje forense
    current_path = data.get('path', '/')
    
    if not os.path.exists(current_path):
        return jsonify({"status": "error", "message": "La ruta no existe"}), 404

    try:
        items = []
        for item_name in os.listdir(current_path):
            item_path = os.path.join(current_path, item_name)
            is_dir = os.path.isdir(item_path)
            items.append({
                "name": item_name,
                "path": item_path,
                "is_dir": is_dir
            })
        # Ordenar: primero las carpetas, luego archivos
        items.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
        
        # Obtener ruta padre para el botón de "Atrás"
        parent_path = os.path.dirname(current_path)
        
        return jsonify({
            "status": "success", 
            "current_path": current_path, 
            "parent_path": parent_path,
            "items": items
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/list_devices', methods=['GET'])
def list_devices():
    """Lista dispositivos de bloque disponibles via lsblk para selección desde UI"""
    try:
        result = subprocess.run(
            ['lsblk', '-J', '-o', 'NAME,SIZE,MODEL,TYPE,MOUNTPOINT,RM'],
            capture_output=True, text=True, check=True
        )
        lsblk_data = json.loads(result.stdout)

        devices = []
        def parse_device(dev):
            path = f"/dev/{dev['name']}"
            entry = {
                'name': dev['name'],
                'path': path,
                'size': dev.get('size', '?'),
                'model': dev.get('model') or '',
                'type': dev.get('type', ''),
                'mountpoint': dev.get('mountpoint') or '',
                'removable': dev.get('rm', False),
            }
            devices.append(entry)
            for child in dev.get('children', []):
                parse_device(child)

        for dev in lsblk_data.get('blockdevices', []):
            parse_device(dev)

        return jsonify({"status": "success", "devices": devices})
    except subprocess.CalledProcessError as e:
        return jsonify({"status": "error", "message": f"lsblk error: {e.stderr}"}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/verify_disk', methods=['POST'])
def verify_disk():
    """Realiza las validaciones ISO/IEC 27037 previas a la extracción forense."""
    data = request.json or {}
    target_disk = data.get('target_disk', '').strip()
    
    if not target_disk or not target_disk.startswith('/dev/'):
        return jsonify({"status": "error", "message": "Debe especificar un disco origen válido."}), 400
        
    resultados = {
        "readonly": False,
        "destino_ok": False,
        "cadena_ok": True  # Listo para generarse en el script
    }
    
    # 1. Verificar Bloqueador de Escritura por Software (Logical Write Blocker)
    try:
        # Verificar estado de solo lectura (RO=1)
        check = subprocess.run(['lsblk', '-o', 'RO', '-n', '-d', target_disk], capture_output=True, text=True, timeout=3)
        if "1" in check.stdout:
            resultados['readonly'] = True
    except subprocess.TimeoutExpired:
        pass # Ignorar timeout
    except subprocess.CalledProcessError as e:
        push_log(f'[WARN] No se pudo verificar modo de solo lectura: {e}', 'warn')
        
    # 2. Verificar Destino Montado
    if os.path.ismount('/mnt/Destino_ForenSys'):
        resultados['destino_ok'] = True
        
    status = "success" if (resultados['readonly'] and resultados['destino_ok']) else "warning"
    msg = "Verificación completada." if status == "success" else "Revisar pre-requisitos."
    
    return jsonify({
        "status": status,
        "message": msg,
        "checks": resultados
    })

@app.route('/api/set_readonly', methods=['POST'])
def set_readonly():
    data = request.json or {}
    target_disk = data.get('target_disk', '').strip()
    if not target_disk or not target_disk.startswith('/dev/'):
        return jsonify({"status": "error", "message": "Disco inválido."}), 400
        
    try:
        # Ejecuta el script de python con sudo que ya está autorizado en sudoers sin contraseña
        subprocess.run(['sudo', 'python3', '/home/ciber-admin/ForenSys_Project/scripts/02_deadbox_v2.py', '-t', target_disk, '--set-readonly-only'], check=True, capture_output=True, text=True)
        return jsonify({"status": "success", "message": "Bloqueador activado."})
    except subprocess.CalledProcessError as e:
        push_log(f'[ERROR] Falló activación readonly: {e.stderr}', 'error')
        return jsonify({"status": "error", "message": "Fallo al activar bloqueador lógico."}), 500

@app.route('/api/run/timeline', methods=['POST'])
def run_timeline():
    """Ejecuta el script de normalización en segundo plano"""
    data = request.json or {}
    caso_id = data.get('caso_id')
    ruta_evidencia = data.get('ruta_evidencia')
    
    if not caso_id or not ruta_evidencia:
        return jsonify({"status": "error", "message": "Faltan parámetros 'caso_id' o 'ruta_evidencia'"}), 400
        
    script_path = os.path.join(SCRIPTS_DIR, '06_normalizacion.py')
    
    # Verificamos si el script existe antes de intentar ejecutarlo
    if not os.path.exists(script_path):
        return jsonify({"status": "error", "message": f"Script no encontrado en: {script_path}"}), 404

    try:
        # Iniciamos el proceso inyectando los argumentos recogidos de la web
        comando = ['sudo', 'python3', script_path, '--caso', caso_id, '--ruta', ruta_evidencia]
        proceso = subprocess.Popen(comando, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        return jsonify({
            "status": "success", 
            "message": f"Proceso iniciado exitosamente para el caso: {caso_id}",
            "comando_ejecutado": " ".join(comando)
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/telemetry', methods=['POST'])
def get_telemetry():
    """Retorna la telemetría del sistema en tiempo real"""
    data = request.json or {}
    storage_path = data.get('storage_path', '/')
    
    # Validar ruta de almacenamiento (fallback a '/' si no existe)
    if not os.path.exists(storage_path):
        storage_path = '/'
        
    try:
        # CPU
        cpu_percent = psutil.cpu_percent(interval=0.1)
        
        # RAM
        ram = psutil.virtual_memory()
        ram_total_gb = ram.total / (1024**3)
        ram_free_gb = ram.available / (1024**3)
        ram_percent = ram.percent
        
        # Almacenamiento — usa el mountpoint del dispositivo seleccionado si se recibe
        device_path = data.get('device_path', None)
        if device_path:
            # Find mountpoint for this block device via psutil
            mp = None
            for part in psutil.disk_partitions(all=True):
                if part.device == device_path:
                    mp = part.mountpoint
                    break
            storage_path = mp if mp else storage_path

        disk = shutil.disk_usage(storage_path)
        disk_total_gb = disk.total / (1024**3)
        disk_free_gb = disk.free / (1024**3)
        disk_used_gb = disk.used / (1024**3)
        disk_percent = (disk.used / disk.total) * 100 if disk.total > 0 else 0

        # Temperatura — Raspberry Pi (vcgencmd) y fallback genérico (psutil)
        temp_data = []
        try:
            # Try vcgencmd first (Raspberry Pi native)
            vc_result = subprocess.run(
                ['vcgencmd', 'measure_temp'],
                capture_output=True, text=True, timeout=2
            )
            if vc_result.returncode == 0:
                # Output: temp=52.0'C
                import re as _re
                m = _re.search(r'temp=([\d.]+)', vc_result.stdout)
                if m:
                    temp_data.append({'label': 'CPU (Raspberry Pi)', 'celsius': float(m.group(1))})
        except Exception:
            pass

        if not temp_data:
            # Fallback: psutil sensors_temperatures
            try:
                sensors = psutil.sensors_temperatures()
                for chip, entries in sensors.items():
                    for entry in entries:
                        if entry.current and entry.current > 0:
                            temp_data.append({
                                'label': f'{chip} — {entry.label or "temp"}',
                                'celsius': round(entry.current, 1)
                            })
            except Exception:
                pass

        return jsonify({
            "status": "success",
            "cpu": {
                "percent": round(cpu_percent, 1)
            },
            "ram": {
                "total_gb": round(ram_total_gb, 1),
                "free_gb": round(ram_free_gb, 1),
                "percent": round(ram_percent, 1)
            },
            "storage": {
                "path": storage_path,
                "total_gb": round(disk_total_gb, 1),
                "free_gb": round(disk_free_gb, 1),
                "used_gb": round(disk_used_gb, 1),
                "percent": round(disk_percent, 1)
            },
            "temperature": temp_data
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/logs/stream')
def stream_logs():
    """SSE endpoint — sends real-time log entries to the browser"""
    def event_generator():
        # Send a keepalive comment first so browser knows stream started
        yield ': keepalive\n\n'
        while True:
            try:
                entry = log_queue.get(timeout=20)  # 20-second timeout acts as heartbeat
                yield f'data: {entry}\n\n'
            except queue.Empty:
                # Send SSE comment as heartbeat to keep connection alive
                yield ': heartbeat\n\n'

    return Response(
        stream_with_context(event_generator()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        }
    )


@app.route('/api/run_command', methods=['POST'])
def run_command_api():
    """Executes a shell command and streams its output to the SSE log queue.
    This powers the Manual Command Mode in the UI."""
    global running_proc

    data = request.json or {}
    cmd = data.get('command', '').strip()
    caso_id = data.get('caso_id', 'MANUAL')

    if not cmd:
        return jsonify({'status': 'error', 'message': 'Comando vacío'}), 400

    def run_in_thread(command, case):
        global running_proc
        push_log(f'[OPERADOR] Ejecutando: {command}', 'warn')
        try:
            env = os.environ.copy()
            env['PYTHONUNBUFFERED'] = '1'
            proc = subprocess.Popen(
                command, shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env
            )
            with running_proc_lock:
                running_proc = proc

            for line in iter(proc.stdout.readline, ''):
                line = line.rstrip('\n')
                if line:
                    push_log(line, 'info')

            proc.wait()
            rc = proc.returncode
            if rc == 0:
                push_log(f'[OK] Proceso finalizado (código de salida: {rc})', 'success')
            else:
                push_log(f'[ERROR] Proceso terminado con código: {rc}', 'error')
        except Exception as e:
            push_log(f'[ERROR] Excepción al ejecutar comando: {e}', 'error')
        finally:
            with running_proc_lock:
                running_proc = None

    t = threading.Thread(target=run_in_thread, args=(cmd, caso_id), daemon=True)
    t.start()
    return jsonify({'status': 'success', 'message': 'Comando enviado al ejecutor'})


@app.route('/api/kill_command', methods=['POST'])
def kill_command():
    """Terminates the currently running subprocess if any."""
    global running_proc
    with running_proc_lock:
        if running_proc and running_proc.poll() is None:
            # Send term signal to the immediate process (sudo)
            # The python script inside sudo will catch it and kill its children.
            running_proc.terminate()
            push_log('[SISTEMA] Proceso interrumpido por el operador.', 'warn')
            return jsonify({'status': 'success', 'message': 'Proceso terminado'})
    return jsonify({'status': 'error', 'message': 'No hay proceso activo'})


if __name__ == '__main__':
    # Escucha en todas las interfaces de red de la Raspberry Pi
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)
