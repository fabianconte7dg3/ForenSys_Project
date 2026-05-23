#!/usr/bin/env python3
"""
01_wiping.py — Esterilización de disco destino (NIST 800-88)
Ejecutar con: sudo python3 01_wiping.py --target /dev/sdX --force
"""
import subprocess
import sys
import time
import os
import re
import argparse
import signal

proc_hijo = None  # Referencia global al subproceso dc3dd

def handle_sigterm(signum, frame):
    global proc_hijo
    print("\n[!] Señal de interrupción recibida. Terminando dc3dd...", flush=True)
    if proc_hijo:
        try:
            proc_hijo.terminate()
            proc_hijo.wait(timeout=5)
        except Exception:
            proc_hijo.kill()
    sys.exit(1)

signal.signal(signal.SIGTERM, handle_sigterm)
signal.signal(signal.SIGINT, handle_sigterm)


def main():
    global proc_hijo

    parser = argparse.ArgumentParser(description="Foren-Sys: Wiping y Preparación de Disco Destino")
    parser.add_argument("-t", "--target", required=True, help="Ruta del disco destino (ej. /dev/sdb)")
    parser.add_argument("-f", "--force", action="store_true", help="Omitir confirmación manual")
    args = parser.parse_args()

    disco = args.target

    print("==================================================")
    print("   FOREN-SYS: ESTERILIZACIÓN DE DISCO (WIPING)   ")
    print("      Cumplimiento Normativa NIST 800-88          ")
    print("==================================================")
    print(f"\n[*] Disco objetivo : {disco}")

    # Validaciones básicas
    if not disco.startswith("/dev/"):
        print(f"[X] Ruta inválida: {disco}. Abortando.")
        sys.exit(1)

    if not os.path.exists(disco):
        print(f"[X] El dispositivo {disco} no existe. Abortando.")
        sys.exit(1)

    if not args.force:
        resp = input('[?] Escriba "CONFIRMAR" en mayúsculas para proceder: ')
        if resp.strip() != "CONFIRMAR":
            print("[!] Cancelado por el usuario.")
            sys.exit(0)
    else:
        print("[!] Modo --force activo. Saltando confirmación.")

    # PASO 0: Desmontar particiones activas
    print("\n[*] PASO 0/3: Desmontando particiones del disco...")
    subprocess.run(['umount', f'{disco}1'], stderr=subprocess.DEVNULL)
    subprocess.run(['umount', f'{disco}p1'], stderr=subprocess.DEVNULL)
    subprocess.run(['umount', '/mnt/Destino_ForenSys'], stderr=subprocess.DEVNULL)
    print("[+] Particiones desmontadas (o no estaban montadas).")

    # PASO 1: Wiping con dc3dd (sin sudo — ya somos root)
    print(f"\n[*] PASO 1/3: Iniciando limpieza con dc3dd en {disco}...")
    print("[*] (Este proceso puede tardar varios minutos según el tamaño del disco)")

    # Asegurar que el disco NO está en modo solo-lectura antes de escribir
    print(f"[*] Desactivando bloqueo de escritura en {disco}...")
    rw_result = subprocess.run(['blockdev', '--setrw', disco], capture_output=True)
    if rw_result.returncode != 0:
        print(f"[!] Advertencia: No se pudo desactivar read-only: {rw_result.stderr.strip()}")
    else:
        print(f"[+] Disco {disco} en modo lectura-escritura.")

    cmd_wipe = ['dc3dd', f'wipe={disco}']
    try:
        proc_hijo = subprocess.Popen(
            cmd_wipe,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,   # fusionar stderr en stdout
            text=True,
            bufsize=1
        )

        buf = ''
        while True:
            char = proc_hijo.stdout.read(1)
            if not char:
                break
            if char in ('\r', '\n'):
                linea = buf.strip()
                if linea:
                    # dc3dd usa paréntesis: '196608 bytes ( 192 K ) copied ( 15% )'
                    # Extraer porcentaje y emitir como [PROGRESO:X]
                    pct_match = re.search(r'\(\s*(\d+)%\s*\)', linea)
                    if pct_match:
                        pct = pct_match.group(1)
                        print(f"[PROGRESO:{pct}] {linea}", flush=True)
                    else:
                        print(linea, flush=True)
                buf = ''
            else:
                buf += char
        # Volcar lo que quede en el buffer
        if buf.strip():
            print(buf.strip(), flush=True)

        proc_hijo.wait()
        rc = proc_hijo.returncode

        if rc not in [0, 1]:
            print(f"\n[X] dc3dd terminó con código de error: {rc}")
            sys.exit(1)

    except FileNotFoundError:
        print("[X] 'dc3dd' no encontrado. Instale con: sudo apt install dc3dd")
        sys.exit(1)

    print("\n[SUCCESS] Disco sobrescrito con ceros exitosamente.")

    # PASO 2: Crear partición y formatear
    print("\n[*] PASO 2/3: Creando tabla de particiones GPT y formateando en ext4...")
    subprocess.run(['parted', '-s', disco, 'mklabel', 'gpt'], check=True)
    subprocess.run(['parted', '-s', disco, 'mkpart', 'primary', 'ext4', '0%', '100%'], check=True)
    subprocess.run(['partprobe', disco])
    time.sleep(3)

    if "nvme" in disco or "loop" in disco:
        particion = f"{disco}p1"
    else:
        particion = f"{disco}1"

    print(f"[*] Formateando {particion} como ext4...")
    subprocess.run(['mkfs.ext4', '-F', particion], check=True)
    print("[SUCCESS] Formato ext4 aplicado.")

    # PASO 3: Montaje
    print("\n[*] PASO 3/3: Montando disco en /mnt/Destino_ForenSys...")
    punto_montaje = "/mnt/Destino_ForenSys"
    os.makedirs(punto_montaje, exist_ok=True)
    subprocess.run(['mount', particion, punto_montaje], check=True)

    print("\n==================================================")
    print("   [✔] WIPING COMPLETADO — SISTEMA LISTO         ")
    print("==================================================")
    print(f"[*] Disco {disco} estéril, formateado y montado en: {punto_montaje}")


if __name__ == "__main__":
    if os.geteuid() != 0:
        print("[X] Este script requiere permisos de root. Use: sudo python3 01_wiping.py ...")
        sys.exit(1)
    main()
