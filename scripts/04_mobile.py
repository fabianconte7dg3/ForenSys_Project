import os
import sys
import subprocess
import time

def imprimir_banner():
    print("==================================================")
    print("   FOREN-SYS: EXTRACCIÓN MÓVIL LÓGICA (ADB)       ")
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

def conectar_adb():
    """Verifica si el celular está conectado y depurando"""
    print("\n[*] 1/3: Verificando conexión y autorización del dispositivo móvil (ADB)...")
    try:
        # Iniciar el servidor ADB silenciosamente
        subprocess.run(['adb', 'start-server'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        resultado = subprocess.run(['adb', 'devices'], capture_output=True, text=True, check=True)
        lineas = resultado.stdout.strip().split('\n')
        
        # Filtramos para encontrar dispositivos que no digan "offline" ni "unauthorized"
        dispositivos = [linea for linea in lineas[1:] if 'device' in linea and 'unauthorized' not in linea and 'offline' not in linea]
        no_autorizados = [linea for linea in lineas[1:] if 'unauthorized' in linea]
        
        if no_autorizados:
            print("\n[!] ALERTA: Celular detectado, pero NO AUTORIZADO.")
            print("    -> Desbloquea la pantalla del celular y presiona 'Permitir depuración USB'.")
            sys.exit(1)
            
        if not dispositivos:
            print("\n[X] ERROR: No se detectó ningún celular conectado.")
            print("    Pasos en el celular sospechoso:")
            print("    1. Conecta el cable USB a la Raspberry.")
            print("    2. Ve a Opciones de Desarrollador -> Activa 'Depuración USB'.")
            sys.exit(1)
            
        print("[+] [ÉXITO] Dispositivo móvil detectado y autorizado:")
        for d in dispositivos:
            print(f"    -> {d}")
            
    except FileNotFoundError:
        print("\n[X] ERROR FATAL: Herramienta ADB no instalada en la Raspberry.")
        print("    Ejecuta el siguiente comando para instalarla:")
        print("    sudo apt update && sudo apt install adb -y")
        sys.exit(1)

def extraccion_logica(carpeta_caso, caso_id):
    """Extrae el backup .ab y la galería de fotos mediante adb pull"""
    print("\n[*] 2/3: Iniciando Extracción Lógica (Backup de Aplicaciones)...")
    
    archivo_backup = os.path.join(carpeta_caso, f"{caso_id}_backup_celular.ab")
    
    # [!] ALERTA FORENSE CRÍTICA
    print("\n------------------------------------------------------------")
    print("[!] ATENCIÓN PERITO: Revisa la pantalla del celular sospechoso.")
    print(f"[!] Ingresa una contraseña (opcional) y presiona 'Respaldar mis datos'.")
    print("    El script quedará en pausa hasta que lo apruebes en el teléfono...")
    print("------------------------------------------------------------\n")
    
    try:
        # Comando: adb backup -all -f backup_celular.ab
        comando_backup = ['adb', 'backup', '-all', '-f', archivo_backup]
        subprocess.run(comando_backup, check=True)
        
        if os.path.exists(archivo_backup) and os.path.getsize(archivo_backup) > 0:
            peso_mb = os.path.getsize(archivo_backup) / (1024 * 1024)
            print(f"[+] [ÉXITO] Backup lógico guardado ({peso_mb:.2f} MB): {archivo_backup}")
        else:
            print("[!] El backup parece estar vacío. Asegúrate de haber presionado 'Respaldar' en el celular.")
    except subprocess.CalledProcessError as e:
        print(f"\n[X] Error durante el backup de ADB: {e}")

    print("\n[*] 3/3: Extrayendo Galería Multimedia (Data Pulling / DCIM)...")
    carpeta_fotos = os.path.join(carpeta_caso, "Fotos_DCIM")
    
    try:
        # Comando: adb pull /sdcard/DCIM/ ./ForenSys/Mobile/Fotos/
        comando_pull = ['adb', 'pull', '/sdcard/DCIM/', carpeta_fotos]
        # Mostramos la salida para que se vea el progreso de las fotos copiándose
        subprocess.run(comando_pull, check=True)
        print(f"\n[+] [ÉXITO] Galería multimedia clonada en: {carpeta_fotos}")
    except subprocess.CalledProcessError as e:
        print(f"\n[X] Error extrayendo fotos: {e}")
        print("    (Es posible que el celular tenga bloqueados los permisos de almacenamiento)")

def main():
    imprimir_banner()
    
    destino_base = "/mnt/Destino_ForenSys"
    if not os.path.ismount(destino_base):
        print(f"\n[X] ALERTA: La bóveda SDA ({destino_base}) no está montada.")
        print("    Ejecute primero la esterilización o el montador.")
        sys.exit(1)

    # 1. Aplicamos llave maestra al disco destino
    auto_desbloquear_destino(destino_base)
    
    # 2. Verificamos conexión con el móvil
    conectar_adb()
    
    # 3. Solicitamos ID del caso y creamos la carpeta
    caso_id = input("\n[?] Ingrese el ID del Caso (Ej. CASO_005): ").strip()
    carpeta_caso = os.path.join(destino_base, f"{caso_id}_MOBILE")
    os.makedirs(carpeta_caso, exist_ok=True)
    
    # 4. Iniciamos la extracción
    extraccion_logica(carpeta_caso, caso_id)
    
    print("\n==================================================")
    print("   [✔] EXTRACCIÓN MÓVIL COMPLETADA                ")
    print("==================================================")
    print(f"[*] Toda la evidencia del celular reside segura en {carpeta_caso}")

if __name__ == "__main__":
    if os.geteuid() != 0:
        print("\n[X] Error: Este script interactúa con hardware USB.")
        print("    Ejecuta: sudo python3 04_mobile.py")
        sys.exit(1)
    main()
