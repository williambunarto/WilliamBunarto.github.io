#!/usr/bin/env python3
"""
Fix for "AI error: ... model_not_found" in WBAgent (EOD report / open pulse
commentary / all Groq-backed AI replies).

Root cause (two parts):
  1. MODELS = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"] -- Groq has
     fully retired both of these; neither appears in Groq's live model
     catalog any more (confirmed against GET /openai/v1/models).
  2. call_groq()'s fallback-to-next-model logic only treats
     rate_limit/quota/429/connection/timeout-style errors as retryable.
     A 404 model_not_found error doesn't match any of those keywords, so
     instead of trying the next model (or falling back to Gemini), the
     function immediately returned the raw error string to the user. This
     is the actual bug: it means ANY future Groq model rename/retirement
     will silently break AI replies again in exactly this way.

Fixes applied (idempotent):
  1. MODELS updated to Groq's current general-purpose chat models
     (openai/gpt-oss-120b primary, openai/gpt-oss-20b secondary).
  2. call_groq()'s retryable-error check extended to also treat
     model_not_found / "does not exist" / 404 / decommissioned as
     retryable, so it falls through to the next model and ultimately to
     the existing Gemini fallback instead of surfacing a raw error.
  3. portfolio.py's three groq_fn() call sites had tight max_tokens
     budgets (150/40/60) sized for the old non-reasoning llama models.
     openai/gpt-oss-* are reasoning models that spend part of the token
     budget on a hidden "reasoning" field before the visible answer
     (confirmed: 16-73 reasoning tokens for a trivial prompt) -- with a
     tight budget this silently returns EMPTY content instead of an
     error. Bumped to 400/200/200 for headroom.
"""
import sys
import subprocess

BOT_PATH = "/home/ubuntu/bot.py"
PORTFOLIO_PATH = "/home/ubuntu/portfolio.py"


def compile_check(path, content):
    tmp = path + ".patch_tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(content)
    result = subprocess.run(
        ["python3", "-m", "py_compile", tmp], capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"SYNTAX ERROR compiling {tmp}: {result.stderr}")
        sys.exit(1)
    return tmp


with open(BOT_PATH, "r", encoding="utf-8") as f:
    bot = f.read()

changed = False

# 1. Replace the deprecated MODELS list
old_models = (
    "MODELS = [\n"
    '    "llama-3.3-70b-versatile",\n'
    '    "llama-3.1-8b-instant",\n'
    "]"
)
new_models = (
    "MODELS = [\n"
    '    "openai/gpt-oss-120b",\n'
    '    "openai/gpt-oss-20b",\n'
    "]"
)
if old_models in bot:
    bot = bot.replace(old_models, new_models, 1)
    changed = True
    print("MODELS list updated: openai/gpt-oss-120b, openai/gpt-oss-20b")
elif new_models in bot:
    print("MODELS list already up to date -- nothing to do.")
else:
    print("ERROR: MODELS list not found in expected form -- aborting.")
    sys.exit(1)

# 2. Extend the retryable-error keyword set so model_not_found/404 falls
#    through to the next model instead of surfacing a raw error.
old_check = (
    '            if any(k in err for k in ("rate_limit", "quota", "429", "limit",\n'
    '                                       "connection", "timeout", "network",\n'
    '                                       "unreachable", "refused", "reset")):'
)
new_check = (
    '            if any(k in err for k in ("rate_limit", "quota", "429", "limit",\n'
    '                                       "connection", "timeout", "network",\n'
    '                                       "unreachable", "refused", "reset",\n'
    '                                       "model_not_found", "does not exist",\n'
    '                                       "404", "decommissioned")):'
)
if old_check in bot:
    bot = bot.replace(old_check, new_check, 1)
    changed = True
    print("call_groq() retry classification extended to cover model_not_found/404/decommissioned.")
elif new_check in bot:
    print("call_groq() retry classification already up to date -- nothing to do.")
else:
    print("ERROR: call_groq() retryable-error check not found in expected form -- aborting.")
    sys.exit(1)

if changed:
    tmp_bot = compile_check(BOT_PATH, bot)
    import os
    os.replace(tmp_bot, BOT_PATH)
    print("bot.py patched OK.")
else:
    print("Nothing to patch (bot.py).")

# ─────────────────────────────────────────────────────────────────────────
# portfolio.py: give the tight max_tokens budgets headroom for gpt-oss's
# hidden reasoning tokens, so per-stock commentary / signals don't come
# back silently empty.
# ─────────────────────────────────────────────────────────────────────────
with open(PORTFOLIO_PATH, "r", encoding="utf-8") as f:
    pf = f.read()

pf_changed = False

pf_replacements = [
    (
        '        resp = groq_fn([{"role": "user", "content": prompt}], max_tokens=150)',
        '        resp = groq_fn([{"role": "user", "content": prompt}], max_tokens=400)',
        "150 -> 400",
    ),
    (
        '        raw = groq_fn([{"role": "user", "content": prompt}], max_tokens=40).strip()',
        '        raw = groq_fn([{"role": "user", "content": prompt}], max_tokens=200).strip()',
        "40 -> 200",
    ),
    (
        '            verdict = groq_fn([{"role": "user", "content": verdict_prompt}], max_tokens=60).strip()',
        '            verdict = groq_fn([{"role": "user", "content": verdict_prompt}], max_tokens=200).strip()',
        "60 -> 200",
    ),
]

for old, new, label in pf_replacements:
    if old in pf:
        pf = pf.replace(old, new, 1)
        pf_changed = True
        print(f"portfolio.py: bumped max_tokens ({label})")
    elif new in pf:
        pass  # already patched
    else:
        print(f"ERROR: expected portfolio.py call site not found -- aborting: {old!r}")
        sys.exit(1)

if pf_changed:
    tmp_pf = compile_check(PORTFOLIO_PATH, pf)
    import os
    os.replace(tmp_pf, PORTFOLIO_PATH)
    print("portfolio.py patched OK.")
else:
    print("Nothing to patch (portfolio.py already up to date).")

print("Patch complete.")
