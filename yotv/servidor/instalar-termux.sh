#!/data/data/com.termux/files/usr/bin/bash
# Instala y arranca YoTV dentro de la tele usando Termux.
# Uso (dentro de Termux, en la carpeta del servidor):  bash instalar-termux.sh
set -e
cd "$(dirname "$0")"

echo "== Instalando Python, ffmpeg y Node (para el reto de JavaScript de YouTube) =="
pkg update -y
pkg install -y python ffmpeg nodejs

echo "== Instalando yt-dlp y el SDK de Claude =="
pip install --upgrade -r requirements.txt

[ -f config.toml ] || cp config.ejemplo.toml config.toml

# Arranque automático cuando la tele se prende (requiere la app Termux:Boot).
mkdir -p ~/.termux/boot
cat > ~/.termux/boot/yotv.sh <<EOF
#!/data/data/com.termux/files/usr/bin/bash
termux-wake-lock
cd "$PWD"
python -m yotv correr >> yotv.log 2>&1
EOF
chmod +x ~/.termux/boot/yotv.sh

echo
echo "Listo. Para arrancar ahora:   termux-wake-lock; python -m yotv correr"
echo "Edita config.toml (nano config.toml) y copia tu cookies.txt en esta carpeta."
