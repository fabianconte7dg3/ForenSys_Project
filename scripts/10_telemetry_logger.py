#!/usr/bin/env python3
"""
Módulo 10: Telemetría Logger (ForenSys)
Monitorea el consumo de CPU, RAM, I/O y temperatura de un proceso forense.
Guarda los resultados en un archivo JSON en el directorio del caso.
"""
import argparse
import json
import os
import time
import sys
import subprocess

try:
    import psutil
except ImportError:
    psutil = None

def get_rpi_temp():
    try:
        with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
            return float(f.read().strip()) / 1000.0
    except Exception:
        return 0.0

def monitor_process(pid, module_name, case_dir):
    if not psutil:
        print("[TELEMETRÍA] Error: psutil no está instalado. No se puede monitorear.")
        return

    try:
        proc = psutil.Process(pid)
    except psutil.NoSuchProcess:
        print(f"[TELEMETRÍA] Proceso {pid} no existe.")
        return

    print(f"[TELEMETRÍA] Monitoreo activado para PID: {pid} ({module_name})")

    metrics = {
        "module": module_name,
        "start_time": time.time(),
        "end_time": 0,
        "cpu_percent_avg": 0,
        "cpu_percent_max": 0,
        "ram_mb_avg": 0,
        "ram_mb_max": 0,
        "temp_c_max": 0,
        "temp_c_avg": 0,
        "io_read_mb": 0,
        "io_write_mb": 0,
        "duration_sec": 0
    }

    cpu_samples = []
    ram_samples = []
    temp_samples = []
    start_io = None

    try:
        start_io = proc.io_counters()
    except Exception:
        pass

    while proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE:
        try:
            cpu = proc.cpu_percent(interval=1.0)
            ram = proc.memory_info().rss / (1024 * 1024)
            temp = get_rpi_temp()

            cpu_samples.append(cpu)
            ram_samples.append(ram)
            if temp > 0:
                temp_samples.append(temp)
                
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            break

    # Finalizar cálculos
    metrics["end_time"] = time.time()
    metrics["duration_sec"] = metrics["end_time"] - metrics["start_time"]

    if cpu_samples:
        metrics["cpu_percent_avg"] = sum(cpu_samples) / len(cpu_samples)
        metrics["cpu_percent_max"] = max(cpu_samples)
    
    if ram_samples:
        metrics["ram_mb_avg"] = sum(ram_samples) / len(ram_samples)
        metrics["ram_mb_max"] = max(ram_samples)

    if temp_samples:
        metrics["temp_c_avg"] = sum(temp_samples) / len(temp_samples)
        metrics["temp_c_max"] = max(temp_samples)

    try:
        if start_io:
            end_io = proc.io_counters()
            metrics["io_read_mb"] = (end_io.read_bytes - start_io.read_bytes) / (1024 * 1024)
            metrics["io_write_mb"] = (end_io.write_chars - start_io.write_chars) / (1024 * 1024)
    except Exception:
        pass

    # Extraer velocidad de wiping si existe
    if "Wiping" in module_name and os.path.exists("/tmp/wiping_speed.txt"):
        try:
            with open("/tmp/wiping_speed.txt", "r") as f:
                speed_str = f.read().strip()
                # Parsear "14.6 MB/s" o similar
                val = float(speed_str.split()[0])
                metrics['io_write_mb'] = val * metrics['duration_s']
        except Exception as e:
            pass
        # Clean up
        try:
            os.remove("/tmp/wiping_speed.txt")
        except:
            pass

    # Guardar en JSON
    os.makedirs(case_dir, exist_ok=True)
    safe_module = module_name.replace(" ", "_").replace("/", "_")
    out_file = os.path.join(case_dir, f"telemetry_{safe_module}.json")

    with open(out_file, 'w') as f:
        json.dump(metrics, f, indent=4)
        
    print(f"[TELEMETRÍA] Finalizado. Resultados guardados en {out_file}")

    # Llamar al generador de PDF automáticamente
    pdf_script = os.path.join(os.path.dirname(__file__), '10_reporte_telemetria.py')
    if os.path.exists(pdf_script):
        subprocess.Popen([sys.executable, pdf_script, '--caso_dir', case_dir])

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--module", type=str, required=True)
    parser.add_argument("--case_dir", type=str, required=True)
    args = parser.parse_args()

    monitor_process(args.pid, args.module, args.case_dir)
