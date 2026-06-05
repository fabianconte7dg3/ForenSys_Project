import os
import sys
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
from flask import Flask, render_template, jsonify, request, Response, stream_with_context, send_from_directory

app = Flask(__name__)

# ── Real-time Log Stream via SSE ──────────────────────────────────
# PubSub model: each SSE connection gets its own queue
log_subscribers = []
log_subscribers_lock = threading.Lock()

# Currently running process (for signal/kill support)
running_proc = None
running_proc_lock = threading.Lock()

def push_log(message: str, level: str = 'info'):
    """Thread-safe helper to push a log line into the SSE queue."""
    ts = datetime.now().strftime('%H:%M:%S.') + f"{datetime.now().microsecond // 1000:03d}"
    entry = json.dumps({'ts': ts, 'msg': message, 'level': level})
    with log_subscribers_lock:
        for q in log_subscribers:
            try:
                q.put_nowait(entry)
            except queue.Full:
                pass


# Definir la ruta base de tus scripts
SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts'))

# Ruta base donde se almacenan los casos forenses (local)
CASES_BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'Casos_ForenSys'))
# Registro centralizado de casos
CASES_REGISTRY = os.path.join(CASES_BASE_DIR, 'casos_registro.json')
# Dispositivo externo forense — toda la evidencia real vive aquí
DESTINO_FORENSYS = '/mnt/Destino_ForenSys'

# ── Protección: Disco del Sistema Operativo ────────────────────────────────
def get_system_disk():
    """Detecta el disco físico que aloja el sistema operativo (donde está montado /).

    Funciona con cualquier nombre de dispositivo: mmcblk0, sda, nvme0n1, etc.
    Retorna un set con el disco base y TODAS sus particiones, por ejemplo:
        {'mmcblk0', 'mmcblk0p1', 'mmcblk0p2'}
    De esta forma ninguna partición del disco del sistema puede ser
    accedida por las herramientas forenses, previniendo borrados accidentales.
    """
    protected = set()
    try:
        # Obtener el dispositivo que contiene el mount point raíz '/'
        result = subprocess.run(
            ['lsblk', '-J', '-o', 'NAME,MOUNTPOINT,PKNAME,TYPE'],
            capture_output=True, text=True, check=True
        )
        data = json.loads(result.stdout)

        # 1) Encontrar el nombre del disco padre donde está montado '/'
        system_disk_name = None

        def find_root_disk(devices):
            """Busca recursivamente el disco padre del mount point '/'."""
            nonlocal system_disk_name
            for dev in devices:
                if dev.get('mountpoint') == '/':
                    # pkname = disco padre (p.ej. 'mmcblk0' para 'mmcblk0p2')
                    pkname = dev.get('pkname')
                    if pkname:
                        system_disk_name = pkname
                    else:
                        # El propio dispositivo es el disco (sin partición)
                        system_disk_name = dev['name']
                    return
                find_root_disk(dev.get('children', []))

        find_root_disk(data.get('blockdevices', []))

        if not system_disk_name:
            return protected  # No se pudo determinar — falla segura (no protege nada)

        # 2) Recopilar el disco y TODAS sus particiones/hijos
        def collect_disk_and_children(devices):
            for dev in devices:
                if dev['name'] == system_disk_name or dev.get('pkname') == system_disk_name:
                    protected.add(dev['name'])
                collect_disk_and_children(dev.get('children', []))

        collect_disk_and_children(data.get('blockdevices', []))
        protected.add(system_disk_name)  # Asegurar que el disco base siempre esté

    except Exception:
        pass  # Falla silenciosa — la UI mostrará todos los discos en el peor caso

    return protected

# Calcular al iniciar la app (una sola vez) para no impactar rendimiento
SYSTEM_DISK_NAMES = get_system_disk()

def get_case_results_path(caso_id):
    """Devuelve la ruta a la carpeta de resultados del caso,
    buscando primero en el dispositivo externo y luego en local."""
    for base in (DESTINO_FORENSYS, CASES_BASE_DIR):
        ruta = os.path.join(base, caso_id, '03_Results_(Resultados_Extraidos)')
        if os.path.exists(ruta):
            return ruta
    return None

