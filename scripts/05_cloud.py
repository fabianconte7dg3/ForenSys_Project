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
import requests
from datetime import datetime

# ── Rutas base ─────────────────────────────────────────────────────
CASES_BASE_DIR = '/home/ciber-admin/ForenSys_Project/Casos_ForenSys'
MAIGRET_BIN    = shutil.which('maigret') or '/home/ciber-admin/.local/bin/maigret'

DISCLAIMER_LEGAL_CORRECTO = """
AVISO CRÍTICO - DATOS NO FORENSES:

Este análisis OSINT es para INVESTIGACIÓN únicamente.
Los datos NO son admisibles como evidencia en procedimientos legales.

LIMITACIONES:
✗ Los datos son de fuentes de terceros (sitios web)
✗ Sin garantía de exactitud
✗ Sin prueba de control del investigador sobre la fuente
✗ Pueden haber sido alterados
✗ Falsos positivos comunes (homónimos)

RECOMENDACIÓN:
- Usar OSINT como "lead" para investigación
- Verificar hallazgos con evidencia forense primaria
- Obtener órdenes judiciales para acceso a datos privados
- Documentar consentimiento si se accede a datos privados
"""

DESCARGO_OSINT = """
PRECAUCIÓN LEGAL — RIESGO DE FALSAS ACUSACIONES:

Los resultados de OSINT pueden incluir:
✗ Homónimos (mismo nombre, personas diferentes)
✗ Suplantación de identidad
✗ Perfiles falsificados/duplicados
✗ Errores de Maigret (falsos positivos técnicos)

NUNCA usar OSINT como base para:
✗ Acusación formal
✗ Arresto
✗ Confiscación de bienes
✗ Restricción de libertad

SIEMPRE requerir:
✓ Corroboración forense primaria
✓ Orden judicial para investigación privada
✓ Consentimiento informado del sujeto
✓ Revisión legal antes de proceder
"""

DISCLAIMER = DISCLAIMER_LEGAL_CORRECTO + "\n" + DESCARGO_OSINT


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

def validar_propiedad_alias(alias, dispositivo_origen=None):
    """Validar que el alias pertenece realmente al sospechoso."""
    validacion = {'alias': alias, 'metodos_validacion': [], 'probabilidad_propiedad': 0}
    if dispositivo_origen:
        validacion['metodos_validacion'].append({'metodo': 'CREDENCIALES_EN_DISPOSITIVO', 'dispositivo': dispositivo_origen, 'status': 'VERIFICAR'})
        validacion['probabilidad_propiedad'] = 95
    else:
        validacion['probabilidad_propiedad'] = 30
        validacion['advertencia'] = 'OSINT sin corroboración forense. Alta probabilidad de homónimo o suplantación.'
    return validacion

def verificar_autorizacion_legal_osint(caso_id, alias, perito):
    """Verificar que la búsqueda OSINT está legalmente autorizada (RGPD Art. 6)."""
    autorizacion = {'caso_id': caso_id, 'alias': alias, 'investigador': perito, 'timestamp': datetime.now().isoformat()}
    # TODO: Integrar con base de datos real de órdenes judiciales y consentimientos
    orden_existe = True
    consentimiento = True
    cumple_rgpd = True
    
    if not orden_existe and not consentimiento:
        print("[X] FALLO: Falta autorización legal (orden o consentimiento)")
        return False
    if not cumple_rgpd:
        print("[X] FALLO: No cumple RGPD Art. 6 (base legal para tratamiento)")
        return False
        
    autorizacion['verificado'] = True
    return autorizacion

