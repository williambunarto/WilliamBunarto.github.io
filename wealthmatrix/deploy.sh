#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  WealthMatrix v2 — Deploy to /wealth/ subpath
#  Domain: williambunarto.duckdns.org/wealth/
# ═══════════════════════════════════════════════════════════════
set -e

APP_DIR="$HOME/wealthmatrix"
APP_NAME="wealthmatrix"
PORT=3001

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║     WealthMatrix v2 — /wealth/ Subpath Deploy       ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

echo "[1/6] Checking system packages..."
sudo apt-get update -qq
sudo apt-get install -y -qq curl nginx

if ! command -v node &>/dev/null || [[ "$(node -v | cut -d. -f1 | tr -d 'v')" -lt "18" ]]; then
  echo "[2/6] Installing Node.js 20 LTS..."
  curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
  sudo apt-get install -y nodejs
else
  echo "[2/6] Node.js $(node -v) already installed."
fi

if ! command -v pm2 &>/dev/null; then
  echo "[3/6] Installing PM2..."
  sudo npm install -g pm2
else
  echo "[3/6] PM2 already installed."
fi

echo "[4/6] Installing app dependencies..."
cd "$APP_DIR"
npm install --production 2>&1 | tail -5
mkdir -p data uploads

echo "[5/6] Starting WealthMatrix on port $PORT..."
pm2 delete "$APP_NAME" 2>/dev/null || true
PORT=$PORT BASE_PATH=/wealth pm2 start server.js \
  --name "$APP_NAME" \
  --restart-delay=3000 \
  --max-restarts=10
pm2 save
pm2 startup 2>/dev/null | grep sudo | bash 2>/dev/null || true

echo "[6/6] Configuring Nginx /wealth/ location..."
NGINX_CONF="/etc/nginx/sites-available/williambunarto"

if [ ! -f "$NGINX_CONF" ]; then
  sudo tee "$NGINX_CONF" > /dev/null <<NGINX
server {
    listen 80;
    server_name williambunarto.duckdns.org;
    client_max_body_size 30M;

    location /wealth/ {
        proxy_pass http://localhost:$PORT/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_cache_bypass \$http_upgrade;
        proxy_read_timeout 60s;
    }

    location / {
        return 200 'OK';
        add_header Content-Type text/plain;
    }
}
NGINX
  sudo ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/
  sudo rm -f /etc/nginx/sites-enabled/default
else
  if ! grep -q "location /wealth/" "$NGINX_CONF"; then
    echo ""
    echo "⚠  Existing Nginx config found. Add this block inside your server {} in $NGINX_CONF:"
    echo ""
    echo "    location /wealth/ {"
    echo "        proxy_pass http://localhost:$PORT/;"
    echo "        proxy_http_version 1.1;"
    echo "        proxy_set_header Host \$host;"
    echo "        proxy_set_header X-Real-IP \$remote_addr;"
    echo "        proxy_cache_bypass \$http_upgrade;"
    echo "    }"
    echo ""
  else
    sudo sed -i "s|proxy_pass http://localhost:[0-9]*/;|proxy_pass http://localhost:$PORT/;|" "$NGINX_CONF"
    echo "   Updated port to $PORT in existing config."
  fi
fi

sudo nginx -t && sudo systemctl reload nginx

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  ✓ WealthMatrix deployed!                           ║"
echo "╠══════════════════════════════════════════════════════╣"
echo "║  URL  : https://williambunarto.duckdns.org/wealth/  ║"
echo "║  Login: williambunarto / william123                  ║"
echo "║  Port : 3001 (internal)                             ║"
echo "║  Logs : pm2 logs wealthmatrix                       ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
