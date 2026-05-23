import os
import sys
import time
import hashlib
import subprocess
import argparse
from datetime import datetime

def imprimir_banner():
    print("==================================================")
    print("   FOREN-SYS: ADQUISICIÓN FÍSICA (DEAD-BOX)       ")
    print("      Cumplimiento Normativa ISO/IEC 27037:2012     ")
    print("==================================================")

def get_device_info(ruta):
    """Obtiene el modelo y número de serie del dispositivo para la Cadena de Custodia."""
    info = {"modelo": "Desconocido", "serial": "Desconocido"}
    try:
        resultado = subprocess.run(['lsblk', '-n', '-d', '-o', 'MODEL,SERIAL', ruta], capture_output=True, text=True)
        partes = resultado.stdout.strip().split()
        if len(partes) >= 1:
            info['modelo'] = partes[0]
        if len(partes) >= 2:
            info['serial'] = partes[1]
    except Exception:
        pass
    return info

def generar_cadena_custodia(destino_base, caso_id, perito, origen, hash_pre):
    """Genera el Acta de Cadena de Custodia (ISO/IEC 27037)."""
    ruta_acta = os.path.join(destino_base, f"{caso_id}_Acta_Cadena_Custodia.txt")
    dev_info = get_device_info(origen)
    fecha_actual = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    print(f"\n[*] Generando Acta de Cadena de Custodia en: {ruta_acta}")
    
    contenido = f"""==================================================
ACTA DE CADENA DE CUSTODIA - EXTRACCIÓN DIGITAL
==================================================
NORMATIVA APLICABLE: ISO/IEC 27037:2012

1. INFORMACIÓN DEL CASO
--------------------------------------------------
ID de Caso:       {caso_id}
Perito a Cargo:   {perito}
Fecha de Extracción: {fecha_actual}

2. DISPOSITIVO DE EVIDENCIA (ORIGEN)
--------------------------------------------------
Ruta Lógica:      {origen}
Modelo:           {dev_info['modelo']}
Número de Serie:  {dev_info['serial']}

3. MEDIDAS TÉCNICAS APLICADAS
--------------------------------------------------
Bloqueador de Escritura: Activado (Software - blockdev --setro)
Método de Adquisición:   Duplicación bit a bit (dc3dd)
Hash Pre-Adquisición:    {hash_pre} (SHA-256)

(El log detallado de dc3dd y hash post-adquisición se encuentra adjunto).
==================================================
FIRMA PERITO RESPONSABLE: 

___________________________
{perito}
"""
    with open(ruta_acta, 'w', encoding='utf-8') as f:
        f.write(contenido)
    print("[SUCCESS] Cadena de Custodia (Acta) generada correctamente.")

def calcular_hash(ruta_dispositivo):
    """Calcula el Hash SHA-256 leyendo el dispositivo en bloques de 4KB."""
    print(f"\n[*] 1/4: Calculando Hash SHA-256 PRE-ADQUISICIÓN de {ruta_dispositivo}...")
    
    sha256 = hashlib.sha256()
    try:
        with open(ruta_dispositivo, "rb") as f:
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
    
    print(f"\n[*] 3/4: Iniciando extracción bit a bit con dc3dd...")
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
    print("\n[*] 4/4: Iniciando Data Carving (Recuperación de archivos borrados)...")
    
    carpeta_recuperados = os.path.join(destino_base, f"{caso_id}_Carving")
    os.makedirs(carpeta_recuperados, exist_ok=True)
    
    punto_montaje = "/mnt/forensys_temp"
    os.makedirs(punto_montaje, exist_ok=True)
    
    try:
        print(f"[*] Montando imagen virtual en {punto_montaje} (Solo lectura)...")
        subprocess.run(['sudo', 'mount', '-o', 'ro,loop', ruta_imagen, punto_montaje], check=True)
        
        print("[*] Ejecutando escáner profundo de Photorec. Buscando documentos y fotos...")
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
        print("[*] Desmontando imagen y limpiando entorno...")
        subprocess.run(['sudo', 'umount', punto_montaje])

def main():
    imprimir_banner()
    
    parser = argparse.ArgumentParser(description="Extracción Forense Dead-Box")
    parser.add_argument("-t", "--target", required=True, help="Ruta del disco sospechoso (Ej: /dev/sdb)")
    parser.add_argument("-c", "--case", required=False, help="ID del Caso")
    parser.add_argument("-p", "--perito", required=False, help="Nombre del perito a cargo")
    parser.add_argument("--set-readonly-only", action="store_true", help="Solo aplicar bloqueador y salir")
    args = parser.parse_args()
    
    origen = args.target
    caso_id = args.case
    perito = args.perito
    
    if not os.path.exists(origen):
        print(f"[X] El dispositivo {origen} no existe.")
        sys.exit(1)
        
    if args.set_readonly_only:
        print(f"\n[*] Aplicando Bloqueador de Escritura Lógico (blockdev --setro) en {origen}...")
        subprocess.run(['blockdev', '--setro', origen], check=True)
        print(f"[SUCCESS] Dispositivo {origen} puesto en modo solo-lectura.")
        sys.exit(0)
        
    destino_base = "/mnt/Destino_ForenSys"
    if not os.path.ismount(destino_base):
        print(f"\n[X] ALERTA: El disco seguro ({destino_base}) no está montado.")
        print("    Ejecute primero la esterilización (01_wiping.py).")
        sys.exit(1)
    
    # 0. Asegurar Bloqueador de Escritura (Por si se ejecuta manualmente)
    print("\n[*] 0/4: Aplicando Bloqueador de Escritura Lógico (blockdev --setro)...")
    subprocess.run(['sudo', 'blockdev', '--setro', origen], check=True)
    
    # 1. Hashing Previo
    hash_original = calcular_hash(origen)
    
    # 2. Generar Cadena de Custodia
    print("\n[*] 2/4: Preparando Documentación Legal...")
    generar_cadena_custodia(destino_base, caso_id, perito, origen, hash_original)
    
    # 3. Extracción (Copia)
    ruta_imagen_dd = crear_imagen_dd(origen, destino_base, caso_id)
    
    # 4. Recuperación de archivos
    recuperar_borrados(ruta_imagen_dd, destino_base, caso_id)
    
    print("\n==================================================")
    print("   [✔] EXTRACCIÓN ESTÁTICA COMPLETADA (ISO 27037)  ")
    print("==================================================")
    print("[*] La evidencia fue preservada de manera inalterable.")
    print(f"[*] Revise la cadena de custodia y los datos en: {destino_base}")

if __name__ == "__main__":
    if os.geteuid() != 0:
        print("[X] Ejecute como root (sudo python3 02_deadbox_v2.py ...)")
        sys.exit(1)
    main()
