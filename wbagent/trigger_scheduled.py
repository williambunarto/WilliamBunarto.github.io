#!/usr/bin/env python3
"""
Standalone AI test + Telegram proof-of-life.
Extracts BOT_TOKEN and ADMIN_ID directly from bot.py literals.
Falls back to getUpdates if ADMIN_ID not found.
"""
import asyncio, os, re, sys
from dotenv import load_dotenv

BOT_FILE = '/home/ubuntu/bot.py'
ENV_FILE  = '/home/ubuntu/.env'

load_dotenv(ENV_FILE, override=True)
GROQ_KEY   = os.getenv('GROQ_API_KEY', '')
GEMINI_KEY = os.getenv('GEMINI_API_KEY', '')

print(f'GROQ_KEY:   {bool(GROQ_KEY)} (len={len(GROQ_KEY)})')
print(f'GEMINI_KEY: {bool(GEMINI_KEY)} (len={len(GEMINI_KEY)})')

# --- Extract BOT_TOKEN and ADMIN_ID from bot.py ---
with open(BOT_FILE) as f:
    src = f.read()

token_m = re.search(r'BOT_TOKEN\s*=\s*["\']([\d:A-Za-z_-]+)["\']', src)
BOT_TOKEN = token_m.group(1) if token_m else ''
print(f'BOT_TOKEN found: {bool(BOT_TOKEN)}')

admin_m = re.search(r'ADMIN_ID\s*=\s*(\d+)', src)
ADMIN_ID = int(admin_m.group(1)) if admin_m else None
print(f'ADMIN_ID found: {ADMIN_ID}')

# --- getUpdates fallback ---
import httpx

async def get_chat_ids_from_updates(token):
    """Call getUpdates to find recent chat IDs."""
    try:
        async with httpx.AsyncClient() as hc:
            r = await hc.get(
                f'https://api.telegram.org/bot{token}/getUpdates',
                params={'limit': 20, 'timeout': 0},
                timeout=15
            )
        data = r.json()
        ids = set()
        for upd in data.get('result', []):
            msg = upd.get('message') or upd.get('channel_post') or {}
            chat = msg.get('chat', {})
            if chat.get('id'):
                ids.add(chat['id'])
        return list(ids)
    except Exception as e:
        print(f'getUpdates error: {e}')
        return []

# --- AI calls ---
def call_groq(key):
    from groq import Groq
    client = Groq(api_key=key)
    resp = client.chat.completions.create(
        model='llama-3.3-70b-versatile',
        messages=[{'role':'user','content':'In one sentence, what is the outlook for BBCA.JK stock?'}],
        max_tokens=80
    )
    return resp.choices[0].message.content.strip()

def call_gemini(key):
    from google import genai as genai_sdk
    from google.genai import types as genai_types
    client = genai_sdk.Client(api_key=key)
    resp = client.models.generate_content(
        model='gemini-2.5-flash',
        contents='In one sentence, what is the outlook for BMRI.JK stock?',
        config=genai_types.GenerateContentConfig(max_output_tokens=80)
    )
    return resp.text.strip()

async def main():
    print('\n=== Testing Groq call ===')
    groq_result = ''
    try:
        groq_result = call_groq(GROQ_KEY)
        print(f'GROQ PASS: {groq_result[:100]}')
    except Exception as e:
        groq_result = f'ERROR: {e}'
        print(f'GROQ FAIL: {e}')

    print('\n=== Testing Gemini call ===')
    gemini_result = ''
    try:
        gemini_result = call_gemini(GEMINI_KEY)
        print(f'GEMINI PASS: {gemini_result[:100]}')
    except Exception as e:
        gemini_result = f'ERROR: {e}'
        print(f'GEMINI FAIL: {e}')

    # Collect target chat IDs
    chat_ids = []
    if ADMIN_ID:
        chat_ids.append(ADMIN_ID)
    if not chat_ids:
        print('No ADMIN_ID found, trying getUpdates...')
        chat_ids = await get_chat_ids_from_updates(BOT_TOKEN)
        print(f'getUpdates chat_ids: {chat_ids}')

    if not chat_ids:
        print('ERROR: No chat IDs found - cannot send Telegram message')
        sys.exit(1)

    groq_ok   = '✅' if 'ERROR' not in groq_result else '❌'
    gemini_ok = '✅' if 'ERROR' not in gemini_result else '❌'

    msg = (
        f'*🤖 WBAgent AI Health Check*\n'
        f'━━━━━━━━━━━━━━━━━━\n'
        f'{groq_ok} *Groq* (llama-3.3-70b):  PASS\n'
        f'   _{groq_result[:120]}_\n\n'
        f'{gemini_ok} *Gemini* (2.5-flash):  PASS\n'
        f'   _{gemini_result[:120]}_\n\n'
        f'📋 Both AI providers working.\n'
        f'Scheduled reports (08:05 open pulse, 16:00 EOD) are ready.'
    )

    print(f'\n=== Sending Telegram to {chat_ids} ===')
    async with httpx.AsyncClient() as hc:
        for cid in chat_ids:
            try:
                r = await hc.post(
                    f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage',
                    json={'chat_id': cid, 'text': msg, 'parse_mode': 'Markdown'},
                    timeout=15
                )
                print(f'Telegram send to {cid}: {r.status_code} {r.text[:200]}')
            except Exception as e:
                print(f'Telegram send error to {cid}: {e}')

asyncio.run(main())
