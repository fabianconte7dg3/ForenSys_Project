#!/bin/bash
# =============================================================================
# ForenSys - Instalador de servicios y comando kiosk
# Ejecutar con: sudo bash install_services.sh
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
USER_NAME="ciber-admin"

echo "=============================================="
echo "  ForenSys - Instalador de Servicios"
echo "=============================================="
echo "Directorio del proyecto: $PROJECT_DIR"
echo ""

# 1. Instalar forensys.service (web app Flask)
echo "[1/4] Instalando forensys.service..."
cp "$SCRIPT_DIR/forensys.service" /etc/systemd/system/forensys.service
# Ajustar ruta al usuario real
sed -i "s|/home/ciber-admin|/home/$USER_NAME|g" /etc/systemd/system/forensys.service
sed -i "s|User=ciber-admin|User=$USER_NAME|g" /etc/systemd/system/forensys.service
echo "      OK"

# 2. Instalar kiosk.service (navegador Wayland)
echo "[2/4] Instalando kiosk.service..."
cp "$SCRIPT_DIR/kiosk.service" /etc/systemd/system/kiosk.service
sed -i "s|/home/ciber-admin|/home/$USER_NAME|g" /etc/systemd/system/kiosk.service
sed -i "s|User=ciber-admin|User=$USER_NAME|g" /etc/systemd/system/kiosk.service
echo "      OK"

# 3. Instalar override para auto-login en TTY1 (arranca kiosko sin login manual)
echo "[3/4] Configurando auto-login en TTY1..."
mkdir -p /etc/systemd/system/getty@tty1.service.d/
cp "$SCRIPT_DIR/getty_override.conf" /etc/systemd/system/getty@tty1.service.d/override.conf
sed -i "s|ciber-admin|$USER_NAME|g" /etc/systemd/system/getty@tty1.service.d/override.conf
echo "      OK"

# 4. Instalar el comando 'kiosk' en /usr/local/bin
echo "[4/4] Instalando comando 'kiosk'..."
cp "$SCRIPT_DIR/kiosk_cmd.sh" /usr/local/bin/kiosk
chmod +x /usr/local/bin/kiosk
echo "      OK"

# Recargar systemd y habilitar servicios
echo ""
echo "Recargando systemd..."
systemctl daemon-reload

echo "Habilitando seatd (gestor de asientos Wayland)..."
systemctl enable --now seatd

echo "Habilitando forensys.service (arranca en boot)..."
systemctl enable forensys.service

echo "Habilitando kiosk.service (arranca en boot)..."
systemctl enable kiosk.service

echo ""
echo "=============================================="
echo "  Instalación completada exitosamente!"
echo "=============================================="
echo ""
echo "Comandos disponibles:"
echo "  kiosk start   → Inicia el modo kiosko"
echo "  kiosk stop    → Detiene el modo kiosko"
echo "  kiosk status  → Estado de los servicios"
echo ""
echo "Los servicios arrancarán automáticamente en el próximo reinicio."
echo "Para iniciar ahora sin reiniciar, ejecuta:"
echo "  sudo systemctl start forensys.service"
echo "  sudo systemctl start kiosk.service"
echo ""
