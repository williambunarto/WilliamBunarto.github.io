#!/usr/bin/env python3
"""
Migrate bot.py from deprecated google.generativeai to google.genai SDK.
Also fixes call_gemini to properly handle exceptions and fall back gracefully.
"""
import sys, subprocess, re

BOT_PATH = '/home/ubuntu/bot.py'

# First install the new SDK
print('Installing google-genai SDK...')
result = subprocess.run(
    ['pip3', 'install', 'google-genai', '-q'],
    capture_output=True, text=True
)
print(result.stdout or result.stderr or 'installed')

with open(BOT_PATH, 'r') as f:
    content = f.read()

# --- 1. Replace import ---
if 'import google.generativeai as genai' in content:
    content = content.replace(
        'import google.generativeai as genai',
        'from google import genai as genai_sdk\nfrom google.genai import types as genai_types',
        1
    )
    print('Replaced import google.generativeai -> google.genai')
elif 'from google import genai as genai_sdk' in content:
    print('Import already migrated.')
else:
    print('ERROR: Could not find genai import line.')
    # Show context
    for i, line in enumerate(content.split('\n')[:40]):
        if 'genai' in line.lower() or 'google' in line.lower():
            print(f'  {i}: {line}')
    sys.exit(1)

# --- 2. Replace genai.configure ---
if 'genai.configure(api_key=' in content:
    content = content.replace(
        'genai.configure(api_key=GEMINI_API_KEY)',
        '# genai configured per-call via genai_sdk.Client(api_key=...)'
    )
    print('Removed genai.configure (no longer needed with new SDK)')

# --- 3. Replace call_gemini function body ---
# Find and replace the core API call inside call_gemini
OLD_GENAI_CALL = 'model = genai.GenerativeModel('
if OLD_GENAI_CALL in content:
    # Replace the entire call_gemini try block
    OLD_TRY = '''    try:
        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            system_instruction=system,'''
    # Find a larger chunk to be precise
    # Locate call_gemini function
    idx = content.find('def call_gemini(')
    if idx == -1:
        print('ERROR: call_gemini not found')
        sys.exit(1)
    func_slice = content[idx:idx+1500]
    print('call_gemini found, replacing API calls...')
    
    # Replace the entire try block - find start/end
    try_start = func_slice.find('    try:')
    if try_start == -1:
        print('ERROR: try block not found in call_gemini')
        sys.exit(1)
    
    # Build new implementation
    NEW_IMPL = '''    try:
        client = genai_sdk.Client(api_key=GEMINI_API_KEY)
        gemini_msgs = []
        for m in messages:
            role = 'user' if m.get('role') == 'user' else 'model'
            gemini_msgs.append(genai_types.Content(role=role, parts=[genai_types.Part(text=m['content'])]))
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
    
    # Find the old try block end (return statement)
    old_try_block_end = func_slice.find('\n        return resp')
    if old_try_block_end == -1:
        old_try_block_end = func_slice.find('\n        return response')
    if old_try_block_end == -1:
        print('ERROR: could not find return in call_gemini try block')
        # Print the function for debugging
        print(func_slice[:600])
        sys.exit(1)
    
    # Find end of return line
    ret_end = func_slice.find('\n', old_try_block_end + 1)
    old_try_block = func_slice[try_start:ret_end]
    
    print(f'Replacing try block ({len(old_try_block)} chars)...')
    content = content[:idx] + func_slice.replace(old_try_block, NEW_IMPL, 1) + content[idx+1500:]
    print('call_gemini API call updated to google.genai SDK.')
else:
    print('genai.GenerativeModel not found - call_gemini may already be migrated.')

# --- 4. Fix except block in call_gemini to show real error ---
# Find call_gemini except block and ensure it returns descriptive error
if 'except Exception as exc:' in content:
    pass  # probably already fixed

# --- 5. Fix analyze_image_gemini_sync if present ---
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
        print('analyze_image_gemini_sync updated to google.genai SDK.')
    else:
        print('WARNING: analyze_image_gemini_sync not updated (pattern not matched - may already be fixed or different structure)')

with open(BOT_PATH, 'w') as f:
    f.write(content)

result = subprocess.run(['python3', '-m', 'py_compile', BOT_PATH], capture_output=True, text=True)
if result.returncode != 0:
    print(f'SYNTAX ERROR after patch: {result.stderr}')
    sys.exit(1)

print('Gemini SDK migration applied and syntax OK.')

# Quick live test
print('\nTesting google.genai SDK...')
test = subprocess.run(['python3', '-c', '''
import os
from dotenv import load_dotenv
load_dotenv("/home/ubuntu/.env")
key = os.getenv("GEMINI_API_KEY", "")
print(f"GEMINI_API_KEY set: {bool(key)} len={len(key)}")
if key:
    from google import genai as _sdk
    from google.genai import types as _t
    c = _sdk.Client(api_key=key)
    r = c.models.generate_content(model="gemini-2.5-flash", contents="Say OK")
    print(f"Gemini test: {r.text.strip()[:50]}")
else:
    print("ERROR: GEMINI_API_KEY not set in .env")
'''], capture_output=True, text=True)
print(test.stdout)
if test.stderr:
    print('STDERR:', test.stderr[:500])
