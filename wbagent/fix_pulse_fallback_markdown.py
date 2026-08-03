#!/usr/bin/env python3
"""
Hotfix for patch_notification_reliability.py's fallback-message bug.

The open-pulse fallback message embeds the raw, unescaped exception text
inside a parse_mode="Markdown" send. If that text contains an unmatched
Markdown special character (_, *, `, [), Telegram rejects the send with
"can't parse entities" -- which is then silently swallowed by the
surrounding bare except, so the admin gets NO notification at all on
some failures. Fix: drop parse_mode for the fallback send (plain text,
no entity parsing, cannot fail this way).

Idempotent -- safe to run multiple times.
"""
import sys
import subprocess

BOT_PATH = "/home/ubuntu/bot.py"

with open(BOT_PATH, "r", encoding="utf-8") as f:
    bot = f.read()

old = '            await _send_admin_message(app, fallback, parse_mode="Markdown", retries=2, delay=3)'
new = "            # No parse_mode: fallback embeds raw, unescaped exception text --\n            # Markdown mode would risk a \"can't parse entities\" send failure.\n            await _send_admin_message(app, fallback, retries=2, delay=3)"

if old not in bot:
    if new in bot:
        print("Already fixed -- nothing to do.")
        sys.exit(0)
    print("ERROR: expected fallback send line not found -- aborting.")
    sys.exit(1)

bot = bot.replace(old, new, 1)

tmp = BOT_PATH + ".patch_tmp"
with open(tmp, "w", encoding="utf-8") as f:
    f.write(bot)
result = subprocess.run(["python3", "-m", "py_compile", tmp], capture_output=True, text=True)
if result.returncode != 0:
    print(f"SYNTAX ERROR: {result.stderr}")
    sys.exit(1)

import os
os.replace(tmp, BOT_PATH)
print("Fixed: open-pulse fallback message no longer uses parse_mode=Markdown.")
