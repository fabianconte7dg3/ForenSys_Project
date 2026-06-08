#!/bin/bash
# start_forensys.sh - Lanzador Principal
# Asegura que el entorno portable esté configurado y levanta la aplicación

PROJECT_DIR=$(pwd)

echo "[*] Inicializando ForenSys..."
bash setup_env.sh

if [ $? -ne 0 ]; then
    echo "[X] Error durante la configuración del entorno. Abortando."
    exit 1
fi

echo "[*] Levantando aplicación web..."
cd "$PROJECT_DIR"
source venv/bin/activate
pip install -q -r requirements.txt
python3 web_app/app.py