def get_case_base_from_registry(caso_id):
    """Obtiene la ruta base del caso desde el registro (puede ser ext. o local)."""
    registry = load_registry()
    for caso in registry:
        if caso.get('caso_id') == caso_id:
            ruta = caso.get('ruta', '')
            if ruta:
                return os.path.dirname(ruta)  # ruta_base es la carpeta padre del caso
    return DESTINO_FORENSYS

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
    if request.headers.get('HX-Request'):
        if not registry:
            return "<tr><td colspan='6' class='text-center py-4 text-gray-500'>No hay casos registrados aún.</td></tr>"
        
        html = ""
        for caso in registry:
            fecha = caso.get('fecha_apertura', '')[:19].replace('T', ' ') if caso.get('fecha_apertura') else '—'
            estado = caso.get('estado', 'abierto')
            
            if estado == 'abierto':
                badge = "<span style='padding: 2px 10px; border-radius: 4px; font-size: 0.72rem; font-weight: 600; background: rgba(16,185,129,.15); color: var(--accent-green);'>ABIERTO</span>"
            else:
                badge = "<span style='padding: 2px 10px; border-radius: 4px; font-size: 0.72rem; font-weight: 600; background: rgba(239,68,68,.15); color: var(--accent-red);'>CERRADO</span>"
                
            hash_ctx = caso.get('hash_contexto', '')
            hash_display = f"<a href='#' onclick='event.preventDefault(); showHashDetails(\"Hash del Contexto de Incidente\", \"{hash_ctx}\", \"Garantiza que los datos iniciales del caso no han sido alterados.\");' style='font-family: var(--font-mono); font-size: 0.72rem;' title='{hash_ctx}'>{hash_ctx[:16]}...</a>" if hash_ctx else '—'
                
            html += f"""
            <tr class="hover:bg-white/5 transition-colors">
                <td style="font-family: var(--font-mono); padding: 14px 18px;">{caso.get('caso_id', '')}</td>
                <td style="padding: 14px 18px;">{caso.get('perito', '')}</td>
                <td style="padding: 14px 18px;">{caso.get('clasificacion', '')}</td>
                <td style="font-size: 0.78rem; padding: 14px 18px;">{fecha}</td>
                <td style="padding: 14px 18px;">{badge}</td>
                <td style="padding: 14px 18px;">{hash_display}</td>
                <td style="padding: 14px 18px;">
                    <button class="pipe-btn pb-blue" style="padding: 4px 10px; font-size: 0.7rem;" onclick="loadCaseFromPath('{caso.get('ruta', '')}')">
                        <i class="bi bi-folder-symlink"></i> Cargar
                    </button>
                </td>
            </tr>
            """
        return html
        
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
    # Validar que la ruta del caso está dentro de CASES_BASE_DIR o DESTINO_FORENSYS
    resolved = os.path.realpath(carpeta_caso)
    allowed_bases = [
        os.path.realpath(CASES_BASE_DIR) + os.sep,
        os.path.realpath(DESTINO_FORENSYS) + os.sep,
    ]
    if not any(resolved.startswith(base) for base in allowed_bases):
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


