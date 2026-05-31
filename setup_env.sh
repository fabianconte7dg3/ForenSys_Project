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

echo "[*] 1. Descargando dependencias forenses en modo User-Space (sin instalación global)..."
mkdir -p "$TOOLS_DIR"
cd "$TOOLS_DIR"

# Descargamos los debs y los extraemos en tools_bin
apt-get download dc3dd dcfldd testdisk libimobiledevice-utils ideviceinstaller >/dev/null 2>&1
for deb in *.deb; do
    if [ -f "$deb" ]; then
        echo "   -> Desempaquetando $deb..."
        dpkg -x "$deb" .
        rm "$deb"
    fi
done
cd "$PROJECT_DIR"

echo "[*] 2. Configurando permisos SUDO transparentes para los scripts de ForenSys..."
USER_NAME=$(whoami)
SUDOERS_FILE="/etc/sudoers.d/010_forensys_${USER_NAME}"

# Solo pedimos contraseña de sudo una vez
echo "   [!] Por favor, ingresa tu contraseña para autorizar la ejecución silenciosa de los scripts (solo ocurrirá esta vez)."
sudo bash -c "echo '$USER_NAME ALL=(ALL) NOPASSWD: /usr/bin/python3 $PROJECT_DIR/scripts/*.py' > $SUDOERS_FILE"
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

# Marcador de finalización
touch "$MARKER"
echo "=================================================="
echo "   [ÉXITO] ENTORNO PORTABLE LISTO PARA USAR     "
echo "=================================================="
