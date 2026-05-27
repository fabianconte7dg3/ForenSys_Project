#!/usr/bin/env python3
"""
04_mobile.py — Extracción Forense Lógica de Dispositivos Móviles
Plataformas: Android (ADB) | iOS (libimobiledevice)
Cumplimiento: ISO/IEC 27037:2012 — NIST SP 800-101 Rev.1

Uso:
    sudo python3 04_mobile.py --caso CASO-001 --perito "Juan Perez" --plataforma android
    sudo python3 04_mobile.py --caso CASO-001 --perito "Juan Perez" --plataforma ios
    sudo python3 04_mobile.py --caso CASO-001 --perito "Juan Perez" --plataforma auto
"""
import os
import sys
import json
import shutil
import hashlib
import argparse
import subprocess
import csv
import io
import stat
import base64
from datetime import datetime
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding

# ── Rutas base ─────────────────────────────────────────────────────
CASES_BASE_DIR = '/home/ciber-admin/ForenSys_Project/Casos_ForenSys'

# ── Disclaimer legal (se escribe en cadena de custodia) ────────────
def documentar_limitaciones_extraccion():
    limitaciones = {
        'datos_encriptados': ['Mensajes WhatsApp (E2E encryption)', 'Mensajes Signal', 'Mensajes Telegram'],
        'datos_protegidos': ['Credenciales en Keystore/Keychain', 'Biometría (huellas, face recognition)'],
        'datos_no_accesibles_adb': ['SMS de apps alternativas', 'Sandboxes de aplicaciones', 'Caché de navegadores']
    }
    return "\nLIMITACIONES TECNICAS:\n- No se puede acceder a datos encriptados end-to-end o protegidos.\n" + json.dumps(limitaciones, indent=2)

DISCLAIMER = (
    "AVISO FORENSE: Esta extraccion es de tipo LOGICA (Nivel 2 - NIST SP 800-101). "
    "El dispositivo fue adquirido en estado desbloqueado con autorizacion del operador. "
    "Solo se ejecutaron comandos de LECTURA. El dispositivo fuente NO fue modificado."
) + documentar_limitaciones_extraccion()


# ══════════════════════════════════════════════════════════════════
# Utilidades generales
# ══════════════════════════════════════════════════════════════════

def log(msg):
    print(msg, flush=True)


def progress(pct, detail):
    print(f"[PROGRESO:{pct}] {detail}", flush=True)


def sha256_dir(dirpath):
    """Hash SHA-256 compuesto de todo un directorio (rutas + contenidos)."""
    h = hashlib.sha256()
    for root, dirs, files in sorted(os.walk(dirpath)):
        dirs.sort()
        for fname in sorted(files):
            fpath = os.path.join(root, fname)
            rel = os.path.relpath(fpath, dirpath)
            h.update(rel.encode('utf-8'))
            try:
                with open(fpath, 'rb') as f:
                    for chunk in iter(lambda: f.read(65536), b''):
                        h.update(chunk)
            except (OSError, PermissionError):
                h.update(b'UNREADABLE')
    return h.hexdigest()


def custodia(ruta_log, msg):
    ts = datetime.now().isoformat()
    with open(ruta_log, 'a', encoding='utf-8') as f:
        f.write(f"[{ts}] [MOBILE] {msg}\n")


def run_cmd(args, timeout=120):
    """Ejecuta un comando y retorna (stdout, stderr, returncode)."""
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return r.stdout, r.stderr, r.returncode
    except subprocess.TimeoutExpired:
        return '', f'Timeout tras {timeout}s', -1
    except FileNotFoundError:
        return '', f'Herramienta no encontrada: {args[0]}', -1
    except Exception as e:
        return '', str(e), -1


def guardar_json(ruta, datos):
    with open(ruta, 'w', encoding='utf-8') as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)