@app.route('/api/case/<raw_caso_id>/results', methods=['GET'])
def list_case_results(raw_caso_id):
    """Lista los archivos de resultados de normalización (03_Results) para el Explorador de Evidencia."""
    caso_id = sanitize_case_id(raw_caso_id)
    if not caso_id:
        return jsonify({"status": "error", "message": "caso_id inválido."}), 400

    ruta_results = get_case_results_path(caso_id)
    if not ruta_results:
        return jsonify({"status": "ok", "archivos": [], "message": "No se encontró carpeta de resultados."})

    # Archivos clave producidos por la normalización
    archivos_clave = [
        {"key": "reporte_maestro",         "filename": "Reporte_Forense_Maestro.txt",         "tipo": "txt",  "categoria": "Super Timeline",        "icono": "bi-file-text-fill",         "color": "#93c5fd"},
        {"key": "master_timeline",         "filename": "Master_Timeline.jsonl",               "tipo": "jsonl", "categoria": "Super Timeline",       "icono": "bi-filetype-json",          "color": "#93c5fd"},
        {"key": "filesystem_timeline",     "filename": "filesystem_timeline.csv",             "tipo": "csv",  "categoria": "Super Timeline",        "icono": "bi-table",                  "color": "#6ee7b7"},
        {"key": "eventos_sistema",         "filename": "Eventos_Sistema.csv",                 "tipo": "csv",  "categoria": "Seguridad y Eventos",   "icono": "bi-shield-lock",            "color": "#6ee7b7"},
        {"key": "web_history",             "filename": "Web_History_and_Bookmarks.txt",       "tipo": "txt",  "categoria": "Artefactos Web",        "icono": "bi-globe",                  "color": "#67e8f9"},
        {"key": "descargas_web",           "filename": "Descargas_Web.csv",                   "tipo": "csv",  "categoria": "Artefactos Web",        "icono": "bi-cloud-arrow-down-fill",  "color": "#67e8f9"},
        {"key": "usuarios_equipo",         "filename": "Usuarios_Equipo.csv",                 "tipo": "csv",  "categoria": "Sistema y Persistencia","icono": "bi-person-fill",            "color": "#c4b5fd"},
        {"key": "hardware_usb",            "filename": "Hardware_y_USB.csv",                  "tipo": "csv",  "categoria": "Sistema y Persistencia","icono": "bi-usb-symbol",             "color": "#c4b5fd"},
        {"key": "programas_instalados",    "filename": "Lista_Programas_Instalados.csv",      "tipo": "csv",  "categoria": "Sistema y Persistencia","icono": "bi-grid-3x3-gap-fill",      "color": "#c4b5fd"},
        {"key": "mecanismos_persistencia", "filename": "Mecanismos_Persistencia.csv",          "tipo": "csv",  "categoria": "Sistema y Persistencia","icono": "bi-exclamation-triangle-fill","color": "#fcd34d"},
        {"key": "archivos_borrados",       "filename": "Archivos_Borrados_Recuperados.jsonl", "tipo": "jsonl","categoria": "Recuperación y Anomalías","icono": "bi-trash3-fill",            "color": "#fcd34d"},
        {"key": "metadatos_multimedia",    "filename": "Metadatos_Multimedia.csv",             "tipo": "csv",  "categoria": "Recuperación y Anomalías","icono": "bi-camera-fill",            "color": "#fcd34d"},
        {"key": "sintesis_ia",              "filename": f"Sintesis_IA_{caso_id}.md",         "tipo": "md",   "categoria": "Síntesis IA",           "icono": "bi-robot",                  "color": "#fca5a5"},
        {"key": "auditoria_ia",             "filename": f"Auditoria_IA_{caso_id}_*.json",    "tipo": "json", "categoria": "Síntesis IA",           "icono": "bi-filetype-json",          "color": "#fb923c"},
    ]

    resultado = []
    for arch in archivos_clave:
        patron = arch["filename"]
        if '*' in patron:
            # Archivo con timestamp en el nombre — buscar el más reciente
            import glob as _glob
            matches = sorted(_glob.glob(os.path.join(ruta_results, patron)))
            if not matches:
                continue
            ruta_archivo = matches[-1]  # Tomar el más reciente
            filename_real = os.path.basename(ruta_archivo)
        else:
            ruta_archivo  = os.path.join(ruta_results, patron)
            filename_real = patron
            if not os.path.exists(ruta_archivo):
                continue

        stat = os.stat(ruta_archivo)
        size_kb = round(stat.st_size / 1024, 1)
        resultado.append({
            "key":      arch["key"],
            "filename": filename_real,
            "tipo":     arch["tipo"],
            "categoria":arch["categoria"],
            "icono":    arch["icono"],
            "color":    arch["color"],
            "size_kb":  size_kb,
            "ruta_abs": ruta_archivo,
        })

    ruta_recuperados = os.path.join(CASES_BASE_DIR, caso_id, "02_Views_(Vistas)", "File_Types")
    if os.path.exists(ruta_recuperados):
        archivos_encontrados = 0
        for root, dirs, files in os.walk(ruta_recuperados):
            if archivos_encontrados >= 1000:
                break
            for f in files:
                if archivos_encontrados >= 1000:
                    break
                ruta_completa = os.path.join(root, f)
                try:
                    stat = os.stat(ruta_completa)
                    size_kb = round(stat.st_size / 1024, 1)
                    if size_kb == 0: continue # Skip empty files
                    
                    ext = os.path.splitext(f)[1].lower()
                    tipo = "binario"
                    categoria = "Evidencia: Otros"
                    icono = "bi-file-earmark-binary"
                    color = "#94a3b8"

                    if ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg']:
                        tipo = "imagen"
                        categoria = "Evidencia: Imágenes"
                        icono = "bi-image"
                        color = "#f472b6"
                    elif ext in ['.mp4', '.mkv', '.avi', '.mov', '.wmv']:
                        tipo = "video"
                        categoria = "Evidencia: Videos"
                        icono = "bi-film"
                        color = "#38bdf8"
                    elif ext in ['.mp3', '.wav', '.ogg', '.flac']:
                        tipo = "audio"
                        categoria = "Evidencia: Audios"
                        icono = "bi-music-note-beamed"
                        color = "#a78bfa"
                    elif ext in ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt']:
                        tipo = "documento"
                        categoria = "Evidencia: Documentos"
                        icono = "bi-file-earmark-text"
                        color = "#fbbf24"
                    elif ext in ['.exe', '.dll', '.bat', '.ps1', '.sh']:
                        tipo = "ejecutable"
                        categoria = "Evidencia: Ejecutables"
                        icono = "bi-file-earmark-code"
                        color = "#ef4444"
                    
                    # Guardamos ruta relativa para el endpoint de descarga
                    rel_path = os.path.relpath(ruta_completa, os.path.join(CASES_BASE_DIR, caso_id))
                    
                    resultado.append({
                        "key":      f"recuperado_{archivos_encontrados}",
                        "filename": f,
                        "filepath": rel_path,
                        "tipo":     tipo,
                        "categoria":categoria,
                        "icono":    icono,
                        "color":    color,
                        "size_kb":  size_kb,
                        "ruta_abs": ruta_completa,
                    })
                    archivos_encontrados += 1
                except Exception:
                    pass

    if request.headers.get('HX-Request'):
        if not resultado:
            return "<div class='p-4 text-center text-gray-500 text-sm'>⚠ No se encontraron archivos. ¿Está conectado el disco externo y se ejecutó el Módulo 7?</div>"
            
        # Agrupar por categoría
        categorias = {}
        for arch in resultado:
            cat = arch['categoria']
            if cat not in categorias:
                categorias[cat] = []
            categorias[cat].append(arch)
            
        html = ""
        for i, (cat, archivos) in enumerate(categorias.items()):
            cat_id = f"real-cat-{i}"
            html += f"""
            <div class="tree-category open" id="{cat_id}">
                <div class="tree-category-label" onclick="toggleCategory('{cat_id}')">
                    <i class="bi bi-folder2-open" style="color:#94a3b8;"></i>
                    {cat}
                    <i class="bi bi-chevron-right caret"></i>
                </div>
                <div class="tree-children">
            """
            for arch in archivos:
                filepath_escaped = (arch.get('filepath') or arch['filename']).replace('\\', '\\\\').replace("'", "\\'")
                filename_escaped = arch['filename'].replace("'", "\\'")
                html += f"""
                    <div class="tree-file" onclick="selectRealFile('{caso_id}', '{filepath_escaped}', '{filename_escaped}', '{arch['tipo']}', {arch['size_kb']})">
                        <i class="bi {arch['icono']} tree-file-icon" style="color:{arch['color']};"></i>
                        {arch['filename']}
                        <span style="margin-left:auto; font-size:0.68rem; color:var(--text-muted);">{arch['size_kb']} KB</span>
                    </div>
                """
            html += """
                </div>
            </div>
            """
        return html

    return jsonify({"status": "ok", "archivos": resultado, "ruta_base": ruta_results})

