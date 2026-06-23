#!/usr/bin/env python3
"""
Migrate bot.py from deprecated google.generativeai to google.genai SDK.
Safe approach: read current state, fix any prior partial patches, apply cleanly.
"""
import sys, subprocess, re

BOT_PATH = '/home/ubuntu/bot.py'

# First install the new SDK
print('Installing google-genai SDK...')
result = subprocess.run(
    ['pip3', 'install', 'google-genai', '-q'],
    capture_output=True, text=True
)
print(result.stdout.strip() or result.stderr.strip() or 'ok')

with open(BOT_PATH, 'r') as f:
    content = f.read()

# Show current state around the known problem line
lines = content.split('\n')
print(f'\nbot.py has {len(lines)} lines')
print('Lines 110-125:')
for i, l in enumerate(lines[109:125], start=110):
    print(f'  {i}: {repr(l)}')

# --- Fix 1: Repair IndentationError from previous partial patch ---
# The genai.configure replacement left `if GEMINI_API_KEY:` with only a comment body
# Comments are not valid statements - need `pass`
if '# genai configured per-call via genai_sdk.Client(api_key=...)' in content:
    content = content.replace(
        '# genai configured per-call via genai_sdk.Client(api_key=...)',
        'pass  # genai_sdk.Client(api_key=GEMINI_API_KEY) used per-call'
    )
    print('Fixed: empty if-block comment -> pass')

# Also catch the raw configure line if not yet replaced
if 'genai.configure(api_key=GEMINI_API_KEY)' in content:
    content = content.replace(
        'genai.configure(api_key=GEMINI_API_KEY)',
        'pass  # genai_sdk.Client(api_key=GEMINI_API_KEY) used per-call'
    )
    print('Fixed: genai.configure -> pass')

# --- Fix 2: Replace import if still using old SDK ---
if 'import google.generativeai as genai' in content:
    content = content.replace(
        'import google.generativeai as genai',
        'from google import genai as genai_sdk\nfrom google.genai import types as genai_types',
        1
    )
    print('Replaced import: google.generativeai -> google.genai')
elif 'from google import genai as genai_sdk' in content:
    print('Import already migrated OK.')
else:
    print('WARNING: genai import line not found - check manually')

# --- Fix 3: Replace call_gemini function body if still using old SDK call ---
if 'genai.GenerativeModel' in content or 'genai_sdk.GenerativeModel' in content:
    # Find call_gemini
    idx = content.find('def call_gemini(')
    if idx == -1:
        print('ERROR: call_gemini not found')
        sys.exit(1)
    
    func_end = content.find('\ndef ', idx + 10)
    if func_end == -1:
        func_end = len(content)
    func_body = content[idx:func_end]
    
    # Build replacement - keep the signature and early returns, replace the try block
    # Find if-not-key guard
    guard_end = func_body.find('\n    try:')
    if guard_end == -1:
        print('ERROR: try block not found in call_gemini')
        print('Function body (first 500 chars):', repr(func_body[:500]))
        sys.exit(1)
    
    preamble = func_body[:guard_end]  # everything up to try:
    
    # Find end of try block - look for `except` at 4-space indent
    except_pos = func_body.find('\n    except ', guard_end)
    if except_pos == -1:
        except_pos = func_body.find('\n    except:', guard_end)
    
    if except_pos == -1:
        print('ERROR: except block not found in call_gemini')
        sys.exit(1)
    
    # Get except block through end of function
    except_block = func_body[except_pos:]
    
    # Rebuild the function
    new_try_block = '''
    try:
        client = genai_sdk.Client(api_key=GEMINI_API_KEY)
        gemini_msgs = []
        for m in messages:
            role = 'user' if m.get('role') == 'user' else 'model'
            gemini_msgs.append(
                genai_types.Content(
                    role=role,
                    parts=[genai_types.Part(text=str(m.get('content', '')))]
                )
            )
        resp = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=gemini_msgs,
            config=genai_types.GenerateContentConfig(
                system_instruction=system,
                max_output_tokens=max_tokens,
                temperature=0.7,
            )
        )
        return resp.text'''
    
    new_func = preamble + new_try_block + except_block
    content = content[:idx] + new_func + content[func_end:]
    print('call_gemini updated to google.genai SDK.')