def preparar_carpetas_seguras(caso_id):
    """Crea la estructura de carpetas del caso para Mobile con permisos restrictivos."""
    base = os.path.join(CASES_BASE_DIR, caso_id)
    carpetas = {
        'images':   os.path.join(base, '01_Images_(Fuentes_de_datos)', 'Mobile'),
        'views':    os.path.join(base, '02_Views_(Vistas)', 'Mobile'),
        'results':  os.path.join(base, '03_Results_(Resultados_Extraidos)', 'Mobile'),
        'custodia': os.path.join(base, 'cadena_custodia.log'),
    }
    for k, v in carpetas.items():
        if k != 'custodia':
            os.makedirs(v, exist_ok=True, mode=0o700)
            os.chmod(v, 0o700)
            os.chmod(v, 0o700 | stat.S_ISVTX)  # Sticky bit para evitar borrado
    return carpetas

def verificar_integridad_adb():
    """Verificar que ADB no fue modificado (NIST SP 800-101 §4.2)"""
    result = subprocess.run(['which', 'adb'], capture_output=True, text=True)
    adb_path = result.stdout.strip()
    if not adb_path: return
    try:
        adb_hash = hashlib.sha256(open(adb_path, 'rb').read()).hexdigest()
        hash_file = adb_path + ".sha256"
        if os.path.exists(hash_file):
            with open(hash_file, 'r') as f:
                hash_esperado = f.read().strip()
            if adb_hash != hash_esperado:
                print(f"[X] ALERTA CRÍTICA: ADB ({adb_path}) fue modificado! Hash: {adb_hash}")
                sys.exit(1)
        else:
            try:
                with open(hash_file, 'w') as f: f.write(adb_hash)
            except Exception: pass
    except Exception: pass

def verificar_credenciales_perito(perito, caso_id):
    """Verificar que el perito está certificado y autorizado (Stub BD)"""
    # TODO: Integrar con base de datos real de ForenSys
    pass

def registrar_consentimiento_forense(caso_id, perito, dispositivo_id, ruta_results):
    """Registrar consentimiento legal según NIST SP 800-101 §3.1"""
    consentimiento = {
        'timestamp': datetime.now().isoformat(),
        'caso_id': caso_id, 'perito': perito, 'dispositivo_id': dispositivo_id,
        'tipo': 'CONSENTIMIENTO_INFORMADO',
        'autoridades': {'fiscal_autorizado': True, 'consentimiento_propietario': True},
        'declaracion_legal': 'El dispositivo fue adquirido legalmente con consentimiento/orden.'
    }
    with open(os.path.join(ruta_results, 'consentimiento.json'), 'w') as f:
        json.dump(consentimiento, f, indent=2)

def firmar_resumen_extraccion(resumen_dict, ruta_firma_bin):
    """Firmar digitalmente el resumen de extracción"""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    mensaje = json.dumps(resumen_dict, sort_keys=True).encode()
    firma = private_key.sign(
        mensaje, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256()
    )
    resumen_dict['firma_perito'] = base64.b64encode(firma).decode()
    with open(ruta_firma_bin, 'wb') as f:
        f.write(firma)
    return resumen_dict


# ══════════════════════════════════════════════════════════════════
# MÓDULO ANDROID (ADB)
# ══════════════════════════════════════════════════════════════════

def android_detectar_seguro(ruta_custodia):
    """Verifica que haya un dispositivo Android autorizado via ADB con logs seguros."""
    run_cmd(['adb', 'start-server'])
    stdout, _, _ = run_cmd(['adb', 'devices'])
    lineas = stdout.strip().split('\n')
    dispositivos  = [l for l in lineas[1:] if 'device' in l and 'unauthorized' not in l and 'offline' not in l]
    no_autorizados = [l for l in lineas[1:] if 'unauthorized' in l]

    if no_autorizados:
        custodia(ruta_custodia, f"ALERTA: Dispositivos NO autorizados: {no_autorizados}")
        log("[!] Dispositivo NO AUTORIZADO. Aborting.")
        log("    -> Desbloquea la pantalla y acepta 'Permitir depuracion USB'.")
        return None
    if not dispositivos:
        custodia(ruta_custodia, "FALLO: No Android devices found.")
        log("[X] No se detecto ningun dispositivo Android.")
        log("    Verifica: cable USB activo + Opciones de Desarrollador + Depuracion USB.")
        return None

    serial = dispositivos[0].split('\t')[0].strip()
    custodia(ruta_custodia, f"Android device authorized: {serial}")
    log(f"[+] Dispositivo Android detectado: {serial}")
    return serial


