#!/usr/bin/env python3
"""Patch bot.py to add Gemini 2.5 Flash as final fallback after Groq.

Expects GEMINI_API_KEY in environment (injected by CI workflow).
"""
import sys, os

BOT_PATH = '/home/ubuntu/bot.py'
GEMINI_KEY = os.environ['GEMINI_API_KEY']

with open(BOT_PATH, 'r') as f:
    content = f.read()

# Idempotency guard
if 'call_gemini' in content:
    print('Already patched -- nothing to do.')
    sys.exit(0)

# 1. Add google.generativeai import after groq import
content = content.replace(
    'from groq import Groq',
    'from groq import Groq\nimport google.generativeai as genai',
    1
)

# 2. Add GEMINI_API_KEY after GROQ_API_KEY line
if 'GEMINI_API_KEY' not in content:
    content = content.replace(
        'GROQ_API_KEY = ',
        'GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")  # loaded from .env via shell\nGROQ_API_KEY = ',
        1
    )

# 3. Configure genai after groq_client init
if 'genai.configure' not in content:
    content = content.replace(
        'groq_client = Groq(api_key=GROQ_API_KEY)',
        'groq_client = Groq(api_key=GROQ_API_KEY)\nif GEMINI_API_KEY:\n    genai.configure(api_key=GEMINI_API_KEY)',
        1
    )

# 4. Replace final Groq fallback return with call_gemini, add call_gemini function
OLD_RETURN = '    return "❌ All models quota exceeded. Try again in a minute."'
NEW_BLOCK = '''    return call_gemini(messages, system=system, max_tokens=max_tokens)


def call_gemini(messages, system=SYSTEM_PROMPT, max_tokens=1200):
    """Gemini 2.5 Flash fallback when all Groq models are quota-exhausted."""
    if not GEMINI_API_KEY:
        return "❌ All AI models quota exceeded. Try again later."
    try:
        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            system_instruction=system,
        )
        history = []
        for m in messages[:-1]:
            role = "user" if m["role"] == "user" else "model"
            history.append({"role": role, "parts": [m["content"]]})
        last_msg = messages[-1]["content"] if messages else ""
        chat = model.start_chat(history=history)
        resp = chat.send_message(last_msg, generation_config={"max_output_tokens": max_tokens})
        return resp.text
    except Exception as e:
        log.error(f"Gemini fallback error: {e}")
        return "❌ All AI models quota exceeded. Try again later."
'''

if OLD_RETURN not in content:
    print(f'ERROR: fallback return line not found -- aborting')
    sys.exit(1)

content = content.replace(OLD_RETURN, NEW_BLOCK, 1)

with open(BOT_PATH, 'w') as f:
    f.write(content)

print('Gemini patch applied OK')
