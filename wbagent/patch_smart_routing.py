#!/usr/bin/env python3
"""
Smart model routing patch for WBAgent bot.py

Adds:
  - /img <prompt>        -> image generation via Pollinations.ai (free, no key)
  - Photo messages       -> Gemini 2.5 Flash vision (analyze / edit)
  - smart_call()         -> routes text tasks to best free model:
      long context (>6k chars) -> Gemini first
      reasoning / math         -> Gemini first
      code tasks               -> Gemini first
      everything else          -> Groq (fastest)
"""
import sys, os, re

BOT_PATH = '/home/ubuntu/bot.py'

with open(BOT_PATH, 'r') as f:
    content = f.read()

if 'generate_image_pollinations' in content:
    print('Already patched -- nothing to do.')
    sys.exit(0)

# ── 1. New imports ────────────────────────────────────────────────────────────
# Insert after 'import os' (guaranteed present)
NEW_IMPORTS = """
import io
import urllib.parse
try:
    import httpx as _httpx_mod
except ImportError:
    _httpx_mod = None
"""
content = content.replace('import os\n', 'import os\n' + NEW_IMPORTS, 1)

# ── 2. New functions block ────────────────────────────────────────────────────
NEW_FUNCTIONS = '''
# ═══════════════════════════════════════════════════════════════════════════════
# SMART MODEL ROUTER
# ═══════════════════════════════════════════════════════════════════════════════

_ROUTE_GEMINI_FIRST = (
    # reasoning / math
    'calculate', 'solve', 'math', 'equation', 'proof', 'prove',
    'step by step', 'think through', 'explain in depth',
    # code
    'write code', 'write a script', 'debug this', 'fix this error',
    'implement', 'python script', 'javascript', 'typescript',
    'write a function', 'write a class',
    # long documents (detected by length below)
)

def detect_task(text: str, has_photo: bool = False) -> str:
    """Return task type string used for routing."""
    t = (text or '').lower()
    if has_photo:
        edit_words = ('edit ', 'modify ', 'change the ', 'make it ', 'transform',
                      'add to ', 'remove the ', 'filter', 'style it')
        return 'image_edit' if any(w in t for w in edit_words) else 'image_analyze'
    gen_words = ('draw ', 'generate image', 'create image', 'make image',
                 'paint ', 'illustrate', 'sketch ', 'design an image',
                 'image of ', 'picture of ', 'generate a photo', 'create a photo')
    if any(w in t for w in gen_words):
        return 'image_generate'
    if len(text or '') > 6000:
        return 'long_context'
    if any(w in t for w in _ROUTE_GEMINI_FIRST):
        return 'gemini_preferred'
    return 'chat'


def smart_call(messages, system=None, max_tokens=1200):
    """Route to the best available free model for the detected task."""
    if system is None:
        system = SYSTEM_PROMPT
    last_text = messages[-1]['content'] if messages else ''
    task = detect_task(last_text)
    if task in ('long_context', 'gemini_preferred') and GEMINI_API_KEY:
        result = call_gemini(messages, system=system, max_tokens=max_tokens)
        if not result.startswith('❌'):
            return result
    # Default path: Groq (already falls back to Gemini internally)
    return call_groq(messages, system=system, max_tokens=max_tokens)


def analyze_image_gemini_sync(image_bytes: bytes, question: str) -> str:
    """Analyze/describe an image using Gemini 2.5 Flash vision (synchronous)."""
    if not GEMINI_API_KEY:
        return '❌ Image analysis requires Gemini API key (not configured).'
    try:
        import google.generativeai as _genai
        model = _genai.GenerativeModel('gemini-2.5-flash')
        prompt = question if question.strip() else 'Describe this image in detail. Be thorough and helpful.'
        response = model.generate_content([
            prompt,
            {"mime_type": "image/jpeg", "data": image_bytes}
        ])
        return response.text
    except Exception as exc:
        log.error(f'Gemini vision error: {exc}')
        return f'❌ Image analysis failed: {exc}'


def generate_image_pollinations(prompt: str) -> bytes:
    """Generate image via Pollinations.ai FLUX (free, no API key needed)."""
    if _httpx_mod is None:
        raise RuntimeError('httpx not installed')
    url = (
        'https://image.pollinations.ai/prompt/'
        + urllib.parse.quote(prompt)
        + '?model=flux&width=1024&height=1024&nologo=true&enhance=true'
    )
    with _httpx_mod.Client(timeout=120, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()
        ct = resp.headers.get('content-type', '')
        if not ct.startswith('image'):
            raise ValueError(f'Unexpected content-type: {ct}')
        return resp.content


async def handle_img_command(update, context):
    """Handler for /img <prompt> — generate image via Pollinations.ai."""
    prompt = ' '.join(context.args) if context.args else ''
    if not prompt:
        await update.message.reply_text(
            '\U0001f5bc Usage: /img <your image prompt>\n'
            'Example: /img a futuristic city at sunset, digital art'
        )
        return
    status = await update.message.reply_text('\U0001f3a8 Generating image… (may take up to 30s)')
    try:
        import asyncio
        img_bytes = await asyncio.get_event_loop().run_in_executor(
            None, generate_image_pollinations, prompt
        )
        await update.message.reply_photo(
            photo=img_bytes,
            caption=f'\U0001f5bc {prompt[:900]}'
        )
        await status.delete()
    except Exception as exc:
        log.error(f'Image generation failed: {exc}')
        await status.edit_text(
            f'❌ Image generation failed. Try a different prompt.\n_Error: {exc}_',
            parse_mode='Markdown'
        )


async def handle_photo_message(update, context):
    """Handler for incoming photo messages — analyze or edit via Gemini vision."""
    caption = (update.message.caption or '').strip()
    task = detect_task(caption, has_photo=True)

    # Download photo (highest resolution)
    photo = update.message.photo[-1]
    file_obj = await context.bot.get_file(photo.file_id)
    buf = io.BytesIO()
    await file_obj.download_to_memory(buf)
    image_bytes = buf.getvalue()

    if task == 'image_edit':
        status = await update.message.reply_text('\U0001f50d Analyzing image before editing…')
        import asyncio
        description = await asyncio.get_event_loop().run_in_executor(
            None, analyze_image_gemini_sync, image_bytes,
            'Describe this image with precise visual details for use as an image generation prompt. Include style, colors, composition, and subjects.'
        )
        combined_prompt = f'{description}. Modification requested: {caption}'
        await status.edit_text('\U0001f3a8 Generating edited version…')
        try:
            edited_bytes = await asyncio.get_event_loop().run_in_executor(
                None, generate_image_pollinations, combined_prompt
            )
            await update.message.reply_photo(
                photo=edited_bytes,
                caption=f'✏️ Edited: {caption[:900]}'
            )
            await status.delete()
        except Exception as exc:
            log.error(f'Image edit generation failed: {exc}')
            await status.edit_text(f'❌ Edit generation failed: {exc}')
    else:
        status = await update.message.reply_text('\U0001f50d Analyzing image…')
        import asyncio
        result = await asyncio.get_event_loop().run_in_executor(
            None, analyze_image_gemini_sync, image_bytes, caption
        )
        # Telegram message limit is 4096 chars
        if len(result) <= 4096:
            await status.edit_text(result)
        else:
            await status.delete()
            # Split into chunks
            for i in range(0, len(result), 4000):
                await update.message.reply_text(result[i:i+4000])


# ═══════════════════════════════════════════════════════════════════════════════
# END SMART MODEL ROUTER
# ═══════════════════════════════════════════════════════════════════════════════
'''