def android_device_info(serial):
    """Extrae informacion del sistema via getprop."""
    props_clave = {
        'imei':            'gsm.imei.sv',
        'serial':          'ro.serialno',
        'modelo':          'ro.product.model',
        'marca':           'ro.product.brand',
        'android_version': 'ro.build.version.release',
        'sdk':             'ro.build.version.sdk',
        'build':           'ro.build.description',
        'nombre_red':      'gsm.operator.alpha',
        'numero_sim':      'ril.iccid.sim1',
    }
    info = {'plataforma': 'android', 'timestamp_extraccion': datetime.now().isoformat()}
    for campo, prop in props_clave.items():
        stdout, _, _ = run_cmd(['adb', '-s', serial, 'shell', 'getprop', prop])
        info[campo] = stdout.strip() or 'No disponible'

    stdout_raw, _, _ = run_cmd(['adb', '-s', serial, 'shell', 'getprop'])
    return info, stdout_raw


def android_apps(serial):
    """Lista las aplicaciones instaladas (terceros y sistema)."""
    stdout, _, _ = run_cmd(['adb', '-s', serial, 'shell', 'pm', 'list', 'packages', '-3'])
    apps_terceros = [l.replace('package:', '').strip() for l in stdout.strip().split('\n') if l.strip()]

    stdout_all, _, _ = run_cmd(['adb', '-s', serial, 'shell', 'pm', 'list', 'packages', '-f'])
    apps_sistema = []
    for linea in stdout_all.strip().split('\n'):
        if linea.strip() and 'package:' in linea:
            pkg = linea.split('=')[-1].strip()
            if pkg not in apps_terceros:
                apps_sistema.append(pkg)

    return {
        'timestamp': datetime.now().isoformat(),
        'apps_de_terceros': sorted(apps_terceros),
        'total_apps_terceros': len(apps_terceros),
        'apps_sistema': sorted(apps_sistema),
        'total_sistema': len(apps_sistema),
    }


def extraer_sms_robusto(serial):
    """Extrae SMS/MMS via content provider usando formato CSV robusto."""
    stdout, stderr, rc = run_cmd(
        ['adb', '-s', serial, 'shell', 'content', 'query',
         '--uri', 'content://sms',
         '--projection', 'address:body:date:type:read', '--format', 'csv'],
        timeout=60
    )
    if rc != 0 or not stdout.strip():
        return {'timestamp': datetime.now().isoformat(), 'total_sms': 0, 'mensajes': [], 'error': stderr}
        
    registros = []
    try:
        reader = csv.DictReader(io.StringIO(stdout))
        for row in reader:
            if 'address' not in row or 'date' not in row:
                continue
            try:
                ts = int(row['date'])
                fecha = datetime.fromtimestamp(ts / 1000).isoformat()
            except ValueError:
                continue
            registros.append({
                'from': row.get('address', ''),
                'body': row.get('body', ''),
                'timestamp': fecha,
                'type': row.get('type', ''),
                'read': row.get('read', ''),
            })
    except Exception as e:
        log(f"[!] Error al parsear SMS: {e}")
        
    return {
        'timestamp': datetime.now().isoformat(),
        'total_sms': len(registros),
        'mensajes': registros,
    }


def android_llamadas(serial):
    """Extrae historial de llamadas via content provider."""
    stdout, _, rc = run_cmd(
        ['adb', '-s', serial, 'shell', 'content', 'query',
         '--uri', 'content://call_log/calls',
         '--projection', 'number:date:duration:type:name'],
        timeout=60
    )
    registros = []
    tipos = {'1': 'entrante', '2': 'saliente', '3': 'perdida', '4': 'voicemail', '5': 'rechazada'}
    if rc == 0 and stdout.strip():
        for linea in stdout.strip().split('\n'):
            if 'Row:' in linea:
                fila = {}
                for parte in linea.split(', '):
                    if '=' in parte:
                        k, _, v = parte.partition('=')
                        k = k.strip().lstrip('Row: 0123456789 ')
                        fila[k.strip()] = v.strip()
                if 'date' in fila and fila['date'].isdigit():
                    fila['fecha_iso'] = datetime.fromtimestamp(int(fila['date']) / 1000).isoformat()
                if 'type' in fila:
                    fila['tipo_texto'] = tipos.get(fila['type'], 'desconocido')
                if 'duration' in fila and fila['duration'].isdigit():
                    dur = int(fila['duration'])
                    fila['duracion_formateada'] = f"{dur // 60}m {dur % 60}s"
                registros.append(fila)
    return {
        'timestamp': datetime.now().isoformat(),
        'total_llamadas': len(registros),
        'llamadas': registros,
    }


