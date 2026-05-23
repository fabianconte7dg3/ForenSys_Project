import os
import sys
import subprocess

def imprimir_banner():
    print("==================================================")
    print("   FOREN-SYS: ANÁLISIS DINÁMICO DE RAM            ")
    print("==================================================")

def buscar_archivos_ram():
    """Busca archivos de volcado de memoria ignorando la bóveda para no duplicar"""
    rutas_busqueda = ['/media', '/mnt', '/home/ciber-admin']
    archivos_encontrados = []

    print("\n[*] Escaneando USBs y carpetas en busca de evidencias de RAM...")
    for ruta_base in rutas_busqueda:
        if os.path.exists(ruta_base):
            for root, dirs, files in os.walk(ruta_base):
                # Evitamos buscar dentro de la bóveda (SDA) para no confundir al script
                if "/mnt/Destino_ForenSys" in root:
                    continue
                # Limitar a 3 niveles de profundidad
                if root.count(os.sep) - ruta_base.count(os.sep) > 3:
                    del dirs[:]
                for file in files:
                    if file.lower().endswith(('.raw', '.mem', '.dmp')):
                        archivos_encontrados.append(os.path.join(root, file))
    return archivos_encontrados

def seleccionar_archivo():
    """Muestra un menú interactivo para seleccionar el archivo"""
    archivos = buscar_archivos_ram()

    if not archivos:
        print("[!] No se encontraron archivos .raw, .mem o .dmp automáticamente.")
        return input("[?] Ingrese la ruta manual del archivo de RAM: ").strip()

    print("\n--- ARCHIVOS DE MEMORIA ENCONTRADOS ---")
    for i, archivo in enumerate(archivos, 1):
        peso_mb = os.path.getsize(archivo) / (1024 * 1024)
        print(f"[{i}] {archivo} ({peso_mb:.1f} MB)")
    print("[0] Ingresar ruta manualmente")
    print("---------------------------------------")

    while True:
        try:
            opcion = int(input("\n[?] Seleccione el número del archivo a analizar: "))
            if opcion == 0:
                return input("[?] Ingrese la ruta manual del archivo de RAM: ").strip()
            elif 1 <= opcion <= len(archivos):
                return archivos[opcion - 1]
            else:
                print("[X] Opción fuera de rango.")
        except ValueError:
            print("[X] Por favor, ingrese un número.")

def auto_desbloquear_destino(destino_base):
    """Detecta el disco de la bóveda (SDA) y lo desbloquea temporalmente"""
    print("[*] Aplicando Llave Maestra: Asegurando permisos de escritura en la bóveda SDA...")
    try:
        comando_dev = ['findmnt', '-n', '-o', 'SOURCE', destino_base]
        resultado = subprocess.run(comando_dev, capture_output=True, text=True)
        particion_destino = resultado.stdout.strip()
        
        if particion_destino:
            disco_base = particion_destino.rstrip('0123456789')
            # Quitar candado físico
            subprocess.run(['sudo', 'blockdev', '--setrw', disco_base], check=False, stderr=subprocess.DEVNULL)
            subprocess.run(['sudo', 'blockdev', '--setrw', particion_destino], check=False, stderr=subprocess.DEVNULL)
            # Quitar candado de montaje
            subprocess.run(['sudo', 'mount', '-o', 'remount,rw', destino_base], check=False, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"[!] Aviso: No se pudo auto-desbloquear el destino. Error: {e}")

def analizar_ram(ruta_archivo_memoria, destino_base, caso_id):
    print(f"\n[*] Iniciando análisis de memoria volátil para: {caso_id}")
    print(f"[*] Archivo origen: {ruta_archivo_memoria}")

    # 1. Definir la ruta de Volatility 3
    ruta_base_proyecto = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ruta_volatility = os.path.join(ruta_base_proyecto, "volatility3", "vol.py")

    if not os.path.exists(ruta_volatility):
        print(f"\n[X] ALERTA CRÍTICA: No se encontró Volatility 3 en: {ruta_volatility}")
        sys.exit(1)

    # 2. Desbloquear la bóveda SDA antes de intentar crear la carpeta
    auto_desbloquear_destino(destino_base)

    # 3. Preparar el entorno de resultados (Ahora no dará el error "Errno 30")
    carpeta_resultados = os.path.join(destino_base, f"{caso_id}_RAM")
    try:
        os.makedirs(carpeta_resultados, exist_ok=True)
    except OSError as e:
        print(f"\n[X] ERROR FATAL: El disco sigue bloqueado contra escritura ({e}).")
        sys.exit(1)

    ruta_procesos = os.path.join(carpeta_resultados, "ram_procesos.txt")
    ruta_malware = os.path.join(carpeta_resultados, "ram_malware.txt")

    # [X] COMANDO 1: LISTA DE PROCESOS (PsList)
    print("\n[*] 1/2: Extrayendo árbol de procesos activos (windows.pslist.PsList)...")
    try:
        with open(ruta_procesos, "w") as archivo_salida:
            comando_pslist = ['python3', ruta_volatility, '-f', ruta_archivo_memoria, 'windows.pslist.PsList']
            subprocess.run(comando_pslist, stdout=archivo_salida, stderr=subprocess.PIPE, check=True)
        print(f"[+] Lista de procesos guardada en: {ruta_procesos}")
    except subprocess.CalledProcessError as e:
        print(f"\n[X] Fallo al ejecutar PsList: {e.stderr.decode('utf-8', errors='ignore')}")

    # [X] COMANDO 2: BÚSQUEDA DE MALWARE INYECTADO (Malfind) -> Reemplaza a NetScan
    print("\n[*] 2/2: Buscando inyecciones de código malicioso (windows.malfind.Malfind)...")
    try:
        with open(ruta_malware, "w") as archivo_salida:
            comando_malfind = ['python3', ruta_volatility, '-f', ruta_archivo_memoria, 'windows.malfind.Malfind']
            subprocess.run(comando_malfind, stdout=archivo_salida, stderr=subprocess.PIPE, check=True)
        print(f"[+] Reporte de malware generado en: {ruta_malware}")
    except subprocess.CalledProcessError as e:
        print(f"\n[X] Fallo al ejecutar Malfind: {e.stderr.decode('utf-8', errors='ignore')}")

    print("\n==================================================")
    print("   [✔] ANÁLISIS DE RAM COMPLETADO                 ")
    print("==================================================")
    print(f"[*] Los archivos .txt están listos en {carpeta_resultados}")
    print("[*] Quedan a la espera para ser inyectados en la IA (Fase 4).")

def main():
    imprimir_banner()

    destino_base = "/mnt/Destino_ForenSys"
    if not os.path.ismount(destino_base):
        print(f"\n[X] ALERTA: El disco seguro ({destino_base}) no está montado.")
        print("    Ejecute primero la esterilización (01_wiping.py) o el montador (01_b_montar_destino.py).")
        sys.exit(1)

    ruta_ram = seleccionar_archivo()

    if not os.path.exists(ruta_ram):
        print(f"\n[X] ERROR: El archivo {ruta_ram} no existe.")
        sys.exit(1)

    caso_id = input("\n[?] Ingrese el ID del Caso (Ej. CASO_001): ").strip()

    analizar_ram(ruta_ram, destino_base, caso_id)

if __name__ == "__main__":
    if os.geteuid() != 0:
        print("\n[X] Error: Ejecuta como root (sudo python3 03_live_ram.py)")
        sys.exit(1)
    main()
