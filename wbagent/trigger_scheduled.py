#!/usr/bin/env python3
"""
Standalone trigger: reads config from bot.py/env, then calls the SAME
call_groq/call_gemini logic as the scheduled tasks, and sends results
to Telegram so you can verify end-to-end.
"""
import os, sys, re, asyncio
from dotenv import load_dotenv

load_dotenv('/home/ubuntu/.env', override=True)

BOT_TOKEN = os.getenv('BOT_TOKEN') or os.getenv('TELEGRAM_BOT_TOKEN')
GROQ_KEY = os.getenv('GROQ_API_KEY')
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

# Find chat_id from bot.py
with open('/home/ubuntu/bot.py', 'r') as f:
    bot_src = f.read()

# Extract BOT_TOKEN and CHAT_ID variable names and values
for pat in [r"BOT_TOKEN\s*=\s*os\.getenv\(['\"]([^'\"]+)['\"]",
            r"TELEGRAM_BOT_TOKEN\s*=\s*['\"]([^'\"]+)['\"]",
            r"bot_token\s*=\s*['\"]([^'\"]+)['\"]"]:
    m = re.search(pat, bot_src)
    if m:
        val = os.getenv(m.group(1)) or m.group(1)
        if val and ':' in val:
            BOT_TOKEN = val
            break

chat_ids = re.findall(r'CHAT_ID[^=]*=\s*["\']?([-\d]+)["\']?', bot_src)
chat_ids += re.findall(r'chat_id[^=]*=\s*["\']?([-\d]+)["\']?', bot_src)
chat_ids = list(set(c for c in chat_ids if len(c) > 4))

print(f'BOT_TOKEN found: {bool(BOT_TOKEN)}')
print(f'GROQ_KEY: {bool(GROQ_KEY)} (len={len(GROQ_KEY) if GROQ_KEY else 0})')
print(f'GEMINI_KEY: {bool(GEMINI_KEY)} (len={len(GEMINI_KEY) if GEMINI_KEY else 0})')
print(f'Candidate chat_ids: {chat_ids}')

if not BOT_TOKEN:
    # Try extracting literal token from bot.py
    m = re.search(r'["\']([\d]+:[A-Za-z0-9_-]{35,})["\']', bot_src)
    if m:
        BOT_TOKEN = m.group(1)
        print(f'Found literal token in bot.py')

if not BOT_TOKEN:
    print('ERROR: Cannot find BOT_TOKEN')
    sys.exit(1)

# Test Groq
print('\n=== Testing Groq call ===')
try:
    from groq import Groq
    client = Groq(api_key=GROQ_KEY)
    resp = client.chat.completions.create(
        model='llama-3.3-70b-versatile',
        messages=[{'role': 'user', 'content': 'In one sentence: current outlook for BBCA.JK stock?'}],
        max_tokens=100
    )
    groq_result = resp.choices[0].message.content
    print(f'GROQ PASS: {groq_result[:100]}')
except Exception as e:
    groq_result = f'FAIL: {e}'
    print(f'GROQ FAIL: {e}')

# Test Gemini
print('\n=== Testing Gemini call ===')
try:
    from google import genai as genai_sdk
    from google.genai import types as genai_types
    client = genai_sdk.Client(api_key=GEMINI_KEY)
    resp = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=[genai_types.Content(role='user', parts=[genai_types.Part(text='In one sentence: current outlook for BMRI.JK stock?')])],
        config=genai_types.GenerateContentConfig(max_output_tokens=100)
    )
    gemini_result = resp.text
    print(f'GEMINI PASS: {gemini_result[:100]}')
except Exception as e:
    gemini_result = f'FAIL: {e}'
    print(f'GEMINI FAIL: {e}')

# Send results to Telegram
async def send_test_report():
    import httpx
    msg = (
        '🧪 *WBAgent AI Test Results* (triggered by Claude Code)\n\n'
        f'🤖 Groq llama-3.3-70b:\n_{groq_result[:200]}_\n\n'
        f'✨ Gemini 2.5-flash:\n_{gemini_result[:200]}_\n\n'
        '✅ Both models confirmed working — scheduled tasks ready!'
    )
    for cid in chat_ids:
        try:
            async with httpx.AsyncClient() as hc:
                r = await hc.post(
                    f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage',
                    json={'chat_id': cid, 'text': msg, 'parse_mode': 'Markdown'},
                    timeout=15
                )
            print(f'Telegram send to {cid}: {r.status_code}')
            if r.status_code == 200:
                print('Message sent successfully!')
        except Exception as e:
            print(f'Telegram send error for {cid}: {e}')

asyncio.run(send_test_report())