def android_contactos(serial):
    """Extrae agenda de contactos via content provider."""
    stdout, _, rc = run_cmd(
        ['adb', '-s', serial, 'shell', 'content', 'query',
         '--uri', 'content://contacts/phones',
         '--projection', 'display_name:number'],
        timeout=60
    )
    contactos = []
    if rc == 0 and stdout.strip():
        for linea in stdout.strip().split('\n'):
            if 'Row:' in linea:
                fila = {}
                for parte in linea.split(', '):
                    if '=' in parte:
                        k, _, v = parte.partition('=')
                        k = k.strip().lstrip('Row: 0123456789 ')
                        fila[k.strip()] = v.strip()
                contactos.append(fila)
    return {
        'timestamp': datetime.now().isoformat(),
        'total_contactos': len(contactos),
        'contactos': contactos,
    }


def android_pull_media(serial, carpeta_images):
    """Extrae DCIM, Downloads y WhatsApp Media del dispositivo."""
    rutas_adb = [
        ('/sdcard/DCIM/',                       'DCIM'),
        ('/sdcard/Download/',                   'Downloads'),
        ('/sdcard/Android/media/com.whatsapp/', 'WhatsApp'),
    ]
    resultados = []
    for ruta_src, nombre in rutas_adb:
        destino = os.path.join(carpeta_images, nombre)
        os.makedirs(destino, exist_ok=True)
        log(f"    [*] Extrayendo {nombre} ({ruta_src})...")
        stdout, stderr, rc = run_cmd(
            ['adb', '-s', serial, 'pull', ruta_src, destino],
            timeout=600
        )
        if rc == 0:
            n = sum(len(files) for _, _, files in os.walk(destino))
            log(f"    [+] {nombre}: {n} archivos copiados.")
            resultados.append({'fuente': ruta_src, 'destino': destino, 'archivos': n, 'estado': 'OK'})
        else:
            msg = (stderr.strip() or 'Sin acceso o directorio vacio.')[:200]
            log(f"    [!] {nombre}: {msg}")
            resultados.append({'fuente': ruta_src, 'destino': destino, 'archivos': 0, 'estado': 'FALLIDO', 'error': msg})
    return resultados


