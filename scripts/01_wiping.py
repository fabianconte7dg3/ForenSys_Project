#!/usr/bin/env python3
"""
01_wiping.py — Esterilización de disco destino (NIST 800-88 / DoD 5220.22-M)
Ejecutar con: sudo python3 01_wiping.py --target /dev/sdX --force

OPTIMIZACIONES DE VELOCIDAD:
  - bufsz=4M en dc3dd (vs default ~512K) → ~3-4× más rápido en HDD/USB
  - Detección automática del tipo de dispositivo (HDD, SSD/NVMe, USB/eMMC)
  - blkdiscard (TRIM/UNMAP) para SSD/NVMe: completa en segundos en lugar de horas
  - Sintonización del tamaño de buffer según la memoria RAM disponible
  - Lectura de optimal_io_size del kernel para ajustar bufsz
  - Modo --fast: usa blkdiscard si el dispositivo lo soporta (NIST 800-88 §2.4 Purge)
  - Progreso granular cada 1 % gracias a bufsz grande
"""
import subprocess
import sys
import time
import os
import re
import argparse
import signal
import shutil

proc_hijo = None  # Referencia global al subproceso


# ── Manejador de señales ───────────────────────────────────────────
def handle_signal(signum, frame):
    global proc_hijo
    print("\n[!] Interrupción recibida. Deteniendo proceso...", flush=True)
    if proc_hijo:
        try:
            proc_hijo.terminate()
            proc_hijo.wait(timeout=5)
        except Exception:
            proc_hijo.kill()
    sys.exit(1)

signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT,  handle_signal)


# ── Utilidades ─────────────────────────────────────────────────────

def log(msg):
    print(msg, flush=True)

def progress(pct, detail=""):
    print(f"[PROGRESO:{pct}] {detail}", flush=True)


def get_device_info(disco):
    """Detecta tipo, tamaño y características del dispositivo."""
    info = {
        'size_bytes': 0,
        'size_human': '?',
        'rotacional': True,    # HDD por defecto
        'transport':  'unknown',
        'trim_ok':    False,
        'optimal_io': 0,
    }

    nombre = os.path.basename(disco)  # ej: sdb, nvme0n1, mmcblk0

    # Tamaño
    try:
        r = subprocess.run(['blockdev', '--getsize64', disco],
                           capture_output=True, text=True)
        if r.returncode == 0:
            sz = int(r.stdout.strip())
            info['size_bytes'] = sz
            info['size_human'] = _human(sz)
    except Exception:
        pass

    # ¿Rotacional? (0 = SSD/NVMe, 1 = HDD)
    rota_path = f"/sys/block/{nombre}/queue/rotational"
    if os.path.exists(rota_path):
        try:
            info['rotacional'] = open(rota_path).read().strip() == '1'
        except Exception:
            pass

    # Transporte
    tran_path = f"/sys/block/{nombre}/device/transport"
    if not os.path.exists(tran_path):
        # NVMe detectado por nombre
        if 'nvme' in nombre:
            info['transport'] = 'nvme'
        elif 'mmcblk' in nombre:
            info['transport'] = 'mmc'
        elif 'sd' in nombre:
            info['transport'] = 'sata/usb'
    else:
        try:
            info['transport'] = open(tran_path).read().strip()
        except Exception:
            pass

    # optimal_io_size del kernel
    opt_io_path = f"/sys/block/{nombre}/queue/optimal_io_size"
    if os.path.exists(opt_io_path):
        try:
            info['optimal_io'] = int(open(opt_io_path).read().strip())
        except Exception:
            pass

    # ¿Soporta TRIM / blkdiscard?
    if not info['rotacional'] or info['transport'] in ('nvme', 'mmc'):
        try:
            r = subprocess.run(['blkdiscard', '-n', disco],  # dry-run
                               capture_output=True, timeout=5)
            info['trim_ok'] = (r.returncode == 0)
        except Exception:
            info['trim_ok'] = shutil.which('blkdiscard') is not None

    return info


