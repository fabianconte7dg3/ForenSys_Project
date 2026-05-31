#!/bin/bash
# =============================================================================
# ForenSys - Instalador Completo (Sistema + Dependencias + Servicios)
#
# Uso:  sudo bash install_services.sh
#
# Instala:
#   1. Paquetes del sistema (Wayland, herramientas forenses, utilidades)
#   2. Entorno virtual Python y dependencias (requirements.txt)
#   3. Servicios systemd (forensys + kiosk) con arranque automático
#   4. Comando 'kiosk' global en /usr/local/bin
# =============================================================================

set -e

# --- Colores ---
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC}  $1"; }
err()  { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }
step() { echo -e "\n${YELLOW}▶ $1${NC}"; }

# --- Verificar root ---
[ "$EUID" -ne 0 ] && err "Ejecuta este script con sudo: sudo bash $0"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
USER_NAME="${SUDO_USER:-ciber-admin}"
USER_HOME="/home/$USER_NAME"
VENV_DIR="$PROJECT_DIR/venv"

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║       ForenSys - Instalador Completo             ║"
echo "╚══════════════════════════════════════════════════╝"
echo "  Proyecto : $PROJECT_DIR"
echo "  Usuario  : $USER_NAME"
echo ""

# =============================================================================
# PASO 1: Paquetes del Sistema
# =============================================================================
step "1/5 Actualizando repositorios..."
apt-get update -qq
ok "Repositorios actualizados"

step "2/5 Instalando paquetes del sistema..."

# -- Wayland / Kiosko --
PKGS_WAYLAND=(
    cage
    seatd
    chromium-browser
    xwayland
)

# -- Herramientas Forenses --
PKGS_FORENSIC=(
    dc3dd           # Imagen forense bit a bit (reemplaza dd)
    dcfldd          # Alternativa forense a dd
    sleuthkit       # fls, mmls, icat, mactime (análisis de filesystem)
    testdisk        # Recuperación de particiones
    photorec        # Recuperación de archivos borrados
    foremost        # Carving de archivos
    bulk-extractor  # Extracción de artefactos en masa
    adb             # Android Debug Bridge (extracción móvil)
    libusb-1.0-0    # Soporte USB para ADB
)

# -- Python y Utilidades Generales --
PKGS_UTILS=(
    python3
    python3-pip
    python3-venv
    git
    lsblk
    parted
    util-linux      # blkid, fdisk, ionice, etc.
    coreutils
    procps
    curl
    wget
)

echo "  Instalando paquetes Wayland..."
apt-get install -y "${PKGS_WAYLAND[@]}" 2>&1 | grep -E "^Setting|already" || true
ok "Wayland/Kiosko OK"

echo "  Instalando herramientas forenses..."
apt-get install -y "${PKGS_FORENSIC[@]}" 2>&1 | grep -E "^Setting|already" || true
ok "Herramientas forenses OK"

echo "  Instalando utilidades generales..."
apt-get install -y "${PKGS_UTILS[@]}" 2>&1 | grep -E "^Setting|already" || true
ok "Utilidades OK"

# =============================================================================
# PASO 2: Entorno Virtual Python
# =============================================================================
step "3/5 Configurando entorno Python..."

if [ ! -d "$VENV_DIR" ]; then
    echo "  Creando entorno virtual en $VENV_DIR..."
    sudo -u "$USER_NAME" python3 -m venv "$VENV_DIR"
    ok "Entorno virtual creado"
else
    ok "Entorno virtual ya existe"
fi

REQUIREMENTS="$PROJECT_DIR/requirements.txt"
if [ -f "$REQUIREMENTS" ]; then
    echo "  Instalando dependencias Python desde requirements.txt..."
    sudo -u "$USER_NAME" "$VENV_DIR/bin/pip" install --upgrade pip -q
    sudo -u "$USER_NAME" "$VENV_DIR/bin/pip" install -r "$REQUIREMENTS" -q
    ok "Dependencias Python instaladas"
else
    warn "No se encontró requirements.txt — saltando instalación de paquetes Python"
fi

# =============================================================================
# PASO 3: Servicios Systemd
# =============================================================================
step "4/5 Instalando servicios systemd..."

# -- forensys.service (web app Flask) --
cp "$SCRIPT_DIR/forensys.service" /etc/systemd/system/forensys.service
sed -i "s|/home/ciber-admin|$USER_HOME|g" /etc/systemd/system/forensys.service
sed -i "s|User=ciber-admin|User=$USER_NAME|g" /etc/systemd/system/forensys.service
ok "forensys.service instalado"

# -- kiosk.service (navegador Wayland) --
cp "$SCRIPT_DIR/kiosk.service" /etc/systemd/system/kiosk.service
sed -i "s|/home/ciber-admin|$USER_HOME|g" /etc/systemd/system/kiosk.service
sed -i "s|User=ciber-admin|User=$USER_NAME|g" /etc/systemd/system/kiosk.service
ok "kiosk.service instalado"

# -- Auto-login en TTY1 (arranca el kiosko sin intervención) --
mkdir -p /etc/systemd/system/getty@tty1.service.d/
cp "$SCRIPT_DIR/getty_override.conf" /etc/systemd/system/getty@tty1.service.d/override.conf
sed -i "s|ciber-admin|$USER_NAME|g" /etc/systemd/system/getty@tty1.service.d/override.conf
ok "Auto-login en TTY1 configurado"

# -- Recargar systemd y habilitar servicios --
systemctl daemon-reload

systemctl enable --now seatd
ok "seatd habilitado y activo"

# Agregar usuario al grupo video (acceso a /run/seatd.sock)
usermod -aG video "$USER_NAME" 2>/dev/null || true
ok "Usuario $USER_NAME en grupo 'video'"

systemctl enable forensys.service
ok "forensys.service habilitado (arranca en boot)"

systemctl enable kiosk.service
ok "kiosk.service habilitado (arranca en boot)"

# =============================================================================
# PASO 4: Comando 'kiosk' Global
# =============================================================================
step "5/5 Instalando comando 'kiosk'..."
cp "$SCRIPT_DIR/kiosk_cmd.sh" /usr/local/bin/kiosk
chmod +x /usr/local/bin/kiosk
ok "Comando 'kiosk' disponible globalmente"

# =============================================================================
# RESUMEN FINAL
# =============================================================================
echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║     ✅  Instalación completada exitosamente      ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""
echo "  Comandos disponibles:"
echo "    kiosk start    → Inicia la web app + modo kiosko"
echo "    kiosk stop     → Detiene el modo kiosko"
echo "    kiosk status   → Estado de los servicios"
echo ""
echo "  ⚠  Para aplicar cambios de grupo (video), reinicia la sesión o el sistema."
echo "  En el próximo arranque, ForenSys iniciará automáticamente en modo kiosko."
echo ""