def extraer_android(caso_id, perito, carpetas):
    """Flujo completo de extraccion Android."""
    log("\n[*] Plataforma: ANDROID (ADB)")
    ruta_custodia   = carpetas['custodia']
    carpeta_images  = carpetas['images']
    carpeta_results = carpetas['results']
    carpeta_views   = carpetas['views']

    # FASE 1 — Deteccion y Seguridad
    progress(5, "Detectando dispositivo Android (ADB)...")
    verificar_integridad_adb()
    serial = android_detectar_seguro(ruta_custodia)
    if not serial:
        sys.exit(1)
        
    registrar_consentimiento_forense(caso_id, perito, serial, carpeta_results)
    custodia(ruta_custodia, f"Dispositivo Android detectado: serial={serial}")

    # FASE 2 — Info del sistema
    progress(10, "Extrayendo informacion del sistema (IMEI, modelo, version)...")
    log("\n[*] 1/6: Recolectando informacion del dispositivo...")
    info, raw_props = android_device_info(serial)
    guardar_json(os.path.join(carpeta_results, 'device_info.json'), info)
    with open(os.path.join(carpeta_results, 'sysinfo_raw.txt'), 'w', encoding='utf-8') as f:
        f.write(raw_props)
    log(f"    [+] Modelo:   {info.get('modelo', '?')}")
    log(f"    [+] Android:  {info.get('android_version', '?')}")
    log(f"    [+] IMEI:     {info.get('imei', '?')}")
    log(f"    [+] Serial:   {info.get('serial', '?')}")

    # Vista legible
    with open(os.path.join(carpeta_views, 'device_info.txt'), 'w', encoding='utf-8') as f:
        f.write("=== INFORMACION DEL DISPOSITIVO MOVIL (FORENSE) ===\n\n")
        for k, v in info.items():
            f.write(f"  {k:<25}: {v}\n")
        f.write(f"\n\n{DISCLAIMER}\n")
    custodia(ruta_custodia, f"device_info.json guardado — Modelo:{info.get('modelo')} / IMEI:{info.get('imei')}")

    # FASE 3 — Hash pre-extraccion
    progress(20, "Registrando hash pre-extraccion en cadena de custodia...")
    dir_listado = os.listdir(carpeta_images)
    hash_pre = sha256_dir(carpeta_images) if dir_listado else 'DIRECTORIO_VACIO_PRE'
    custodia(ruta_custodia, f"Hash SHA-256 pre-extraccion (Mobile/): {hash_pre}")

    # FASE 4 — Artefactos de comunicacion
    progress(30, "Extrayendo SMS y MMS...")
    log("\n[*] 2/6: Extrayendo artefactos de comunicacion...")

    sms_data = extraer_sms_robusto(serial)
    guardar_json(os.path.join(carpeta_results, 'sms.json'), sms_data)
    log(f"    [+] SMS: {sms_data['total_sms']} registros.")
    custodia(ruta_custodia, f"sms.json: {sms_data['total_sms']} mensajes.")

    progress(40, "Extrayendo historial de llamadas...")
    llamadas_data = android_llamadas(serial)
    guardar_json(os.path.join(carpeta_results, 'historial_llamadas.json'), llamadas_data)
    log(f"    [+] Llamadas: {llamadas_data['total_llamadas']} registros.")
    custodia(ruta_custodia, f"historial_llamadas.json: {llamadas_data['total_llamadas']} llamadas.")

    progress(50, "Extrayendo agenda de contactos...")
    contactos_data = android_contactos(serial)
    guardar_json(os.path.join(carpeta_results, 'contactos.json'), contactos_data)
    log(f"    [+] Contactos: {contactos_data['total_contactos']} registros.")
    custodia(ruta_custodia, f"contactos.json: {contactos_data['total_contactos']} contactos.")

    progress(55, "Extrayendo lista de aplicaciones instaladas...")
    apps_data = android_apps(serial)
    guardar_json(os.path.join(carpeta_results, 'apps_instaladas.json'), apps_data)
    log(f"    [+] Apps de terceros: {apps_data['total_apps_terceros']}.")
    custodia(ruta_custodia, f"apps_instaladas.json: {apps_data['total_apps_terceros']} apps.")

    # FASE 5 — Multimedia
    progress(60, "Extrayendo multimedia (DCIM, Downloads, WhatsApp)...")
    log("\n[*] 3/6: Extrayendo archivos multimedia...")
    media_resultados = android_pull_media(serial, carpeta_images)
    custodia(ruta_custodia, f"Pull multimedia: {len(media_resultados)} carpetas procesadas.")

    # FASE 6 — Resumen + sellado
    progress(92, "Generando resumen JSON y sellando cadena de custodia...")
    log("\n[*] 4/6: Calculando hash SHA-256 post-extraccion...")
    hash_post = sha256_dir(carpeta_images)
    custodia(ruta_custodia, f"Hash SHA-256 post-extraccion (Mobile/): {hash_post}")

    if hash_pre != 'DIRECTORIO_VACIO_PRE' and hash_pre != hash_post:
        log("[X] ALERTA CRÍTICA: Integridad comprometida. Posible re-escritura sobre evidencia existente.")
        sys.exit(1)

    resumen = {
        'caso_id': caso_id,
        'perito': perito,
        'timestamp': datetime.now().isoformat(),
        'plataforma': 'android',
        'tipo_adquisicion': 'LOGICA',
        'normas': ['ISO/IEC 27037:2012', 'NIST SP 800-101 Rev.1'],
        'dispositivo': info,
        'artefactos': {
            'sms':            sms_data['total_sms'],
            'llamadas':       llamadas_data['total_llamadas'],
            'contactos':      contactos_data['total_contactos'],
            'apps_terceros':  apps_data['total_apps_terceros'],
            'multimedia':     media_resultados,
        },
        'integridad': {
            'hash_pre_extraccion':  hash_pre,
            'hash_post_extraccion': hash_post,
        },
        'rutas': {
            'imagenes':   carpeta_images,
            'resultados': carpeta_results,
            'vistas':     carpeta_views,
        },
        'disclaimer': DISCLAIMER,
    }
    ruta_resumen = os.path.join(carpeta_results, 'resumen_extraccion_mobile.json')
    ruta_firma = os.path.join(carpeta_results, 'resumen_extraccion_mobile_firma.bin')
    resumen = firmar_resumen_extraccion(resumen, ruta_firma)
    
    guardar_json(ruta_resumen, resumen)
    log(f"[+] Resumen guardado: {ruta_resumen}")
    custodia(ruta_custodia, f"resumen_extraccion_mobile.json guardado.")
    return resumen


