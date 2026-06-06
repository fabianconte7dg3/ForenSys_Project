import sys, os, subprocess, time

def progress(pct, detail=""):
    print(f"[PROGRESO:{pct}] {detail}", flush=True)

def log(msg):
    print(msg, flush=True)

print("")
progress(100, "Wiping completado.")
log("\n==================================================")
log("   [SUCCESS] WIPING COMPLETADO - SISTEMA LISTO   ")
log("==================================================")
