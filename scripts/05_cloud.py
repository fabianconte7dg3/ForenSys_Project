#!/usr/bin/env python3
"""
05_cloud.py — OSINT: Rastreo de Alias en Internet (Maigret)
Busca un username en +3000 sitios web y construye un perfil digital.
Cumplimiento: ISO/IEC 27037:2012

Uso:
    python3 05_cloud.py --alias john_doe --caso CASO-001 --perito "Juan Perez"
    python3 05_cloud.py --alias john_doe --caso CASO-001 --perito "Juan Perez" --top 500
"""
import os
import sys
import json
import shutil
import hashlib
import argparse
import subprocess
from datetime import datetime

# ── Rutas base ─────────────────────────────────────────────────────
CASES_BASE_DIR = '/home/ciber-admin/ForenSys_Project/Casos_ForenSys'
MAIGRET_BIN    = shutil.which('maigret') or '/home/ciber-admin/.local/bin/maigret'

DISCLAIMER = (
    "AVISO LEGAL: Los datos recopilados provienen exclusivamente de fuentes de "
    "acceso publico en Internet. Esta busqueda se realiza en el marco de una "
    "investigacion forense autorizada. El operador es responsable del cumplimiento "
    "de la normativa vigente de proteccion de datos (RGPD / LOPDGDD)."
)


# ══════════════════════════════════════════════════════════════════
# Utilidades generales
# ══════════════════════════════════════════════════════════════════

def log(msg):
    print(msg, flush=True)


def progress(pct, detail):
    print(f"[PROGRESO:{pct}] {detail}", flush=True)


def sha256_dir(dirpath):
    """Hash SHA-256 compuesto de todo un directorio."""
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
        f.write(f"[{ts}] [OSINT] {msg}\n")


def guardar_json(ruta, datos):
    with open(ruta, 'w', encoding='utf-8') as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)


def preparar_carpetas(caso_id):
    base = os.path.join(CASES_BASE_DIR, caso_id)
    carpetas = {
        'images':   os.path.join(base, '01_Images_(Fuentes_de_datos)', 'OSINT'),
        'views':    os.path.join(base, '02_Views_(Vistas)', 'OSINT'),
        'results':  os.path.join(base, '03_Results_(Resultados_Extraidos)', 'OSINT'),
        'custodia': os.path.join(base, 'cadena_custodia.log'),
    }
    for k, v in carpetas.items():
        if k != 'custodia':
            os.makedirs(v, exist_ok=True)
    return carpetas


def sanitizar_alias(alias):
    """Elimina caracteres peligrosos del alias para evitar inyeccion de comandos."""
    return ''.join(c for c in alias if c.isalnum() or c in ('-', '_', '.'))


# ══════════════════════════════════════════════════════════════════
# LÓGICA MAIGRET
# ══════════════════════════════════════════════════════════════════

def verificar_maigret():
    """Verifica que maigret esté instalado y accesible."""
    if not MAIGRET_BIN or not os.path.exists(MAIGRET_BIN):
        log("[X] Maigret no encontrado en el sistema.")
        log("    Instalar con: pip3 install maigret --break-system-packages")
        return False
    try:
        r = subprocess.run([MAIGRET_BIN, '--version'],
                           capture_output=True, text=True, timeout=10)
        version = r.stdout.strip().split('\n')[0] if r.returncode == 0 else 'desconocida'
        log(f"[+] Maigret disponible: {version}")
        return True
    except Exception as e:
        log(f"[X] Error verificando Maigret: {e}")
        return False