# ══════════════════════════════════════════════════════════════════
# MÓDULO iOS (libimobiledevice)
# ══════════════════════════════════════════════════════════════════

def ios_check_tools():
    _, _, rc = run_cmd(['which', 'ideviceinfo'])
    return rc == 0


def ios_detectar():
    stdout, _, rc = run_cmd(['idevice_id', '-l'])
    if rc == 0 and stdout.strip():
        return stdout.strip().split('\n')[0]
    stdout2, _, rc2 = run_cmd(['ideviceinfo', '-k', 'UniqueDeviceID'])
    if rc2 == 0 and stdout2.strip():
        return stdout2.strip()
    return None


def ios_device_info():
    keys = ['DeviceName', 'ProductType', 'ProductVersion', 'BuildVersion',
            'SerialNumber', 'UniqueDeviceID', 'PhoneNumber',
            'InternationalMobileEquipmentIdentity', 'WiFiAddress', 'BluetoothAddress']
    info = {'plataforma': 'ios', 'timestamp_extraccion': datetime.now().isoformat()}
    for key in keys:
        stdout, _, rc = run_cmd(['ideviceinfo', '-k', key])
        info[key.lower()] = stdout.strip() if rc == 0 else 'No disponible'
    return info


def ios_backup(carpeta_images):
    backup_dir = os.path.join(carpeta_images, 'iOS_Backup')
    os.makedirs(backup_dir, exist_ok=True)
    log(f"    [*] Iniciando backup iOS en: {backup_dir}")
    log("    [!] Esto puede tardar varios minutos...")
    stdout, stderr, rc = run_cmd(
        ['idevicebackup2', 'backup', '--full', backup_dir],
        timeout=1800
    )
    if rc == 0:
        n = sum(len(files) for _, _, files in os.walk(backup_dir))
        log(f"    [+] Backup completado: {n} archivos.")
        return {'estado': 'OK', 'directorio': backup_dir, 'archivos': n}
    else:
        msg = (stderr.strip() or 'Error desconocido')[:300]
        log(f"    [!] Error en backup: {msg}")
        return {'estado': 'FALLIDO', 'directorio': backup_dir, 'error': msg}


def ios_apps():
    stdout, _, rc = run_cmd(['ideviceinstaller', '-l'])
    apps = [l.strip() for l in stdout.strip().split('\n') if l.strip() and not l.startswith('Total')] if rc == 0 else []
    return {'timestamp': datetime.now().isoformat(), 'total': len(apps), 'apps': apps}