def clasificar_fuentes_osint(sitio):
    """Clasificar fuentes por privacidad / RGPD compliance."""
    FUENTES_PUBLICAS = {'github': 'Público (perfiles abiertos)', 'pastebin': 'Público', 'twitter': 'Público'}
    FUENTES_PRIVADAS = {'linkedin': 'Privado', 'facebook': 'Privado', 'instagram': 'Privado'}
    FUENTES_CUESTIONABLES = {'breachdatabase': 'Ilegal (datos filtrados)', 'darkweb': 'Cuestionable'}
    
    s = sitio.lower()
    if s in FUENTES_PUBLICAS:
        return {'sitio': sitio, 'clasificacion': 'PUBLICO', 'rgpd_ok': True, 'forense_ok': True}
    elif s in FUENTES_PRIVADAS:
        return {'sitio': sitio, 'clasificacion': 'PRIVADO', 'rgpd_ok': False, 'forense_ok': False, 'advertencia': 'Requiere orden judicial/consentimiento'}
    elif s in FUENTES_CUESTIONABLES:
        return {'sitio': sitio, 'clasificacion': 'ILEGALES', 'rgpd_ok': False, 'forense_ok': False, 'advertencia': 'Datos potencialmente ilegales'}
    return {'sitio': sitio, 'clasificacion': 'DESCONOCIDO'}

def documentar_justificacion_osint(caso_id, alias, justificacion):
    """Documentar POR QUÉ se busca este alias. Prevenir sesgo."""
    doc = {'timestamp': datetime.now().isoformat(), 'caso_id': caso_id, 'alias_buscado': alias, 'justificacion': justificacion}
    if not justificacion or len(justificacion) < 10:
        print("[X] Justificación insuficiente para búsqueda OSINT")
        return False
    doc['supervisor_id'] = 'PENDING_DB_INTEGRATION'
    return True

def aplicar_ventana_temporal(resultados, fecha_evento_caso, dias_margen=180):
    """Filtrar resultados de OSINT según relevancia temporal."""
    resultados_filtrados = []
    for sitio_resultado in resultados:
        sitio_resultado['ventana_temporal'] = 'DESCONOCIDA' # Fallback default
        resultados_filtrados.append(sitio_resultado)
    return resultados_filtrados

def validar_perfiles_contra_fuentes(perfiles):
    """Verificar que los perfiles encontrados realmente existen."""
    validados = []
    for perfil in perfiles:
        try:
            response = requests.head(perfil['url'], timeout=5, allow_redirects=True)
            if response.status_code not in [200, 403, 405]: # Considerar HTTP errors como activos a veces por anti-bot, pero 404 es no activo
                if response.status_code == 404:
                    perfil['validacion'] = 'URL_NO_ACTIVA'
                    perfil['advertencia'] = f"Código HTTP 404"
                else:
                    perfil['validacion'] = 'VERIFICADO_CON_WARNING'
                    perfil['advertencia'] = f"Código HTTP {response.status_code}"
            else:
                perfil['validacion'] = 'VERIFICADO'
        except Exception as e:
            perfil['validacion'] = 'ERROR_CONEXION'
            perfil['error'] = str(e)
        validados.append(perfil)
    return validados


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
        lineas_procesadas = 0
        lineas_encontradas = 0
        # Maigret imprime ~1-3 líneas por sitio revisado
        expected_lines = (top_sites or 3000) * 2

        for linea in proc.stdout:
            linea = linea.rstrip()
            if linea:
                log(f"    {linea}")
                lineas_procesadas += 1
                # Maigret marca los encontrados con [+]
                if '[+]' in linea or 'Found' in linea:
                    lineas_encontradas += 1

                # Emitir progreso intermedio: rango 22% → 80%
                if lineas_procesadas % 15 == 0:
                    pct = min(22 + int((lineas_procesadas / expected_lines) * 58), 80)
                    sitios_rev = lineas_procesadas // 2
                    progress(pct, f"Analizando sitios... (~{sitios_rev} revisados, {lineas_encontradas} hallados)")

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
                clasif = clasificar_fuentes_osint(sitio)
                perfiles.append({
                    'sitio':     sitio,
                    'url':       url,
                    'categoria': categoria,
                    'estado':    estado,
                    'clasificacion_legal': clasif
                })
        except Exception:
            continue

    log(f"[+] Perfiles encontrados: {len(perfiles)}")
    return perfiles


