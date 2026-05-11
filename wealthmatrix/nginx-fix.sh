#!/bin/bash
# Inject /wealth/ proxy block into the active Nginx server config
set -e

PORT=3001

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

if sudo grep -q "location /wealth/" "$CONF"; then
  echo "✓ /wealth/ already present — updating port"
  sudo sed -i "s|proxy_pass http://localhost:[0-9]*/;|proxy_pass http://localhost:${PORT}/;|g" "$CONF"
else
  echo "Injecting /wealth/ location block..."
  # Write new block to a temp file
  TMPFILE=$(mktemp)
  sudo cat "$CONF" > "$TMPFILE"

  # Find line number of last closing brace
  LASTLINE=$(grep -n "^}" "$TMPFILE" | tail -1 | cut -d: -f1)

  if [ -z "$LASTLINE" ]; then
    echo "ERROR: Could not find closing brace in config"
    cat "$TMPFILE"
    exit 1
  fi

  # Insert location block before the last closing brace
  sudo sed -i "${LASTLINE}i\\
\\
    location /wealth/ {\\
        proxy_pass http://localhost:${PORT}/;\\
        proxy_http_version 1.1;\\
        proxy_set_header Upgrade \$http_upgrade;\\
        proxy_set_header Connection 'upgrade';\\
        proxy_set_header Host \$host;\\
        proxy_set_header X-Real-IP \$remote_addr;\\
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;\\
        proxy_set_header X-Forwarded-Proto \$scheme;\\
        proxy_cache_bypass \$http_upgrade;\\
        proxy_read_timeout 60s;\\
    }\\
" "$CONF"

  rm -f "$TMPFILE"
fi

echo "--- updated config ---"
sudo cat "$CONF"
echo "----------------------"

sudo nginx -t
sudo systemctl reload nginx
echo "✓ Nginx reloaded successfully"
