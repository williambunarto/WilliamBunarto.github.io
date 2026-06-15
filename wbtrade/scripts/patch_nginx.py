#!/usr/bin/env python3
import re, sys

conf = '/etc/nginx/sites-available/default'
with open(conf) as f:
    content = f.read()

# If already correctly patched (with trailing slash), nothing to do
if 'location /trade {' in content and 'proxy_pass         http://127.0.0.1:8001/;' in content:
    print('Already correctly patched, skipping.')
    sys.exit(0)

# Remove any existing /trade blocks (may have wrong proxy_pass without trailing slash)
content = re.sub(
    r'\n\s*# WB Trade\n.*?location /trade/uploads \{.*?\}\n',
    '\n',
    content,
    flags=re.DOTALL
)

blocks = '''
    # WB Trade
    location /trade {
        proxy_pass         http://127.0.0.1:8001/;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_read_timeout 60s;
        client_max_body_size 20M;
    }
    location /trade/static {
        alias /home/ubuntu/wbtrade/static;
        expires 1h;
    }
    location /trade/uploads {
        alias /home/ubuntu/wbtrade/uploads;
        expires 7d;
    }
'''

content = re.sub(r'(\}\s*$)', blocks + r'\1', content, count=1)
with open(conf, 'w') as f:
    f.write(content)
print('Nginx config patched successfully.')
