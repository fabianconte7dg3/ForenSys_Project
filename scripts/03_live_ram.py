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
from datetime import datetime

# ── Configuración de rutas ─────────────────────────────────────────
CASES_BASE_DIR = '/home/ciber-admin/ForenSys_Project/Casos_ForenSys'
VOLATILITY_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'volatility3', 'vol.py'
)

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


def sha256_file(path):
    """Calcula SHA-256 leyendo por bloques para archivos grandes."""
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


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

    # Preparar carpetas del caso
    carpeta_caso    = os.path.join(CASES_BASE_DIR, caso_id)
    carpeta_images  = os.path.join(carpeta_caso, '01_Images_(Fuentes_de_datos)', 'RAM')
    carpeta_views   = os.path.join(carpeta_caso, '02_Views_(Vistas)', 'RAM')
    carpeta_results = os.path.join(carpeta_caso, '03_Results_(Resultados_Extraidos)', 'RAM')
    ruta_custodia   = os.path.join(carpeta_caso, 'cadena_custodia.log')

    for carpeta in [carpeta_images, carpeta_views, carpeta_results]:
        os.makedirs(carpeta, exist_ok=True)

    log(f"\n[*] Caso:   {caso_id}")
    log(f"[*] Perito: {perito}")
    log(f"[*] Imagen: {mem_file}")

    # FASE 1: Hash pre-analisis (ISO 27037 — integridad)
    progress(5, "Calculando hash SHA-256 pre-analisis...")
    log("\n[*] 1/6: Calculando hash SHA-256 del volcado (pre-analisis)...")
    hash_pre = sha256_file(mem_file)
    log(f"[+] Hash Pre-Analisis SHA-256: {hash_pre}")
    custodia_append(ruta_custodia, f"INICIO analisis RAM por '{perito}'")
    custodia_append(ruta_custodia, f"Archivo fuente: {mem_file}")
    custodia_append(ruta_custodia, f"Hash Pre-Analisis SHA-256: {hash_pre}")

    # FASE 2: Copia sellada a 01_Images/RAM/
    progress(10, "Copiando volcado a boveda del caso (01_Images/RAM/)...")
    log("\n[*] 2/6: Copiando imagen forense al directorio de fuentes del caso...")
    nombre_imagen  = os.path.basename(mem_file)
    destino_imagen = os.path.join(carpeta_images, nombre_imagen)
    if not os.path.exists(destino_imagen):
        shutil.copy2(mem_file, destino_imagen)
        hash_copia = sha256_file(destino_imagen)
        if hash_copia == hash_pre:
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

    # FASE 5: Resumen JSON
    progress(92, "Generando resumen del analisis...")
    log("\n[*] 4/6: Generando resumen del analisis...")
    resumen = {
        "caso_id": caso_id,
        "perito": perito,
        "timestamp": datetime.now().isoformat(),
        "archivo_fuente": mem_file,
        "hash_pre": hash_pre,
        "os_detectado": os_detected,
        "plugins_exitosos": exitosos,
        "plugins_fallidos": len(fallidos),
        "detalle_fallidos": [{"plugin": p, "error": e} for p, e in fallidos]
    }
    ruta_resumen = os.path.join(carpeta_results, 'resumen_analisis_ram.json')
    with open(ruta_resumen, 'w', encoding='utf-8') as f:
        json.dump(resumen, f, ensure_ascii=False, indent=2)
    log(f"[+] Resumen guardado: {ruta_resumen}")

    # FASE 6: Sellado final
    progress(97, "Sellando cadena de custodia...")
    log("\n[*] 5/6: Verificando integridad post-analisis...")
    hash_post = sha256_file(mem_file)
    integridad_ok = (hash_post == hash_pre)
    custodia_append(ruta_custodia, f"Hash Post-Analisis SHA-256: {hash_post}")
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

    if not os.path.exists(args.archivo):
        print(f"[X] Archivo no encontrado: {args.archivo}")
        sys.exit(1)

    carpeta_caso = os.path.join(CASES_BASE_DIR, args.caso)
    if not os.path.exists(carpeta_caso):
        print(f"[X] Caso '{args.caso}' no existe en {CASES_BASE_DIR}.")
        print("    Abra primero el caso desde la interfaz web.")
        sys.exit(1)

    analizar_ram(args.archivo, args.caso, args.perito)


if __name__ == "__main__":
    if os.geteuid() != 0:
        print("\n[X] Ejecuta como root: sudo python3 03_live_ram.py ...")
        sys.exit(1)
    main()
