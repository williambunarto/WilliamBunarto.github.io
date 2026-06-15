#!/usr/bin/env python3
"""Idempotent nginx patcher: removes ALL /trade location blocks from healthos,
inserts correct ones. healthos is the default_server for williambunarto.duckdns.org."""
import re, sys

conf = '/etc/nginx/sites-available/healthos'
with open(conf) as f:
    content = f.read()

# Already correctly patched?
if 'location /trade/' in content and 'proxy_pass         http://127.0.0.1:8001/;' in content:
    print('Already correctly patched, skipping.')
    sys.exit(0)

# Remove every line/block that mentions /trade (handles duplicates)
lines = content.splitlines(keepends=True)
output = []
i = 0
skipped_any = False
while i < len(lines):
    line = lines[i]
    if re.match(r'\s*(# WB Trade|location /trade|location = /trade)', line):
        depth = 0
        found_brace = False
        j = i
        while j < len(lines):
            for ch in lines[j]:
                if ch == '{':
                    depth += 1
                    found_brace = True
                elif ch == '}':
                    depth -= 1
            j += 1
            if found_brace and depth == 0:
                break
        if not found_brace:
            j = i + 1
        i = j
        skipped_any = True
    else:
        output.append(line)
        i += 1

if skipped_any:
    print('Removed existing /trade blocks.')

content = ''.join(output)

# location /trade/ with trailing slash: nginx strips /trade/ prefix before forwarding
# /trade/ -> /, /trade/journal -> /journal, etc.
blocks = '''
    # WB Trade
    location = /trade {
        return 301 /trade/;
    }
    location /trade/ {
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

# Insert before the last closing brace of the server block
content = re.sub(r'(\}\s*)$', blocks + r'\1', content.rstrip(), count=1) + '\n'

with open(conf, 'w') as f:
    f.write(content)
print('Nginx config (healthos) patched successfully.')