@app.route('/api/case/<raw_caso_id>/download', methods=['GET'])
def download_case_file(raw_caso_id):
    """Devuelve los bytes crudos de un archivo (imágenes, videos, etc)."""
    caso_id = sanitize_case_id(raw_caso_id)
    if not caso_id:
        return "caso_id inválido.", 400

    filepath = request.args.get('filepath', '').strip()
    preview = request.args.get('preview', 'false').lower() == 'true'
    if not filepath or '..' in filepath:
        return "Path traversal no permitido.", 403

    case_dir = os.path.join(CASES_BASE_DIR, caso_id)
    # Validar que el archivo exista dentro del case_dir
    ruta_absoluta = os.path.abspath(os.path.join(case_dir, filepath))
    if not ruta_absoluta.startswith(os.path.abspath(case_dir)):
        return "Acceso denegado.", 403

    if preview:
        ext = os.path.splitext(ruta_absoluta)[1].lower()
        if ext in ['.docx', '.doc', '.pptx', '.ppt', '.xlsx', '.xls']:
            import subprocess
            import tempfile
            
            # Usar un directorio temporal para almacenar el PDF convertido
            temp_dir = tempfile.gettempdir()
            filename_pdf = os.path.splitext(os.path.basename(ruta_absoluta))[0] + ".pdf"
            pdf_path = os.path.join(temp_dir, filename_pdf)
            
            # Ejecutar libreoffice headless para convertir a PDF
            try:
                subprocess.run([
                    "libreoffice", "--headless", "--convert-to", "pdf",
                    ruta_absoluta, "--outdir", temp_dir
                ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                if os.path.exists(pdf_path):
                    return send_from_directory(temp_dir, filename_pdf)
            except Exception as e:
                return f"Error convirtiendo a PDF: {str(e)}", 500

    return send_from_directory(case_dir, filepath)


@app.route('/api/case/<raw_caso_id>/file_content', methods=['GET'])
def get_file_content(raw_caso_id):
    """Devuelve las primeras N líneas de un archivo de resultados para el visor."""
    caso_id = sanitize_case_id(raw_caso_id)
    if not caso_id:
        return jsonify({"status": "error", "message": "caso_id inválido."}), 400

    filename = request.args.get('filename', '').strip()
    # Sanitizar: prohibir traversal estricto
    if not filename or '..' in filename:
        return jsonify({"status": "error", "message": "Nombre de archivo o ruta inválida."}), 400

    case_dir = os.path.join(CASES_BASE_DIR, caso_id)
    ruta_archivo = os.path.abspath(os.path.join(case_dir, filename))
    # Prevenir path traversal verificando que el archivo esté dentro de case_dir
    if not ruta_archivo.startswith(os.path.abspath(case_dir) + os.sep):
        return jsonify({"status": "error", "message": "Acceso denegado."}), 403

    if not os.path.exists(ruta_archivo):
        return jsonify({"status": "error", "message": f"Archivo '{filename}' no encontrado."}), 404

    try:
        max_chars = 8000  # Límite para no sobrecargar el frontend
        with open(ruta_archivo, 'r', encoding='utf-8', errors='replace') as f:
            contenido = f.read(max_chars)
        truncado = os.path.getsize(ruta_archivo) > max_chars
        sha = hashlib.sha256()
        with open(ruta_archivo, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha.update(chunk)
        return jsonify({
            "status":   "ok",
            "content":  contenido,
            "truncado": truncado,
            "sha256":   sha.hexdigest(),
            "size_bytes": os.path.getsize(ruta_archivo),
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/case/<raw_caso_id>/ai_report', methods=['GET'])
def get_ai_report(raw_caso_id):
    """Devuelve el contenido de la Síntesis IA (Markdown) del caso."""
    caso_id = sanitize_case_id(raw_caso_id)
    if not caso_id:
        return jsonify({"status": "error", "message": "caso_id inválido."}), 400

    ruta_results = get_case_results_path(caso_id)
    if not ruta_results:
        return jsonify({"status": "not_found", "exists": False})

    nombre_informe = f"Sintesis_IA_{caso_id}.md"
    ruta_informe = os.path.join(ruta_results, nombre_informe)

    if not os.path.exists(ruta_informe):
        return jsonify({"status": "not_found", "exists": False,
                        "message": "La Síntesis IA aún no ha sido generada."})

    try:
        with open(ruta_informe, 'r', encoding='utf-8', errors='replace') as f:
            contenido = f.read()
        return jsonify({"status": "ok", "exists": True, "content": contenido,
                        "filename": nombre_informe})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/run/ia', methods=['POST'])
def run_ia():
    """Ejecuta el Módulo 8 (Triaje IA) en segundo plano vía SSE."""
    global running_proc
    data = request.json or {}
    caso_id = sanitize_case_id(data.get('caso_id', '').strip())
    if not caso_id:
        return jsonify({"status": "error", "message": "caso_id es obligatorio."}), 400

    # Determinar destino real del caso
    base_dest = get_case_base_from_registry(caso_id) or DESTINO_FORENSYS

    script_path = os.path.join(SCRIPTS_DIR, '08_analista_ia.py')
    if not os.path.exists(script_path):
        return jsonify({"status": "error", "message": f"Script no encontrado: {script_path}"}), 404

    # Opciones de IA enviadas desde el frontend
    motor = data.get('motor', 'local').strip()
    modelo = data.get('modelo', '').strip()
    telemetry = data.get('telemetry', False)

    def run_in_thread():
        global running_proc
        cmd = ['python3', script_path, '--caso', caso_id, '--dest', base_dest, '--motor', motor]
        if modelo:
            cmd.extend(['--model', modelo])
            
        push_log(f'[SISTEMA] Iniciando Módulo 8: Triaje IA para caso {caso_id}', 'warn')
        push_log(f'$ {" ".join(cmd)}', 'warn')
        try:
            env = os.environ.copy()
            env['PYTHONUNBUFFERED'] = '1'
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, env=env, start_new_session=True
            )
            with running_proc_lock:
                running_proc = proc
            
            if telemetry:
                logger_script = os.path.join(SCRIPTS_DIR, '10_telemetry_logger.py')
                subprocess.Popen([sys.executable, logger_script, '--pid', str(proc.pid), '--module', 'Modulo_8_IA', '--case_dir', base_dest], start_new_session=True)
                
            for line in iter(proc.stdout.readline, ''):
                line = line.rstrip('\n')
                if line:
                    push_log(line, 'info')
            proc.wait()
            rc = proc.returncode
            if rc == 0:
                push_log(f'[OK] Triaje IA completado (código: {rc})', 'success')
            else:
                push_log(f'[ERROR] Triaje IA terminó con código: {rc}', 'error')
        except Exception as e:
            push_log(f'[ERROR] Excepción en Módulo 8: {e}', 'error')
        finally:
            with running_proc_lock:
                running_proc = None

    t = threading.Thread(target=run_in_thread, daemon=True)
    t.start()
    return jsonify({"status": "success", "message": f"Módulo 8 iniciado para caso {caso_id} con motor {motor}"})


@app.route('/api/config/ia', methods=['GET', 'POST'])

@app.route('/api/config/ia/models', methods=['GET'])
def get_ia_models():
    import requests
    local_models = []
    remote_models = []
    
    # Local Models
    try:
        resp = requests.get('http://localhost:11434/api/tags', timeout=2)
        if resp.status_code == 200:
            local_models = [m['name'] for m in resp.json().get('models', [])]
    except Exception:
        pass
        
    # Remote Models
    remote_host = request.args.get('remote_host', '').rstrip('/')
    if not remote_host:
        config_path = os.path.join(DESTINO_FORENSYS, ".ia_config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    conf = json.load(f)
                    remote_host = conf.get('remote_host', '').rstrip('/')
            except Exception:
                pass
                
    if remote_host:
        try:
            resp = requests.get(f'{remote_host}/api/tags', timeout=2)
            if resp.status_code == 200:
                remote_models = [m['name'] for m in resp.json().get('models', [])]
        except Exception:
            pass
            
    return jsonify({
        "status": "success",
        "local": local_models,
        "remote": remote_models
    })


@app.route('/api/config/ia', methods=['GET', 'POST'])
def manage_ia_config():
    """Gestiona la configuración del motor de IA."""
    config_path = os.path.join(DESTINO_FORENSYS, ".ia_config.json")
    
    if request.method == 'GET':
        if not os.path.exists(config_path):
            return jsonify({"remote_host": "", "ctx": 4096, "threads": 12})
        try:
            with open(config_path, 'r') as f:
                return jsonify(json.load(f))
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500
            
    if request.method == 'POST':
        data = request.json or {}
        try:
            # Si el directorio no existe, se intenta crear
            os.makedirs(DESTINO_FORENSYS, exist_ok=True)
            with open(config_path, 'w') as f:
                json.dump(data, f, indent=4)
            return jsonify({"status": "success", "message": "Configuración guardada."})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/case/<raw_caso_id>/images', methods=['GET'])
def list_case_images(raw_caso_id):
    """Escanea la carpeta de un caso en busca de imágenes forenses (.dd, .img, .raw, .e01)."""
    caso_id = sanitize_case_id(raw_caso_id)
    if not caso_id:
        return jsonify({"status": "error", "message": "caso_id inválido."}), 400

    registry = load_registry()
    caso_encontrado = None
    for caso in registry:
        if caso['caso_id'] == caso_id and caso['estado'] == 'abierto':
            caso_encontrado = caso
            break

    if not caso_encontrado:
        return jsonify({"status": "error", "message": f"No se encontró un caso abierto con ID: {caso_id}"}), 404

    carpeta_caso = caso_encontrado['ruta']

    if not os.path.exists(carpeta_caso):
        return jsonify({"status": "error", "message": "El caso no existe en disco."}), 404

    valid_extensions = ('.dd', '.img', '.raw', '.e01', '.iso', '.bin')
    found_images = []

    # Escanear recursivamente
    for root, dirs, files in os.walk(carpeta_caso):
        for file in files:
            if file.lower().endswith(valid_extensions):
                abs_path = os.path.join(root, file)
                rel_path = os.path.relpath(abs_path, carpeta_caso)
                size_mb = round(os.path.getsize(abs_path) / (1024 * 1024), 2)
                found_images.append({
                    "name": file,
                    "rel_path": rel_path,
                    "abs_path": abs_path,
                    "size_mb": size_mb
                })

    return jsonify({"status": "success", "images": found_images})


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


# --- Rutas de Resultados OSINT ---

def _osint_results_dir(caso_id):
    return os.path.join(CASES_BASE_DIR, caso_id, '03_Results_(Resultados_Extraidos)', 'OSINT')

def _osint_images_dir(caso_id):
    return os.path.join(CASES_BASE_DIR, caso_id, '01_Images_(Fuentes_de_datos)', 'OSINT')


@app.route('/api/osint/list/<caso_id>', methods=['GET'])
def osint_list(caso_id):
    """Retorna el índice de todas las búsquedas OSINT del caso (osint_index.json)."""
    caso_id = sanitize_case_id(caso_id)
    if not caso_id:
        return jsonify({"status": "error", "message": "caso_id inválido"}), 400

    ruta_index = os.path.join(_osint_results_dir(caso_id), 'osint_index.json')
    if not os.path.exists(ruta_index):
        return jsonify({"status": "ok", "busquedas": [], "ultima": None})

    try:
        with open(ruta_index, 'r', encoding='utf-8') as f:
            indice = json.load(f)
        return jsonify({
            "status":    "ok",
            "busquedas": indice.get('busquedas', []),
            "ultima":    indice.get('ultima_busqueda'),
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/osint/results/<caso_id>', methods=['GET'])
def osint_results(caso_id):
    """
    Retorna el resumen de una búsqueda específica.
    Query param: ?alias=<alias>   (requerido)
    """
    caso_id = sanitize_case_id(caso_id)
    if not caso_id:
        return jsonify({"status": "error", "message": "caso_id inválido"}), 400

    alias_raw = request.args.get('alias', '').strip()
    if not alias_raw:
        return jsonify({"status": "error", "message": "Parámetro 'alias' requerido."}), 400

    # Sanitizar alias: solo alfanumérico, guion, subguion, punto
    alias = ''.join(c for c in alias_raw if c.isalnum() or c in ('-', '_', '.'))
    if not alias:
        return jsonify({"status": "error", "message": "Alias inválido."}), 400

    nombre_json = f"resumen_osint_{alias}.json"
    ruta_resumen = os.path.join(_osint_results_dir(caso_id), nombre_json)

    if not os.path.exists(ruta_resumen):
        return jsonify({"status": "error", "message": f"No hay resultados OSINT para el alias '{alias}' en el caso '{caso_id}'."}), 404

    try:
        with open(ruta_resumen, 'r', encoding='utf-8') as f:
            datos = json.load(f)
        return jsonify({"status": "success", "data": datos})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/osint/report/<caso_id>', methods=['GET'])
def osint_html_report(caso_id):
    """
    Sirve el reporte HTML de Maigret del alias especificado.
    Query param: ?alias=<alias>   (requerido)
    """
    from flask import send_file
    caso_id = sanitize_case_id(caso_id)
    if not caso_id:
        return "caso_id inválido", 400

    alias_raw = request.args.get('alias', '').strip()
    if not alias_raw:
        return "<h2>Falta el parámetro 'alias'. Selecciona una búsqueda desde el panel.</h2>", 400

    alias = ''.join(c for c in alias_raw if c.isalnum() or c in ('-', '_', '.'))
    if not alias:
        return "Alias inválido", 400

    html_file = os.path.join(_osint_images_dir(caso_id), f"maigret_{alias}.html")

    if not os.path.exists(html_file):
        return f"<h2>Reporte HTML para '@{alias}' no encontrado. Ejecuta el módulo OSINT con ese alias primero.</h2>", 404

    return send_file(html_file, mimetype='text/html')


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
    """Lista dispositivos de bloque disponibles via lsblk para selección desde UI.

    SEGURIDAD: El disco del sistema operativo (y todas sus particiones) se
    excluye automáticamente del listado para prevenir borrados accidentales.
    """
    try:
        result = subprocess.run(
            ['lsblk', '-J', '-o', 'NAME,SIZE,MODEL,TYPE,MOUNTPOINT,RM,PKNAME'],
            capture_output=True, text=True, check=True
        )
        lsblk_data = json.loads(result.stdout)

        devices = []
        def parse_device(dev):
            # ── PROTECCIÓN: omitir el disco del sistema y sus particiones ──
            if dev['name'] in SYSTEM_DISK_NAMES:
                return  # Este dispositivo pertenece al disco del SO — ignorar

            path = f"/dev/{dev['name']}"
            entry = {
                'name': dev['name'],
                'path': path,
                'size': dev.get('size', '?'),
                'model': dev.get('model') or '',
                'type': dev.get('type', ''),
                'mountpoint': dev.get('mountpoint') or '',
                'removable': dev.get('rm', False),
                'system_disk': False,  # Siempre False aquí (los del sistema no llegan)
            }
            devices.append(entry)
            for child in dev.get('children', []):
                parse_device(child)

        for dev in lsblk_data.get('blockdevices', []):
            parse_device(dev)

        return jsonify({
            "status": "success",
            "devices": devices,
            "protected_disk": sorted(SYSTEM_DISK_NAMES),  # Info para debugging
        })
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

    # ── PROTECCIÓN: Bloquear el disco del sistema operativo ──
    disk_name = target_disk.replace('/dev/', '')
    if disk_name in SYSTEM_DISK_NAMES:
        return jsonify({
            "status": "error",
            "message": f"⛔ Acceso denegado: '{target_disk}' pertenece al disco del sistema operativo "
                       f"(Raspberry Pi). No se puede operar sobre él para evitar daños al sistema."
        }), 403
        
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

    # ── PROTECCIÓN: Bloquear el disco del sistema operativo ──
    disk_name = target_disk.replace('/dev/', '')
    if disk_name in SYSTEM_DISK_NAMES:
        return jsonify({
            "status": "error",
            "message": f"⛔ Acceso denegado: '{target_disk}' pertenece al disco del sistema operativo. "
                       f"No se puede aplicar el bloqueador de escritura sobre el disco de la Raspberry Pi."
        }), 403
        
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

        # Temperatura — Raspberry Pi (vcgencmd) y genérico (psutil)
        temp_data = []
        
        # 1. Intentar psutil (más completo, detecta NVMe, placa, etc.)
        try:
            sensors = psutil.sensors_temperatures()
            for chip, entries in sensors.items():
                for i, entry in enumerate(entries):
                    if entry.current and entry.current > 0:
                        # Limpiar etiqueta vacía
                        label = entry.label if entry.label else f"Sensor {i+1}"
                        temp_data.append({
                            'label': f'{chip} — {label}',
                            'celsius': round(entry.current, 1)
                        })
        except Exception:
            pass

        # 2. Si no hay CPU reportado o fallback Raspberry Pi via vcgencmd
        if not any('cpu' in t['label'].lower() for t in temp_data):
            try:
                vc_result = subprocess.run(
                    ['vcgencmd', 'measure_temp'],
                    capture_output=True, text=True, timeout=2
                )
                if vc_result.returncode == 0:
                    import re as _re
                    m = _re.search(r'temp=([\d.]+)', vc_result.stdout)
                    if m:
                        temp_data.append({'label': 'CPU (vcgencmd)', 'celsius': float(m.group(1))})
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
        # Crear cola para este cliente
        q = queue.Queue(maxsize=1000)
        with log_subscribers_lock:
            log_subscribers.append(q)
            
        try:
            # Send a keepalive comment first so browser knows stream started
            yield ': keepalive\n\n'
            while True:
                try:
                    entry = q.get(timeout=20)  # 20-second timeout acts as heartbeat
                    yield f'data: {entry}\n\n'
                except queue.Empty:
                    # Send SSE comment as heartbeat to keep connection alive
                    yield ': heartbeat\n\n'
        finally:
            with log_subscribers_lock:
                if q in log_subscribers:
                    log_subscribers.remove(q)

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
    telemetry = data.get('telemetry', False)
    
    # Determinar destino
    base_dest = get_case_base_from_registry(caso_id) or DESTINO_FORENSYS
    case_dir = os.path.join(base_dest, caso_id) if caso_id != 'MANUAL' else base_dest

    if not cmd:
        return jsonify({'status': 'error', 'message': 'Comando vacío'}), 400

    def run_in_thread(command, case):
        global running_proc
        push_log(f'[OPERADOR] Ejecutando: {command}', 'warn')
        try:
            env = os.environ.copy()
            env['PYTHONUNBUFFERED'] = '1'
            # Inyectar herramientas locales para portabilidad
            project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            tools_bin = os.path.join(project_dir, 'tools_bin')
            local_paths = f"{tools_bin}/usr/bin:{tools_bin}/bin:{tools_bin}/sbin:{tools_bin}/usr/sbin"
            env['PATH'] = f"{local_paths}:{env.get('PATH', '')}"
            proc = subprocess.Popen(
                command, shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
                # Crear nuevo grupo de procesos para poder matar toda la cadena
                start_new_session=True,
            )
            with running_proc_lock:
                running_proc = proc

            if telemetry:
                module_name = "Comando_Manual"
                if "01_" in command: module_name = "Wiping_Disco_Destino"
                elif "02_" in command: module_name = "Modulo_2_Hashes"
                elif "07_" in command: module_name = "Modulo_7_Normalizacion"
                elif "09_" in command: module_name = "Modulo_9_Reporte"
                
                logger_script = os.path.join(SCRIPTS_DIR, '10_telemetry_logger.py')
                subprocess.Popen([sys.executable, logger_script, '--pid', str(proc.pid), '--module', module_name, '--case_dir', case_dir], start_new_session=True)

            # readline() es más eficiente que iterar char a char
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


@app.route('/api/logs/wiping', methods=['GET'])
def get_wiping_logs():
    """Retorna el log estructurado forense de la limpieza de disco."""
    try:
        with open('/var/log/forensys_wiping.log', 'r') as f:
            return f.read(), 200, {'Content-Type': 'text/plain'}
    except FileNotFoundError:
        return "Aún no hay logs de Wiping. El archivo /var/log/forensys_wiping.log no existe.", 404
    except Exception as e:
        return f"Error leyendo logs: {str(e)}", 500


@app.route('/api/logs/coc', methods=['GET'])
def get_coc_logs():
    """Retorna la cadena de custodia (Chain of Custody)."""
    try:
        with open('/var/log/forensys_coc.log', 'r') as f:
            return f.read(), 200, {'Content-Type': 'text/plain'}
    except FileNotFoundError:
        return "Aún no hay Cadena de Custodia. El archivo /var/log/forensys_coc.log no existe.", 404
    except Exception as e:
        return f"Error leyendo logs: {str(e)}", 500

@app.route('/api/deadbox/report/<caso_id>', methods=['GET'])
def get_deadbox_report(caso_id):
    """Retorna el reporte estructurado JSON generado por Deadbox."""
    # Buscar en la carpeta destino por defecto
    ruta = f"/mnt/Destino_ForenSys/{caso_id}_REPORTE.json"
    if not os.path.exists(ruta):
        # Si no está ahí, intentar buscar en el directorio actual (fallback)
        ruta = f"./{caso_id}_REPORTE.json"
        if not os.path.exists(ruta):
            return f"Reporte no encontrado para el caso {caso_id}", 404
    return send_file(ruta, mimetype='application/json')

@app.route('/api/deadbox/signature/<caso_id>', methods=['GET'])
def get_deadbox_signature(caso_id):
    """Retorna la firma criptográfica RSA generada por Deadbox."""
    ruta = f"/mnt/Destino_ForenSys/{caso_id}_COC_firma.bin"
    if not os.path.exists(ruta):
        ruta = f"./{caso_id}_COC_firma.bin"
        if not os.path.exists(ruta):
            return f"Firma no encontrada para el caso {caso_id}", 404
    return send_file(ruta, as_attachment=True, download_name=f"{caso_id}_COC_firma.bin")

@app.route('/api/ram/report/<caso_id>', methods=['GET'])
def get_ram_report(caso_id):
    """Retorna el reporte estructurado JSON generado por Análisis RAM."""
    ruta = f"{app_config['cases_base_dir']}/{caso_id}/03_Results_(Resultados_Extraidos)/RAM/resumen_analisis_ram.json"
    if not os.path.exists(ruta): return f"Reporte no encontrado para el caso {caso_id}", 404
    return send_file(ruta, mimetype='application/json')

@app.route('/api/ram/signature/<caso_id>', methods=['GET'])
def get_ram_signature(caso_id):
    """Retorna la firma criptográfica RSA generada por Análisis RAM."""
    ruta = f"{app_config['cases_base_dir']}/{caso_id}/03_Results_(Resultados_Extraidos)/RAM/resumen_analisis_ram_firma.bin"
    if not os.path.exists(ruta): return f"Firma no encontrada para el caso {caso_id}", 404
    return send_file(ruta, as_attachment=True, download_name=f"{caso_id}_ram_firma.bin")

@app.route('/api/mobile/report/<caso_id>', methods=['GET'])
def get_mobile_report(caso_id):
    """Retorna el reporte estructurado JSON generado por Extracción Móvil."""
    ruta = f"{app_config['cases_base_dir']}/{caso_id}/03_Results_(Resultados_Extraidos)/Mobile/resumen_extraccion_mobile.json"
    if not os.path.exists(ruta): return f"Reporte no encontrado para el caso {caso_id}", 404
    return send_file(ruta, mimetype='application/json')

@app.route('/api/mobile/signature/<caso_id>', methods=['GET'])
def get_mobile_signature(caso_id):
    """Retorna la firma criptográfica RSA generada por Extracción Móvil."""
    ruta = f"{app_config['cases_base_dir']}/{caso_id}/03_Results_(Resultados_Extraidos)/Mobile/resumen_extraccion_mobile_firma.bin"
    if not os.path.exists(ruta): return f"Firma no encontrada para el caso {caso_id}", 404
    return send_file(ruta, as_attachment=True, download_name=f"{caso_id}_mobile_firma.bin")



@app.route('/api/kill_command', methods=['POST'])
def kill_command():
    """Termina el subproceso activo y TODOS sus hijos (sudo → python → dc3dd, etc.)."""
    global running_proc
    with running_proc_lock:
        proc = running_proc

    if proc and proc.poll() is None:
        try:
            pgid = os.getpgid(proc.pid)
            # SIGTERM al grupo completo — propaga a toda la cadena de procesos hijos
            os.killpg(pgid, __import__('signal').SIGTERM)
            # Esperar hasta 3 s; si no termina, SIGKILL
            import signal as _sig
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(pgid, _sig.SIGKILL)
        except (ProcessLookupError, PermissionError) as e:
            # Fallback: matar solo el proceso raíz
            try:
                proc.kill()
            except Exception:
                pass
            push_log(f'[SISTEMA] Fallback kill (pgid no disponible): {e}', 'warn')
        push_log('[SISTEMA] Proceso interrumpido por el operador.', 'warn')
        with running_proc_lock:
            running_proc = None
        return jsonify({'status': 'success', 'message': 'Proceso terminado'})

    return jsonify({'status': 'error', 'message': 'No hay proceso activo'})


@app.route('/api/exit_kiosk', methods=['POST'])
def exit_kiosk():
    """Cancela el auto-arranque y cierra el kiosko actual (cage/chromium)."""
    try:
        # Tocar bandera para cancelar auto-loop
        subprocess.run(['touch', '/tmp/kiosk_exit'], check=True)
        # Matar cage (esto terminará todo el stack gráfico y chromium)
        subprocess.run(['pkill', '-x', 'cage'], check=False)
        return jsonify({'status': 'success', 'message': 'Kiosko detenido. Terminal lista.'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/case/<raw_caso_id>/telemetry_pdf', methods=['GET'])
def get_telemetry_pdf(raw_caso_id):
    from flask import send_file
    caso_id = sanitize_case_id(raw_caso_id)
    if not caso_id:
        return "caso_id inválido.", 400
    base_dest = get_case_base_from_registry(caso_id) or DESTINO_FORENSYS
    pdf_path = os.path.join(base_dest, caso_id, "Reporte_Rendimiento_Hardware.pdf")
    if os.path.exists(pdf_path):
        return send_file(pdf_path, mimetype='application/pdf')
    else:
        return "El reporte de telemetría aún no ha sido generado para este caso.", 404


if __name__ == '__main__':
    # Escucha en todas las interfaces de red de la Raspberry Pi
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)