def ejecutar_maigret(alias, carpeta_tmp, top_sites=None):
    """
    Ejecuta maigret en modo JSON + HTML.
    - Salida JSON:  <carpeta_tmp>/<alias>.json
    - Salida HTML:  <carpeta_tmp>/<alias>.html
    Retorna (ruta_json, ruta_html, returncode).
    """
    cmd = [
        MAIGRET_BIN,
        alias,
        '--folderoutput', carpeta_tmp,
        '-J', 'simple',       # JSON simple — el mas compatible con nuestro parser
        '-H',                  # HTML report
        '--no-color',
        '--no-autoupdate',
    ]

    if top_sites:
        cmd += ['--top-sites', str(top_sites)]

    log(f"[*] Comando: {' '.join(cmd)}")

    # Ejecutamos mostrando salida en tiempo real (stream)
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        lineas_encontradas = 0
        for linea in proc.stdout:
            linea = linea.rstrip()
            if linea:
                log(f"    {linea}")
                # Maigret marca los encontrados con [+]
                if '[+]' in linea or 'Found' in linea:
                    lineas_encontradas += 1
        proc.wait()
        rc = proc.returncode
    except FileNotFoundError:
        log(f"[X] Maigret no encontrado en: {MAIGRET_BIN}")
        return None, None, -1
    except Exception as e:
        log(f"[X] Error ejecutando Maigret: {e}")
        return None, None, -1

    # Buscar archivos de salida generados por Maigret
    ruta_json = None
    ruta_html = None
    for fname in os.listdir(carpeta_tmp):
        fpath = os.path.join(carpeta_tmp, fname)
        if fname.endswith('.json') and alias.lower() in fname.lower():
            ruta_json = fpath
        if fname.endswith('.html') and alias.lower() in fname.lower():
            ruta_html = fpath

    return ruta_json, ruta_html, rc


def parsear_resultados(ruta_json, alias):
    """
    Parsea el JSON de Maigret y extrae los perfiles encontrados.
    Retorna una lista de dicts normalizados.
    """
    if not ruta_json or not os.path.exists(ruta_json):
        log("[!] No se genero archivo JSON de Maigret. Puede que el alias no haya sido encontrado.")
        return []

    try:
        with open(ruta_json, 'r', encoding='utf-8') as f:
            datos = json.load(f)
    except Exception as e:
        log(f"[!] Error leyendo JSON de Maigret: {e}")
        return []

    perfiles = []
    # Estructura del JSON de maigret -J simple:
    # { "sitio": { "status": {"status": "Claimed"}, "url_user": "...", "site": {...} } }
    for sitio, info in datos.items():
        try:
            status = info.get('status', {})
            estado = status.get('status', 'Unknown')
            if estado == 'Claimed':
                url = info.get('url_user', '')
                categoria = info.get('site', {}).get('tags', ['Sin categoria'])
                if isinstance(categoria, list):
                    categoria = ', '.join(categoria)
                perfiles.append({
                    'sitio':     sitio,
                    'url':       url,
                    'categoria': categoria,
                    'estado':    estado,
                })
        except Exception:
            continue

    log(f"[+] Perfiles encontrados: {len(perfiles)}")
    return perfiles


