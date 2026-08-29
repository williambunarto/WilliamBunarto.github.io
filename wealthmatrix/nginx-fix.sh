#!/bin/bash
# Inject /wealth/ and /api/ proxy blocks into the active Nginx server config
set -e

PORT=3001

PROXY_HEADERS='
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection '"'"'upgrade'"'"';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
        proxy_read_timeout 60s;'

# Find the main active config (skip defaults, mime types etc)
CONF=""
for f in /etc/nginx/sites-enabled/*; do
  if sudo grep -q "server_name" "$f" 2>/dev/null; then
    CONF=$(sudo realpath "$f")
    break
  fi
done

if [ -z "$CONF" ]; then
  CONF="/etc/nginx/sites-available/default"
fi

echo "Target config: $CONF"
echo "--- current content ---"
sudo cat "$CONF"
echo "-----------------------"

# ── /wealth/ block ──────────────────────────────────────────
if sudo grep -q "location /wealth/" "$CONF"; then
  echo "✓ /wealth/ already present — updating port"
  sudo sed -i "s|proxy_pass http://localhost:[0-9]*/;|proxy_pass http://localhost:${PORT}/;|g" "$CONF"
else
  echo "Injecting /wealth/ location block..."
  LASTLINE=$(sudo grep -n "^}" "$CONF" | tail -1 | cut -d: -f1)
  sudo sed -i "${LASTLINE}i\\
\\
    location /wealth/ {\\
        proxy_pass http://localhost:${PORT}/;${PROXY_HEADERS}\\
    }\\
" "$CONF"
fi

# ── /api/ block ─────────────────────────────────────────────
# Frontend JS makes absolute calls to /api/* (not /wealth/api/*).
# We need Nginx to proxy these to the app as well.
if sudo grep -q "location /api/" "$CONF"; then
  echo "✓ /api/ already present — updating port"
  sudo sed -i "s|proxy_pass http://localhost:[0-9]*/api/;|proxy_pass http://localhost:${PORT}/api/;|g" "$CONF"
else
  echo "Injecting /api/ location block..."
  LASTLINE=$(sudo grep -n "^}" "$CONF" | tail -1 | cut -d: -f1)
  sudo sed -i "${LASTLINE}i\\
\\
    location /api/ {\\
        proxy_pass http://localhost:${PORT}/api/;${PROXY_HEADERS}\\
    }\\
" "$CONF"
fi

echo "--- updated config ---"
sudo cat "$CONF"
echo "----------------------"

sudo nginx -t
sudo systemctl reload nginx
echo "✓ Nginx reloaded successfully"