# Insert new functions just before 'def main():' or before ApplicationBuilder
main_match = re.search(r'\ndef main\(\):', content)
app_match = re.search(r'\n    application = ApplicationBuilder', content)

if main_match:
    pos = main_match.start()
    content = content[:pos] + NEW_FUNCTIONS + content[pos:]
elif app_match:
    pos = app_match.start()
    content = content[:pos] + NEW_FUNCTIONS + content[pos:]
else:
    # Fallback: append before last block
    content = content + NEW_FUNCTIONS

# ── 3. Register new handlers ─────────────────────────────────────────────────
# Strategy: insert before run_polling() call
NEW_HANDLERS = """
    # Smart routing handlers (added by patch_smart_routing.py)
    from telegram.ext import CommandHandler as _CH, MessageHandler as _MH, filters as _F
    application.add_handler(_CH('img', handle_img_command))
    application.add_handler(_MH(_F.PHOTO, handle_photo_message))
"""

run_match = re.search(r'(\n    application\.run_polling)', content)
if run_match:
    pos = run_match.start()
    content = content[:pos] + NEW_HANDLERS + content[pos:]
else:
    # Fallback: look for .run_polling( anywhere
    run_match2 = re.search(r'(\.run_polling\()', content)
    if run_match2:
        # Find the start of that line
        line_start = content.rfind('\n', 0, run_match2.start()) + 1
        content = content[:line_start] + NEW_HANDLERS + content[line_start:]
    else:
        print('WARNING: could not find run_polling -- handlers NOT registered automatically.')
        print('Add manually: application.add_handler(CommandHandler("img", handle_img_command))')
        print('              application.add_handler(MessageHandler(filters.PHOTO, handle_photo_message))')

# ── 4. Write and verify ───────────────────────────────────────────────────────
with open(BOT_PATH, 'w') as f:
    f.write(content)

import subprocess
result = subprocess.run(['python3', '-m', 'py_compile', BOT_PATH], capture_output=True, text=True)
if result.returncode != 0:
    print(f'SYNTAX ERROR: {result.stderr}')
    sys.exit(1)

print('Patch applied and syntax verified OK.')
print('New features: /img command, photo analysis/editing, smart text routing.')
