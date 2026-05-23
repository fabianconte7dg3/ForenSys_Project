import os
import sys
import time
import re
import subprocess
import shutil
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

def imprimir_banner():
    print("==================================================")
    print("   FOREN-SYS: ADQUISICIÓN OSINT (WEB / NUBE)      ")
    print("==================================================")

def auto_desbloquear_destino(destino_base):
    """Detecta el disco de la bóveda (SDA) y lo desbloquea temporalmente"""
    print("[*] Aplicando Llave Maestra: Asegurando permisos de escritura en la bóveda SDA...")
    try:
        comando_dev = ['findmnt', '-n', '-o', 'SOURCE', destino_base]
        resultado = subprocess.run(comando_dev, capture_output=True, text=True)
        particion_destino = resultado.stdout.strip()

        if particion_destino:
            disco_base = particion_destino.rstrip('0123456789')
            subprocess.run(['sudo', 'blockdev', '--setrw', disco_base], check=False, stderr=subprocess.DEVNULL)
            subprocess.run(['sudo', 'blockdev', '--setrw', particion_destino], check=False, stderr=subprocess.DEVNULL)
            subprocess.run(['sudo', 'mount', '-o', 'remount,rw', destino_base], check=False, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"[!] Aviso: No se pudo auto-desbloquear el destino. Error: {e}")

def capturar_perfil(url_red_social, carpeta_caso):
    print(f"\n[*] 1/2: Desplegando rastreador fantasma (ARM64 Optimized)...")
    print(f"[*] Objetivo: {url_red_social}")

    # Definición de rutas según tu instalación actual
    ruta_chromedriver = "/usr/bin/chromedriver"
    ruta_chromium = "/usr/bin/chromium"

    # Verificación de existencia de binarios
    if not os.path.exists(ruta_chromedriver):
        ruta_chromedriver = shutil.which('chromedriver')
        if not ruta_chromedriver:
            print("\n[X] ERROR FATAL: No se encuentra 'chromedriver' en /usr/bin/")
            sys.exit(1)

    # Limpieza rigurosa de perfil temporal para evitar conflictos de Root
    user_data_dir = "/tmp/forensys_browser_profile"
    if os.path.exists(user_data_dir):
        shutil.rmtree(user_data_dir, ignore_errors=True)
    os.makedirs(user_data_dir, exist_ok=True)

    # CONFIGURACIÓN DEL NAVEGADOR
    opciones = Options()
    opciones.binary_location = ruta_chromium

    # Argumentos críticos para Raspberry Pi y ejecución como Root
    opciones.add_argument('--headless=new')
    opciones.add_argument('--no-sandbox')
    opciones.add_argument('--disable-dev-shm-usage')
    opciones.add_argument('--disable-gpu')
    opciones.add_argument(f'--user-data-dir={user_data_dir}')
    opciones.add_argument('--remote-debugging-port=9222')
    
    # User-Agent de Linux Real para evadir detección de bots en Instagram
    opciones.add_argument("user-agent=Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

    archivo_html = os.path.join(carpeta_caso, "evidencia_nube.html")

    try:
        # Forzamos el uso del ejecutable específico
        servicio = Service(executable_path=ruta_chromedriver)
        driver = webdriver.Chrome(service=servicio, options=opciones)

        print("[*] Conexión establecida. Extrayendo datos dinámicos...")
        driver.get(url_red_social)

        # Espera de 10 segundos: Instagram tarda en cargar los perfiles vía React
        time.sleep(10)

        codigo_fuente = driver.page_source

        with open(archivo_html, 'w', encoding='utf-8') as f:
            f.write(codigo_fuente)

        print(f"[+] [ÉXITO] Código fuente preservado en la bóveda.")
        driver.quit()
        return archivo_html

    except Exception as e:
        print(f"\n[X] Error crítico en Selenium: {e}")
        sys.exit(1)

def extraer_ids(html_path, carpeta_caso):
    print("\n[*] 2/2: Iniciando autopsia del código fuente (BS4 + Regex)...")
    archivo_reporte = os.path.join(carpeta_caso, "reporte_osint.txt")

    try:
        with open(html_path, 'r', encoding='utf-8') as f:
            html_content = f.read()

        soup = BeautifulSoup(html_content, 'html.parser')
        titulo = soup.title.string if soup.title else "Sin Título detectable"

        # Regex mejorado para capturar IDs de Instagram (logging_page_id, profile_id, etc)
        patron_ids = r'(?i)("profile_id"|"userid"|"id_str"|"actorid"|"target_id"|"entity_id")\s*[:=]\s*["\']?(\d+)["\']?'
        ids_encontrados = re.findall(patron_ids, html_content)
        ids_unicos = list(set(ids_encontrados))

        with open(archivo_reporte, 'w', encoding='utf-8') as f:
            f.write("==================================================\n")
            f.write("        REPORTE OSINT - FOREN-SYS CLOUD           \n")
            f.write("==================================================\n\n")
            f.write(f"[*] Meta-Título: {titulo}\n")
            f.write(f"[*] Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")

            if ids_unicos:
                f.write("[!] IDENTIFICADORES NUMÉRICOS ENCONTRADOS:\n")
                for etiqueta, valor in ids_unicos:
                    f.write(f"    -> {etiqueta.strip('\"')} = {valor}\n")
            else:
                f.write("[-] No se detectaron identificadores numéricos en el HTML superficial.\n")

        print(f"[+] [ÉXITO] Análisis completado. Reporte: {archivo_reporte}")

    except Exception as e:
        print(f"\n[X] Error en el análisis forense: {e}")

def main():
    imprimir_banner()

    destino_base = "/mnt/Destino_ForenSys"
    if not os.path.ismount(destino_base):
        print(f"\n[X] ERROR: La bóveda ({destino_base}) no está montada.")
        sys.exit(1)

    auto_desbloquear_destino(destino_base)

    caso_id = input("\n[?] ID del Caso (Ej. CASO_006): ").strip()
    url_objetivo = input("[?] URL del Perfil Objetivo: ").strip()

    if not url_objetivo.startswith("http"):
        print("[!] Error: La URL debe incluir http:// o https://")
        sys.exit(1)

    carpeta_caso = os.path.join(destino_base, f"{caso_id}_OSINT")
    os.makedirs(carpeta_caso, exist_ok=True)

    ruta_html = capturar_perfil(url_objetivo, carpeta_caso)
    extraer_ids(ruta_html, carpeta_caso)

    print("\n==================================================")
    print("   [✔] PROCESO FINALIZADO CON ÉXITO               ")
    print("==================================================")

if __name__ == "__main__":
    if os.geteuid() != 0:
        print("\n[X] Error: Este script requiere privilegios de Root (sudo).")
        sys.exit(1)
    main()