else:
    print('call_gemini API calls already migrated or not found with old pattern.')

# --- Fix 4: Replace analyze_image_gemini_sync if still using old _genai ---
if 'import google.generativeai as _genai' in content:
    OLD_IMG = '''        import google.generativeai as _genai
        model = _genai.GenerativeModel('gemini-2.5-flash')
        prompt = question if question.strip() else 'Describe this image in detail.'
        response = model.generate_content([
            prompt,
            {"mime_type": "image/jpeg", "data": image_bytes}
        ])
        return response.text'''
    NEW_IMG = '''        from google import genai as _genai_sdk
        from google.genai import types as _gtypes
        _client = _genai_sdk.Client(api_key=GEMINI_API_KEY)
        _resp = _client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[
                _gtypes.Content(parts=[
                    _gtypes.Part(text=question if question.strip() else 'Describe this image in detail.'),
                    _gtypes.Part(inline_data=_gtypes.Blob(mime_type='image/jpeg', data=image_bytes))
                ])
            ]
        )
        return _resp.text'''
    if OLD_IMG in content:
        content = content.replace(OLD_IMG, NEW_IMG, 1)
        print('analyze_image_gemini_sync updated.')
    else:
        print('WARNING: analyze_image_gemini_sync old pattern not matched exactly.')
        # Try a simpler targeted replacement
        if "import google.generativeai as _genai" in content:
            content = content.replace(
                'import google.generativeai as _genai\n        model = _genai.GenerativeModel',
                'from google import genai as _genai_sdk\n        model = _genai_sdk',
            )
            print('Applied partial analyze_image fix.')
else:
    print('analyze_image_gemini_sync: old import not present, skipping.')

with open(BOT_PATH, 'w') as f:
    f.write(content)

# Verify syntax
result = subprocess.run(['python3', '-m', 'py_compile', BOT_PATH], capture_output=True, text=True)
if result.returncode != 0:
    print(f'SYNTAX ERROR: {result.stderr}')
    # Show lines around error
    import re as _re
    m = _re.search(r'line (\d+)', result.stderr)
    if m:
        err_line = int(m.group(1))
        lines = content.split('\n')
        for i, l in enumerate(lines[max(0,err_line-5):err_line+5], start=max(1,err_line-4)):
            print(f'  {i}: {repr(l)}')
    sys.exit(1)

print('Syntax OK!')

# Live test
print('\nTesting Gemini API with new SDK...')
test = subprocess.run(['python3', '-c', '''
import os
from dotenv import load_dotenv
load_dotenv("/home/ubuntu/.env")
key = os.getenv("GEMINI_API_KEY", "")
print(f"GEMINI_API_KEY present: {bool(key)} (len={len(key)})")
if key:
    try:
        from google import genai as sdk
        from google.genai import types as t
        c = sdk.Client(api_key=key)
        r = c.models.generate_content(
            model="gemini-2.5-flash",
            contents="Reply with just the word OK"
        )
        print(f"Gemini response: {r.text.strip()[:80]}")
        print("GEMINI: WORKING")
    except Exception as e:
        print(f"Gemini ERROR: {type(e).__name__}: {e}")
else:
    print("ERROR: GEMINI_API_KEY not in .env")
'''], capture_output=True, text=True)
print(test.stdout)
if test.stderr:
    print('STDERR:', test.stderr[:300])

# Test Groq too
print('Testing Groq API...')
groq_test = subprocess.run(['python3', '-c', '''
import os
from dotenv import load_dotenv
load_dotenv("/home/ubuntu/.env")
key = os.getenv("GROQ_API_KEY", "")
print(f"GROQ_API_KEY present: {bool(key)} (len={len(key)})")
if key:
    try:
        from groq import Groq
        c = Groq(api_key=key)
        r = c.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role":"user","content":"Reply with just the word OK"}],
            max_tokens=5
        )
        print(f"Groq response: {r.choices[0].message.content.strip()}")
        print("GROQ: WORKING")
    except Exception as e:
        print(f"Groq ERROR: {type(e).__name__}: {e}")
'''], capture_output=True, text=True)
print(groq_test.stdout)
if groq_test.stderr:
    print('STDERR:', groq_test.stderr[:300])

print('\nMigration complete. Ready to restart bot.')
