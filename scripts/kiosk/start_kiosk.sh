#!/bin/bash
# ============================================================
# Comando: kiosk
# Inicia el dashboard ForenSys en la pantalla táctil HDMI
# Uso: kiosk
# Para detenerlo: Ctrl+C  (o desde otra terminal: pkill cage)
# ============================================================

export XDG_RUNTIME_DIR=/run/user/$(id -u)
export LIBSEAT_BACKEND=seatd

# Forzar card1 = RP1 que maneja HDMI en Raspberry Pi 5
export WLR_DRM_DEVICES=/dev/dri/card1

# Sin dispositivos de entrada virtuales (evita errores de libinput en SSH)
export WLR_LIBINPUT_NO_DEVICES=1

mkdir -p "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"

echo ""
echo "  ╔══════════════════════════════════════════╗"
echo "  ║      ForenSys Kiosk — Iniciando          ║"
echo "  ║  Dashboard: http://127.0.0.1:5000        ║"
echo "  ║  Para detener: Ctrl+C  ó  pkill cage     ║"
echo "  ╚══════════════════════════════════════════╝"
echo ""

exec cage -s -- \
    /usr/bin/chromium \
        --kiosk \
        --noerrdialogs \
        --disable-infobars \
        --incognito \
        --no-sandbox \
        --disable-dev-shm-usage \
        --ozone-platform=wayland \
        --disable-gpu \
        --disable-software-rasterizer \
        --ignore-gpu-blocklist \
        --use-gl=egl \
        http://127.0.0.1:5000
