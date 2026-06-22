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
import sys, os, re, subprocess

BOT_PATH = '/home/ubuntu/bot.py'

with open(BOT_PATH, 'r') as f:
    content = f.read()

# -- 0. Handle already-patched state (possibly broken) -----------------------
if 'generate_image_pollinations' in content:
    check = subprocess.run(['python3', '-m', 'py_compile', BOT_PATH], capture_output=True, text=True)
    if check.returncode == 0:
        print('Already patched and syntax OK -- nothing to do.')
        sys.exit(0)
    print(f'Previous patch has syntax error: {check.stderr.strip()}')
    print('Stripping broken patch and reapplying...')
    content = re.sub(
        r'\n# [=]+\n# SMART MODEL ROUTER.*?# END SMART MODEL ROUTER\n# [=]+\n',
        '\n',
        content,
        flags=re.DOTALL
    )
    content = re.sub(r'\nimport io\n', '\n', content)
    content = re.sub(
        r'\ntry:\n    import httpx as _httpx_mod.*?_httpx_mod = None\n',
        '\n',
        content,
        flags=re.DOTALL
    )
    content = re.sub(
        r'\n    # Smart routing handlers.*?handle_photo_message\)\)\n',
        '\n',
        content,
        flags=re.DOTALL
    )
    content = re.sub(r'\nimport urllib\.parse\n', '\n', content)
    print('Stripped old broken patch.')

# -- 1. New imports -----------------------------------------------------------
NEW_IMPORTS = """
import io
import urllib.parse
try:
    import httpx as _httpx_mod
except ImportError:
    _httpx_mod = None
"""
content = content.replace('import os\n', 'import os\n' + NEW_IMPORTS, 1)

# -- 2. New functions block ---------------------------------------------------
NEW_FUNCTIONS = '''
# =============================================================================
# SMART MODEL ROUTER
# =============================================================================

_ROUTE_GEMINI_FIRST = (
    'calculate', 'solve', 'math', 'equation', 'proof', 'prove',
    'step by step', 'think through', 'explain in depth',
    'write code', 'write a script', 'debug this', 'fix this error',
    'implement', 'python script', 'javascript', 'typescript',
    'write a function', 'write a class',
)

def detect_task(text, has_photo=False):
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
    if system is None:
        system = SYSTEM_PROMPT
    last_text = messages[-1]['content'] if messages else ''
    task = detect_task(last_text)
    if task in ('long_context', 'gemini_preferred') and GEMINI_API_KEY:
        result = call_gemini(messages, system=system, max_tokens=max_tokens)
        if not result.startswith('❌'):
            return result
    return call_groq(messages, system=system, max_tokens=max_tokens)


def analyze_image_gemini_sync(image_bytes, question):
    if not GEMINI_API_KEY:
        return '❌ Image analysis requires Gemini API key (not configured).'
    try:
        import google.generativeai as _genai
        model = _genai.GenerativeModel('gemini-2.5-flash')
        prompt = question if question.strip() else 'Describe this image in detail.'
        response = model.generate_content([
            prompt,
            {"mime_type": "image/jpeg", "data": image_bytes}
        ])
        return response.text
    except Exception as exc:
        log.error(f'Gemini vision error: {exc}')
        return f'❌ Image analysis failed: {exc}'


def generate_image_pollinations(prompt):
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
    prompt = ' '.join(context.args) if context.args else ''
    if not prompt:
        await update.message.reply_text(
            'Usage: /img <your image prompt>\n'
            'Example: /img a futuristic city at sunset, digital art'
        )
        return
    status = await update.message.reply_text('\U0001f3a8 Generating image... (may take up to 30s)')
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
            f'❌ Image generation failed. Try a different prompt.\nError: {exc}'
        )


async def handle_photo_message(update, context):
    caption = (update.message.caption or '').strip()
    task = detect_task(caption, has_photo=True)
    photo = update.message.photo[-1]
    file_obj = await context.bot.get_file(photo.file_id)
    buf = io.BytesIO()
    await file_obj.download_to_memory(buf)
    image_bytes = buf.getvalue()

    import asyncio
    if task == 'image_edit':
        status = await update.message.reply_text('\U0001f50d Analyzing image before editing...')
        description = await asyncio.get_event_loop().run_in_executor(
            None, analyze_image_gemini_sync, image_bytes,
            'Describe this image with precise visual details for an image generation prompt.'
        )
        combined_prompt = f'{description}. Modification: {caption}'
        await status.edit_text('\U0001f3a8 Generating edited version...')
        try:
            edited_bytes = await asyncio.get_event_loop().run_in_executor(
                None, generate_image_pollinations, combined_prompt
            )
            await update.message.reply_photo(photo=edited_bytes, caption=f'Edited: {caption[:900]}')
            await status.delete()
        except Exception as exc:
            log.error(f'Image edit failed: {exc}')
            await status.edit_text(f'❌ Edit generation failed: {exc}')
    else:
        status = await update.message.reply_text('\U0001f50d Analyzing image...')
        result = await asyncio.get_event_loop().run_in_executor(
            None, analyze_image_gemini_sync, image_bytes, caption
        )
        if len(result) <= 4096:
            await status.edit_text(result)
        else:
            await status.delete()
            for i in range(0, len(result), 4000):
                await update.message.reply_text(result[i:i+4000])


# =============================================================================
# END SMART MODEL ROUTER
# =============================================================================
'''

main_match = re.search(r'\ndef main\(\):', content)
if main_match:
    pos = main_match.start()
    content = content[:pos] + NEW_FUNCTIONS + content[pos:]
else:
    content = content + NEW_FUNCTIONS

# -- 3. Detect application variable name -------------------------------------
app_var_match = re.search(r'(\w+)\s*=\s*ApplicationBuilder', content)
app_var = app_var_match.group(1) if app_var_match else 'application'
print(f'Detected application variable: {app_var}')

# -- 4. Register handlers before run_polling() --------------------------------
NEW_HANDLERS = f"""
    # Smart routing handlers (added by patch_smart_routing.py)
    from telegram.ext import CommandHandler as _CH, MessageHandler as _MH, filters as _F
    {app_var}.add_handler(_CH('img', handle_img_command))
    {app_var}.add_handler(_MH(_F.PHOTO, handle_photo_message))
"""

run_match = re.search(r'(\n    \w+\.run_polling)', content)
if run_match:
    pos = run_match.start()
    content = content[:pos] + NEW_HANDLERS + content[pos:]
else:
    run_match2 = re.search(r'(\.run_polling\()', content)
    if run_match2:
        line_start = content.rfind('\n', 0, run_match2.start()) + 1
        content = content[:line_start] + NEW_HANDLERS + content[line_start:]
    else:
        print('WARNING: could not find run_polling -- handlers NOT registered.')

# -- 5. Write and verify ------------------------------------------------------
with open(BOT_PATH, 'w') as f:
    f.write(content)

result = subprocess.run(['python3', '-m', 'py_compile', BOT_PATH], capture_output=True, text=True)
if result.returncode != 0:
    print(f'SYNTAX ERROR after patch: {result.stderr}')
    sys.exit(1)

print('Patch applied and syntax verified OK.')
print('New features: /img command, photo analysis/editing, smart text routing.')
