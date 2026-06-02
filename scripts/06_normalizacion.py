# =============================================================
# STDLIB — Librería Estándar de Python (PEP 8 §Imports)
# =============================================================
import argparse
import atexit
import csv
import email
import glob
import hashlib
import json
import logging
import math
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime
from email import policy
from zipfile import ZipFile

# =============================================================
# THIRD-PARTY — Dependencias externas (pip)
# =============================================================
try:
    from PIL import Image
    from PIL.ExifTags import TAGS, GPSTAGS
    import fitz  # PyMuPDF
    import pefile
    from regipy.registry import RegistryHive
except ImportError as e:
    print(f"[!] Faltan dependencias. Ejecuta: sudo pip install Pillow PyMuPDF regipy pefile --break-system-packages")
    print(f"[!] Error exacto: {e}")
    sys.exit(1)

# python-evtx es opcional (para Event Logs de Windows)
try:
    import Evtx.Evtx as evtx
    import Evtx.Views as evtx_views
    EVTX_DISPONIBLE = True
except ImportError:
    EVTX_DISPONIBLE = False

# ==========================================
# CONFIGURACIÓN GLOBAL
# ==========================================
DIRECTORIO_DEFAULT = "/mnt/Destino_ForenSys"
UMBRAL_ENTROPIA_SOSPECHOSA = 7.2

# Rutas base permitidas para imágenes forenses (path traversal prevention)
RUTAS_IMAGEN_PERMITIDAS = [
    '/mnt/',
    '/media/',
    '/home/ciber-admin/ForenSys_Project',
    '/opt/',
]

CATEGORIAS_ARCHIVOS = {
    'Images': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp', '.ico'],
    'Videos': ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv'],
    'Audio': ['.mp3', '.wav', '.aac', '.wma', '.flac', '.ogg'],
    'Documents': ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt', '.csv'],
    'Executables': ['.exe', '.dll', '.sys', '.bat', '.ps1', '.sh'],
    'Emails': ['.eml', '.msg', '.pst', '.ost']
}

# Motor Web Inteligente: Patrones de detección por navegador
NAVEGADORES = {
    "Chrome": {
        "archivo_historial": "history",
        "ruta_pista": "google/chrome",
        "sql_historial": (
            "SELECT urls.url, urls.title, "
            "datetime(visits.visit_time/1000000-11644473600,'unixepoch','localtime'), "
            "CAST((visits.visit_time/1000000-11644473600) AS INTEGER) "
            "FROM urls JOIN visits ON urls.id = visits.url "
            "ORDER BY visits.visit_time DESC"
        ),
        "sql_descargas": (
            "SELECT target_path, tab_url, "
            "datetime(start_time/1000000-11644473600,'unixepoch','localtime'), "
            "total_bytes FROM downloads"
        ),
    },
    "Edge": {
        "archivo_historial": "history",
        "ruta_pista": "microsoft/edge",
        "sql_historial": (
            "SELECT urls.url, urls.title, "
            "datetime(visits.visit_time/1000000-11644473600,'unixepoch','localtime'), "
            "CAST((visits.visit_time/1000000-11644473600) AS INTEGER) "
            "FROM urls JOIN visits ON urls.id = visits.url "
            "ORDER BY visits.visit_time DESC"
        ),
        "sql_descargas": (
            "SELECT target_path, tab_url, "
            "datetime(start_time/1000000-11644473600,'unixepoch','localtime'), "
            "total_bytes FROM downloads"
        ),
    },
    "Firefox": {
        "archivo_historial": "places.sqlite",
        "ruta_pista": "mozilla/firefox",
        "sql_historial": (
            "SELECT url, title, "
            "datetime(last_visit_date/1000000,'unixepoch','localtime'), "
            "CAST(last_visit_date/1000000 AS INTEGER) "
            "FROM moz_places WHERE last_visit_date IS NOT NULL"
        ),
        "sql_descargas": (
            "SELECT content, source, "
            "datetime(dateAdded/1000000,'unixepoch','localtime'), 0 "
            "FROM moz_annos WHERE anno_attribute_id=1"
        ),
    }
}

# Módulo de logging forense centralizado
_forensic_logger = None

def setup_forensic_logging(caso_id):
    """Configura logging forense con timestmaps UTC. NIST 800-88 §4.3."""
    global _forensic_logger
    log_dir = '/var/log'
    if not os.access(log_dir, os.W_OK):
        log_dir = tempfile.gettempdir()
    log_file = os.path.join(log_dir, f'forensys_normalizacion_{caso_id}_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.log')
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s UTC [%(levelname)s] [%(funcName)s:%(lineno)d] %(message)s',
        datefmt='%Y-%m-%dT%H:%M:%S',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler(sys.stdout),
        ]
    )
    _forensic_logger = logging.getLogger('ForenSys.Normalizacion')
    _forensic_logger.info("=== INICIO DE NORMALIZACIÓN FORENSE ===")
    _forensic_logger.info(f"Caso ID : {caso_id}")
    _forensic_logger.info(f"PID     : {os.getpid()}")
    _forensic_logger.info(f"Python  : {sys.version.split()[0]}")
    _forensic_logger.info(f"Log     : {log_file}")
    return _forensic_logger

def flog(msg, level='info'):
    """Helper de logging. Si el logger no está inicializado, imprime a stdout."""
    if _forensic_logger:
        getattr(_forensic_logger, level, _forensic_logger.info)(msg)
    else:
        print(msg)

# Archivo temporal seguro: mkstemp + registro atexit para limpieza garantizada
def get_secure_tempfile(suffix='', prefix='forensys_'):
    """Crea un archivo temporal seguro (sin race condition). NIST SP 800-88."""
    fd, path = tempfile.mkstemp(suffix=suffix, prefix=prefix)
    os.close(fd)  # Cerrar descriptor; shutil.copy2 lo abrirá él mismo
    os.chmod(path, 0o600)
    atexit.register(lambda p=path: os.unlink(p) if os.path.exists(p) else None)
    return path