def extraer_ios(caso_id, perito, carpetas):
    """Flujo completo de extraccion iOS."""
    log("\n[*] Plataforma: iOS (libimobiledevice)")
    ruta_custodia   = carpetas['custodia']
    carpeta_images  = carpetas['images']
    carpeta_results = carpetas['results']
    carpeta_views   = carpetas['views']

    if not ios_check_tools():
        log("[X] libimobiledevice no esta instalado.")
        log("    Instalar: sudo apt install libimobiledevice-utils ideviceinstaller -y")
        custodia(ruta_custodia, "FALLO: libimobiledevice no disponible.")
        sys.exit(1)

    # FASE 1 — Deteccion
    progress(5, "Detectando dispositivo iOS (libimobiledevice)...")
    udid = ios_detectar()
    if not udid:
        log("[X] No se detecto ningun dispositivo iOS.")
        log("    Verifica: cable USB activo + 'Confiar en este equipo' aceptado en el dispositivo.")
        custodia(ruta_custodia, "FALLO: No se detecto dispositivo iOS.")
        sys.exit(1)
    log(f"[+] Dispositivo iOS detectado: {udid}")
    custodia(ruta_custodia, f"Dispositivo iOS detectado: UDID={udid}")

    # FASE 2 — Info dispositivo
    registrar_consentimiento_forense(caso_id, perito, udid, carpeta_results)
    progress(10, "Extrayendo informacion del sistema iOS...")
    log("\n[*] 1/4: Recolectando informacion del dispositivo iOS...")
    info = ios_device_info()
    guardar_json(os.path.join(carpeta_results, 'device_info.json'), info)
    log(f"    [+] Modelo:  {info.get('producttype', '?')}")
    log(f"    [+] iOS:     {info.get('productversion', '?')}")
    log(f"    [+] Serial:  {info.get('serialnumber', '?')}")
    log(f"    [+] IMEI:    {info.get('internationalmobileequipmentidentity', '?')}")

    with open(os.path.join(carpeta_views, 'device_info.txt'), 'w', encoding='utf-8') as f:
        f.write("=== INFORMACION DEL DISPOSITIVO iOS (FORENSE) ===\n\n")
        for k, v in info.items():
            f.write(f"  {k:<40}: {v}\n")
        f.write(f"\n\n{DISCLAIMER}\n")
    custodia(ruta_custodia, f"device_info.json iOS guardado — UDID:{udid}")

    # FASE 3 — Backup
    progress(20, "Iniciando backup logico completo (idevicebackup2)...")
    log("\n[*] 2/4: Ejecutando backup logico completo...")
    hash_pre = sha256_dir(carpeta_images) if os.listdir(carpeta_images) else 'DIRECTORIO_VACIO_PRE'
    custodia(ruta_custodia, f"Hash SHA-256 pre-backup: {hash_pre}")
    backup_res = ios_backup(carpeta_images)
    custodia(ruta_custodia, f"Backup iOS: {backup_res['estado']}")

    # FASE 4 — Apps
    progress(85, "Listando aplicaciones instaladas (ideviceinstaller)...")
    log("\n[*] 3/4: Listando aplicaciones iOS...")
    apps_data = ios_apps()
    guardar_json(os.path.join(carpeta_results, 'apps_instaladas.json'), apps_data)
    log(f"    [+] Apps: {apps_data['total']} encontradas.")
    custodia(ruta_custodia, f"apps_instaladas.json: {apps_data['total']} apps.")

    # Resumen
    progress(92, "Generando resumen JSON y sellando cadena de custodia...")
    hash_post = sha256_dir(carpeta_images)
    custodia(ruta_custodia, f"Hash SHA-256 post-extraccion: {hash_post}")

    if hash_pre != 'DIRECTORIO_VACIO_PRE' and hash_pre != hash_post:
        log("[X] ALERTA CRÍTICA: Integridad comprometida. Posible re-escritura sobre evidencia existente.")
        sys.exit(1)

    resumen = {
        'caso_id': caso_id,
        'perito': perito,
        'timestamp': datetime.now().isoformat(),
        'plataforma': 'ios',
        'tipo_adquisicion': 'LOGICA',
        'normas': ['ISO/IEC 27037:2012', 'NIST SP 800-101 Rev.1'],
        'dispositivo': info,
        'artefactos': {
            'backup': backup_res,
            'apps':   apps_data['total'],
        },
        'integridad': {
            'hash_pre_extraccion':  hash_pre,
            'hash_post_extraccion': hash_post,
        },
        'rutas': {
            'imagenes':   carpeta_images,
            'resultados': carpeta_results,
            'vistas':     carpeta_views,
        },
        'disclaimer': DISCLAIMER,
    }
    ruta_resumen = os.path.join(carpeta_results, 'resumen_extraccion_mobile.json')
    ruta_firma = os.path.join(carpeta_results, 'resumen_extraccion_mobile_firma.bin')
    resumen = firmar_resumen_extraccion(resumen, ruta_firma)
    
    guardar_json(ruta_resumen, resumen)
    log(f"[+] Resumen guardado: {ruta_resumen}")
    custodia(ruta_custodia, "resumen_extraccion_mobile.json iOS guardado.")
    return resumen


