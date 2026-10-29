#!/usr/bin/env bash
# Instala YoTV en cualquier Linux (PS4 con Linux, una compu vieja, una Raspberry Pi)
# y lo deja corriendo como servicio que arranca solo al prender el equipo.
# Uso:  bash instalar-linux.sh
set -e
cd "$(dirname "$0")"
CARPETA="$PWD"

need() { command -v "$1" >/dev/null 2>&1; }
if ! need ffmpeg || ! need python3 || ! { need node || need deno; }; then
  echo "== Instalando python3, ffmpeg y nodejs =="
  if need apt-get; then sudo apt-get update && sudo apt-get install -y python3 python3-venv ffmpeg nodejs
  elif need pacman; then sudo pacman -Sy --noconfirm python ffmpeg nodejs
  elif need dnf; then sudo dnf install -y python3 ffmpeg nodejs
  else echo "Instala a mano: python3, ffmpeg y nodejs"; exit 1; fi
fi

echo "== Entorno de Python =="
python3 -m venv .venv
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install --upgrade -r requirements.txt -q
[ -f config.toml ] || cp config.ejemplo.toml config.toml

if need systemctl; then
  echo "== Servicio que arranca solo =="
  sudo tee /etc/systemd/system/yotv.service >/dev/null <<EOF
[Unit]
Description=YoTV - canal personal de YouTube para la tele
After=network-online.target
Wants=network-online.target

[Service]
User=$USER
WorkingDirectory=$CARPETA
EnvironmentFile=-$CARPETA/.env
ExecStart=$CARPETA/.venv/bin/python -m yotv correr
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
EOF
  sudo systemctl daemon-reload
  sudo systemctl enable --now yotv
  echo "Servicio activo. Ver mensajes:  journalctl -u yotv -f"
else
  echo "Arranca con:  .venv/bin/python -m yotv correr"
fi

IP=$(hostname -I 2>/dev/null | awk '{print $1}')
echo
echo "En la app de la tele pon como servidor:  http://${IP:-IP-DE-ESTE-EQUIPO}:8765"
echo "Pon tu API key de Claude en $CARPETA/.env así:  ANTHROPIC_API_KEY=sk-ant-..."
