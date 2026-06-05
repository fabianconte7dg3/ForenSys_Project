#!/bin/bash
# setup_env.sh - Script de Inicialización y Empaquetado Local ForenSys
# Garantiza la portabilidad sin instalar dependencias globales

PROJECT_DIR=$(pwd)
TOOLS_DIR="$PROJECT_DIR/tools_bin"
MARKER="$PROJECT_DIR/.env_setup_done"

if [ -f "$MARKER" ]; then
    echo "[+] El entorno ya fue configurado exitosamente. Saltando setup."
    exit 0
fi

echo "=================================================="
echo "   CONFIGURACIÓN DE ENTORNO PORTABLE FORENSYS   "
echo "=================================================="

echo "[*] 1. Instalando dependencias forenses base en el sistema operativo..."
# Pedimos permisos si es necesario
sudo apt-get update >/dev/null 2>&1
sudo apt-get install -y dc3dd dcfldd testdisk libimobiledevice-utils ideviceinstaller sleuthkit

echo "[*] 2. Configurando permisos SUDO transparentes para los scripts de ForenSys..."
USER_NAME=$(whoami)
SUDOERS_FILE="/etc/sudoers.d/010_forensys_${USER_NAME}"

# Descargar Volatility3 si no existe
echo "   -> Verificando Volatility3..."
if [ ! -d "$PROJECT_DIR/volatility3" ]; then
    echo "   -> Clonando repositorio Volatility3..."
    git clone https://github.com/volatilityfoundation/volatility3.git "$PROJECT_DIR/volatility3" >/dev/null 2>&1
fi

# Solo pedimos contraseña de sudo una vez
echo "   [!] Por favor, ingresa tu contraseña para autorizar la ejecución silenciosa de los scripts (solo ocurrirá esta vez)."
sudo bash -c "echo '$USER_NAME ALL=(ALL) NOPASSWD: $PROJECT_DIR/venv/bin/python3 $PROJECT_DIR/scripts/*.py' > $SUDOERS_FILE"
sudo chmod 0440 "$SUDOERS_FILE"
echo "   [OK] Permisos sudo silenciosos configurados para $PROJECT_DIR/scripts/"

echo "[*] 3. Verificando entorno virtual de Python..."
if [ ! -d "venv" ]; then
    echo "   -> Creando entorno virtual..."
    python3 -m venv venv
fi
echo "   -> Instalando librerías..."
venv/bin/pip install --upgrade pip -q
venv/bin/pip install -r requirements.txt -q
venv/bin/pip install -r requirements-test.txt -q

echo "[*] 4. Compilando estilos Frontend (Tailwind CSS)..."
mkdir -p "$PROJECT_DIR/web_app/tools"
if [ ! -f "$PROJECT_DIR/web_app/tools/tailwindcss" ]; then
    echo "   -> Descargando Tailwind CLI Standalone..."
    curl -sLO https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-linux-arm64
    mv tailwindcss-linux-arm64 "$PROJECT_DIR/web_app/tools/tailwindcss"
    chmod +x "$PROJECT_DIR/web_app/tools/tailwindcss"
fi

if [ -x "$PROJECT_DIR/web_app/tools/tailwindcss" ]; then
    "$PROJECT_DIR/web_app/tools/tailwindcss" -i "$PROJECT_DIR/web_app/static/tailwind-input.css" -o "$PROJECT_DIR/web_app/static/tailwind.css" --minify
    echo "   [OK] CSS compilado exitosamente."
else
    echo "   [!] Error al descargar o dar permisos a Tailwind CLI."
fi

# Marcador de finalización
touch "$MARKER"
echo "=================================================="
echo "   [ÉXITO] ENTORNO PORTABLE LISTO PARA USAR     "
echo "=================================================="
