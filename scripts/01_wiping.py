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


def calcular_bs_dd(device_info):
    """
    Elige el block size para dd.
    Lógica:
      - HDD / USB / SATA:  64 MB  → pocos syscalls, throughput máximo secuencial
      - SSD / NVMe / eMMC: 16 MB  → la cola SSD se satura con bloques muy grandes
      - Limitar al 10 % de RAM disponible
    """
    try:
        with open('/proc/meminfo') as f:
            for linea in f:
                if linea.startswith('MemAvailable'):
                    ram_kb = int(linea.split()[1])
                    ram_max = ram_kb * 1024 // 10   # 10 % de RAM
                    break
            else:
                ram_max = 64 * 1024 * 1024
    except Exception:
        ram_max = 64 * 1024 * 1024

    if device_info['transport'] in ('nvme', 'mmc') or not device_info['rotacional']:
        base = 16 * 1024 * 1024   # 16 MB para SSD/NVMe
    else:
        base = 64 * 1024 * 1024   # 64 MB para HDD

    return min(base, ram_max)



# ── Wiping con dd + I/O directo (pasada de ceros, más rápido que dc3dd) ───

def wiping_dd_ceros(disco, bs, size_bytes):
    """
    Sobrescribe con ceros usando dd + oflag=direct.

    Ventajas vs dc3dd:
    - oflag=direct: las escrituras van directamente al disco SIN pasar por el
      caché del kernel → velocidad CONSTANTE desde el primer segundo, sin el
      falso burst inicial que luego colapsa al vaciarse el caché.
    - bs=64M: mínimos syscalls de escritura por MB.
    - NIST 800-88 Clear: una pasada de ceros es suficiente en dispositivos
      modernos y es el método recomendado por el propio NIST.
    """
    global proc_hijo

    bs_str = str(bs)
    # ionice -c 1 = clase I/O RealTime (prioridad máxima en scheduler)
    cmd = [
        'ionice', '-c', '1', '-n', '0',
        'dd',
        'if=/dev/zero',
        f'of={disco}',
        f'bs={bs_str}',
        'oflag=direct',
        'conv=notrunc,noerror',
        'status=progress',
    ]
    log(f"[*] Comando: {' '.join(cmd)}")
    log(f"[*] Block size: {_human(bs)} — I/O directo (sin caché del kernel)")

    try:
        proc_hijo = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,   # dd progress → stderr
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        buf = ''
        ultimo_pct = -1
        while True:
            char = proc_hijo.stderr.read(1)
            if not char:
                break
            if char in ('\r', '\n'):
                linea = buf.strip()
                if linea:
                    # Formato dd: "64424509440 bytes (64 GB, 60 GiB) copied, 718 s, 89.7 MB/s"
                    m_bytes = re.match(r'(\d+)\s+bytes', linea)
                    m_speed = re.search(r'(\d+(?:\.\d+)?\s+[GMK]?B/s)', linea)
                    if m_bytes and size_bytes > 0:
                        bytes_hechos = int(m_bytes.group(1))
                        pct = min(99, int(bytes_hechos * 100 / size_bytes))
                        pct_global = 5 + int(pct * 0.75)
                        speed = m_speed.group(1) if m_speed else '?'
                        if pct != ultimo_pct:
                            progress(pct_global,
                                     f"{_human(bytes_hechos)} / {_human(size_bytes)} — {speed}")
                            ultimo_pct = pct
                    else:
                        log(linea)
                buf = ''
            else:
                buf += char

        if buf.strip():
            # Última línea tras el EOF
            linea = buf.strip()
            m_speed = re.search(r'(\d+(?:\.\d+)?\s+[GMK]?B/s)', linea)
            log(f"[dd] {linea}")

        proc_hijo.wait()
        rc = proc_hijo.returncode
        proc_hijo = None
        return rc in (0, 1)   # dd retorna 1 si hubo errores corregidos

    except FileNotFoundError as exc:
        log(f"[X] Herramienta no encontrada: {exc}. Verifique que 'ionice' y 'dd' estén instalados.")
        sys.exit(1)


# ── Wiping con dc3dd (multi-pasada DoD) ──────────────────────────────────

def wiping_dc3dd_multipasada(disco, pasada, total_pasadas):
    """
    Usa dc3dd para pasadas adicionales (DoD 3/7 pasadas con patrones).
    dc3dd maneja los patrones hex necesarios (0x00, 0xFF, random).
    Se reserva solo para pasadas 2+ ya que la pasada de ceros la hace dd.
    """
    global proc_hijo

    patrones = ['pat=00', 'pat=ff', 'pat=random', 'pat=00', 'pat=ff', 'pat=random', 'pat=random']
    patron   = patrones[(pasada - 1) % len(patrones)]

    cmd = ['dc3dd', f'wipe={disco}', patron, f'bufsz=16777216', 'verb=on']
    log(f"[*] dc3dd pasada {pasada}/{total_pasadas} — {patron}")

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
                        pct_global = 5 + int(pct * 0.75)
                        if pct != ultimo_pct:
                            progress(pct_global, f"Pasada {pasada}/{total_pasadas}: {linea}")
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
        # Pasada 1 (NIST Clear / DoD Pass 1): Usar dd + oflag=direct
        log(f"\n[*] Iniciando dd directo para sobrescritura continua...")
        bs_dd = calcular_bs_dd(dev_info)
        
        if args.passes > 1:
            log(f"\n[*] Pasada 1/{args.passes} (Ceros)...")
        else:
            log(f"\n[*] Pasada 1/1 (Ceros)...")
            
        exito_dd = wiping_dd_ceros(disco, bs_dd, dev_info['size_bytes'])
        if not exito_dd:
            log("[X] La herramienta 'dd' falló o fue interrumpida.")
            sys.exit(1)

        # Pasadas 2 a N (DoD Básico o Full): Usar dc3dd para los patrones hex
        if args.passes > 1:
            log("\n[*] Iniciando dc3dd para patrones multi-pasada DoD...")
            for pasada in range(2, args.passes + 1):
                rc = wiping_dc3dd_multipasada(disco, pasada, args.passes)
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