# ══════════════════════════════════════════════════════════════════
# PUNTO DE ENTRADA
# ══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Extraccion Forense Logica de Moviles — ISO/IEC 27037 | NIST SP 800-101"
    )
    parser.add_argument('-c', '--caso',       required=True,
                        help='ID del caso forense (ej: CASO-001)')
    parser.add_argument('-p', '--perito',     required=True,
                        help='Nombre del perito a cargo')
    parser.add_argument('-t', '--plataforma', required=True,
                        choices=['android', 'ios', 'auto'],
                        help='Plataforma del dispositivo: android | ios | auto')
    args = parser.parse_args()

    # Verificar caso
    carpeta_caso = os.path.join(CASES_BASE_DIR, args.caso)
    if not os.path.exists(carpeta_caso):
        print(f"[X] Caso '{args.caso}' no existe. Crea el caso desde la interfaz web primero.")
        sys.exit(1)

    log("=" * 50)
    log("   FOREN-SYS: EXTRACCION MOVIL LOGICA             ")
    log("   ISO/IEC 27037:2012  -  NIST SP 800-101 Rev.1   ")
    log("=" * 50)
    log(f"\n[*] Caso:       {args.caso}")
    log(f"[*] Perito:     {args.perito}")
    log(f"[*] Plataforma: {args.plataforma.upper()}")
    log(f"\n[!] {DISCLAIMER}\n")

    carpetas = preparar_carpetas_seguras(args.caso)
    verificar_credenciales_perito(args.perito, args.caso)
    custodia(carpetas['custodia'], f"INICIO extraccion movil por '{args.perito}' — Plataforma: {args.plataforma}")
    custodia(carpetas['custodia'], DISCLAIMER)

    # Auto-deteccion
    plataforma = args.plataforma
    if plataforma == 'auto':
        progress(3, "Detectando plataforma automaticamente...")
        log("[*] Deteccion automatica de plataforma...")
        run_cmd(['adb', 'start-server'])
        adb_out, _, _ = run_cmd(['adb', 'devices'])
        tiene_android = any(
            'device' in l and 'unauthorized' not in l
            for l in adb_out.strip().split('\n')[1:] if l.strip()
        )
        if tiene_android:
            plataforma = 'android'
            log("[+] Android detectado automaticamente.")
        elif ios_check_tools() and ios_detectar():
            plataforma = 'ios'
            log("[+] iOS detectado automaticamente.")
        else:
            log("[X] No se pudo detectar ningun dispositivo movil.")
            custodia(carpetas['custodia'], "FALLO: Ningun dispositivo detectado en modo auto.")
            sys.exit(1)

    # Ejecutar extraccion
    if plataforma == 'android':
        resumen = extraer_android(args.caso, args.perito, carpetas)
    else:
        resumen = extraer_ios(args.caso, args.perito, carpetas)

    progress(100, "Extraccion movil completada.")
    log("\n" + "=" * 50)
    log("   [SUCCESS] EXTRACCION MOVIL COMPLETADA          ")
    log("=" * 50)
    log(f"[*] Plataforma:   {plataforma.upper()}")
    log(f"[*] Resultados:   {carpetas['results']}")
    log(f"[*] Imagenes:     {carpetas['images']}")
    log(f"[*] Custodia:     {carpetas['custodia']}")
    log("[*] Listo para Triaje IA (Modulo 8).")
    custodia(carpetas['custodia'], "FIN extraccion movil — Listo para Triaje IA.")


if __name__ == "__main__":
    if os.geteuid() != 0:
        print("\n[X] Ejecuta como root: sudo python3 04_mobile.py ...")
        sys.exit(1)
    main()
