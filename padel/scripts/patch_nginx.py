#!/usr/bin/env python3
"""Idempotent nginx patcher: removes ALL /padel location blocks from healthos,
inserts correct ones. healthos is the default_server for williambunarto.duckdns.org.

NOTE: on this server, sites-enabled/healthos and sites-available/healthos are
two independent plain files (NOT a symlink pair, unlike a stock nginx setup —
see wbtrade's deploy workflow, which explicitly copies into both for the same
reason). nginx only ever reads sites-enabled/healthos, so both copies must be
patched identically or the change silently never takes effect while `nginx -t`
still happily validates the untouched sites-enabled copy.
"""
import re, sys

CONF_PATHS = [
    '/etc/nginx/sites-enabled/healthos',
    '/etc/nginx/sites-available/healthos',
]

# location /padel/ with trailing slash: nginx strips /padel/ prefix before forwarding
# /padel/ -> /, /padel/api/... -> /api/..., etc.
BLOCKS = '''
    # Padel Wallet
    location = /padel {
        return 301 /padel/;
    }
    location /padel/ {
        proxy_pass         http://127.0.0.1:8002/;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_read_timeout 60s;
        client_max_body_size 10M;
    }
'''


def patch(conf):
    with open(conf) as f:
        content = f.read()

    if 'location /padel/' in content and 'proxy_pass         http://127.0.0.1:8002/;' in content:
        print(f'{conf}: already correctly patched, skipping.')
        return

    # Remove every line/block that mentions /padel (handles duplicates / re-runs)
    lines = content.splitlines(keepends=True)
    output = []
    i = 0
    skipped_any = False
    while i < len(lines):
        line = lines[i]
        if re.match(r'\s*(# Padel|location /padel|location = /padel)', line):
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
        print(f'{conf}: removed existing /padel blocks.')

    content = ''.join(output)

    # Insert before the last closing brace of the server block
    content = re.sub(r'(\}\s*)$', BLOCKS + r'\1', content.rstrip(), count=1) + '\n'

    with open(conf, 'w') as f:
        f.write(content)
    print(f'{conf}: patched successfully.')


for path in CONF_PATHS:
    patch(path)
