import time
import sys
print("[*] Iniciando wiping dummy", flush=True)
for i in range(5):
    time.sleep(0.5)
    print(f"[PROGRESO:{i*20}] {i} GB / 10 GB — 15 MB/s", flush=True)
print("[+] Wiping exitoso", flush=True)
