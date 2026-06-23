#!/usr/bin/env python3
"""
Replace decommissioned llama3-8b-8192 with llama-3.1-8b-instant in bot.py GROQ_MODELS list.
"""
import sys, subprocess

BOT_PATH = '/home/ubuntu/bot.py'

with open(BOT_PATH, 'r') as f:
    content = f.read()

if 'llama3-8b-8192' not in content:
    if 'llama-3.1-8b-instant' in content:
        print('llama3-8b-8192 already replaced. Nothing to do.')
    else:
        print('llama3-8b-8192 not found in bot.py. May already be patched.')
    sys.exit(0)

content = content.replace('llama3-8b-8192', 'llama-3.1-8b-instant')

with open(BOT_PATH, 'w') as f:
    f.write(content)

result = subprocess.run(['python3', '-m', 'py_compile', BOT_PATH], capture_output=True, text=True)
if result.returncode != 0:
    print(f'SYNTAX ERROR after patch: {result.stderr}')
    sys.exit(1)

print('Patched: llama3-8b-8192 -> llama-3.1-8b-instant')
