#!/usr/bin/env python3
"""
Fix env loading so bot.py reads .env directly at startup.
This ensures GEMINI_API_KEY and other keys are always available
regardless of how the bot process is launched.
"""
import sys, subprocess

BOT_PATH = '/home/ubuntu/bot.py'

with open(BOT_PATH, 'r') as f:
    content = f.read()

lines = content.split('\n')
print(f'bot.py: {len(lines)} lines')

# Check if load_dotenv is already called with explicit path
if "load_dotenv('/home/ubuntu/.env'" in content or 'load_dotenv("/home/ubuntu/.env"' in content:
    print('load_dotenv with explicit path already present.')
elif 'load_dotenv()' in content:
    # Replace bare load_dotenv() with explicit path + override
    content = content.replace(
        'load_dotenv()',
        "load_dotenv('/home/ubuntu/.env', override=True)",
        1
    )
    print('Patched: load_dotenv() -> load_dotenv with explicit path + override')
elif 'from dotenv import load_dotenv' in content:
    # load_dotenv imported but not called with path - add explicit call
    content = content.replace(
        'from dotenv import load_dotenv',
        'from dotenv import load_dotenv\nload_dotenv(\'/home/ubuntu/.env\', override=True)',
        1
    )
    print('Added explicit load_dotenv call after import')
else:
    # Add import + call at top, after the existing imports block
    idx = content.find('import os')
    if idx != -1:
        eol = content.find('\n', idx)
        content = content[:eol+1] + "from dotenv import load_dotenv\nload_dotenv('/home/ubuntu/.env', override=True)\n" + content[eol+1:]
        print('Inserted load_dotenv after import os')
    else:
        print('ERROR: could not find import os')
        sys.exit(1)

with open(BOT_PATH, 'w') as f:
    f.write(content)

result = subprocess.run(['python3', '-m', 'py_compile', BOT_PATH], capture_output=True, text=True)
if result.returncode != 0:
    print(f'SYNTAX ERROR: {result.stderr}')
    sys.exit(1)

print('Syntax OK!')

# Now test that env loading works
print('\n=== Testing env loading from .env file ===')
test = subprocess.run(['python3', '-c', '''
from dotenv import load_dotenv
import os
result = load_dotenv("/home/ubuntu/.env", override=True)
print(f"load_dotenv result: {result}")
groq_key = os.getenv("GROQ_API_KEY", "")
gemini_key = os.getenv("GEMINI_API_KEY", "")
print(f"GROQ_API_KEY: {bool(groq_key)} len={len(groq_key)}")
print(f"GEMINI_API_KEY: {bool(gemini_key)} len={len(gemini_key)}")
'''], capture_output=True, text=True)
print(test.stdout)
if test.stderr.strip():
    print('STDERR:', test.stderr[:400])

# Check raw .env file format
print('=== Raw .env file first 5 lines ===')
cat = subprocess.run(['cat', '-A', '/home/ubuntu/.env'], capture_output=True, text=True)
for line in cat.stdout.split('\n')[:8]:
    print(repr(line))

print('\nEnv fix applied successfully.')
