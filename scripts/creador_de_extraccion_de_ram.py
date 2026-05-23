import subprocess
import sys
import time
import os
import shutil

def listar_discos():
    print("\n--- UNIDADES DETECTADAS ---")
    subprocess.run(['lsblk', '-o', 'NAME,SIZE,MODEL,MOUNTPOINT,RO'], check=True)
    print("---------------------------\n")

def preparar_live_usb():
    print("==================================================")
    print("   FOREN-SYS: CREADOR DE EXTRACCIÓN DE RAM        ")
    print("   (Generador de Live Response USB)               ")
    print("==================================================")
    
    listar_discos()
    
    print("[!] Conecta un USB VACÍO (Recomendado: 8GB - 16GB).")
    print("    Este USB se usará para ir a la PC víctima y extraer su RAM.")
    disco_usb = input("[?] Ingrese la ruta del USB (Ej. /dev/sdd): ").strip()
    
    if not disco_usb.startswith("/dev/sd"):
        print("[X] Ruta inválida. Abortando.")
        sys.exit(1)

    print(f"\n[PELIGRO] Se borrará TODO en {disco_usb} para crear el kit forense.")
    if input('Escriba "PREPARAR" en mayúsculas para continuar: ') != "PREPARAR":
        print("[!] Operación cancelada.")
        sys.exit(0)

    try:
        # 0. Desactivar el Bloqueador Forense (udev)
        print("\n[*] 0/4: Desactivando bloqueador de escritura forense para este disco...")
        subprocess.run(['sudo', 'blockdev', '--setrw', disco_usb], check=True)

        # 1. Limpieza y Destrucción de Cabeceras (Solución al error 2048 vs 512 bytes)
        print("[*] 1/4: Aplicando borrado profundo de cabeceras MBR/GPT e ISO...")
        for i in range(1, 6):
            subprocess.run(['sudo', 'umount', f'{disco_usb}{i}'], stderr=subprocess.DEVNULL)
            
        # Nukeamos los primeros 10MB para destruir cualquier rastro de instalaciones previas
        subprocess.run(['sudo', 'dd', 'if=/dev/zero', f'of={disco_usb}', 'bs=1M', 'count=10', 'status=none'], check=True)
        subprocess.run(['sync'], check=True)
        time.sleep(2) # Pausa vital para que el Kernel asimile que el disco ahora está en blanco
        
        # 2. Crear tabla de particiones y partición primaria
        print("[*] 2/4: Reconstruyendo tabla de particiones limpia...")
        subprocess.run(['sudo', 'parted', '-s', disco_usb, 'mklabel', 'msdos'], check=True)
        subprocess.run(['sudo', 'parted', '-s', disco_usb, 'mkpart', 'primary', 'fat32', '1MiB', '100%'], check=True)
        subprocess.run(['sudo', 'partprobe', disco_usb])
        time.sleep(2)
        
        # 3. Formatear como exFAT
        print("[*] 3/4: Formateando en exFAT (Formato Universal)...")
        particion = f"{disco_usb}1"
        subprocess.run(['sudo', 'mkfs.exfat', '-n', 'RAM_KIT', particion], check=True)

        # 4. Montar y copiar herramientas
        print("[*] 4/4: Inyectando herramientas forenses (Extractor de RAM)...")
        punto_montaje = "/mnt/temp_usb_kit"
        subprocess.run(['sudo', 'mkdir', '-p', punto_montaje], check=True)
        subprocess.run(['sudo', 'mount', particion, punto_montaje], check=True)

        ruta_herramientas = "/home/ciber-admin/ForenSys_Project/tools_bin/"
        
        if os.path.exists(ruta_herramientas) and os.listdir(ruta_herramientas):
            for item in os.listdir(ruta_herramientas):
                origen = os.path.join(ruta_herramientas, item)
                destino = os.path.join(punto_montaje, item)
                if os.path.isfile(origen):
                    shutil.copy2(origen, destino)
            print("[+] Herramienta inyectada con éxito.")
        else:
            print("\n[!] ALERTA: La carpeta 'tools_bin' está vacía o no existe.")
            print("    El USB se formateó, pero no tiene el .exe adentro.")

        # 5. Sincronizar y desmontar
        print("[*] Finalizando y sellando el USB...")
        subprocess.run(['sync'], check=True)
        subprocess.run(['sudo', 'umount', punto_montaje], check=True)
        
        print("\n==================================================")
        print("   [SUCCESS] LIVE RESPONSE USB ESTÁ LISTO         ")
        print("==================================================")
        print("[*] Instrucciones para la escena del crimen:")
        print("    1. Conecta este USB a la PC sospechosa (Mientras está encendida).")
        print("    2. Entra al USB y haz doble clic en 'DumpIt_ForenSys.exe'.")
        print("    3. Espera a que termine. Se creará un archivo .raw enorme.")
        print("    4. Trae el USB de vuelta y usa el script '03_live_ram.py'.")

    except subprocess.CalledProcessError as e:
        print(f"\n[X] Error fatal ejecutando comandos de disco: {e}")
    except Exception as e:
        print(f"\n[X] Error inesperado: {e}")

if __name__ == "__main__":
    if os.geteuid() != 0:
        print("\n[X] Error: Este script requiere acceso a hardware.")
        print("Ejecuta: sudo python3 creador_de_extraccion_de_ram.py\n")
        sys.exit(1)
    preparar_live_usb()
