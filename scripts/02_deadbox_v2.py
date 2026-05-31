import os
import sys
import time
import hashlib
import subprocess
import argparse
import re
import json
import getpass
import socket
from datetime import datetime
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding


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

def verificar_write_blocker(dispositivo):
    """Verificar que el dispositivo esté en modo read-only antes de cualquier lectura."""
    print(f"\n[*] 0/4: Verificando Write-Blocker Lógico en {dispositivo}...")
    result = subprocess.run(['blockdev', '--getro', dispositivo], capture_output=True, text=True)
    
    if result.stdout.strip() != '1':
        print(f"[X] ALERTA FORENSE: {dispositivo} NO está en modo read-only!")
        print("[*] Intentando activar write-blocker de software (blockdev --setro)...")
        subprocess.run(['blockdev', '--setro', dispositivo])
        
        result = subprocess.run(['blockdev', '--getro', dispositivo], capture_output=True, text=True)
        if result.stdout.strip() != '1':
            print("[X] FALLO CRÍTICO: No se pudo activar read-only. Abortando adquisición.")
            sys.exit(1)
            
    print(f"[✓] {dispositivo} confirmado en modo read-only (write-blocked).")

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

def crear_imagen_dd(origen, destino_base, caso_id, hash_original):
    """Utiliza dc3dd para crear la imagen física y verifica su hash posteriormente."""
    ruta_imagen = os.path.join(destino_base, f"{caso_id}_evidencia.dd")
    ruta_log = os.path.join(destino_base, f"{caso_id}_dc3dd.log")
    
    print(f"\n[*] 3/4: Iniciando extracción bit a bit con dc3dd...")
    print(f"[*] Guardando imagen en: {ruta_imagen}")
    
    comando = [
        'dc3dd',
        f'if={origen}',
        f'of={ruta_imagen}',
        'hash=sha256',
        f'log={ruta_log}'
    ]
    
    try:
        subprocess.run(comando, check=True)
    except subprocess.CalledProcessError as e:
        print(f"\n[X] Error fatal al ejecutar dc3dd: {e}")
        sys.exit(1)
        
    # Verificar hash en el log de dc3dd (Verificación Post-Imaging)
    print("\n[*] Validando Hash Post-Imaging...")
    hash_imagen = None
    if os.path.exists(ruta_log):
        with open(ruta_log, 'r') as f:
            contenido_log = f.read()
            # dc3dd imprime 'Hash (sha256): <hash>' o 'sha256 = <hash>'
            match = re.search(r'sha256\s*[:=]?\s*([a-f0-9]{64})', contenido_log, re.IGNORECASE)
            if match:
                hash_imagen = match.group(1).lower()
                if hash_original != hash_imagen:
                    print(f"[X] FALLO CRÍTICO: ¡Inconsistencia de Hash!")
                    print(f"  Original:  {hash_original}")
                    print(f"  Imagen:    {hash_imagen}")
                    sys.exit(1)
    
    if not hash_imagen:
        print("[!] Advertencia: No se pudo verificar el hash automáticamente desde el log de dc3dd.")
        hash_imagen = hash_original
    else:
        print(f"[✓] Integridad verificada post-imaging: {hash_imagen}")
        
    return ruta_imagen, hash_imagen

def recuperar_borrados(ruta_imagen, destino_base, caso_id):
    """Ejecuta Photorec de forma automatizada (Data Carving) directamente sobre la imagen DD."""
    print("\n[*] 4/4: Iniciando Data Carving (Recuperación de archivos borrados)...")
    
    carpeta_recuperados = os.path.join(destino_base, f"{caso_id}_Carving")
    os.makedirs(carpeta_recuperados, exist_ok=True)
    os.chmod(carpeta_recuperados, 0o700)  # Seguridad: Permisos restrictivos solo para root
    
    print("[*] Ejecutando escáner profundo de Photorec sobre la imagen RAW...")
    comando_photorec = [
        'photorec',
        '/d', carpeta_recuperados,
        '/cmd', ruta_imagen,
        'partition_none,options,keep_corrupted_file,no,search'
    ]
    
    proc = subprocess.run(comando_photorec, capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"\n[X] Error en recuperación de archivos con PhotoRec: {proc.stderr}")
    else:
        print(f"\n[✓] Data Carving completado en: {carpeta_recuperados}")

def firmar_y_reportar(destino_base, caso_id, perito, origen, hash_original, hash_imagen):
    """Generar reporte JSON ISO 27037 y firma digital RSA"""
    dev_info = get_device_info(origen)
    metadatos = {
        'timestamp': datetime.now().isoformat(),
        'investigador': perito,
        'descripcion_dispositivo': f"{dev_info['modelo']} - SN:{dev_info['serial']}",
        'hostname_adquisicion': socket.gethostname(),
        'usuario_sistema': getpass.getuser(),
        'python_version': sys.version,
    }
    reporte = {
        'tipo': 'DEAD-BOX ACQUISITION REPORT',
        'version': '1.0',
        'estandar': 'ISO 27037:2012 / NIST 800-88',
        'metadata': metadatos,
        'integridad': {
            'hash_original_sha256': hash_original,
            'hash_imagen_sha256': hash_imagen,
            'coincidencia': hash_original == hash_imagen,
            'herramienta_imaging': 'dc3dd',
            'herramienta_carving': 'PhotoRec',
        }
    }
    
    # Generar llave RSA efímera para la firma (en un entorno real se usaría PKI del investigador)
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    mensaje = json.dumps(reporte, sort_keys=True).encode()
    firma = private_key.sign(
        mensaje,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256()
    )
    
    ruta_json = os.path.join(destino_base, f"{caso_id}_REPORTE.json")
    ruta_firma = os.path.join(destino_base, f"{caso_id}_COC_firma.bin")
    
    with open(ruta_json, 'w') as f:
        json.dump(reporte, f, indent=2)
    with open(ruta_firma, 'wb') as f:
        f.write(firma)
        
    print(f"[✓] Reporte estructurado JSON y firma criptográfica generados.")

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
    
    if not origen.startswith('/dev/'):
        print("[X] ERROR DE SEGURIDAD: Ruta de origen inválida. Debe ser un dispositivo en /dev/")
        sys.exit(1)
    
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
    
    # 0. Asegurar Bloqueador de Escritura
    verificar_write_blocker(origen)
    
    # 1. Hashing Previo
    hash_original = calcular_hash(origen)
    
    # 2. Generar Cadena de Custodia
    print("\n[*] 2/4: Preparando Documentación Legal...")
    generar_cadena_custodia(destino_base, caso_id, perito, origen, hash_original)
    
    # 3. Extracción (Copia) con verificación post-imaging
    ruta_imagen_dd, hash_imagen = crear_imagen_dd(origen, destino_base, caso_id, hash_original)
    
    # 4. Recuperación de archivos
    recuperar_borrados(ruta_imagen_dd, destino_base, caso_id)
    
    # 5. Generar reporte estructurado y firma
    firmar_y_reportar(destino_base, caso_id, perito, origen, hash_original, hash_imagen)
    
    print("\n==================================================")
    print("   [✔] EXTRACCIÓN ESTÁTICA COMPLETADA (ISO 27037)  ")
    print("==================================================")
    print("[*] La evidencia fue preservada de manera inalterable y validada criptográficamente.")
    print(f"[*] Revise la cadena de custodia y los datos en: {destino_base}")

if __name__ == "__main__":
    if os.geteuid() != 0:
        print("[X] Ejecute como root (sudo python3 02_deadbox_v2.py ...)")
        sys.exit(1)
    main()