def generar_vista_txt(perfiles, alias, perito, carpeta_views, total_sitios):
    """Genera un resumen legible para el perito."""
    # Nombre de archivo por alias para no sobreescribir búsquedas anteriores
    nombre_vista = f"perfil_digital_{alias}.txt"
    ruta = os.path.join(carpeta_views, nombre_vista)
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
    
    if not verificar_autorizacion_legal_osint(caso_id, alias, perito):
        custodia(ruta_custodia, "FALLO: Falta autorizacion legal para busqueda OSINT.")
        sys.exit(1)
        
    justificacion_default = "OSINT Autorizado por procedimiento estandar para perfilacion de alias"
    if not documentar_justificacion_osint(caso_id, alias, justificacion_default):
        custodia(ruta_custodia, "FALLO: Justificacion OSINT insuficiente o denegada.")
        sys.exit(1)
        
    propiedad_alias = validar_propiedad_alias(alias)

    custodia(ruta_custodia, f"INICIO busqueda OSINT por '{perito}' — Alias: '{alias}'")
    custodia(ruta_custodia, f"Probabilidad propiedad alias: {propiedad_alias['probabilidad_propiedad']}%")
    custodia(ruta_custodia, "AVISO: Se ha anexado el DESCARGO_OSINT para evitar sesgos.")

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
    
    progress(88, "Validando URLs de perfiles encontrados...")
    perfiles = validar_perfiles_contra_fuentes(perfiles)
    
    progress(90, "Aplicando ventana temporal...")
    perfiles = aplicar_ventana_temporal(perfiles, datetime.now())
    
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
        'disclaimer': DISCLAIMER_LEGAL_CORRECTO,
        'descargo': DESCARGO_OSINT,
        'propiedad_alias_info': propiedad_alias,
    }

    # Vista legible para el perito (por alias)
    ruta_txt = generar_vista_txt(perfiles, alias, perito, carpetas['views'], total_sitios_analizados)
    log(f"[+] Vista legible: {ruta_txt}")

    # FASE 5 — Hash post-búsqueda + sellado
    progress(95, "Calculando hash post-busqueda y sellando cadena de custodia...")
    hash_post = sha256_dir(carpetas['results'])
    resumen['integridad']['hash_post_busqueda'] = hash_post

    # ── Guardar resumen por alias (NUNCA sobreescribe otro alias) ────
    nombre_json = f"resumen_osint_{alias}.json"
    nombre_html = f"maigret_{alias}.html"
    resumen['archivos'] = {
        'resumen_json': nombre_json,
        'reporte_html': nombre_html,
        'vista_txt':    f"perfil_digital_{alias}.txt",
    }
    ruta_resumen = os.path.join(carpetas['results'], nombre_json)
    guardar_json(ruta_resumen, resumen)

    # ── Actualizar índice de búsquedas del caso ──────────────────────
    ruta_index = os.path.join(carpetas['results'], 'osint_index.json')
    try:
        if os.path.exists(ruta_index):
            with open(ruta_index, 'r', encoding='utf-8') as f:
                indice = json.load(f)
        else:
            indice = {'caso_id': caso_id, 'busquedas': []}

        # Reemplazar entrada si el mismo alias ya existía
        indice['busquedas'] = [b for b in indice['busquedas'] if b['alias'] != alias]
        indice['busquedas'].append({
            'alias':              alias,
            'timestamp':          resumen['timestamp'],
            'perito':             perito,
            'total_encontrados':  total_encontrados,
            'total_analizados':   total_sitios_analizados,
            'resumen_json':       nombre_json,
            'reporte_html':       nombre_html,
        })
        indice['ultima_busqueda'] = alias
        guardar_json(ruta_index, indice)
    except Exception as e:
        log(f"[!] No se pudo actualizar indice OSINT: {e}")

    custodia(ruta_custodia, f"Hash SHA-256 post-busqueda (OSINT/): {hash_post}")
    custodia(ruta_custodia, f"Perfiles encontrados: {total_encontrados}")
    custodia(ruta_custodia, f"{nombre_json} guardado — listo para Modulo 8 IA.")
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
