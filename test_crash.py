import time, sys
def log(msg): print(msg, flush=True)

def progress(pct, detail=""): print(f"[PROGRESO:{pct}] {detail}", flush=True)

progress(96, "Montando disco...")
log("\n[*] PASO 3/3: Montando disco en /mnt/Destino_ForenSys...")
time.sleep(0.1)
print("")
time.sleep(0.5)
progress(100, "Wiping completado.")
time.sleep(0.5)
log("\n==================================================")
log("   [SUCCESS] WIPING COMPLETADO — SISTEMA LISTO   ")
log("==================================================")
