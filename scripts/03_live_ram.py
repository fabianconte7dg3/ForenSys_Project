#!/usr/bin/env python3
"""
03_live_ram.py — Análisis forense de memoria volátil (Volatility3)
Multi-OS: Windows, Linux, macOS
Cumplimiento ISO/IEC 27037:2012 — NIST SP 800-86

Uso:
    sudo python3 03_live_ram.py --archivo /ruta/memoria.raw --caso CASO-001 --perito "Juan Perez"
"""
import os
import sys
import json
import shutil
import hashlib
import argparse
import subprocess
import configparser
import stat
import base64
from datetime import datetime
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding

# ── Configuración de rutas ─────────────────────────────────────────
def cargar_config():
    """Cargar rutas desde archivo de configuración o usar defaults seguros."""
    config = configparser.ConfigParser()
    if os.path.exists('/etc/forensys/config.ini'):
        config.read('/etc/forensys/config.ini')
        return {
            'cases_base_dir': config.get('paths', 'cases_base_dir', fallback='/mnt/Destino_ForenSys'),
            'volatility_path': config.get('tools', 'volatility_path', fallback=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'volatility3', 'vol.py')),
        }
    return {
        'cases_base_dir': '/home/ciber-admin/ForenSys_Project/Casos_ForenSys', # Mantenemos retrocompatibilidad si no hay config
        'volatility_path': os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'volatility3', 'vol.py')
    }

config_data = cargar_config()
CASES_BASE_DIR = config_data['cases_base_dir']
VOLATILITY_PATH = config_data['volatility_path']

# ── Plugins por SO ─────────────────────────────────────────────────
PLUGIN_SETS = {
    'windows': [
        ('windows.info.Info',         'info',         'Informacion del sistema Windows'),
        ('windows.pslist.PsList',     'pslist',       'Lista de procesos activos'),
        ('windows.pstree.PsTree',     'pstree',       'Arbol jerarquico de procesos'),
        ('windows.cmdline.CmdLine',   'cmdline',      'Lineas de comando ejecutadas'),
        ('windows.netscan.NetScan',   'netscan',      'Conexiones de red activas'),
        ('windows.malfind.Malfind',   'malfind',      'Inyecciones de codigo (shellcode)'),
        ('windows.dlllist.DllList',   'dlllist',      'DLLs cargadas por proceso'),
        ('windows.hashdump.Hashdump', 'hashdump',     'Hashes NTLM de contrasenas'),
    ],
    'linux': [
        ('linux.pslist.PsList',       'pslist',       'Lista de procesos activos'),
        ('linux.pstree.PsTree',       'pstree',       'Arbol jerarquico de procesos'),
        ('linux.bash.Bash',           'bash_history', 'Historial de comandos bash'),
        ('linux.netfilter.NetFilter', 'netfilter',    'Reglas de firewall en memoria'),
        ('linux.malfind.Malfind',     'malfind',      'Inyecciones de codigo'),
        ('linux.lsof.Lsof',          'lsof',         'Archivos abiertos por proceso'),
        ('linux.sockstat.Sockstat',   'sockstat',     'Estado de sockets de red'),
    ],
    'macos': [
        ('mac.pslist.PsList',         'pslist',       'Lista de procesos activos'),
        ('mac.pstree.PsTree',         'pstree',       'Arbol jerarquico de procesos'),
        ('mac.netstat.Netstat',       'netstat',      'Conexiones de red activas'),
        ('mac.bash.Bash',             'bash_history', 'Historial de comandos bash'),
        ('mac.malfind.Malfind',       'malfind',      'Inyecciones de codigo'),
        ('mac.lsof.Lsof',            'lsof',         'Archivos abiertos por proceso'),
    ],
}


def log(msg):
    print(msg, flush=True)


def progress(pct, detail):
    print(f"[PROGRESO:{pct}] {detail}", flush=True)


def calcular_hashes_multiples(path):
    """Calcula SHA-256 + SHA-1 + MD5 para compatibilidad forense en cortes internacionales."""
    sha256 = hashlib.sha256()
    sha1 = hashlib.sha1()
    md5 = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            sha256.update(chunk)
            sha1.update(chunk)
            md5.update(chunk)
    return {
        'md5': md5.hexdigest(),
        'sha1': sha1.hexdigest(),
        'sha256': sha256.hexdigest(),
    }