# Gestor de checkpoints para recuperación de análisis largos
class CheckpointManager:
    """Persiste el progreso de análisis para poder retomar sin rehacer pasos completados."""
    def __init__(self, caso_id, ruta_resultados):
        self.ruta = os.path.join(ruta_resultados, f'_checkpoint_{caso_id}.json')
        self.data = self._cargar()

    def _cargar(self):
        if os.path.exists(self.ruta):
            try:
                with open(self.ruta, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {'completados': [], 'timestamps': {}}

    def completado(self, paso):
        return paso in self.data['completados']

    def marcar(self, paso):
        if paso not in self.data['completados']:
            self.data['completados'].append(paso)
        self.data['timestamps'][paso] = datetime.utcnow().isoformat()
        self._guardar()

    def _guardar(self):
        try:
            with open(self.ruta, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=2)
            os.chmod(self.ruta, 0o600)
        except Exception as e:
            flog(f'[!] No se pudo guardar checkpoint: {e}', 'warning')

# Validaciones de entrada
def validar_caso_id(caso_id):
    """Valida formato ID de caso. Previene path traversal."""
    if not re.match(r'^[A-Za-z0-9_-]{1,80}$', caso_id):
        print(f"[X] ID de caso inválido: '{caso_id}'")
        print("    Permitido: alfanuméricos, guiones, guiones_bajos (máx. 80 chars)")
        sys.exit(1)
    return caso_id

def validar_ruta_imagen(ruta_imagen):
    """Valida que la imagen forense sea segura para procesar."""
    if not os.path.exists(ruta_imagen):
        print(f"[X] Ruta no encontrada: {ruta_imagen}")
        sys.exit(1)
    # Rechazar symlinks
    if os.path.islink(ruta_imagen):
        print(f"[X] Symlinks no permitidos por seguridad forense: {ruta_imagen}")
        sys.exit(1)
    # Rechazar directorios
    if not os.path.isfile(ruta_imagen):
        print(f"[X] La ruta debe apuntar a un archivo, no a un directorio: {ruta_imagen}")
        sys.exit(1)
    # Rechazar path traversal y rutas fuera de las permitidas
    ruta_abs = os.path.realpath(ruta_imagen)
    if not any(ruta_abs.startswith(p) for p in RUTAS_IMAGEN_PERMITIDAS):
        print(f"[X] Ruta fuera de directorios forenses permitidos: {ruta_abs}")
        print(f"    Permitidos: {RUTAS_IMAGEN_PERMITIDAS}")
        sys.exit(1)
    # Rechazar argumentos disfrazados de flags
    if ruta_imagen.strip().startswith('-'):
        print(f"[X] Ruta no puede comenzar con '-': {ruta_imagen}")
        sys.exit(1)
    if not os.access(ruta_imagen, os.R_OK):
        print(f"[X] Sin permisos de lectura: {ruta_imagen}")
        sys.exit(1)
    return ruta_abs

def verificar_integridad_normalizacion(ruta_resultados):
    """
    Calcula y registra SHA-256 de los archivos críticos de la normalización.
    NIST 800-88 §4.7: Verificación de integridad post-proceso.
    Retorna dict {archivo: hash} para auditoría.
    """
    archivos_criticos = [
        'Master_Timeline.jsonl',
        'SuperTimeline.sqlite',
        'Reporte_Forense_Maestro.txt',
    ]
    hashes_finales = {}
    flog("\n[*] Verificando integridad de archivos críticos generados...")
    for nombre in archivos_criticos:
        ruta = os.path.join(ruta_resultados, nombre)
        if not os.path.exists(ruta):
            flog(f"    [!] Archivo no generado (puede ser normal): {nombre}", 'warning')
            continue
        try:
            sha256 = hashlib.sha256()
            with open(ruta, 'rb') as f:
                for bloque in iter(lambda: f.read(65536), b''):
                    sha256.update(bloque)
            h = sha256.hexdigest()
            hashes_finales[nombre] = h
            flog(f"    [+] {nombre}: SHA-256 = {h}")
        except Exception as e:
            flog(f"    [X] Error calculando hash de {nombre}: {e}", 'error')
    return hashes_finales

def imprimir_banner():
    print("""
    ========================================================
      ███████╗███████╗███████╗████████╗███████╗███╗   ███╗
      ██╔════╝██╔════╝██╔════╝╚══██╔══╝██╔════╝████╗ ████║
      █████╗  █████╗  █████╗     ██║   █████╗  ██╔████╔██║
      ██╔══╝  ██╔══╝  ██╔══╝     ██║   ██╔══╝  ██║╚██╔╝██║
      ██║     ███████╗███████╗   ██║   ███████╗██║ ╚═╝ ██║
      ╚═╝     ╚══════╝╚══════╝   ╚═╝   ╚══════╝╚═╝     ╚═╝
    FOREN-SYS: SUITE DE ANÁLISIS FORENSE (V11.0 NECROMANTE)
    * Web Intel | MFT Recovery | Persistence | EventLogs *
    ========================================================
    """)

# ==========================================
# MOTOR BASE (TSK Y DISCO)
# ==========================================
def detectar_imagenes_segmentadas(ruta_inicial):
    lista_archivos = []
    if ruta_inicial.endswith('.001'):
        base = ruta_inicial[:-4]
        lista_archivos = sorted(glob.glob(f"{base}.[0-9][0-9][0-9]"))
    elif ruta_inicial.lower().endswith('.e01'):
        base = ruta_inicial[:-4]
        lista_archivos = sorted(glob.glob(f"{base}.[eE][0-9][0-9]"))
    else:
        lista_archivos = [ruta_inicial]
    return lista_archivos

def encontrar_offset_y_so(lista_imagenes):
    print("\n[*] Analizando tabla de particiones y huella del sistema...")
    try:
        comando = ["mmls"] + lista_imagenes
        resultado = subprocess.run(comando, capture_output=True, text=True)
        if resultado.returncode != 0: return ("0", "Desconocido", "Genérico")

        mejor_offset = None
        max_sectores = 0
        sistema_archivos = "Desconocido"

        for linea in resultado.stdout.split('\n'):
            if any(ignoralo in linea for ignoralo in ["Unallocated", "Meta", "Table", "Extended", "Slot", "MAC"]): continue
            linea_limpia = re.sub(r'\d+:\d+', '', linea)
            linea_limpia = re.sub(r'\d+:', '', linea_limpia)
            partes = linea_limpia.split()
            numeros = [p for p in partes if p.isdigit()]
            if len(numeros) >= 3:
                start = numeros[0]
                length = numeros[2]
                if int(length) > max_sectores:
                    max_sectores = int(length)
                    mejor_offset = start
                    desc_idx = linea.find(length) + len(length)
                    sistema_archivos = linea[desc_idx:].strip()

        if mejor_offset:
            os_detectado = "Windows" if any(x in sistema_archivos.lower() for x in ["ntfs", "fat", "exfat"]) else "Linux/Mac"
            print(f"[+] Offset dinámico exacto: {mejor_offset} ({sistema_archivos})")
            return (mejor_offset, sistema_archivos, os_detectado)
        return ("0", "Desconocido", "Genérico")
    except Exception as e:
        return ("0", "Error", "Genérico")

def extraer_todo_el_disco(lista_imagenes, offset, carpeta_destino):
    print(f"[PROGRESO:20] Reconstruyendo el sistema de archivos desde el offset {offset}...")
    os.makedirs(carpeta_destino, exist_ok=True)
    comando = ["tsk_recover", "-a", "-o", str(offset)] + lista_imagenes + [carpeta_destino]
    try:
        subprocess.run(comando, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False

def recuperar_archivos_borrados(lista_imagenes, offset, ruta_unalloc):
    print("[PROGRESO:35] Iniciando Motor de Carving (PhotoRec) sobre espacio no asignado...")
    archivo_bloques = os.path.join(ruta_unalloc, "unallocated_blocks.dd")

    print("    [1/2] Extrayendo espacio no asignado (blkls)...")
    comando_blkls = ["blkls", "-a", "-o", str(offset)] + lista_imagenes
    try:
        with open(archivo_bloques, "wb") as f_out:
            subprocess.run(comando_blkls, stdout=f_out, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"    [X] Error extrayendo bloques: {e}")
        return

    print("    [2/2] Esculpiendo archivos con PhotoRec... (Esto tomará tiempo)")
    comando_photorec = ["photorec", "/d", ruta_unalloc, "/cmd", archivo_bloques, "partition_none,search"]
    try:
        subprocess.run(comando_photorec, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("    [+] Recuperación de borrados finalizada.")
    except Exception as e:
        print(f"    [X] Error en PhotoRec (Asegúrate de instalar 'testdisk'): {e}")

    if os.path.exists(archivo_bloques): os.remove(archivo_bloques)

def recuperar_borrados_mft(lista_imagenes, offset, carpeta_borrados, f_jsonl):
    """
    NECROMANTE DE ARCHIVOS: Usa fls (TSK) para leer la MFT y encontrar
    archivos marcados como borrados. Luego usa icat para recuperar cada
    uno con su nombre original.
    """
    print("\n[*] Iniciando Necromante de Archivos (Recuperación por MFT)...")
    os.makedirs(carpeta_borrados, exist_ok=True)

    # fls -r -d → lista solo archivos BORRADOS (-d) recursivamente (-r)
    cmd_fls = ["fls", "-r", "-d", "-p", "-o", str(offset)] + lista_imagenes
    try:
        resultado = subprocess.run(cmd_fls, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        print("    [X] fls excedió el tiempo límite (10 min).")
        return 0
    except Exception as e:
        print(f"    [X] Error ejecutando fls: {e}")
        return 0

    if resultado.returncode != 0:
        print(f"    [X] Error en fls: {resultado.stderr[:200]}")
        return 0

    contador = 0
    errores = 0

    for linea in resultado.stdout.strip().split('\n'):
        if not linea.strip():
            continue
        # Formato fls: "r/r * inode:  ruta/del/archivo"
        match = re.match(r'[rd]/[rd]\s+\*?\s*(\d+[-\d]*):\s+(.+)', linea)
        if not match:
            continue

        inode = match.group(1)
        ruta_original = match.group(2).strip()
        nombre_archivo = os.path.basename(ruta_original)

        if not nombre_archivo or nombre_archivo == '.':
            continue

        # Crear subestructura preservando la ruta original
        directorio_destino = os.path.join(carpeta_borrados, os.path.dirname(ruta_original))
        os.makedirs(directorio_destino, exist_ok=True)

        archivo_destino = os.path.join(directorio_destino, nombre_archivo)

        # Evitar sobreescribir
        if os.path.exists(archivo_destino):
            base, ext = os.path.splitext(nombre_archivo)
            archivo_destino = os.path.join(directorio_destino, f"{base}_dup{contador}{ext}")

        # icat para extraer el contenido real del archivo
        cmd_icat = ["icat", "-o", str(offset)] + lista_imagenes + [inode.split('-')[0]]
        try:
            with open(archivo_destino, 'wb') as f_out:
                subprocess.run(cmd_icat, stdout=f_out, stderr=subprocess.DEVNULL, timeout=30)

            # Verificar que el archivo no esté vacío (0 bytes = irrecuperable)
            if os.path.getsize(archivo_destino) == 0:
                os.remove(archivo_destino)
                continue

            contador += 1

            # Registrar en JSONL con alerta forense
            evento = {
                "timestamp": "N/A (archivo borrado)",
                "fuente": "MFT_DELETED",
                "tipo": "archivo_borrado_recuperado",
                "descripcion": f"ARCHIVO BORRADO RECUPERADO: {ruta_original}",
                "archivo_origen": archivo_destino,
                "metadatos": {
                    "inode_original": inode,
                    "ruta_original_en_disco": ruta_original,
                    "alerta": "Este archivo fue borrado por el usuario intencionalmente"
                }
            }
            f_jsonl.write(json.dumps(evento, ensure_ascii=False) + '\n')

        except subprocess.TimeoutExpired:
            errores += 1
        except Exception:
            errores += 1

    print(f"    [+] {contador} archivos borrados recuperados con nombre original")
    if errores > 0:
        print(f"    [!] {errores} archivos no pudieron ser recuperados (datos sobreescritos)")
    return contador

def calcular_entropia(ruta_archivo, max_bytes=1048576):
    """Calcula la entropía de Shannon (0-8). >7.2 sugiere cifrado/empaquetado."""
    try:
        with open(ruta_archivo, "rb") as f:
            data = f.read(max_bytes)
        if not data:
            return 0.0
        conteo = Counter(data)
        longitud = len(data)
        entropia = -sum(
            (freq / longitud) * math.log2(freq / longitud)
            for freq in conteo.values()
        )
        return round(entropia, 4)
    except Exception:
        return -1.0

def generar_timeline_tsk(ruta_dd, offset, carpeta_caso):
    print("\n[*] Generando Timeline de Sistema de Archivos (MACB Times) con TSK...")
    bodyfile = os.path.join(carpeta_caso, "bodyfile.txt")
    timeline_csv = os.path.join(carpeta_caso, "filesystem_timeline.csv")

    cmd_fls = ["fls", "-r", "-m", "/", "-o", str(offset), ruta_dd]
    with open(bodyfile, 'w') as bf:
        subprocess.run(cmd_fls, stdout=bf, stderr=subprocess.DEVNULL)

    cmd_mactime = ["mactime", "-b", bodyfile, "-d"]
    with open(timeline_csv, 'w') as tc:
        subprocess.run(cmd_mactime, stdout=tc, stderr=subprocess.DEVNULL)

    if os.path.exists(bodyfile): os.remove(bodyfile)
    print(f"    [+] Timeline MACB exportado a: {timeline_csv}")
    return timeline_csv

def importar_timeline_real(timeline_csv, conn):
    """
    IMPORTA los timestamps REALES del filesystem_timeline.csv (generado por
    mactime/fls) al SQLite. Estos son los timestamps originales del disco,
    NO los de la fecha de extracción.
    """
    print("\n[*] Importando Timeline MACB real (timestamps originales del disco)...")
    cursor = conn.cursor()
    importados = 0

    if not os.path.exists(timeline_csv):
        print("    [!] filesystem_timeline.csv no encontrado.")
        return 0

    try:
        with open(timeline_csv, 'r', encoding='utf-8', errors='ignore') as f:
            reader = csv.reader(f)
            next(reader, None)  # Saltar header de mactime
            lote = []
            for fila in reader:
                try:
                    # Formato mactime CSV: Date,Size,Type,Mode,UID,GID,Meta,File Name
                    if len(fila) < 8:
                        continue
                    fecha_str = fila[0].strip()
                    tipo_macb = fila[2].strip()  # m.., .a., ..c, .b.
                    ruta_archivo = fila[7].strip() if len(fila) > 7 else fila[-1].strip()

                    if not fecha_str or fecha_str == '0':
                        continue

                    # Convertir fecha mactime a unix timestamp
                    try:
                        # mactime formato: "Fri Apr 15 2025 10:30:00"
                        dt = datetime.strptime(fecha_str, '%a %b %d %Y %H:%M:%S')
                        ts_unix = int(dt.timestamp())
                    except ValueError:
                        try:
                            dt = datetime.strptime(fecha_str, '%Y-%m-%d %H:%M:%S')
                            ts_unix = int(dt.timestamp())
                        except ValueError:
                            continue

                    # Mapear tipo MACB
                    if 'm' in tipo_macb.lower():
                        event_type = "Modified"
                        mapping = "M..."
                    elif 'a' in tipo_macb.lower():
                        event_type = "Accessed"
                        mapping = ".A.."
                    elif 'c' in tipo_macb.lower():
                        event_type = "Changed"
                        mapping = "..C."
                    elif 'b' in tipo_macb.lower():
                        event_type = "Born/Created"
                        mapping = "...B"
                    else:
                        event_type = tipo_macb
                        mapping = tipo_macb

                    lote.append((ts_unix, "TSK_REAL", event_type, ruta_archivo, mapping))
                    importados += 1

                    # Insertar en lotes de 5000
                    if len(lote) >= 5000:
                        cursor.executemany('INSERT INTO eventos (timestamp, source, event_type, description, mapping) VALUES (?, ?, ?, ?, ?)', lote)
                        conn.commit()
                        lote = []
                except Exception:
                    continue

            # Insertar el resto
            if lote:
                cursor.executemany('INSERT INTO eventos (timestamp, source, event_type, description, mapping) VALUES (?, ?, ?, ?, ?)', lote)
                conn.commit()

    except Exception as e:
        print(f"    [X] Error importando timeline: {e}")

    print(f"    [+] {importados} eventos MACB reales importados al Super Timeline")
    return importados

# ==========================================
# TIMELINE: SQLITE & HTML GUI
# ==========================================
def iniciar_db_timeline(ruta_db):
    conn = sqlite3.connect(ruta_db)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS eventos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp INTEGER,
            source TEXT,
            event_type TEXT,
            description TEXT,
            mapping TEXT
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON eventos(timestamp)')
    conn.commit()
    return conn

def generar_gui_timeline(conn, ruta_salida):
    print("[*] Renderizando Dashboard HTML de Línea de Tiempo...")
    cursor = conn.cursor()
    cursor.execute("SELECT timestamp, source, event_type, description, mapping FROM eventos ORDER BY timestamp DESC")
    eventos = cursor.fetchall()

    clusters = {}
    for evt in eventos:
        ts, src, evt_type, desc, mapping = evt
        carpeta_base = os.path.dirname(desc) if src == "FS" else "Navegador Web"
        key = (ts, evt_type, carpeta_base)

        if key not in clusters:
            clusters[key] = {'timestamp': ts, 'source': src, 'event_type': evt_type, 'archivos': [], 'mapping': mapping, 'folder': carpeta_base}
        clusters[key]['archivos'].append(desc)

    datos_grafico = {}
    html_rows = ""
    for key, data in clusters.items():
        dt_obj = datetime.fromtimestamp(data['timestamp'])
        fecha_str = dt_obj.strftime('%Y-%m-%d %H:%M:%S')
        dia_str = dt_obj.strftime('%Y-%m-%d')

        datos_grafico[dia_str] = datos_grafico.get(dia_str, 0) + len(data['archivos'])
        color_class = "tag-file"
        if data['source'] == "WEB": color_class = "tag-web"

        cantidad = len(data['archivos'])
        if cantidad > 1:
            resumen = f"<b>[Clúster: {cantidad} eventos simultáneos]</b> en <i>{data['folder']}</i>"
            detalles = "<br>".join([f"- {f}" for f in data['archivos'][:10]])
            if cantidad > 10: detalles += f"<br><i>...y {cantidad - 10} más.</i>"
            desc_html = f"<details><summary>{resumen}</summary><div style='padding-top:10px; font-size: 0.9em; color: #888;'>{detalles}</div></details>"
        else:
            desc_html = data['archivos'][0]

        html_rows += f"<tr><td style='white-space: nowrap; color: #aaa;'>{fecha_str}</td><td><span class='tag {color_class}'>{data['event_type']}</span> <span style='font-size:0.8em; color:#666;'>({data['mapping']})</span></td><td>{desc_html}</td></tr>"

    labels_js = list(datos_grafico.keys())
    data_js = list(datos_grafico.values())

    chartjs_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'web_app', 'static', 'vendor', 'chartjs', 'chart.min.js')
    chartjs_content = ""
    try:
        with open(chartjs_path, 'r', encoding='utf-8') as f:
            chartjs_content = f.read()
    except Exception as e:
        chartjs_content = "console.error('Error cargando Chart.js localmente');"

    html_content = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <title>Foren-Sys: Dashboard Super Timeline</title>
        <script>{chartjs_content}</script>
        <style>
            body {{ background-color: #0d1117; color: #e6edf3; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; margin: 0; padding: 20px; }}
            h1, h2 {{ color: #58a6ff; border-bottom: 1px solid #30363d; padding-bottom: 10px; }}
            .container {{ max-width: 1400px; margin: 0 auto; }}
            .chart-container {{ background: #161b22; padding: 20px; border-radius: 8px; border: 1px solid #30363d; margin-bottom: 30px; }}
            table {{ width: 100%; border-collapse: collapse; background: #161b22; border-radius: 8px; overflow: hidden; border: 1px solid #30363d; }}
            th, td {{ padding: 12px 15px; text-align: left; border-bottom: 1px solid #30363d; }}
            th {{ background-color: #21262d; color: #c9d1d9; font-weight: bold; text-transform: uppercase; position: sticky; top: 0; z-index: 10; }}
            tr:hover {{ background-color: #2a2a2a; }}
            .tag {{ display: inline-block; padding: 4px 8px; border-radius: 2em; font-size: 11px; font-weight: 600; }}
            .tag-web {{ background-color: #1f6feb; color: white; }}
            .tag-file {{ background-color: #da3633; color: white; }}
            details summary {{ cursor: pointer; color: #8b949e; }}
            details summary:hover {{ color: #58a6ff; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Super Timeline Forense (Macro, Mesa, Micro)</h1>
            <div class="chart-container">
                <h2>Actividad General del Sistema (Nivel Macro)</h2>
                <canvas id="timelineChart" height="80"></canvas>
            </div>
            <h2>Registro Detallado de Eventos (Nivel Mesa/Micro)</h2>
            <table>
                <thead><tr><th width="15%">Timestamp (UTC)</th><th width="15%">Tipo de Evento</th><th width="70%">Descripción Técnica / Ruta de Evidencia</th></tr></thead>
                <tbody>{html_rows}</tbody>
            </table>
        </div>
        <script>
            const ctx = document.getElementById('timelineChart').getContext('2d');
            new Chart(ctx, {{
                type: 'bar',
                data: {{ labels: {labels_js}, datasets: [{{ label: 'Volumen de Eventos por Día', data: {data_js}, backgroundColor: '#58a6ff', borderColor: '#1f6feb', borderWidth: 1 }}] }},
                options: {{ scales: {{ y: {{ beginAtZero: true, grid: {{ color: '#30363d' }} }}, x: {{ grid: {{ color: '#30363d' }} }} }}, plugins: {{ legend: {{ labels: {{ color: '#c9d1d9' }} }} }} }}
            }});
        </script>
    </body>
    </html>
    """
    with open(ruta_salida, 'w', encoding='utf-8') as f:
        f.write(html_content)

# ==========================================
# MÓDULOS DE METADATOS Y DEEP INSPECTION
# ==========================================
def calcular_sha256(ruta_archivo):
    sha256 = hashlib.sha256()
    try:
        with open(ruta_archivo, "rb") as f:
            for bloque in iter(lambda: f.read(8192), b""): sha256.update(bloque)
        return sha256.hexdigest()
    except Exception: return "ERROR_LECTURA"

def extraer_mac_times(ruta_archivo):
    try:
        stat = os.stat(ruta_archivo)
        return {'size_bytes': stat.st_size, 'mtime': int(stat.st_mtime), 'atime': int(stat.st_atime), 'ctime': int(stat.st_ctime)}
    except Exception: return None

def extraer_exif(ruta_imagen):
    metadatos = {}
    try:
        img = Image.open(ruta_imagen)
        exif_data = img._getexif()
        if exif_data:
            for tag_id, value in exif_data.items():
                tag = TAGS.get(tag_id, tag_id)
                if tag == 'DateTimeOriginal': metadatos['fecha_captura'] = str(value)
                elif tag == 'Make': metadatos['fabricante'] = str(value)
                elif tag == 'Model': metadatos['modelo'] = str(value)
                elif tag == 'Software': metadatos['software'] = str(value)
                elif tag == 'GPSInfo':
                    gps = {}
                    for gps_tag_id, gps_value in value.items(): gps[GPSTAGS.get(gps_tag_id, gps_tag_id)] = str(gps_value)
                    metadatos['gps'] = gps
    except Exception: pass
    return metadatos

def extraer_metadata_pdf(ruta_pdf):
    metadatos = {}
    try:
        doc = fitz.open(ruta_pdf)
        meta = doc.metadata
        metadatos['autor'] = meta.get('author', '')
        metadatos['creador'] = meta.get('creator', '')
        metadatos['productor'] = meta.get('producer', '')
        metadatos['fecha_creacion'] = meta.get('creationDate', '')
        doc.close()
    except Exception: pass
    return metadatos

def extraer_metadata_office(ruta_doc):
    metadatos = {}
    try:
        with ZipFile(ruta_doc, 'r') as z:
            if 'docProps/core.xml' in z.namelist():
                core = ET.fromstring(z.read('docProps/core.xml'))
                ns = {'dc': 'http://purl.org/dc/elements/1.1/', 'dcterms': 'http://purl.org/dc/terms/', 'cp': 'http://schemas.openxmlformats.org/package/2006/metadata/core-properties'}
                metadatos['autor'] = core.findtext('dc:creator', '', ns)
                metadatos['ultima_modificacion_por'] = core.findtext('cp:lastModifiedBy', '', ns)
                metadatos['fecha_creacion'] = core.findtext('dcterms:created', '', ns)
    except Exception: pass
    return metadatos

def extraer_metadata_pe(ruta_exe):
    metadatos = {}
    try:
        pe = pefile.PE(ruta_exe, fast_load=True)
        metadatos['fecha_compilacion'] = datetime.fromtimestamp(pe.FILE_HEADER.TimeDateStamp).strftime('%Y-%m-%d %H:%M:%S')
        pe.close()
    except Exception: pass
    return metadatos

def parsear_eml(ruta_eml):
    metadatos = {}
    try:
        with open(ruta_eml, 'rb') as f:
            msg = email.message_from_binary_file(f, policy=policy.default)
        metadatos['de'] = msg['from']
        metadatos['para'] = msg['to']
        metadatos['fecha'] = msg['date']
        metadatos['asunto'] = msg['subject']
        metadatos['adjuntos'] = [part.get_filename() for part in msg.iter_attachments() if part.get_filename()]
    except Exception: pass
    return metadatos

# ==========================================
# MÓDULOS FORENSES AVANZADOS (V11.0)
# ==========================================
def extraer_programas_instalados(ruta_fuente, ruta_resultados, f_jsonl, eventos_lote):
    """
    AUDITOR DE SOFTWARE: Busca el hive SOFTWARE (case-insensitive) y extrae
    la lista real de programas instalados en un CSV limpio.
    """
    print("\n[*] Iniciando Auditor de Software (Programas Instalados)...")
    ruta_hive = None

    # Búsqueda case-insensitive del archivo SOFTWARE
    for raiz, _, archivos_dir in os.walk(ruta_fuente):
        ruta_relativa = os.path.relpath(raiz, ruta_fuente).lower().replace("\\", "/")
        for arch in archivos_dir:
            ruta_test = f"{ruta_relativa}/{arch}".lower()
            if ruta_test.endswith("windows/system32/config/software") and arch.lower() == "software":
                ruta_hive = os.path.join(raiz, arch)
                break
        if ruta_hive:
            break

    if not ruta_hive:
        print("    [!] Hive SOFTWARE no encontrado en la imagen.")
        return 0

    print(f"    [+] Hive encontrado: {ruta_hive}")

    # Copiar a temporal para no bloquear
    temp_hive = get_secure_tempfile(suffix="_SOFTWARE")
    shutil.copy2(ruta_hive, temp_hive)

    csv_path = os.path.join(ruta_resultados, "Lista_Programas_Instalados.csv")
    claves_uninstall = [
        r"\Microsoft\Windows\CurrentVersion\Uninstall",
    ]

    programas = []
    try:
        try:
            reg = RegistryHive(temp_hive)
        except Exception:
            reg = RegistryHive(temp_hive, apply_transaction_logs=False)
        for clave_base in claves_uninstall:
            try:
                key = reg.get_key(clave_base)
                for subkey in key.iter_subkeys():
                    nombre = version = fecha = editor = ""
                    for val in subkey.iter_values():
                        if val.name == "DisplayName": nombre = str(val.value)
                        elif val.name == "DisplayVersion": version = str(val.value)
                        elif val.name == "InstallDate": fecha = str(val.value)
                        elif val.name == "Publisher": editor = str(val.value)
                    if nombre:
                        programas.append({
                            "nombre": nombre, "version": version,
                            "fecha_instalacion": fecha, "editor": editor
                        })
            except Exception:
                continue
    except Exception as e:
        print(f"    [X] Error parseando hive SOFTWARE: {e}")
    finally:
        if os.path.exists(temp_hive): os.remove(temp_hive)

    # Exportar CSV
    with open(csv_path, 'w', newline='', encoding='utf-8') as csvf:
        writer = csv.writer(csvf)
        writer.writerow(["Nombre_Programa", "Version", "Fecha_Instalacion", "Editor"])
        for p in programas:
            writer.writerow([p["nombre"], p["version"], p["fecha_instalacion"], p["editor"]])
            # JSONL para la IA
            evento = {
                "timestamp": p["fecha_instalacion"] or "Desconocida",
                "fuente": "REGISTRO_WINDOWS",
                "tipo": "programa_instalado",
                "descripcion": f"Programa instalado: {p['nombre']} v{p['version']}",
                "metadatos": {"editor": p["editor"]}
            }
            f_jsonl.write(json.dumps(evento, ensure_ascii=False) + '\n')

    print(f"    [+] {len(programas)} programas encontrados -> {csv_path}")
    return len(programas)

def motor_web_inteligente(ruta_completa, archivo, raiz, f_web, f_jsonl, eventos_lote, ruta_resultados):
    """
    MOTOR WEB INTELIGENTE: Detecta Chrome, Firefox o Edge automáticamente.
    Extrae historial con timestamps correctos + tabla de descargas.
    """
    ruta_lower = raiz.lower().replace("\\", "/")
    nombre_lower = archivo.lower()

    navegador_detectado = None
    config_nav = None

    # Intento 1: Detección por ruta + nombre de archivo
    for nombre_nav, config in NAVEGADORES.items():
        if config["ruta_pista"] in ruta_lower and nombre_lower == config["archivo_historial"]:
            navegador_detectado = nombre_nav
            config_nav = config
            break

    # Intento 2: Fallback solo por nombre de archivo (TSK puede alterar rutas)
    if not navegador_detectado:
        if nombre_lower == "places.sqlite":
            navegador_detectado = "Firefox"
            config_nav = NAVEGADORES["Firefox"]
        elif nombre_lower == "history":
            # Intentar determinar si es Chrome o Edge por contexto de ruta
            if "edge" in ruta_lower:
                navegador_detectado = "Edge"
                config_nav = NAVEGADORES["Edge"]
            else:
                navegador_detectado = "Chrome"
                config_nav = NAVEGADORES["Chrome"]

    if not navegador_detectado:
        return False

    print(f"    [+] Navegador detectado: {navegador_detectado} en {raiz}")

    temp_db = get_secure_tempfile(suffix=f"_{navegador_detectado}.sqlite")
    try:
        shutil.copy2(ruta_completa, temp_db)
        conn_web = sqlite3.connect(temp_db)
        cursor_web = conn_web.cursor()

        # --- HISTORIAL ---
        try:
            cursor_web.execute(config_nav["sql_historial"])
            for url, titulo, fecha_str, ts_unix in cursor_web.fetchall():
                f_web.write(f"[{navegador_detectado}] [{fecha_str}] URL: {url} | Título: {titulo}\n")
                evento = {
                    "timestamp": fecha_str,
                    "fuente": f"{navegador_detectado.upper()}_HISTORY",
                    "tipo": "visita_url",
                    "descripcion": f"Visitó ({navegador_detectado}): {url}",
                    "archivo_origen": ruta_completa,
                    "metadatos": {"titulo": titulo, "navegador": navegador_detectado}
                }
                f_jsonl.write(json.dumps(evento, ensure_ascii=False) + '\n')
                eventos_lote.append((ts_unix, "WEB", "Browser History", f"[{navegador_detectado}] {url} | {titulo}", "Navegación"))
        except Exception:
            pass

        # --- DESCARGAS ---
        if config_nav.get("sql_descargas"):
            descargas_csv = os.path.join(ruta_resultados, "Descargas_Web.csv")
            archivo_existe = os.path.exists(descargas_csv)
            try:
                cursor_web.execute(config_nav["sql_descargas"])
                filas = cursor_web.fetchall()
                if filas:
                    with open(descargas_csv, 'a', newline='', encoding='utf-8') as csvf:
                        writer = csv.writer(csvf)
                        if not archivo_existe:
                            writer.writerow(["Navegador", "Archivo_Descargado", "URL_Origen", "Fecha", "Tamaño_Bytes"])
                        for target, url_src, fecha_dl, size in filas:
                            writer.writerow([navegador_detectado, target, url_src, fecha_dl, size])
                            evento = {
                                "timestamp": fecha_dl,
                                "fuente": f"{navegador_detectado.upper()}_DOWNLOADS",
                                "tipo": "descarga_web",
                                "descripcion": f"Descargó ({navegador_detectado}): {os.path.basename(str(target))}",
                                "archivo_origen": ruta_completa,
                                "metadatos": {"url": url_src, "archivo": target, "tamaño": size}
                            }
                            f_jsonl.write(json.dumps(evento, ensure_ascii=False) + '\n')
                    print(f"    [+] {len(filas)} descargas extraídas de {navegador_detectado}")
            except Exception:
                pass

        conn_web.close()
    except Exception:
        pass
    finally:
        if os.path.exists(temp_db): os.remove(temp_db)

    return True

def auditar_event_logs(ruta_fuente, ruta_resultados, f_jsonl, eventos_lote):
    """
    AUDITOR DE EVENTOS: Busca archivos .evtx (Event Logs de Windows) y
    extrae los eventos forenses más relevantes (logons, servicios, borrado de logs).
    """
    if not EVTX_DISPONIBLE:
        print("    [!] python-evtx no instalado. Saltando auditoría de Event Logs.")
        print("    [!] Instalar con: sudo pip install python-evtx --break-system-packages")
        return 0

    print("\n[*] Iniciando Auditor de Eventos del Sistema (.evtx)...")

    # IDs de eventos forenses críticos
    EVENTOS_CRITICOS = {
        '4624': 'Inicio de sesión exitoso',
        '4625': 'Intento de inicio de sesión fallido',
        '4648': 'Inicio de sesión con credenciales explícitas',
        '4720': 'Cuenta de usuario creada',
        '4732': 'Miembro añadido a grupo local',
        '7045': 'Nuevo servicio instalado',
        '1102': 'Log de auditoría borrado (ANTI-FORENSE)',
        '4688': 'Nuevo proceso creado',
        '4697': 'Servicio instalado en el sistema',
    }

    archivos_evtx = []
    for raiz, _, archivos_dir in os.walk(ruta_fuente):
        for arch in archivos_dir:
            if arch.lower().endswith('.evtx'):
                archivos_evtx.append(os.path.join(raiz, arch))

    if not archivos_evtx:
        print("    [!] No se encontraron archivos .evtx en la imagen.")
        return 0

    print(f"    [+] {len(archivos_evtx)} archivos .evtx encontrados")

    csv_path = os.path.join(ruta_resultados, "Eventos_Sistema.csv")
    total_eventos = 0

    with open(csv_path, 'w', newline='', encoding='utf-8') as csvf:
        writer = csv.writer(csvf)
        writer.writerow(["Archivo_Log", "EventID", "Descripcion_Forense", "Timestamp", "Datos_XML"])

        for archivo_evtx in archivos_evtx:
            temp_evtx = get_secure_tempfile(suffix=".evtx")
            try:
                shutil.copy2(archivo_evtx, temp_evtx)
                with evtx.Evtx(temp_evtx) as log:
                    for record in log.records():
                        try:
                            xml_str = record.xml()
                            # Buscar EventID en el XML
                            match_id = re.search(r'<EventID[^>]*>(\d+)</EventID>', xml_str)
                            match_time = re.search(r'SystemTime="([^"]+)"', xml_str)
                            if match_id:
                                event_id = match_id.group(1)
                                timestamp = match_time.group(1) if match_time else "Desconocido"

                                if event_id in EVENTOS_CRITICOS:
                                    desc = EVENTOS_CRITICOS[event_id]
                                    nombre_log = os.path.basename(archivo_evtx)
                                    writer.writerow([nombre_log, event_id, desc, timestamp, xml_str[:500]])

                                    alerta = "CRITICO" if event_id in ['1102', '7045', '4720'] else "INFO"
                                    evento = {
                                        "timestamp": timestamp,
                                        "fuente": "EVENT_LOG",
                                        "tipo": f"evento_sistema_{event_id}",
                                        "descripcion": f"[{alerta}] EventID {event_id}: {desc}",
                                        "archivo_origen": archivo_evtx,
                                        "metadatos": {"event_id": event_id, "log": nombre_log, "alerta": alerta}
                                    }
                                    f_jsonl.write(json.dumps(evento, ensure_ascii=False) + '\n')
                                    total_eventos += 1
                        except Exception:
                            continue
            except Exception as e:
                print(f"    [!] Error procesando {os.path.basename(archivo_evtx)}: {e}")
            finally:
                if os.path.exists(temp_evtx): os.remove(temp_evtx)

    print(f"    [+] {total_eventos} eventos forenses críticos extraídos -> {csv_path}")
    return total_eventos

def detectar_persistencia(ruta_fuente, ruta_resultados, f_jsonl):
    """
    DETECTOR DE PERSISTENCIA: Lee claves Run/RunOnce del registro
    para encontrar programas configurados para auto-arranque.
    """
    print("\n[*] Iniciando Detector de Persistencia (Auto-arranque)...")

    csv_path = os.path.join(ruta_resultados, "Mecanismos_Persistencia.csv")
    mecanismos = []

    # RUTAS SOSPECHOSAS: si el ejecutable NO está en estas, es sospechoso
    RUTAS_CONFIABLES = ["c:\\windows\\", "c:\\program files\\", "c:\\program files (x86)\\"]

    # 1. Buscar claves Run/RunOnce en NTUSER.DAT (por usuario)
    claves_ntuser = [
        r"\Software\Microsoft\Windows\CurrentVersion\Run",
        r"\Software\Microsoft\Windows\CurrentVersion\RunOnce",
    ]

    for raiz, _, archivos_dir in os.walk(ruta_fuente):
        for arch in archivos_dir:
            if arch.lower() == "ntuser.dat":
                ruta_ntuser = os.path.join(raiz, arch)
                temp_reg = get_secure_tempfile(suffix="_NTUSER")
                try:
                    shutil.copy2(ruta_ntuser, temp_reg)
                    try:
                        reg = RegistryHive(temp_reg)
                    except Exception:
                        reg = RegistryHive(temp_reg, apply_transaction_logs=False)
                    for clave in claves_ntuser:
                        try:
                            key = reg.get_key(clave)
                            for val in key.iter_values():
                                sospechoso = True
                                cmd_lower = str(val.value).lower()
                                for ruta_ok in RUTAS_CONFIABLES:
                                    if ruta_ok in cmd_lower:
                                        sospechoso = False
                                        break
                                mecanismos.append({
                                    "fuente": f"NTUSER.DAT ({os.path.basename(raiz)})",
                                    "clave": clave,
                                    "nombre": val.name,
                                    "comando": str(val.value),
                                    "sospechoso": sospechoso
                                })
                        except Exception:
                            continue
                except Exception:
                    pass
                finally:
                    if os.path.exists(temp_reg): os.remove(temp_reg)

    # 2. Buscar claves Run/RunOnce en SOFTWARE hive (sistema)
    claves_software = [
        r"\Microsoft\Windows\CurrentVersion\Run",
        r"\Microsoft\Windows\CurrentVersion\RunOnce",
    ]

    for raiz, _, archivos_dir in os.walk(ruta_fuente):
        ruta_relativa = os.path.relpath(raiz, ruta_fuente).lower().replace("\\", "/")
        for arch in archivos_dir:
            ruta_test = f"{ruta_relativa}/{arch}".lower()
            if ruta_test.endswith("windows/system32/config/software") and arch.lower() == "software":
                ruta_hive = os.path.join(raiz, arch)
                temp_sw = get_secure_tempfile(suffix="_SOFTWARE_PERSIST")
                try:
                    shutil.copy2(ruta_hive, temp_sw)
                    try:
                        reg = RegistryHive(temp_sw)
                    except Exception:
                        reg = RegistryHive(temp_sw, apply_transaction_logs=False)
                    for clave in claves_software:
                        try:
                            key = reg.get_key(clave)
                            for val in key.iter_values():
                                sospechoso = True
                                cmd_lower = str(val.value).lower()
                                for ruta_ok in RUTAS_CONFIABLES:
                                    if ruta_ok in cmd_lower:
                                        sospechoso = False
                                        break
                                mecanismos.append({
                                    "fuente": "SOFTWARE Hive (Sistema)",
                                    "clave": clave,
                                    "nombre": val.name,
                                    "comando": str(val.value),
                                    "sospechoso": sospechoso
                                })
                        except Exception:
                            continue
                except Exception:
                    pass
                finally:
                    if os.path.exists(temp_sw): os.remove(temp_sw)
                break

    # Exportar
    sospechosos = sum(1 for m in mecanismos if m['sospechoso'])
    with open(csv_path, 'w', newline='', encoding='utf-8') as csvf:
        writer = csv.writer(csvf)
        writer.writerow(["Fuente", "Clave_Registro", "Nombre", "Comando", "Sospechoso"])
        for m in mecanismos:
            writer.writerow([m["fuente"], m["clave"], m["nombre"], m["comando"], "SÍ" if m["sospechoso"] else "NO"])
            evento = {
                "timestamp": "Persistencia (arranque)",
                "fuente": "PERSISTENCIA",
                "tipo": "autoarranque_detectado",
                "descripcion": f"{'⚠️ SOSPECHOSO: ' if m['sospechoso'] else ''}{m['nombre']} -> {m['comando']}",
                "metadatos": {"clave": m["clave"], "fuente_registro": m["fuente"], "sospechoso": m["sospechoso"]}
            }
            f_jsonl.write(json.dumps(evento, ensure_ascii=False) + '\n')

    print(f"    [+] {len(mecanismos)} mecanismos de persistencia encontrados ({sospechosos} sospechosos) -> {csv_path}")
    return len(mecanismos)

def extraer_info_hardware(ruta_fuente, ruta_resultados, f_jsonl):
    """
    AUDITOR DE HARDWARE: Lee el hive SYSTEM para extraer información del equipo,
    dispositivos USB conectados, nombre del equipo, timezone, etc.
    """
    print("\n[*] Iniciando Auditor de Hardware y Dispositivos USB...")

    csv_path = os.path.join(ruta_resultados, "Hardware_y_USB.csv")
    info_hw = []

    # Buscar SYSTEM hive (case-insensitive)
    ruta_system = None
    for raiz, _, archivos_dir in os.walk(ruta_fuente):
        ruta_rel = os.path.relpath(raiz, ruta_fuente).lower().replace("\\", "/")
        for arch in archivos_dir:
            ruta_test = f"{ruta_rel}/{arch}".lower()
            if ruta_test.endswith("windows/system32/config/system") and arch.lower() == "system":
                ruta_system = os.path.join(raiz, arch)
                break
        if ruta_system:
            break

    if not ruta_system:
        print("    [!] Hive SYSTEM no encontrado.")
        return 0

    print(f"    [+] Hive SYSTEM encontrado: {ruta_system}")
    temp_sys = get_secure_tempfile(suffix="_SYSTEM")

    try:
        shutil.copy2(ruta_system, temp_sys)
        try:
            reg = RegistryHive(temp_sys)
        except Exception:
            reg = RegistryHive(temp_sys, apply_transaction_logs=False)

        # Detectar ControlSet activo (normalmente ControlSet001)
        control_sets = ["ControlSet001", "ControlSet002"]

        for cs in control_sets:
            # 1. Nombre del equipo
            try:
                key = reg.get_key(f"\\{cs}\\Control\\ComputerName\\ComputerName")
                for val in key.iter_values():
                    if val.name == "ComputerName":
                        info_hw.append({"categoria": "Sistema", "propiedad": "Nombre del Equipo", "valor": str(val.value), "alerta": ""})
            except Exception:
                pass

            # 2. TimeZone
            try:
                key = reg.get_key(f"\\{cs}\\Control\\TimeZoneInformation")
                for val in key.iter_values():
                    if val.name == "TimeZoneKeyName":
                        info_hw.append({"categoria": "Sistema", "propiedad": "Zona Horaria", "valor": str(val.value), "alerta": ""})
            except Exception:
                pass

            # 3. Último shutdown
            try:
                key = reg.get_key(f"\\{cs}\\Control\\Windows")
                for val in key.iter_values():
                    if val.name == "ShutdownTime":
                        info_hw.append({"categoria": "Sistema", "propiedad": "Último Apagado (raw)", "valor": str(val.value), "alerta": ""})
            except Exception:
                pass

            # 4. DISPOSITIVOS USB (USBSTOR) - Lo más importante forense
            try:
                usb_key = reg.get_key(f"\\{cs}\\Enum\\USBSTOR")
                for device_class in usb_key.iter_subkeys():
                    # device_class.name = "Disk&Ven_SanDisk&Prod_Cruzer&Rev_1.00"
                    partes = device_class.name.replace("&", " ").split()
                    vendor = ""
                    product = ""
                    for p in partes:
                        if p.startswith("Ven_"): vendor = p[4:]
                        elif p.startswith("Prod_"): product = p[5:]

                    for serial in device_class.iter_subkeys():
                        serial_num = serial.name
                        # Buscar FriendlyName si existe
                        friendly = ""
                        try:
                            for val in serial.iter_values():
                                if val.name == "FriendlyName":
                                    friendly = str(val.value)
                        except Exception:
                            pass

                        descripcion = f"{vendor} {product}".strip()
                        if friendly:
                            descripcion = f"{friendly} ({descripcion})"

                        info_hw.append({
                            "categoria": "USB Conectado",
                            "propiedad": descripcion or device_class.name,
                            "valor": f"Serial: {serial_num}",
                            "alerta": "Dispositivo de almacenamiento USB detectado"
                        })
            except Exception:
                pass

            # 5. Adaptadores de red
            try:
                net_key = reg.get_key(f"\\{cs}\\Services\\Tcpip\\Parameters\\Interfaces")
                for iface in net_key.iter_subkeys():
                    ip = dhcp = ""
                    try:
                        for val in iface.iter_values():
                            if val.name == "IPAddress": ip = str(val.value)
                            elif val.name == "DhcpIPAddress": dhcp = str(val.value)
                    except Exception:
                        pass
                    if ip or dhcp:
                        info_hw.append({
                            "categoria": "Red",
                            "propiedad": f"Interfaz {iface.name[:12]}...",
                            "valor": f"IP: {ip or dhcp}",
                            "alerta": ""
                        })
            except Exception:
                pass

            break  # Solo leer el primer ControlSet exitoso

    except Exception as e:
        print(f"    [X] Error parseando SYSTEM hive: {e}")
    finally:
        if os.path.exists(temp_sys): os.remove(temp_sys)

    # Exportar CSV y JSONL
    usb_count = sum(1 for i in info_hw if i['categoria'] == 'USB Conectado')
    with open(csv_path, 'w', newline='', encoding='utf-8') as csvf:
        writer = csv.writer(csvf)
        writer.writerow(["Categoria", "Propiedad", "Valor", "Alerta_Forense"])
        for item in info_hw:
            writer.writerow([item["categoria"], item["propiedad"], item["valor"], item["alerta"]])
            evento = {
                "timestamp": "Info Hardware",
                "fuente": "HARDWARE",
                "tipo": f"hw_{item['categoria'].lower().replace(' ', '_')}",
                "descripcion": f"{item['categoria']}: {item['propiedad']} = {item['valor']}",
                "metadatos": {"alerta": item["alerta"]} if item["alerta"] else {}
            }
            f_jsonl.write(json.dumps(evento, ensure_ascii=False) + '\n')

    print(f"    [+] {len(info_hw)} propiedades de hardware extraídas ({usb_count} dispositivos USB) -> {csv_path}")
    return len(info_hw)

def detectar_usuarios_equipo(ruta_fuente, ruta_resultados, f_jsonl):
    """
    DETECTOR DE USUARIOS: Identifica todos los perfiles de usuario del equipo
    mediante la estructura de carpetas Users/ y el hive SAM del registro.
    """
    print("\n[*] Iniciando Detector de Usuarios del Equipo...")

    csv_path = os.path.join(ruta_resultados, "Usuarios_Equipo.csv")
    usuarios = []

    # Cuentas del sistema que no son personas reales
    CUENTAS_SISTEMA = ["default", "default user", "public", "all users",
                       "defaultapppool", "systemprofile", "localservice",
                       "networkservice", "."]

    # 1. Detectar perfiles por estructura de directorios (Users/ o Documents and Settings/)
    perfiles_encontrados = {}
    for raiz, dirs, _ in os.walk(ruta_fuente):
        ruta_rel = os.path.relpath(raiz, ruta_fuente).lower().replace("\\", "/")
        # Buscar la carpeta Users/ o Documents and Settings/ en raíz
        if ruta_rel in ["users", "documents and settings"]:
            for carpeta_usuario in dirs:
                nombre_lower = carpeta_usuario.lower()
                if nombre_lower not in CUENTAS_SISTEMA:
                    ruta_perfil = os.path.join(raiz, carpeta_usuario)
                    tiene_ntuser = os.path.exists(os.path.join(ruta_perfil, "NTUSER.DAT")) or \
                                   os.path.exists(os.path.join(ruta_perfil, "ntuser.dat"))
                    # Buscar última actividad por fecha del perfil
                    try:
                        stat_perfil = os.stat(ruta_perfil)
                        ultima_mod = datetime.fromtimestamp(stat_perfil.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                    except Exception:
                        ultima_mod = "Desconocida"

                    perfiles_encontrados[nombre_lower] = {
                        "nombre": carpeta_usuario,
                        "ruta_perfil": ruta_perfil,
                        "tiene_ntuser": tiene_ntuser,
                        "ultima_actividad": ultima_mod,
                        "fuente": "Carpeta de perfil",
                        "tipo_cuenta": "Usuario" if tiene_ntuser else "Limitada/Vacía",
                        "rid": "",
                    }
            break  # Solo necesitamos el primer nivel

    # 2. Intentar parsear el SAM hive para datos más precisos
    ruta_sam = None
    for raiz_sam, _, archivos_sam in os.walk(ruta_fuente):
        ruta_rel_sam = os.path.relpath(raiz_sam, ruta_fuente).lower().replace("\\", "/")
        for arch_sam in archivos_sam:
            ruta_test_sam = f"{ruta_rel_sam}/{arch_sam}".lower()
            if ruta_test_sam.endswith("windows/system32/config/sam") and arch_sam.lower() == "sam":
                ruta_sam = os.path.join(raiz_sam, arch_sam)
                break
        if ruta_sam:
            break

    if ruta_sam:
        print(f"    [+] Hive SAM encontrado: {ruta_sam}")
        temp_sam = get_secure_tempfile(suffix="_SAM")
        try:
            shutil.copy2(ruta_sam, temp_sam)
            try:
                reg = RegistryHive(temp_sam)
            except Exception:
                reg = RegistryHive(temp_sam, apply_transaction_logs=False)
            # Leer cuentas de usuario desde SAM\Domains\Account\Users\Names
            try:
                names_key = reg.get_key(r"\SAM\Domains\Account\Users\Names")
                for subkey in names_key.iter_subkeys():
                    nombre_sam = subkey.name
                    nombre_lower = nombre_sam.lower()
                    if nombre_lower in CUENTAS_SISTEMA:
                        continue

                    # Extraer RID del tipo de valor del default value
                    rid = ""
                    try:
                        rid = str(subkey.header.data.value_type)
                    except Exception:
                        pass

                    if nombre_lower in perfiles_encontrados:
                        perfiles_encontrados[nombre_lower]["fuente"] = "SAM + Carpeta"
                        perfiles_encontrados[nombre_lower]["rid"] = rid
                    else:
                        perfiles_encontrados[nombre_lower] = {
                            "nombre": nombre_sam,
                            "ruta_perfil": "Sin carpeta de perfil",
                            "tiene_ntuser": False,
                            "ultima_actividad": "Desconocida",
                            "fuente": "SAM (sin carpeta)",
                            "tipo_cuenta": "Cuenta SAM",
                            "rid": rid,
                        }
            except Exception:
                pass
        except Exception as e:
            print(f"    [!] Error parseando SAM: {e}")
        finally:
            if os.path.exists(temp_sam): os.remove(temp_sam)
    else:
        print("    [!] Hive SAM no encontrado, usando solo estructura de carpetas.")

    # 3. Exportar CSV y JSONL
    with open(csv_path, 'w', newline='', encoding='utf-8') as csvf:
        writer = csv.writer(csvf)
        writer.writerow(["Nombre_Usuario", "RID", "Tipo_Cuenta", "Ruta_Perfil",
                         "Tiene_NTUSER", "Ultima_Actividad", "Fuente_Deteccion"])
        for datos in perfiles_encontrados.values():
            writer.writerow([
                datos["nombre"], datos["rid"], datos["tipo_cuenta"],
                datos["ruta_perfil"], "SÍ" if datos["tiene_ntuser"] else "NO",
                datos["ultima_actividad"], datos["fuente"]
            ])
            usuarios.append(datos["nombre"])
            evento = {
                "timestamp": datos["ultima_actividad"],
                "fuente": "PERFIL_USUARIO",
                "tipo": "usuario_detectado",
                "descripcion": f"Usuario del equipo: {datos['nombre']} ({datos['tipo_cuenta']})",
                "metadatos": {
                    "rid": datos["rid"],
                    "tiene_ntuser": datos["tiene_ntuser"],
                    "ruta_perfil": datos["ruta_perfil"],
                    "alerta": "Cuenta activa con perfil completo" if datos["tiene_ntuser"] else "Cuenta sin perfil activo"
                }
            }
            f_jsonl.write(json.dumps(evento, ensure_ascii=False) + '\n')

    print(f"    [+] {len(perfiles_encontrados)} usuarios detectados -> {csv_path}")
    if usuarios:
        print(f"    [+] Usuarios: {', '.join(usuarios)}")
    return len(perfiles_encontrados)

# ==========================================
# REGISTRO Y FUSIÓN DE FUENTES
# ==========================================
def parsear_ntuser(ruta_ntuser, maestro_file, nombre_usuario="Desconocido"):
    """Parsea NTUSER.DAT extrayendo RecentDocs, TypedPaths y RunMRU."""
    try:
        try:
            reg = RegistryHive(ruta_ntuser)
        except Exception:
            reg = RegistryHive(ruta_ntuser, apply_transaction_logs=False)
    except Exception as e:
        maestro_file.write(f"\n[REGISTRY] No se pudo abrir NTUSER.DAT de {nombre_usuario}: {e}\n")
        return

    maestro_file.write(f"\n[REGISTRY] === Perfil de usuario: {nombre_usuario} ===\n")

    # 1. RecentDocs (últimos archivos abiertos)
    try:
        recent = reg.get_key(r'\Software\Microsoft\Windows\CurrentVersion\Explorer\RecentDocs')
        if recent:
            valores = [v for v in recent.iter_values() if v.name != 'MRUListEx']
            if valores:
                maestro_file.write(f"  [Documentos Recientes] ({len(valores)} encontrados)\n")
                for val in valores[:20]:
                    maestro_file.write(f"    -> {val.name}\n")
    except Exception:
        pass  # No todos los usuarios tienen RecentDocs

    # 2. TypedPaths (rutas escritas manualmente en el Explorador)
    try:
        typed = reg.get_key(r'\Software\Microsoft\Windows\CurrentVersion\Explorer\TypedPaths')
        if typed:
            maestro_file.write(f"  [Rutas Escritas en Explorador]\n")
            for val in typed.iter_values():
                maestro_file.write(f"    -> {val.name}: {val.value}\n")
    except Exception:
        pass

    # 3. RunMRU (comandos ejecutados con Win+R)
    try:
        runmru = reg.get_key(r'\Software\Microsoft\Windows\CurrentVersion\Explorer\RunMRU')
        if runmru:
            maestro_file.write(f"  [Comandos Ejecutados (Win+R)]\n")
            for val in runmru.iter_values():
                if val.name != 'MRUList':
                    maestro_file.write(f"    -> {val.value}\n")
    except Exception:
        pass

    # 4. UserAssist (programas ejecutados con conteo)
    try:
        ua_key = reg.get_key(r'\Software\Microsoft\Windows\CurrentVersion\Explorer\UserAssist')
        if ua_key:
            cuenta = 0
            for subkey in ua_key.iter_subkeys():
                try:
                    count_key = subkey.get_subkey('Count')
                    if count_key:
                        for val in count_key.iter_values():
                            cuenta += 1
                except Exception:
                    continue
            if cuenta > 0:
                maestro_file.write(f"  [UserAssist] {cuenta} programas con registro de ejecución\n")
    except Exception:
        pass

def integrar_fuentes_externas(carpeta_caso, caso_id, maestro):
    carpeta_base = os.path.dirname(carpeta_caso)
    carpeta_ram = os.path.join(carpeta_base, f"{caso_id}_RAM")
    if os.path.exists(carpeta_ram):
        maestro.write("\n\n=== FUENTE: MEMORIA RAM (Volatility 3) ===\n")
        for archivo in ['ram_procesos.txt', 'ram_malware.txt']:
            ruta = os.path.join(carpeta_ram, archivo)
            if os.path.exists(ruta):
                with open(ruta, 'r') as f: maestro.write(f"\n--- {archivo} ---\n{f.read()}\n")

    carpeta_mobile = os.path.join(carpeta_base, f"{caso_id}_MOBILE")
    if os.path.exists(carpeta_mobile):
        maestro.write("\n\n=== FUENTE: DISPOSITIVO MÓVIL (ADB) ===\n")
        carpeta_dcim = os.path.join(carpeta_mobile, "Fotos_DCIM")
        if os.path.exists(carpeta_dcim):
            for root, _, files in os.walk(carpeta_dcim):
                for f in files:
                    stat = os.stat(os.path.join(root, f))
                    fecha = datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                    maestro.write(f"[MOBILE_FOTO] {fecha} | {f}\n")

    carpeta_osint = os.path.join(carpeta_base, f"{caso_id}_OSINT")
    if os.path.exists(carpeta_osint):
        reporte = os.path.join(carpeta_osint, "reporte_osint.txt")
        if os.path.exists(reporte):
            maestro.write("\n\n=== FUENTE: OSINT / NUBE ===\n")
            with open(reporte, 'r') as f: maestro.write(f.read())

def generar_resumen(estadisticas, maestro):
    maestro.write("\n\n" + "="*60 + "\n")
    maestro.write("  RESUMEN EJECUTIVO PARA TRIAGE IA (V11.0)\n")
    maestro.write("="*60 + "\n\n")
    maestro.write(f"Total de archivos procesados: {estadisticas['total']}\n")
    maestro.write(f"  - Multimedia: {estadisticas['multimedia']}\n")
    maestro.write(f"  - Documentos: {estadisticas['documentos']}\n")
    maestro.write(f"  - Ejecutables: {estadisticas['ejecutables']}\n")
    maestro.write(f"  - Emails: {estadisticas['emails']}\n\n")
    maestro.write(f"Archivos con GPS embebido: {estadisticas['con_gps']}\n")
    maestro.write(f"\n--- ALERTAS DE SEGURIDAD ---\n")
    maestro.write(f"Archivos con alta entropía (>7.2): {estadisticas.get('alta_entropia', 0)}\n")
    if estadisticas.get('navegadores_detectados'):
        maestro.write(f"Navegadores detectados: {', '.join(estadisticas['navegadores_detectados'])}\n")
    maestro.write(f"Programas instalados encontrados: {estadisticas.get('programas', 0)}\n")
    maestro.write(f"Eventos de sistema críticos: {estadisticas.get('eventos_sistema', 0)}\n")
    maestro.write(f"Mecanismos de persistencia: {estadisticas.get('persistencia', 0)}\n")
    maestro.write(f"Usuarios del equipo detectados: {estadisticas.get('usuarios', 0)}\n")
    maestro.write(f"Propiedades de hardware/USB: {estadisticas.get('hardware', 0)}\n")
    maestro.write(f"Multimedia con metadatos EXIF: {estadisticas.get('multimedia_con_meta', 0)}\n")
    maestro.write(f"Eventos MACB reales importados: {estadisticas.get('timeline_real', 0)}\n")

# ==========================================
# ORQUESTADOR PRINCIPAL (ETL)
# ==========================================
def organizar_estilo_autopsy(ruta_fuente, ruta_vistas, ruta_resultados, carpeta_caso, caso_id):
    print(f"\n[*] Iniciando Deep Inspection V11.0: Hashing, Entropía, Web Intel, JSONL y SQLite...")

    web_history_file = os.path.join(ruta_resultados, "Web_History_and_Bookmarks.txt")
    jsonl_path = os.path.join(ruta_resultados, "Master_Timeline.jsonl")
    reporte_maestro = os.path.join(ruta_resultados, "Reporte_Forense_Maestro.txt")
    db_timeline_path = os.path.join(ruta_resultados, "SuperTimeline.sqlite")
    html_timeline_path = os.path.join(ruta_vistas, "Dashboard_SuperTimeline.html")

    conn = iniciar_db_timeline(db_timeline_path)
    cursor = conn.cursor()
    eventos_lote = []

    estadisticas = {
        'total': 0, 'multimedia': 0, 'documentos': 0, 'ejecutables': 0,
        'emails': 0, 'con_gps': 0, 'alta_entropia': 0,
        'navegadores_detectados': [], 'programas': 0,
        'eventos_sistema': 0, 'persistencia': 0
    }
    multimedia_meta = []  # Colector de metadatos multimedia

    with open(web_history_file, 'w', encoding='utf-8') as f_web, \
         open(jsonl_path, 'w', encoding='utf-8') as f_jsonl, \
         open(reporte_maestro, 'w', encoding='utf-8') as f_maestro:

        f_web.write("=== WEB HISTORY & BOOKMARKS (Multi-Navegador) ===\n\n")
        f_maestro.write(f"=== REPORTE MAESTRO FOREN-SYS V11.0 (CASO: {caso_id}) ===\n")
        f_maestro.write(f"=== Generado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n\n")

        for raiz, _, archivos in os.walk(ruta_fuente):
            for archivo in archivos:
                ruta_completa = os.path.join(raiz, archivo)
                extension = os.path.splitext(archivo)[1].lower()

                # --- 1. CLASIFICACIÓN Y DEEP INSPECTION ---
                categoria_encontrada = None
                for categoria, extensiones in CATEGORIAS_ARCHIVOS.items():
                    if extension in extensiones:
                        categoria_encontrada = categoria
                        break

                if categoria_encontrada:
                    estadisticas['total'] += 1
                    if categoria_encontrada in ['Images', 'Videos']: estadisticas['multimedia'] += 1
                    elif categoria_encontrada == 'Documents': estadisticas['documentos'] += 1
                    elif categoria_encontrada == 'Executables': estadisticas['ejecutables'] += 1
                    elif categoria_encontrada == 'Emails': estadisticas['emails'] += 1

                    ruta_subcarpeta = os.path.join(ruta_vistas, "File_Types", categoria_encontrada)
                    os.makedirs(ruta_subcarpeta, exist_ok=True)
                    try:
                        shutil.copy2(ruta_completa, ruta_subcarpeta)
                        metadatos_mac = extraer_mac_times(ruta_completa)

                        meta_profundo = {}
                        if categoria_encontrada == 'Images':
                            meta_profundo = extraer_exif(ruta_completa)
                            if 'gps' in meta_profundo: estadisticas['con_gps'] += 1
                        elif extension == '.pdf': meta_profundo = extraer_metadata_pdf(ruta_completa)
                        elif extension in ['.docx', '.xlsx', '.pptx']: meta_profundo = extraer_metadata_office(ruta_completa)
                        elif categoria_encontrada == 'Executables': meta_profundo = extraer_metadata_pe(ruta_completa)
                        elif categoria_encontrada == 'Emails': meta_profundo = parsear_eml(ruta_completa)

                        hash_val = calcular_sha256(ruta_completa) if metadatos_mac and metadatos_mac['size_bytes'] < 50000000 else "OMITIDO (>50MB)"

                        # Entropía de Shannon
                        entropia = calcular_entropia(ruta_completa)
                        sospechoso_entropia = entropia > UMBRAL_ENTROPIA_SOSPECHOSA
                        if sospechoso_entropia:
                            estadisticas['alta_entropia'] += 1

                        # Recolectar metadatos multimedia para CSV dedicado
                        if categoria_encontrada in ['Images', 'Videos', 'Audio'] and meta_profundo:
                            fila_multi = {
                                'archivo': archivo,
                                'ruta': ruta_completa,
                                'extension': extension,
                                'categoria': categoria_encontrada,
                                'tamaño': metadatos_mac['size_bytes'] if metadatos_mac else 0,
                                'hash_sha256': hash_val,
                            }
                            fila_multi.update(meta_profundo)
                            # Aplanar GPS si existe
                            if 'gps' in fila_multi:
                                gps_data = fila_multi.pop('gps')
                                for gk, gv in gps_data.items():
                                    fila_multi[f'gps_{gk}'] = gv
                            multimedia_meta.append(fila_multi)

                        # JSONL (sin timestamps falsos de os.stat)
                        evento = {
                            "fuente": "FILESYSTEM",
                            "tipo": f"archivo_{categoria_encontrada.lower()}",
                            "descripcion": archivo,
                            "archivo_origen": ruta_completa,
                            "hash_sha256": hash_val,
                            "entropia": entropia,
                            "sospechoso_entropia": sospechoso_entropia,
                            "metadatos": meta_profundo
                        }
                        f_jsonl.write(json.dumps(evento, ensure_ascii=False) + '\n')

                        # NO insertamos os.stat() timestamps en SQLite.
                        # Los timestamps REALES vienen de importar_timeline_real()
                    except Exception: pass

                # --- 2. MOTOR WEB INTELIGENTE (Chrome/Edge/Firefox) ---
                elif archivo.lower() in ['history', 'places.sqlite']:
                    web_ok = motor_web_inteligente(ruta_completa, archivo, raiz, f_web, f_jsonl, eventos_lote, ruta_resultados)
                    if web_ok:
                        # Detectar qué navegador fue (con fallback por nombre de archivo)
                        ruta_lower = raiz.lower().replace("\\", "/")
                        nav_detectado = None
                        for nombre_nav, config in NAVEGADORES.items():
                            if config["ruta_pista"] in ruta_lower:
                                nav_detectado = nombre_nav
                                break
                        # Fallback por nombre de archivo
                        if not nav_detectado:
                            if archivo.lower() == 'places.sqlite':
                                nav_detectado = 'Firefox'
                            elif 'edge' in ruta_lower:
                                nav_detectado = 'Edge'
                            elif archivo.lower() == 'history':
                                nav_detectado = 'Chrome'
                        if nav_detectado and nav_detectado not in estadisticas['navegadores_detectados']:
                            estadisticas['navegadores_detectados'].append(nav_detectado)

                # --- 3. REGISTRY (NTUSER.DAT) ---
                elif archivo.lower() == 'ntuser.dat':
                    temp_reg = get_secure_tempfile(suffix="_NTUSER")
                    # Extraer nombre de usuario de la ruta del perfil
                    partes_ruta = raiz.replace("\\", "/").split("/")
                    nombre_usr = partes_ruta[-1] if partes_ruta else "Desconocido"
                    try:
                        shutil.copy2(ruta_completa, temp_reg)
                        parsear_ntuser(temp_reg, f_maestro, nombre_usr)
                    except Exception: pass
                    finally:
                        if os.path.exists(temp_reg): os.remove(temp_reg)

        # --- 4. AUDITOR DE SOFTWARE (Programas Instalados) ---
        estadisticas['programas'] = extraer_programas_instalados(ruta_fuente, ruta_resultados, f_jsonl, eventos_lote)

        # --- 5. AUDITOR DE EVENTOS DEL SISTEMA (.evtx) ---
        estadisticas['eventos_sistema'] = auditar_event_logs(ruta_fuente, ruta_resultados, f_jsonl, eventos_lote)

        # --- 6. DETECTOR DE PERSISTENCIA (Auto-arranque) ---
        estadisticas['persistencia'] = detectar_persistencia(ruta_fuente, ruta_resultados, f_jsonl)

        # --- 7. DETECTOR DE USUARIOS DEL EQUIPO ---
        estadisticas['usuarios'] = detectar_usuarios_equipo(ruta_fuente, ruta_resultados, f_jsonl)

        # --- 8. AUDITOR DE HARDWARE Y USB ---
        estadisticas['hardware'] = extraer_info_hardware(ruta_fuente, ruta_resultados, f_jsonl)

        # --- 9. EXPORTAR METADATOS MULTIMEDIA ---
        if multimedia_meta:
            multimedia_csv_path = os.path.join(ruta_resultados, "Metadatos_Multimedia.csv")
            # Recolectar todas las columnas únicas
            todas_columnas = set()
            for fila in multimedia_meta:
                todas_columnas.update(fila.keys())
            # Ordenar: primero las básicas, luego las de metadatos
            columnas_basicas = ['archivo', 'ruta', 'extension', 'categoria', 'tamaño', 'hash_sha256']
            columnas_meta = sorted([c for c in todas_columnas if c not in columnas_basicas])
            columnas_final = columnas_basicas + columnas_meta

            with open(multimedia_csv_path, 'w', newline='', encoding='utf-8') as csvf:
                writer = csv.DictWriter(csvf, fieldnames=columnas_final, extrasaction='ignore')
                writer.writeheader()
                for fila in multimedia_meta:
                    writer.writerow(fila)
            print(f"    [+] {len(multimedia_meta)} archivos multimedia con metadatos -> {multimedia_csv_path}")
            estadisticas['multimedia_con_meta'] = len(multimedia_meta)

        # Inserción masiva a SQLite
        if eventos_lote:
            cursor.executemany('INSERT INTO eventos (timestamp, source, event_type, description, mapping) VALUES (?, ?, ?, ?, ?)', eventos_lote)
            conn.commit()

        # --- 9. IMPORTAR TIMELINE REAL (MACB del disco, no de extracción) ---
        timeline_csv_path = os.path.join(ruta_resultados, "filesystem_timeline.csv")
        estadisticas['timeline_real'] = importar_timeline_real(timeline_csv_path, conn)

        # Generar Dashboard GUI
        generar_gui_timeline(conn, html_timeline_path)
        conn.close()

        integrar_fuentes_externas(carpeta_caso, caso_id, f_maestro)
        generar_resumen(estadisticas, f_maestro)

    # --- VERIFICACIÓN DE INTEGRIDAD FINAL (NIST 800-88) ---
    hashes_finales = verificar_integridad_normalizacion(ruta_resultados)
    if hashes_finales:
        hashes_path = os.path.join(ruta_resultados, 'hashes_integridad.json')
        with open(hashes_path, 'w', encoding='utf-8') as hf:
            json.dump({
                'caso_id': caso_id,
                'generado_utc': datetime.utcnow().isoformat(),
                'hashes': hashes_finales
            }, hf, indent=2)
        os.chmod(hashes_path, 0o600)
        flog(f"[+] Hashes de integridad guardados en: {hashes_path}")

    flog(f"\n[+] Base de Datos Timeline: Guardada en {db_timeline_path}")
    flog(f"[+] Dashboard Interactivo: Generado en {html_timeline_path}")
    flog(f"[+] Timeline JSONL para IA: Guardado en {jsonl_path}")
    flog(f"[+] Reporte Maestro: Guardado en {reporte_maestro}")
    if estadisticas['alta_entropia'] > 0:
        flog(f"    [!] ALERTA: {estadisticas['alta_entropia']} archivos con alta entropía detectados", 'warning')
    if estadisticas['navegadores_detectados']:
        flog(f"    [+] Navegadores encontrados: {', '.join(estadisticas['navegadores_detectados'])}")
    if estadisticas['programas'] > 0:
        flog(f"    [+] Programas instalados extraídos: {estadisticas['programas']}")
    if estadisticas['persistencia'] > 0:
        flog(f"    [!] Mecanismos de persistencia: {estadisticas['persistencia']}", 'warning')

# ==========================================
# INICIO
# ==========================================
if __name__ == "__main__":
    imprimir_banner()

    # --- VERIFICACIÓN DE PRIVILEGIOS (TSK requiere root) ---
    if os.geteuid() != 0:
        print("[X] Este módulo requiere permisos de root para acceder a imágenes forenses.")
        print("[*] Ejecute: sudo python3 06_normalizacion.py --caso CASO_001 --ruta /mnt/imagen.dd")
        sys.exit(1)

    # --- VERIFICAR HERRAMIENTAS REQUERIDAS ---
    herramientas_requeridas = ['tsk_recover', 'fls', 'icat', 'blkls', 'mactime', 'mmls']
    herramientas_faltantes = [h for h in herramientas_requeridas if not shutil.which(h)]
    if herramientas_faltantes:
        print(f"[X] Herramientas requeridas no encontradas: {', '.join(herramientas_faltantes)}")
        print("[*] Instalar con: sudo apt install sleuthkit")
        sys.exit(1)

    # NUEVO SISTEMA DE ARGUMENTOS (Para control desde Interfaz Web)
    parser = argparse.ArgumentParser(description="Normalización Forense y Super Timeline")
    parser.add_argument("--caso", required=True, help="ID del Caso Forense (Ej. CASO_001)")
    parser.add_argument("--ruta", required=True, help="Ruta absoluta de la imagen o evidencia")
    parser.add_argument("--dest", required=False, help="Directorio destino (Opcional, usa default si no se provee)")
    parser.add_argument("--recuperar", required=False, default="n", choices=["1", "2", "3", "n"],
                        help="Método de rec. borrados: 1=MFT, 2=PhotoRec, 3=Ambos, n=Ninguno")

    args = parser.parse_args()

    # --- VALIDACIÓN ESTRICTA DE ENTRADAS ---
    caso_id          = validar_caso_id(args.caso.strip())
    ruta_dd          = validar_ruta_imagen(args.ruta.strip())
    directorio_base_actual = args.dest.strip() if args.dest else DIRECTORIO_DEFAULT
    opcion_borrados  = args.recuperar.lower()

    # Inicializar logging forense ANTES de cualquier operación
    setup_forensic_logging(caso_id)

    flog(f"[PROGRESO:5] Iniciando normalización para el caso: {caso_id}")
    flog(f"[*] Leyendo evidencia desde: {ruta_dd}")
    flog(f"[*] Método de recuperación: {opcion_borrados.upper()}")

    os.makedirs(directorio_base_actual, exist_ok=True)
    os.chmod(directorio_base_actual, 0o700)
    lista_imagenes_completas = detectar_imagenes_segmentadas(ruta_dd)

    # Rechazar flags disfrazados de rutas en la lista de imágenes
    for img in lista_imagenes_completas:
        if img.strip().startswith('-'):
            flog(f"[X] Ruta de imagen no puede comenzar con '-': {img}", 'error')
            sys.exit(1)

    carpeta_caso     = os.path.join(directorio_base_actual, caso_id)
    ruta_images      = os.path.join(carpeta_caso, "01_Images_(Fuentes_de_datos)")
    ruta_vol_ntfs    = os.path.join(carpeta_caso, "01_Images_(Fuentes_de_datos)", "vol2_NTFS")
    ruta_vol_unalloc = os.path.join(carpeta_caso, "01_Images_(Fuentes_de_datos)", "vol1_Unallocated")
    ruta_vistas      = os.path.join(carpeta_caso, "02_Views_(Vistas)")
    ruta_resultados  = os.path.join(carpeta_caso, "03_Results_(Resultados_Extraidos)")
    ruta_borrados_mft= os.path.join(carpeta_caso, "04_Archivos_Borrados_Recuperados")

    for d in [ruta_vol_ntfs, ruta_vol_unalloc, ruta_vistas, ruta_resultados]:
        os.makedirs(d, exist_ok=True)
        os.chmod(d, 0o700)

    # Inicializar gestor de checkpoints
    checkpoint = CheckpointManager(caso_id, ruta_resultados)

    flog("[PROGRESO:10] Calculando offset y particiones...")
    offset, tipo_fs, os_detectado = encontrar_offset_y_so(lista_imagenes_completas)

    if offset is None:
        flog("[-] ERROR: No se pudo detectar un offset NTFS válido automáticamente.", 'error')
        flog("[-] Asegúrese de que la imagen contenga una partición NTFS de Windows.", 'error')
        sys.exit(1)

    flog("\n========================================================")
    flog("  [PROGRESO:15] INICIANDO ORQUESTADOR FORENSE V11.0 NECROMANTE")
    flog("========================================================")

    if extraer_todo_el_disco(lista_imagenes_completas, offset, ruta_vol_ntfs):
        checkpoint.marcar('extract_disk')

        # --- NECROMANTE DE ARCHIVOS (MFT) ---
        if opcion_borrados in ['1', '3'] and not checkpoint.completado('mft_recovery'):
            flog("[PROGRESO:25] Iniciando recuperación rápida MFT...")
            jsonl_mft_path = os.path.join(ruta_resultados, "Master_Timeline.jsonl")
            with open(jsonl_mft_path, 'a', encoding='utf-8') as f_jsonl_mft:
                total_borrados = recuperar_borrados_mft(lista_imagenes_completas, offset, ruta_borrados_mft, f_jsonl_mft)
            checkpoint.marcar('mft_recovery')

        # --- CARVING CON PHOTOREC ---
        if opcion_borrados in ['2', '3'] and not checkpoint.completado('photorec'):
            recuperar_archivos_borrados(lista_imagenes_completas, offset, ruta_vol_unalloc)
            checkpoint.marcar('photorec')

        if opcion_borrados == 'n':
            flog("[PROGRESO:35] Saltando recuperación de archivos borrados por solicitud del usuario.")

        # --- EXTRACCIÓN MAC TSK ---
        if not checkpoint.completado('timeline_tsk'):
            flog("[PROGRESO:50] Generando línea de tiempo MAC (fls / mactime)...")
            generar_timeline_tsk(ruta_dd, offset, ruta_resultados)
            checkpoint.marcar('timeline_tsk')

        # --- ESTRUCTURA AUTOPSY, SQLITE, JSONL & HTML ---
        flog("[PROGRESO:75] Organizando datos y generando bases de datos SQLite / JSONL...")
        organizar_estilo_autopsy(ruta_vol_ntfs, ruta_vistas, ruta_resultados, carpeta_caso, caso_id)
        checkpoint.marcar('deep_inspection')

        flog("\n========================================================")
        flog("[+] [ÉXITO] ESTRUCTURA PERICIAL V11.0 COMPLETADA")
        flog(f"    [1] Evidencia Cruda:            {ruta_images}")
        flog(f"    [2] Dashboard Web (GUI):        {ruta_vistas}/Dashboard_SuperTimeline.html")
        flog(f"    [3] Base SQLite & Eventos IA:   {ruta_resultados}")
        flog(f"    [4] Archivos Borrados (MFT):    {ruta_borrados_mft}")
        flog(f"    [5] Programas Instalados:       {ruta_resultados}/Lista_Programas_Instalados.csv")
        flog(f"    [6] Mecanismos Persistencia:    {ruta_resultados}/Mecanismos_Persistencia.csv")
        flog("========================================================")
        flog("[PROGRESO:100] Normalización y Triaje finalizados.")