def generar_vista_txt(perfiles, alias, perito, carpeta_views, total_sitios):
    """Genera un resumen legible para el perito."""
    ruta = os.path.join(carpeta_views, 'perfil_digital.txt')
    with open(ruta, 'w', encoding='utf-8') as f:
        f.write("=" * 60 + "\n")
        f.write("    FOREN-SYS — PERFIL DIGITAL OSINT\n")
        f.write("    ISO/IEC 27037:2012\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"  Alias buscado:          {alias}\n")
        f.write(f"  Perito:                 {perito}\n")
        f.write(f"  Fecha:                  {datetime.now().isoformat()}\n")
        f.write(f"  Sitios analizados:      {total_sitios}\n")
        f.write(f"  Perfiles encontrados:   {len(perfiles)}\n\n")
        f.write("-" * 60 + "\n")
        f.write("  SITIOS DONDE SE ENCONTRÓ EL ALIAS:\n")
        f.write("-" * 60 + "\n\n")
        if perfiles:
            for p in perfiles:
                f.write(f"  [{p['categoria']}] {p['sitio']}\n")
                f.write(f"    URL: {p['url']}\n\n")
        else:
            f.write("  No se encontraron perfiles publicos con este alias.\n\n")
        f.write("=" * 60 + "\n")
        f.write(f"\n{DISCLAIMER}\n")
    return ruta


# ══════════════════════════════════════════════════════════════════
# FLUJO PRINCIPAL
# ══════════════════════════════════════════════════════════════════

def buscar_osint(alias, caso_id, perito, top_sites):
    log("=" * 50)
    log("   FOREN-SYS: OSINT — RASTREO DE ALIAS           ")
    log("   Maigret (+3000 sitios)  —  ISO/IEC 27037       ")
    log("=" * 50)
    log(f"\n[*] Alias objetivo: {alias}")
    log(f"[*] Caso:           {caso_id}")
    log(f"[*] Perito:         {perito}")
    if top_sites:
        log(f"[*] Modo rapido:    Top {top_sites} sitios (Alexa)")
    else:
        log("[*] Modo completo:  +3000 sitios")
    log(f"\n[!] {DISCLAIMER}\n")

    carpetas = preparar_carpetas(caso_id)
    ruta_custodia = carpetas['custodia']

    custodia(ruta_custodia, f"INICIO busqueda OSINT por '{perito}' — Alias: '{alias}'")
    custodia(ruta_custodia, DISCLAIMER)

    # FASE 1 — Verificar Maigret
    progress(5, "Verificando disponibilidad de Maigret...")
    if not verificar_maigret():
        custodia(ruta_custodia, "FALLO: Maigret no disponible.")
        sys.exit(1)

    # FASE 2 — Hash pre-búsqueda + cadena de custodia
    progress(10, "Registrando estado inicial en cadena de custodia...")
    dir_listado = os.listdir(carpetas['results'])
    hash_pre = sha256_dir(carpetas['results']) if dir_listado else 'DIRECTORIO_VACIO_PRE'
    custodia(ruta_custodia, f"Hash SHA-256 pre-busqueda (OSINT/): {hash_pre}")
    custodia(ruta_custodia, f"Maigret iniciado — alias: '{alias}' — top_sites: {top_sites or 'ALL'}")

    # FASE 3 — Ejecutar Maigret (la fase más larga)
    progress(20, f"Ejecutando Maigret — rastreando '{alias}' en sitios web...")
    log(f"\n[*] Iniciando rastreo. Esto puede tardar entre 2 y 10 minutos...")
    log("[*] Los perfiles encontrados se mostrarán en tiempo real:\n")

    # Carpeta temporal de trabajo de Maigret
    carpeta_tmp = os.path.join(carpetas['results'], '_maigret_tmp')
    os.makedirs(carpeta_tmp, exist_ok=True)

    ruta_json, ruta_html, rc = ejecutar_maigret(alias, carpeta_tmp, top_sites)

    if rc != 0 and rc != -1:
        log(f"[!] Maigret terminó con código {rc} — pueden existir resultados parciales.")
        custodia(ruta_custodia, f"Maigret terminó con codigo {rc} (parcial).")
    elif rc == 0:
        log("\n[+] Maigret completó la búsqueda exitosamente.")
        custodia(ruta_custodia, "Maigret: busqueda completada.")

    # Mover archivos a carpetas del caso
    if ruta_json and os.path.exists(ruta_json):
        destino_json = os.path.join(carpetas['results'], f"maigret_{alias}.json")
        shutil.move(ruta_json, destino_json)
        ruta_json = destino_json

    if ruta_html and os.path.exists(ruta_html):
        destino_html = os.path.join(carpetas['images'], f"maigret_{alias}.html")
        shutil.move(ruta_html, destino_html)

    # Limpiar tmp
    shutil.rmtree(carpeta_tmp, ignore_errors=True)

    # FASE 4 — Parsear y generar resumen
    progress(85, "Parseando resultados y generando resumen forense...")
    log("\n[*] Procesando resultados de Maigret...")

    perfiles = parsear_resultados(ruta_json, alias)
    total_encontrados = len(perfiles)

    # Estimar total de sitios analizados
    total_sitios_analizados = top_sites if top_sites else 3000

    # Resumen JSON para Módulo 8 (IA)
    resumen = {
        'caso_id':                 caso_id,
        'perito':                  perito,
        'timestamp':               datetime.now().isoformat(),
        'alias_buscado':           alias,
        'tipo_analisis':           'OSINT_USERNAME',
        'normas':                  ['ISO/IEC 27037:2012'],
        'herramienta':             f'Maigret {subprocess.run([MAIGRET_BIN, "--version"], capture_output=True, text=True).stdout.strip().split(chr(10))[0]}',
        'total_sitios_analizados': total_sitios_analizados,
        'total_perfiles_encontrados': total_encontrados,
        'perfiles':                perfiles,
        'integridad': {
            'hash_pre_busqueda':  hash_pre,
            'hash_post_busqueda': '',  # se calcula abajo
        },
        'rutas': {
            'resultados': carpetas['results'],
            'imagenes':   carpetas['images'],
            'vistas':     carpetas['views'],
        },
        'disclaimer': DISCLAIMER,
    }

    # Vista legible para el perito
    ruta_txt = generar_vista_txt(perfiles, alias, perito, carpetas['views'], total_sitios_analizados)
    log(f"[+] Vista legible: {ruta_txt}")

    # FASE 5 — Hash post-búsqueda + sellado
    progress(95, "Calculando hash post-busqueda y sellando cadena de custodia...")
    hash_post = sha256_dir(carpetas['results'])
    resumen['integridad']['hash_post_busqueda'] = hash_post

    ruta_resumen = os.path.join(carpetas['results'], 'resumen_osint.json')
    guardar_json(ruta_resumen, resumen)

    custodia(ruta_custodia, f"Hash SHA-256 post-busqueda (OSINT/): {hash_post}")
    custodia(ruta_custodia, f"Perfiles encontrados: {total_encontrados}")
    custodia(ruta_custodia, f"resumen_osint.json guardado — listo para Modulo 8 IA.")
    custodia(ruta_custodia, f"FIN busqueda OSINT — alias: '{alias}'")

    # Resultado final
    progress(100, "Rastreo OSINT completado.")
    log("\n" + "=" * 50)
    log("   [SUCCESS] OSINT COMPLETADO                     ")
    log("=" * 50)
    log(f"[*] Alias rastreado:     {alias}")
    log(f"[*] Sitios analizados:   {total_sitios_analizados}")
    log(f"[*] Perfiles hallados:   {total_encontrados}")
    log(f"[*] Resultados en:       {carpetas['results']}")
    log(f"[*] Reporte HTML en:     {carpetas['images']}")
    log(f"[*] Cadena custodia:     {ruta_custodia}")
    log("[*] Listo para Triaje IA (Modulo 8).")

    if total_encontrados > 0:
        log(f"\n[*] Top hallazgos:")
        for p in perfiles[:10]:
            log(f"    [+] [{p['categoria']}] {p['sitio']} — {p['url']}")
        if total_encontrados > 10:
            log(f"    ... y {total_encontrados - 10} mas. Ver resumen_osint.json para el listado completo.")


# ══════════════════════════════════════════════════════════════════
# PUNTO DE ENTRADA
# ══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="OSINT: Rastreo de alias en +3000 sitios (Maigret) — ISO/IEC 27037"
    )
    parser.add_argument('-a', '--alias',   required=True,
                        help='Nombre de usuario / alias a rastrear')
    parser.add_argument('-c', '--caso',    required=True,
                        help='ID del caso forense (ej: CASO-001)')
    parser.add_argument('-p', '--perito',  required=True,
                        help='Nombre del perito a cargo')
    parser.add_argument('-t', '--top',     type=int, default=None,
                        help='Limitar a N sitios top por Alexa (ej: 500). Sin este flag = todos los sitios.')
    args = parser.parse_args()

    # Sanitizar alias
    alias_seguro = sanitizar_alias(args.alias)
    if not alias_seguro:
        print("[X] El alias contiene caracteres invalidos.")
        sys.exit(1)
    if alias_seguro != args.alias:
        print(f"[!] Alias sanitizado: '{args.alias}' -> '{alias_seguro}'")

    # Verificar caso
    carpeta_caso = os.path.join(CASES_BASE_DIR, args.caso)
    if not os.path.exists(carpeta_caso):
        print(f"[X] Caso '{args.caso}' no existe. Crea el caso desde la interfaz web primero.")
        sys.exit(1)

    buscar_osint(alias_seguro, args.caso, args.perito, args.top)


if __name__ == "__main__":
    main()