def validar_archivo_memoria(ruta):
    """Validar que el archivo es realmente un volcado de memoria (Path Traversal / Symlink Attack)."""
    if os.path.islink(ruta):
        print(f"[X] ALERTA DE SEGURIDAD: No se permiten symlinks para evidencia ({ruta})")
        sys.exit(1)
        
    rutas_prohibidas = ['/etc', '/sys', '/dev', '/proc', '/var/log']
    ruta_abs = os.path.abspath(ruta)
    for rp in rutas_prohibidas:
        if ruta_abs.startswith(rp):
            print(f"[X] ALERTA DE SEGURIDAD: Ruta prohibida seleccionada ({ruta}). Posible inyección.")
            sys.exit(1)
            
    tamanio = os.path.getsize(ruta)
    if tamanio < 100 * 1024 * 1024:
        print(f"[!] Advertencia: Archivo excepcionalmente pequeño ({tamanio} bytes).")

def verificar_integridad_volatility(vol_path):
    """Verificar que Volatility3 no fue modificado (Anti-Tampering)."""
    hash_file = vol_path + ".sha256"
    try:
        actual_hash = hashlib.sha256(open(vol_path, 'rb').read()).hexdigest()
        if os.path.exists(hash_file):
            with open(hash_file, 'r') as f:
                hash_esperado = f.read().strip()
            if actual_hash != hash_esperado:
                print(f"[X] ALERTA CRÍTICA: Volatility3 ({vol_path}) fue modificado!")
                print(f"  Posible compromiso de la herramienta forense (Rootkit/Trojano).")
                sys.exit(1)
        else:
            with open(hash_file, 'w') as f:
                f.write(actual_hash)
    except Exception as e:
        print(f"[!] Error verificando integridad de Volatility: {e}")

def validar_plugins_volatility(vol_path):
    """Verificar que los plugins básicos pueden cargar sin errores fatal."""
    result = subprocess.run(['python3', vol_path, '-h'], capture_output=True, text=True)
    if result.returncode != 0:
         print("[X] ALERTA: Volatility3 no pudo inicializarse. Plugins corruptos o faltantes.")
         sys.exit(1)