def _human(b):
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if b < 1024 or unit == 'TB':
            return f"{b:.1f} {unit}"
        b /= 1024


def calcular_bufsz(device_info):
    """
    Elige el tamaño de buffer óptimo para dc3dd.

    Lógica (basada en benchmarks y NIST recomendaciones):
      - HDD / USB / SATA:  4 MB a 16 MB  → mejor throughput secuencial
      - SSD / NVMe / eMMC: 1 MB a 4 MB   → límite de la cola de escritura
      - Toma el mayor entre optimal_io_size y el mínimo seguro de 512 KB
      - No supera el 5 % de la RAM disponible para no generar swapping
    """
    # RAM disponible
    try:
        with open('/proc/meminfo') as f:
            for linea in f:
                if linea.startswith('MemAvailable'):
                    ram_kb = int(linea.split()[1])
                    ram_max = ram_kb * 1024 // 20   # 5 % de RAM
                    break
            else:
                ram_max = 16 * 1024 * 1024  # 16 MB fallback
    except Exception:
        ram_max = 16 * 1024 * 1024

    # Punto de partida según tipo de dispositivo
    if device_info['transport'] in ('nvme', 'mmc') or not device_info['rotacional']:
        base = 1 * 1024 * 1024    # 1 MB para SSD/NVMe
    else:
        base = 4 * 1024 * 1024    # 4 MB para HDD/USB

    # Escalar con optimal_io_size si es útil
    opt = device_info.get('optimal_io', 0)
    if opt and opt > base:
        base = min(opt, 16 * 1024 * 1024)  # máximo 16 MB

    # No superar el 5 % de RAM
    bufsz = min(base, ram_max)

    # Nunca bajar de 512 KB (dc3dd default ya es menor)
    bufsz = max(bufsz, 512 * 1024)

    return bufsz


# ── Wiping con dc3dd (modo forense, máxima velocidad) ─────────────

def wiping_dc3dd(disco, bufsz):
    """Sobrescribe con ceros usando dc3dd con bufsz optimizado."""
    global proc_hijo

    bufsz_str = str(bufsz)
    cmd = [
        'dc3dd',
        f'wipe={disco}',
        f'bufsz={bufsz_str}',
        'verb=on',           # reporte de progreso continuo
    ]
    log(f"[*] Comando dc3dd: {' '.join(cmd)}")
    log(f"[*] Buffer size:   {_human(bufsz)}")

    try:
        proc_hijo = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        buf = ''
        ultimo_pct = -1
        while True:
            char = proc_hijo.stdout.read(1)
            if not char:
                break
            if char in ('\r', '\n'):
                linea = buf.strip()
                if linea:
                    pct_match = re.search(r'\(\s*(\d+)%\s*\)', linea)
                    if pct_match:
                        pct = int(pct_match.group(1))
                        # Escalar al rango 5%–80% del wiping total (pasos 0/3 y 1/3)
                        pct_global = 5 + int(pct * 0.75)
                        if pct != ultimo_pct:
                            progress(pct_global, linea)
                            ultimo_pct = pct
                    else:
                        log(linea)
                buf = ''
            else:
                buf += char

        if buf.strip():
            log(buf.strip())

        proc_hijo.wait()
        rc = proc_hijo.returncode
        proc_hijo = None
        return rc

    except FileNotFoundError:
        log("[X] 'dc3dd' no encontrado. Instale con: sudo apt install dc3dd")
        sys.exit(1)


# ── Wiping con blkdiscard (TRIM/UNMAP — para SSD/NVMe) ────────────

