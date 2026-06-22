#!/usr/bin/env python3
"""Patch bot.py to read GROQ_API_KEY from environment instead of hardcode.
Expects GROQ_API_KEY in environment (injected by CI workflow).
"""
import sys, os, re

BOT_PATH = '/home/ubuntu/bot.py'

with open(BOT_PATH, 'r') as f:
    content = f.read()

# Idempotency: already reads from env
if 'os.environ.get("GROQ_API_KEY"' in content:
    print('Already patched -- nothing to do.')
    sys.exit(0)

# Replace hardcoded GROQ_API_KEY with env read
# Matches: GROQ_API_KEY = "gsk_..."
content = re.sub(
    r'GROQ_API_KEY\s*=\s*"gsk_[^"]+"',
    'GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")  # loaded from .env via shell',
    content,
    count=1
)

if 'os.environ.get("GROQ_API_KEY"' not in content:
    print('ERROR: replacement did not apply -- aborting')
    sys.exit(1)

with open(BOT_PATH, 'w') as f:
    f.write(content)

print('GROQ_API_KEY env patch applied OK')
