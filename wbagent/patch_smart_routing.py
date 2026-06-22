#!/usr/bin/env python3
"""
Smart model routing patch for WBAgent bot.py
Version: v3 (loop-strip all blocks)
"""
import sys, os, re, subprocess

BOT_PATH = '/home/ubuntu/bot.py'

with open(BOT_PATH, 'r') as f:
    content = f.read()

# -- 0. Strip ALL previous broken patches (loop until none remain) -------------
if 'generate_image_pollinations' in content or 'SMART MODEL ROUTER' in content:
    check = subprocess.run(['python3', '-m', 'py_compile', BOT_PATH],
                           capture_output=True, text=True)
    if check.returncode == 0 and 'generate_image_pollinations' in content:
        print('Already patched and syntax OK -- nothing to do.')
        sys.exit(0)
    if check.returncode != 0:
        print(f'Syntax error in existing bot.py - stripping all smart routing blocks...')

    removed_count = 0
    while True:
        lines = content.split('\n')
        start_line = None
        end_line = None
        for i, line in enumerate(lines):
            s = line.strip()
            if 'SMART MODEL ROUTER' in s and 'END' not in s:
                start_line = max(0, i - 1)
            elif 'END SMART MODEL ROUTER' in s:
                if start_line is not None:
                    end_line = min(len(lines), i + 2)
                    break
        if start_line is None or end_line is None:
            break
        content = '\n'.join(lines[:start_line] + lines[end_line:])
        removed_count += 1
        print(f'Stripped block #{removed_count} (was lines {start_line}-{end_line}).')

    # Strip injected imports (may have multiple copies too)
    for _ in range(5):
        content = content.replace('\nimport io\n', '\n', 1)
        content = content.replace('\nimport urllib.parse\n', '\n', 1)
    content = re.sub(r'\ntry:\n    import httpx as _httpx_mod[\s\S]*?_httpx_mod = None\n',
                     '\n', content)

    # Strip handler registrations
    while True:
        lines = content.split('\n')
        h_start = None
        h_end = None
        for i, l in enumerate(lines):
            if '# Smart routing handlers (added by patch_smart_routing.py)' in l:
                h_start = i
            if h_start is not None and 'handle_photo_message' in l and 'add_handler' in l:
                h_end = i + 1
                break
        if h_start is None or h_end is None:
            break
        content = '\n'.join(lines[:h_start] + lines[h_end:])
        print('Stripped handler registration block.')

    print(f'Strip complete ({removed_count} function blocks removed). Reapplying...')

# -- 1. New imports ------------------------------------------------------------
NEW_IMPORTS = """
import io
import urllib.parse
try:
    import httpx as _httpx_mod
except ImportError:
    _httpx_mod = None
"""
content = content.replace('import os\n', 'import os\n' + NEW_IMPORTS, 1)

# -- 2. New functions block ----------------------------------------------------
# NOTE: Use \\n inside triple-quoted string to write literal \n in the output file
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
        return '❌ Image analysis requires Gemini API key.'
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
        await update.message.reply_text('Usage: /img <prompt>')
        return
    status = await update.message.reply_text('Generating image... (up to 30s)')
    try:
        import asyncio
        img_bytes = await asyncio.get_event_loop().run_in_executor(
            None, generate_image_pollinations, prompt
        )
        await update.message.reply_photo(photo=img_bytes, caption=prompt[:900])
        await status.delete()
    except Exception as exc:
        log.error(f'Image generation failed: {exc}')
        await status.edit_text(f'❌ Image generation failed: {exc}')


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
        status = await update.message.reply_text('Analyzing image before editing...')
        description = await asyncio.get_event_loop().run_in_executor(
            None, analyze_image_gemini_sync, image_bytes,
            'Describe this image with precise visual details for an image generation prompt.'
        )
        combined_prompt = description + '. Modification: ' + caption
        await status.edit_text('Generating edited version...')
        try:
            edited_bytes = await asyncio.get_event_loop().run_in_executor(
                None, generate_image_pollinations, combined_prompt
            )
            await update.message.reply_photo(photo=edited_bytes, caption='Edited: ' + caption[:900])
            await status.delete()
        except Exception as exc:
            log.error(f'Image edit failed: {exc}')
            await status.edit_text(f'❌ Edit generation failed: {exc}')
    else:
        status = await update.message.reply_text('Analyzing image...')
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

# -- 3. Detect app variable ---------------------------------------------------
app_var_match = re.search(r'(\w+)\s*=\s*ApplicationBuilder', content)
app_var = app_var_match.group(1) if app_var_match else 'application'
print(f'Detected application variable: {app_var}')

# -- 4. Register handlers before run_polling() --------------------------------
NEW_HANDLERS = (
    '\n    # Smart routing handlers (added by patch_smart_routing.py)\n'
    '    from telegram.ext import CommandHandler as _CH, MessageHandler as _MH, filters as _F\n'
    f'    {app_var}.add_handler(_CH(\'img\', handle_img_command))\n'
    f'    {app_var}.add_handler(_MH(_F.PHOTO, handle_photo_message))\n'
)

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

result = subprocess.run(['python3', '-m', 'py_compile', BOT_PATH],
                        capture_output=True, text=True)
if result.returncode != 0:
    print(f'SYNTAX ERROR after patch: {result.stderr}')
    sys.exit(1)

print('Patch applied and syntax verified OK.')
print('New features: /img command, photo analysis/editing, smart text routing.')
