import subprocess
import sys
import os
import time

def imprimir_banner():
    print("==================================================")
    print("   FOREN-SYS: SELECTOR DE DISCO DESTINO           ")
    print("==================================================")

def listar_discos():
    print("\n--- DISCOS DISPONIBLES ---")
    # Mostramos NAME, SIZE y MOUNTPOINT para que el usuario identifique su USB
    subprocess.run(['lsblk', '-o', 'NAME,SIZE,MODEL,MOUNTPOINT'], check=True)
    print("--------------------------\n")

def montar_destino():
    imprimir_banner()
    
    # 1. Pregunta inicial de seguridad
    print("[?] ¿Este disco ya ha sido esterilizado (Wiping NIST 800-88)?")
    respuesta = input("Escriba 'SI' para continuar o 'NO' para abortar: ").strip().upper()
    
    if respuesta != "SI":
        print("\n[!] Alerta: Por integridad forense, no debe usar un disco contaminado.")
        print("[!] Por favor, ejecute primero '01_wiping.py'.")
        sys.exit(0)

    listar_discos()
    
    # 2. Selección del dispositivo
    disco = input("[?] Ingrese la ruta del USB DESTINO (Ej. /dev/sda): ").strip()
    
    if not disco.startswith("/dev/sd"):
        print("[X] Error: Ruta de dispositivo inválida.")
        sys.exit(1)

    # Definimos la partición (asumiendo que es la 1 creada por nuestro script de wiping)
    particion = f"{disco}1"
    punto_montaje = "/mnt/Destino_ForenSys"

    try:
        # 3. Verificación y Creación de Carpeta
        if not os.path.exists(punto_montaje):
            print(f"[*] Creando punto de montaje en {punto_montaje}...")
            subprocess.run(['sudo', 'mkdir', '-p', punto_montaje], check=True)

        # 4. Intento de Montaje
        print(f"[*] Intentando montar {particion} en {punto_montaje}...")
        
        # Sincronizamos el kernel primero por si acaso
        subprocess.run(['sudo', 'partprobe', disco], check=True)
        time.sleep(1)
        
        # Montaje con permisos de escritura (ya que es nuestro disco de destino)
        subprocess.run(['sudo', 'mount', particion, punto_montaje], check=True)
        
        print("\n==================================================")
        print("   [SUCCESS] DISCO DE EVIDENCIA MONTADO           ")
        print("==================================================")
        print(f"[*] Destino listo en: {punto_montaje}")
        print("[*] Ya puede proceder a la FASE 3: Adquisición.")

    except subprocess.CalledProcessError:
        print(f"\n[X] ERROR: No se pudo montar {particion}.")
        print("[!] Asegúrese de que el disco tenga una partición válida y esté conectado.")
        sys.exit(1)

if __name__ == "__main__":
    if os.geteuid() != 0:
        print("\n[X] Error: Ejecute con sudo (sudo python3 01_b_montar_destino.py)")
        sys.exit(1)
    montar_destino()
