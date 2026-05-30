#!/bin/bash
# ============================================================
# Comando: kiosk
# Inicia el dashboard ForenSys en la pantalla tactil HDMI
# Uso: kiosk
# Para detenerlo: Ctrl+C  (o desde otra terminal: pkill cage)
# ============================================================

export XDG_RUNTIME_DIR=/run/user/$(id -u)
export LIBSEAT_BACKEND=seatd
export WLR_LIBINPUT_NO_DEVICES=1

mkdir -p "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"

echo ""
echo "  ╔══════════════════════════════════╗"
echo "  ║    ForenSys Kiosk - Iniciando    ║"
echo "  ╚══════════════════════════════════╝"
echo "  Dashboard: http://127.0.0.1:5000"
echo "  Para detener: Ctrl+C o 'pkill cage' desde SSH"
echo ""

exec /usr/bin/cage -d -s -- \
    /usr/bin/chromium \
        --kiosk \
        --noerrdialogs \
        --disable-infobars \
        --incognito \
        --no-sandbox \
        --disable-dev-shm-usage \
        --ozone-platform=wayland \
        http://127.0.0.1:5000
