#!/usr/bin/env python3
"""
Fix: call_groq should retry on connection/timeout errors (not just quota errors),
so EOD report AI insights fall back to Gemini instead of showing ❌ AI error.
"""
import sys, subprocess

BOT_PATH = '/home/ubuntu/bot.py'

with open(BOT_PATH, 'r') as f:
    content = f.read()

OLD = (
    '            if any(k in err for k in ("rate_limit", "quota", "429", "limit")):\n'
    '                log.warning(f"Model {model} quota hit, trying next...")\n'
    '                continue\n'
    '            log.error(f"Groq error on {model}: {e}")\n'
    '            return f"❌ AI error: {e}"'
)

NEW = (
    '            if any(k in err for k in ("rate_limit", "quota", "429", "limit",\n'
    '                                       "connection", "timeout", "network",\n'
    '                                       "unreachable", "refused", "reset")):\n'
    '                log.warning(f"Model {model} unavailable ({type(e).__name__}), trying next...")\n'
    '                continue\n'
    '            log.error(f"Groq error on {model}: {e}")\n'
    '            return f"❌ AI error: {e}"'
)

if OLD not in content:
    # Try alternate: maybe already partially patched
    if 'connection' in content and 'quota hit' not in content:
        print('AI error fix already applied.')
        sys.exit(0)
    print('ERROR: Could not find target block to patch. Dumping context...')
    # Print lines around the error return for debugging
    for i, line in enumerate(content.split('\n')):
        if 'AI error' in line or 'quota hit' in line:
            start = max(0, i-5)
            end = min(len(content.split('\n')), i+5)
            for j, l in enumerate(content.split('\n')[start:end], start=start):
                print(f'{j}: {repr(l)}')
            break
    sys.exit(1)

content = content.replace(OLD, NEW, 1)

with open(BOT_PATH, 'w') as f:
    f.write(content)

result = subprocess.run(['python3', '-m', 'py_compile', BOT_PATH], capture_output=True, text=True)
if result.returncode != 0:
    print(f'SYNTAX ERROR after patch: {result.stderr}')
    sys.exit(1)

print('AI error fix applied: connection/timeout errors now retry next model -> Gemini fallback.')
