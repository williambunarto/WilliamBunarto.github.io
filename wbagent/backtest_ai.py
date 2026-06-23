#!/usr/bin/env python3
"""
Backtest AI calls - simulate exactly what scheduled_open_pulse and
scheduled_eod_report do when they call the AI for stock insights.
Runs against live APIs to confirm they are working before next scheduled task.
"""
import sys, os
sys.path.insert(0, '/home/ubuntu')

# Load .env first (same as bot.py now does)
from dotenv import load_dotenv
loaded = load_dotenv('/home/ubuntu/.env', override=True)
print(f'load_dotenv loaded file: {loaded}')

GROQ_API_KEY = os.getenv('GROQ_API_KEY', '')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')
print(f'GROQ_API_KEY: {bool(GROQ_API_KEY)} (len={len(GROQ_API_KEY)})')
print(f'GEMINI_API_KEY: {bool(GEMINI_API_KEY)} (len={len(GEMINI_API_KEY)})')

if not GROQ_API_KEY and not GEMINI_API_KEY:
    print('\nERROR: No API keys loaded from .env. Checking shell env...')
    print(f'Shell GROQ: {bool(os.environ.get("GROQ_API_KEY",""))}')
    print(f'Shell GEMINI: {bool(os.environ.get("GEMINI_API_KEY",""))}')
    print('\nTrying to read .env directly...')
    try:
        with open('/home/ubuntu/.env') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k in ('GROQ_API_KEY', 'GEMINI_API_KEY'):
                        os.environ[k] = v
                        print(f'  Manually loaded {k}: len={len(v)}')
        GROQ_API_KEY = os.getenv('GROQ_API_KEY', '')
        GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')
        print(f'After manual load: GROQ={bool(GROQ_API_KEY)} GEMINI={bool(GEMINI_API_KEY)}')
    except Exception as e:
        print(f'Manual read failed: {e}')

all_ok = True

# --- Test 1: Groq llama-3.3-70b ---
print('\n=== Test 1: Groq llama-3.3-70b-versatile ===')
if GROQ_API_KEY:
    try:
        from groq import Groq
        client = Groq(api_key=GROQ_API_KEY)
        r = client.chat.completions.create(
            model='llama-3.3-70b-versatile',
            messages=[{'role': 'user', 'content': 'Give a 1-sentence stock market outlook.'}],
            max_tokens=60
        )
        print(f'PASS: {r.choices[0].message.content.strip()}')
    except Exception as e:
        print(f'FAIL: {type(e).__name__}: {e}')
        all_ok = False
else:
    print('SKIP: no GROQ_API_KEY')
    all_ok = False

# --- Test 2: Groq llama3-8b (fallback model) ---
print('\n=== Test 2: Groq llama3-8b-8192 (fallback) ===')
if GROQ_API_KEY:
    try:
        from groq import Groq
        client = Groq(api_key=GROQ_API_KEY)
        r = client.chat.completions.create(
            model='llama3-8b-8192',
            messages=[{'role': 'user', 'content': 'Reply: OK'}],
            max_tokens=5
        )
        print(f'PASS: {r.choices[0].message.content.strip()}')
    except Exception as e:
        print(f'FAIL: {type(e).__name__}: {e}')
else:
    print('SKIP: no GROQ_API_KEY')

# --- Test 3: Gemini (new SDK) ---
print('\n=== Test 3: Gemini 2.5-flash (google.genai SDK) ===')
if GEMINI_API_KEY:
    try:
        from google import genai as genai_sdk
        from google.genai import types as genai_types
        client = genai_sdk.Client(api_key=GEMINI_API_KEY)
        r = client.models.generate_content(
            model='gemini-2.5-flash',
            contents='Give a 1-sentence stock market outlook.'
        )
        print(f'PASS: {r.text.strip()[:120]}')
    except Exception as e:
        print(f'FAIL: {type(e).__name__}: {e}')
        all_ok = False
else:
    print('SKIP: no GEMINI_API_KEY')
    all_ok = False

# --- Test 4: Simulate call_groq -> call_gemini fallback chain ---
print('\n=== Test 4: Full fallback chain (simulate EOD report AI call) ===')
try:
    import importlib.util, types
    # Quick simulation of call_groq + call_gemini
    MODELS = ['llama-3.3-70b-versatile', 'llama3-8b-8192', 'gemma2-9b-it']
    SYSTEM = 'You are a financial analyst. Be concise.'
    test_messages = [{'role': 'user', 'content': 'BBCA.JK current price Rp6225. Sentiment?'}]
    
    result = None
    for model in MODELS:
        try:
            from groq import Groq
            c = Groq(api_key=GROQ_API_KEY)
            resp = c.chat.completions.create(
                model=model, messages=[{'role': 'system', 'content': SYSTEM}] + test_messages, max_tokens=80
            )
            result = resp.choices[0].message.content.strip()
            print(f'PASS via Groq/{model}: {result[:100]}')
            break
        except Exception as e:
            err = str(e).lower()
            if any(k in err for k in ('connection', 'timeout', 'quota', 'rate', '429', 'limit', 'network', 'refused', 'reset')):
                print(f'  Groq/{model} retry: {type(e).__name__}')
                continue
            print(f'  Groq/{model} hard fail: {e}')
            break
    
    if result is None:
        print('  All Groq models failed, trying Gemini fallback...')
        if GEMINI_API_KEY:
            from google import genai as genai_sdk
            from google.genai import types as genai_types
            client = genai_sdk.Client(api_key=GEMINI_API_KEY)
            gemini_msgs = [genai_types.Content(role='user', parts=[genai_types.Part(text='BBCA.JK current price Rp6225. Sentiment?')])]
            resp = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=gemini_msgs,
                config=genai_types.GenerateContentConfig(system_instruction=SYSTEM, max_output_tokens=80)
            )
            result = resp.text.strip()
            print(f'PASS via Gemini fallback: {result[:100]}')
        else:
            print('FAIL: No GEMINI_API_KEY for fallback')
            all_ok = False
except Exception as e:
    print(f'Test 4 ERROR: {e}')
    all_ok = False

print(f'\n=== BACKTEST RESULT: {"ALL PASS - Ready for next scheduled task" if all_ok else "SOME TESTS FAILED - Needs attention"} ===')
sys.exit(0 if all_ok else 1)