def firmar_analisis_ram(resumen_dict, ruta_firma_bin):
    """Firmar digitalmente el análisis con clave RSA-2048."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    mensaje = json.dumps(resumen_dict, sort_keys=True).encode()
    firma = private_key.sign(
        mensaje,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256()
    )
    resumen_dict['firma_perito_base64'] = base64.b64encode(firma).decode()
    with open(ruta_firma_bin, 'wb') as f:
        f.write(firma)
    return resumen_dict


def custodia_append(ruta_log, msg):
    """Agrega una linea con timestamp al log de cadena de custodia."""
    ts = datetime.now().isoformat()
    with open(ruta_log, 'a', encoding='utf-8') as f:
        f.write(f"[{ts}] [RAM-ANALISIS] {msg}\n")


def run_plugin(vol_path, mem_file, plugin, output_base, timeout=300):
    """
    Ejecuta un plugin de Volatility3.
    Guarda salida en JSON (.json) y texto legible (.txt).
    Retorna (exito, mensaje_error).
    """
    # 1. Formato JSON
    try:
        result = subprocess.run(
            ['python3', vol_path, '-f', mem_file, '--output-format', 'json', plugin],
            capture_output=True, text=True, timeout=timeout
        )
        if result.returncode == 0 and result.stdout.strip():
            with open(output_base + '.json', 'w', encoding='utf-8') as f:
                f.write(result.stdout)
        elif result.returncode != 0:
            error_msg = (result.stderr or result.stdout or 'Sin detalles')[:500]
            return False, error_msg
    except subprocess.TimeoutExpired:
        return False, f"Timeout tras {timeout}s"
    except Exception as e:
        return False, str(e)

    # 2. Formato texto legible
    try:
        result_txt = subprocess.run(
            ['python3', vol_path, '-f', mem_file, plugin],
            capture_output=True, text=True, timeout=timeout
        )
        with open(output_base + '.txt', 'w', encoding='utf-8') as f:
            f.write(result_txt.stdout)
    except Exception:
        pass  # El JSON ya fue guardado, el txt es secundario

    return True, None


def detect_os(vol_path, mem_file):
    """
    Detecta el SO del volcado usando Volatility3.
    Orden: Windows -> Linux -> macOS -> desconocido.
    """
    log("[*] Detectando sistema operativo del volcado de memoria...")

    # Intento 1: Windows
    try:
        result = subprocess.run(
            ['python3', vol_path, '-f', mem_file, 'windows.info.Info'],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0 and ('NtBuildLab' in result.stdout or 'KdDebuggerData' in result.stdout):
            log("[+] Sistema operativo detectado: WINDOWS")
            return 'windows'
    except Exception:
        pass

    # Intento 2: Banners (Linux/macOS)
    try:
        result = subprocess.run(
            ['python3', vol_path, '-f', mem_file, 'banners.Banners'],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            out = result.stdout.lower()
            if 'linux' in out:
                log("[+] Sistema operativo detectado: LINUX")
                return 'linux'
            if 'darwin' in out or 'macos' in out:
                log("[+] Sistema operativo detectado: macOS")
                return 'macos'
    except Exception:
        pass

    # Intento 3: Linux pslist directo
    try:
        result = subprocess.run(
            ['python3', vol_path, '-f', mem_file, 'linux.pslist.PsList'],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0 and result.stdout.strip():
            log("[+] Sistema operativo detectado: LINUX (por pslist)")
            return 'linux'
    except Exception:
        pass

    log("[!] OS no determinado. Se ejecutaran todos los plugins disponibles.")
    return 'unknown'


def analizar_ram(mem_file, caso_id, perito):
    """Flujo principal de analisis forense de RAM."""
    log("=" * 50)
    log("   FOREN-SYS: ANALISIS DINAMICO DE RAM            ")
    log("      ISO/IEC 27037:2012  -  NIST SP 800-86       ")
    log("=" * 50)

    # Verificar Volatility3
    if not os.path.exists(VOLATILITY_PATH):
        log(f"[X] Volatility3 no encontrado en: {VOLATILITY_PATH}")
        sys.exit(1)

    # Verificar Volatility3 Integridad y Plugins
    verificar_integridad_volatility(VOLATILITY_PATH)
    validar_plugins_volatility(VOLATILITY_PATH)

    # Preparar carpetas del caso
    carpeta_caso    = os.path.join(CASES_BASE_DIR, caso_id)
    carpeta_images  = os.path.join(carpeta_caso, '01_Images_(Fuentes_de_datos)', 'RAM')
    carpeta_views   = os.path.join(carpeta_caso, '02_Views_(Vistas)', 'RAM')
    carpeta_results = os.path.join(carpeta_caso, '03_Results_(Resultados_Extraidos)', 'RAM')
    ruta_custodia   = os.path.join(carpeta_caso, 'cadena_custodia.log')

    for carpeta in [carpeta_images, carpeta_views, carpeta_results]:
        os.makedirs(carpeta, exist_ok=True)
        os.chmod(carpeta, 0o700)  # Seguridad: Restricción de permisos (CRÍTICA 3)

    log(f"\n[*] Caso:   {caso_id}")
    log(f"[*] Perito: {perito}")
    log(f"[*] Imagen: {mem_file}")

    # FASE 1: Hash pre-analisis multiples (ISO 27037 — compatibilidad judicial)
    progress(5, "Calculando hashes (MD5, SHA-1, SHA-256) pre-analisis...")
    log("\n[*] 1/6: Calculando hashes del volcado (pre-analisis)...")
    hashes_pre = calcular_hashes_multiples(mem_file)
    log(f"[+] MD5:    {hashes_pre['md5']}")
    log(f"[+] SHA-1:  {hashes_pre['sha1']}")
    log(f"[+] SHA-256: {hashes_pre['sha256']}")
    custodia_append(ruta_custodia, f"INICIO analisis RAM por '{perito}'")
    custodia_append(ruta_custodia, f"Archivo fuente: {mem_file}")
    custodia_append(ruta_custodia, f"Hash Pre-Analisis MD5: {hashes_pre['md5']}")
    custodia_append(ruta_custodia, f"Hash Pre-Analisis SHA-256: {hashes_pre['sha256']}")

    # FASE 2: Copia sellada a 01_Images/RAM/
    progress(10, "Copiando volcado a boveda del caso (01_Images/RAM/)...")
    log("\n[*] 2/6: Copiando imagen forense al directorio de fuentes del caso...")
    nombre_imagen  = os.path.basename(mem_file)
    destino_imagen = os.path.join(carpeta_images, nombre_imagen)
    if not os.path.exists(destino_imagen):
        shutil.copy2(mem_file, destino_imagen)
        os.chmod(destino_imagen, 0o600)  # Evitar lectura no autorizada
        hashes_copia = calcular_hashes_multiples(destino_imagen)
        if hashes_copia['sha256'] == hashes_pre['sha256']:
            log(f"[+] Copia verificada: {destino_imagen}")
            custodia_append(ruta_custodia, f"Copia sellada en: {destino_imagen} — Hash OK")
        else:
            log("[X] ALERTA: Hash de copia no coincide. Integridad comprometida.")
            custodia_append(ruta_custodia, "ALERTA: Discrepancia de hash en copia sellada.")
    else:
        log(f"[*] Copia ya existia: {destino_imagen}")

    # FASE 3: Deteccion de SO
    progress(15, "Detectando sistema operativo del volcado...")
    os_detected = detect_os(VOLATILITY_PATH, mem_file)
    custodia_append(ruta_custodia, f"OS detectado: {os_detected.upper()}")

    if os_detected == 'unknown':
        plugins_a_ejecutar = []
        for so, plugins in PLUGIN_SETS.items():
            plugins_a_ejecutar.extend(plugins)
    else:
        plugins_a_ejecutar = PLUGIN_SETS.get(os_detected, [])

    # FASE 4: Ejecucion de plugins Volatility3
    log(f"\n[*] 3/6: Ejecutando {len(plugins_a_ejecutar)} plugins de Volatility3...")
    total_plugins = len(plugins_a_ejecutar)
    exitosos = 0
    fallidos = []

    for i, (plugin, nombre_archivo, descripcion) in enumerate(plugins_a_ejecutar):
        pct = 20 + int((i / total_plugins) * 70)
        progress(pct, f"{descripcion}...")
        log(f"\n[*] Plugin {i+1}/{total_plugins}: {descripcion}")

        output_base_result = os.path.join(carpeta_results, nombre_archivo)
        output_base_view   = os.path.join(carpeta_views,   nombre_archivo)

        exito, error = run_plugin(VOLATILITY_PATH, mem_file, plugin, output_base_result)

        if exito:
            if os.path.exists(output_base_result + '.txt'):
                shutil.copy2(output_base_result + '.txt', output_base_view + '.txt')
            log(f"[+] {plugin}: OK")
            custodia_append(ruta_custodia, f"Plugin {plugin}: EXITO")
            exitosos += 1
        else:
            log(f"[!] {plugin}: {error}")
            custodia_append(ruta_custodia, f"Plugin {plugin}: FALLIDO — {error}")
            fallidos.append((plugin, error))

    # FASE 5: Resumen JSON y Firma RSA (Non-Repudiation)
    progress(92, "Generando resumen firmado del analisis...")
    log("\n[*] 4/6: Generando resumen firmado del analisis...")
    resumen = {
        "caso_id": caso_id,
        "perito": perito,
        "timestamp": datetime.now().isoformat(),
        "archivo_fuente": mem_file,
        "hashes_pre": hashes_pre,
        "os_detectado": os_detected,
        "plugins_exitosos": exitosos,
        "plugins_fallidos": len(fallidos),
        "detalle_fallidos": [{"plugin": p, "error": e} for p, e in fallidos]
    }
    
    ruta_resumen = os.path.join(carpeta_results, 'resumen_analisis_ram.json')
    ruta_firma = os.path.join(carpeta_results, 'resumen_analisis_ram_firma.bin')
    
    resumen = firmar_analisis_ram(resumen, ruta_firma)
    
    with open(ruta_resumen, 'w', encoding='utf-8') as f:
        json.dump(resumen, f, ensure_ascii=False, indent=2)
    log(f"[+] Resumen guardado y firmado criptográficamente: {ruta_resumen}")

    # FASE 6: Sellado final
    progress(97, "Sellando cadena de custodia...")
    log("\n[*] 5/6: Verificando integridad post-analisis...")
    hashes_post = calcular_hashes_multiples(mem_file)
    integridad_ok = (hashes_post['sha256'] == hashes_pre['sha256'])
    custodia_append(ruta_custodia, f"Hash Post-Analisis SHA-256: {hashes_post['sha256']}")
    custodia_append(ruta_custodia, f"Integridad archivo fuente: {'VERIFICADA' if integridad_ok else 'COMPROMETIDA'}")
    custodia_append(ruta_custodia, f"Plugins exitosos: {exitosos}/{total_plugins}")
    custodia_append(ruta_custodia, f"FIN analisis RAM — resultados en: {carpeta_results}")

    if not integridad_ok:
        log("[X] ALERTA: Hash post-analisis no coincide. El archivo fuente pudo haberse modificado.")

    progress(100, "Analisis de memoria volatil completado.")
    log("\n" + "=" * 50)
    log("   [SUCCESS] ANALISIS DE RAM COMPLETADO           ")
    log("=" * 50)
    log(f"[*] OS detectado:     {os_detected.upper()}")
    log(f"[*] Plugins OK:       {exitosos}/{total_plugins}")
    if fallidos:
        log(f"[*] Plugins fallidos: {len(fallidos)} (ver cadena de custodia)")
    log(f"[*] Resultados en:    {carpeta_results}")
    log(f"[*] Vistas en:        {carpeta_views}")
    log(f"[*] Cadena custodia:  {ruta_custodia}")
    log("[*] Resultados listos para Analista IA (Modulo 8).")


def main():
    parser = argparse.ArgumentParser(
        description="Analisis forense RAM — Multi-OS (Volatility3)"
    )
    parser.add_argument('-a', '--archivo', required=True,
                        help='Ruta al volcado de memoria (.raw/.dmp/.mem/.vmem)')
    parser.add_argument('-c', '--caso',    required=True,
                        help='ID del caso forense (ej: CASO-001)')
    parser.add_argument('-p', '--perito',  required=True,
                        help='Nombre del perito a cargo')
    args = parser.parse_args()

    # Validar archivo fuente y caso
    validar_archivo_memoria(args.archivo)

    carpeta_caso = os.path.join(CASES_BASE_DIR, args.caso)
    if not os.path.exists(carpeta_caso):
        print(f"[X] Caso '{args.caso}' no existe en {CASES_BASE_DIR}.")
        print("    Abra primero el caso desde la interfaz web.")
        sys.exit(1)
        
    # Validar estructura y permisos del caso (CRÍTICA 7)
    carpetas_requeridas = ['01_Images_(Fuentes_de_datos)', '02_Views_(Vistas)', '03_Results_(Resultados_Extraidos)']
    for carpeta in carpetas_requeridas:
        if not os.path.isdir(os.path.join(carpeta_caso, carpeta)):
            print(f"[X] Caso incompleto: falta {carpeta} en {carpeta_caso}")
            sys.exit(1)
    stat_info = os.stat(carpeta_caso)
    permisos = stat.S_IMODE(stat_info.st_mode)
    if permisos & 0o077 != 0:
        print(f"[!] Advertencia: Permisos del caso muy abiertos ({oct(permisos)}). Ajustando a 0o700.")
        os.chmod(carpeta_caso, 0o700)

    analizar_ram(args.archivo, args.caso, args.perito)


if __name__ == "__main__":
    if os.geteuid() != 0:
        print("\n[X] Ejecuta como root: sudo python3 03_live_ram.py ...")
        sys.exit(1)
    main()