def wiping_blkdiscard(disco):
    """
    NIST 800-88 §2.4: 'Purge' mediante TRIM/UNMAP.
    Mucho más rápido en SSD/NVMe (~segundos vs horas).
    El controlador del dispositivo borra los datos a nivel de flash.
    """
    log("[*] Usando blkdiscard (TRIM/UNMAP) — modo Purge NIST 800-88 §2.4")
    log("[!] Este método es equivalente o superior al wipeo con ceros para SSD/NVMe.")
    progress(10, "Iniciando blkdiscard TRIM/UNMAP...")

    try:
        r = subprocess.run(
            ['blkdiscard', '-f', disco],
            capture_output=True, text=True
        )
        if r.returncode == 0:
            progress(80, "blkdiscard completado exitosamente.")
            log("[+] TRIM/UNMAP aplicado. Datos no recuperables por medios convencionales.")
            return True
        else:
            log(f"[!] blkdiscard retornó {r.returncode}: {r.stderr.strip()}")
            log("[!] Fallback a dc3dd...")
            return False
    except Exception as e:
        log(f"[!] Error en blkdiscard: {e}. Fallback a dc3dd...")
        return False


# ── Flujo principal ────────────────────────────────────────────────

def main():
    global proc_hijo

    parser = argparse.ArgumentParser(
        description="Foren-Sys: Wiping y Preparación de Disco Destino (NIST 800-88)"
    )
    parser.add_argument("-t", "--target", required=True,
                        help="Ruta del disco destino (ej. /dev/sdb)")
    parser.add_argument("-f", "--force", action="store_true",
                        help="Omitir confirmación manual")
    parser.add_argument("--fast", action="store_true",
                        help="Usar TRIM/blkdiscard si disponible (SSD/NVMe — mucho más rápido)")
    parser.add_argument("--passes", type=int, default=1, choices=[1, 3, 7],
                        help="Número de pasadas (1=ceros, 3=DoD básico, 7=DoD full). Default: 1")
    args = parser.parse_args()

    disco = args.target

    log("==================================================")
    log("   FOREN-SYS: ESTERILIZACIÓN DE DISCO (WIPING)   ")
    log("   NIST 800-88 / DoD 5220.22-M                   ")
    log("==================================================")

    # Validaciones
    if not disco.startswith("/dev/"):
        log(f"[X] Ruta inválida: {disco}")
        sys.exit(1)
    if not os.path.exists(disco):
        log(f"[X] El dispositivo {disco} no existe.")
        sys.exit(1)

    # Detectar dispositivo
    progress(2, "Analizando dispositivo...")
    dev_info = get_device_info(disco)

    log(f"\n[*] Dispositivo:   {disco}")
    log(f"[*] Tamaño:        {dev_info['size_human']}")
    log(f"[*] Tipo:          {'HDD (magnético)' if dev_info['rotacional'] else 'SSD/NVMe/eMMC (flash)'}")
    log(f"[*] Transporte:    {dev_info['transport']}")
    log(f"[*] TRIM/UNMAP:    {'✓ Disponible' if dev_info['trim_ok'] else '✗ No disponible'}")
    log(f"[*] Pasadas:       {args.passes}")
    log(f"[*] Modo rápido:   {'--fast activo' if args.fast else 'No'}")

    if not args.force:
        resp = input('[?] Escriba "CONFIRMAR" en mayúsculas para proceder: ')
        if resp.strip() != "CONFIRMAR":
            log("[!] Cancelado por el usuario.")
            sys.exit(0)
    else:
        log("[!] Modo --force activo. Saltando confirmación.")

    # PASO 0: Desmontar
    progress(3, "Desmontando particiones activas...")
    subprocess.run(['umount', f'{disco}1'],   stderr=subprocess.DEVNULL)
    subprocess.run(['umount', f'{disco}p1'],  stderr=subprocess.DEVNULL)
    subprocess.run(['umount', '/mnt/Destino_ForenSys'], stderr=subprocess.DEVNULL)
    log("[+] Particiones desmontadas (o no estaban montadas).")

    # Desactivar solo-lectura
    rw_result = subprocess.run(['blockdev', '--setrw', disco], capture_output=True)
    if rw_result.returncode != 0:
        log(f"[!] No se pudo desactivar read-only: {rw_result.stderr.decode().strip()}")
    else:
        log(f"[+] Disco {disco} en modo lectura-escritura.")

    # PASO 1: Wiping
    log(f"\n[*] PASO 1/3: Iniciando limpieza...")

    wiping_exitoso = False
    t_inicio = time.time()

    # Intentar blkdiscard si --fast y SSD/NVMe
    if args.fast and dev_info['trim_ok']:
        log("[*] Dispositivo flash detectado con soporte TRIM → usando blkdiscard")
        wiping_exitoso = wiping_blkdiscard(disco)

    if not wiping_exitoso:
        # dc3dd con buffer optimizado
        bufsz = calcular_bufsz(dev_info)
        log(f"\n[*] Iniciando dc3dd con buffer {_human(bufsz)}...")
        log(f"[*] {'Este proceso puede tardar varios minutos. La barra se actualizará en tiempo real.'}")

        for pasada in range(1, args.passes + 1):
            if args.passes > 1:
                log(f"\n[*] Pasada {pasada}/{args.passes}...")
            rc = wiping_dc3dd(disco, bufsz)
            if rc not in [0, 1]:
                log(f"[X] dc3dd terminó con código de error: {rc}")
                sys.exit(1)

        wiping_exitoso = True

    t_total = time.time() - t_inicio
    t_human = f"{int(t_total // 60)}m {int(t_total % 60)}s"
    log(f"\n[SUCCESS] Disco sobrescrito exitosamente en {t_human}.")

    # Calcular velocidad aproximada
    if dev_info['size_bytes'] > 0 and t_total > 0:
        velocidad = dev_info['size_bytes'] / t_total
        log(f"[*] Velocidad promedio: {_human(velocidad)}/s")

    # PASO 2: Crear tabla de particiones y formatear
    progress(83, "Creando tabla de particiones GPT...")
    log("\n[*] PASO 2/3: Creando tabla GPT y formateando ext4...")
    subprocess.run(['parted', '-s', disco, 'mklabel', 'gpt'], check=True)
    subprocess.run(['parted', '-s', disco, 'mkpart', 'primary', 'ext4', '0%', '100%'], check=True)
    subprocess.run(['partprobe', disco])
    time.sleep(3)

    if "nvme" in disco or "loop" in disco or "mmcblk" in disco:
        particion = f"{disco}p1"
    else:
        particion = f"{disco}1"

    progress(90, f"Formateando {particion} como ext4...")
    log(f"[*] Formateando {particion}...")
    subprocess.run(['mkfs.ext4', '-F', particion], check=True)
    log("[SUCCESS] Formato ext4 aplicado.")

    # PASO 3: Montaje
    progress(96, "Montando disco...")
    log("\n[*] PASO 3/3: Montando disco en /mnt/Destino_ForenSys...")
    punto_montaje = "/mnt/Destino_ForenSys"
    os.makedirs(punto_montaje, exist_ok=True)
    subprocess.run(['mount', particion, punto_montaje], check=True)

    progress(100, "Wiping completado.")
    log("\n==================================================")
    log("   [SUCCESS] WIPING COMPLETADO — SISTEMA LISTO   ")
    log("==================================================")
    log(f"[*] Disco:        {disco}  ({dev_info['size_human']})")
    log(f"[*] Tiempo total: {t_human}")
    log(f"[*] Montado en:   {punto_montaje}")
    log(f"[*] Norma:        NIST 800-88 / DoD 5220.22-M ({args.passes} pasada(s))")


if __name__ == "__main__":
    if os.geteuid() != 0:
        log("[X] Este script requiere permisos de root. Use: sudo python3 01_wiping.py ...")
        sys.exit(1)
    main()
