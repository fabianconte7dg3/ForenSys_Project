import os
import sys
import time
import hashlib
import subprocess

def imprimir_banner():
    print("==================================================")
    print("   FOREN-SYS: ADQUISICIÓN FÍSICA (DEAD-BOX)       ")
    print("==================================================")

def listar_discos():
    print("\n--- DISCOS CONECTADOS ---")
    subprocess.run(['lsblk', '-o', 'NAME,SIZE,MODEL,RO'], check=True)
    # RO = Read Only. Aquí podrás ver si udev bloqueó el USB con éxito (RO=1)
    print("-------------------------\n")

def calcular_hash(ruta_dispositivo):
    """Calcula el Hash SHA-256 puro leyendo el dispositivo en bloques de 4KB."""
    print(f"\n[*] 1/3: Calculando Hash SHA-256 PRE-ADQUISICIÓN de {ruta_dispositivo}...")
    print("[*] (Esto puede tardar dependiendo del tamaño. Paciencia...)")
    
    sha256 = hashlib.sha256()
    try:
        # Leemos en formato binario ('rb')
        with open(ruta_dispositivo, "rb") as f:
            # Leemos en bloques de 4096 bytes para no saturar la RAM
            for bloque in iter(lambda: f.read(4096), b""):
                sha256.update(bloque)
                
        hash_resultado = sha256.hexdigest()
        print(f"[+] HASH ORIGINAL: {hash_resultado}")
        return hash_resultado
    except PermissionError:
        print("\n[X] Permiso denegado. ¡Debes ejecutar el script con sudo!")
        sys.exit(1)
    except FileNotFoundError:
        print(f"\n[X] No se encontró el dispositivo {ruta_dispositivo}.")
        sys.exit(1)

def crear_imagen_dd(origen, destino_base, caso_id):
    """Utiliza dc3dd para crear la imagen física bit a bit."""
    ruta_imagen = os.path.join(destino_base, f"{caso_id}_evidencia.dd")
    ruta_log = os.path.join(destino_base, f"{caso_id}_dc3dd.log")
    
    print(f"\n[*] 2/3: Iniciando extracción bit a bit con dc3dd...")
    print(f"[*] Guardando imagen en: {ruta_imagen}")
    
    comando = [
        'sudo', 'dc3dd',
        f'if={origen}',
        f'of={ruta_imagen}',
        'hash=sha256',
        f'log={ruta_log}'
    ]
    
    try:
        subprocess.run(comando, check=True)
        print("\n[SUCCESS] Imagen RAW/DD generada correctamente.")
        return ruta_imagen
    except subprocess.CalledProcessError as e:
        print(f"\n[X] Error fatal al ejecutar dc3dd: {e}")
        sys.exit(1)

def recuperar_borrados(ruta_imagen, destino_base, caso_id):
    """Monta la imagen y ejecuta Photorec de forma automatizada (Data Carving)."""
    print("\n[*] 3/3: Iniciando Data Carving (Recuperación de archivos borrados)...")
    
    # Preparamos las carpetas
    carpeta_recuperados = os.path.join(destino_base, f"{caso_id}_Carving")
    os.makedirs(carpeta_recuperados, exist_ok=True)
    
    punto_montaje = "/mnt/forensys_temp"
    os.makedirs(punto_montaje, exist_ok=True)
    
    try:
        # Montaje en modo loop y Solo Lectura (ro)
        print(f"[*] Montando imagen virtual en {punto_montaje} (Solo lectura)...")
        subprocess.run(['sudo', 'mount', '-o', 'ro,loop', ruta_imagen, punto_montaje], check=True)
        
        # Ejecución de Photorec en modo CLI (sin menús interactivos)
        print("[*] Ejecutando escáner profundo de Photorec. Buscando documentos y fotos...")
        # Comando estructurado para que no pida confirmación humana
        comando_photorec = [
            'sudo', 'photorec',
            '/d', carpeta_recuperados,
            '/cmd', ruta_imagen,
            'partition_none,options,keep_corrupted_file,no,search'
        ]
        
        subprocess.run(comando_photorec)
        print(f"\n[SUCCESS] Archivos extraídos y guardados en: {carpeta_recuperados}")
        
    except subprocess.CalledProcessError as e:
        print(f"\n[X] Fallo en el montaje o recuperación: {e}")
    finally:
        # Siempre desmontamos la imagen al terminar, incluso si hay error
        print("[*] Desmontando imagen y limpiando entorno...")
        subprocess.run(['sudo', 'umount', punto_montaje])

def main():
    imprimir_banner()
    
    # Validamos que el disco destino esté montado (Fase 1 completada)
    destino_base = "/mnt/Destino_ForenSys"
    if not os.path.ismount(destino_base):
        print(f"\n[X] ALERTA: El disco seguro ({destino_base}) no está montado.")
        print("    Ejecute primero la esterilización (01_wiping.py).")
        sys.exit(1)
        
    listar_discos()
    
    origen = input("[?] Ingrese la ruta del USB SOSPECHOSO (Ej. /dev/sdb): ").strip()
    caso_id = input("[?] Ingrese el ID del Caso (Ej. CASO_001): ").strip()
    
    # --- EJECUCIÓN SECUENCIAL ---
    # 1. Hashing Previo
    hash_original = calcular_hash(origen)
    
    # 2. Extracción (Copia)
    ruta_imagen_dd = crear_imagen_dd(origen, destino_base, caso_id)
    
    # 3. Recuperación de archivos
    recuperar_borrados(ruta_imagen_dd, destino_base, caso_id)
    
    print("\n==================================================")
    print("   [✔] FASE 3: ADQUISICIÓN ESTÁTICA COMPLETADA    ")
    print("==================================================")
    print("[*] El sospechoso fue preservado, copiado y procesado.")
    print(f"[*] Revise la carpeta de Carving en: {destino_base}")

if __name__ == "__main__":
    if os.geteuid() != 0:
        print("[X] Ejecute como root (sudo python3 02_deadbox.py)")
        sys.exit(1)
    main()
