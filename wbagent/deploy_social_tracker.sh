#!/usr/bin/env bash
# deploy_social_tracker.sh — Run this ONCE on the Oracle Cloud VM as ubuntu
# Usage: bash deploy_social_tracker.sh
set -euo pipefail

WBAGENT_DIR="$HOME/wbagent"
ENV_FILE="$HOME/.env_wbagent"

echo "=== Step 1: Checking VM environment ==="
python3 --version
pip3 --version

echo ""
echo "=== Step 2: Writing API keys to $ENV_FILE ==="
# Append only keys that are not already set
add_key() {
    local key="$1" value="$2"
    if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
        echo "  [SKIP] $key already present"
    else
        echo "${key}=${value}" >> "$ENV_FILE"
        echo "  [ADD]  $key"
    fi
}

touch "$ENV_FILE"
add_key "YT_API_KEY"      "AIzaSyCpGUvJgMf_6sqZQWFTGBl7DbMEXnwbCDc"
add_key "FB_PAGE_TOKEN"   "EAAOKQ8vCBHABRQB2wt8ZAvHn4jkCuR73KS8o8EfwcVzFjyXnSfvw7cUliDzBne1ZAAs6saL1cZCqHp8rSPt30kcfqgJMR0bJZCZBQMCxduC6nndwHHhqZBHnfSQPMgMrHybpJpuvJb5aws4GLZAGclFZAQZCmXlyq4gx1Wadozckr7hpOeX4rHutOkqYU3haKAxtzRaYZBBvUZD"
add_key "IG_ACCESS_TOKEN" "IGAAfFMpEA4N1BZAGFTdGFUOVFBWks1dWFUQWhWQm5XWVozaldnNW9STldDOV9mVGtKOGp4eHU0OWl0a3dwUkZAZAWmJkTzlnM1dVc3JSNVdlWTlnTjZAWaUQtbTNoU1o2NTZAnVmNPcmNkTTlBY1BDdlNOak1pcGY2S0JFX1dncXMzNAZDZD"

echo "  Current $ENV_FILE contents (keys only):"
grep -oP '^[A-Z_]+(?==)' "$ENV_FILE" | sed 's/^/    /'

echo ""
echo "=== Step 3: Installing Python dependencies ==="
pip3 install requests python-dotenv --break-system-packages --quiet
echo "  requests + python-dotenv installed"

echo ""
echo "=== Step 4: Deploying wb_social_tracker.py ==="
# Copy tracker from the same directory as this script (if present), or download
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRACKER_SRC="$SCRIPT_DIR/wb_social_tracker.py"

if [[ -f "$TRACKER_SRC" ]]; then
    cp "$TRACKER_SRC" "$WBAGENT_DIR/wb_social_tracker.py"
    echo "  Copied from $TRACKER_SRC"
else
    echo "  ERROR: wb_social_tracker.py not found next to this script at $TRACKER_SRC"
    echo "  Place wb_social_tracker.py in the same directory as this script and re-run."
    exit 1
fi

echo ""
echo "=== Step 5: Inspecting wbagent.py ==="
WBAGENT_PY="$WBAGENT_DIR/wbagent.py"
echo "  --- Top 80 lines ---"
head -80 "$WBAGENT_PY"
echo "  --- Scheduler / Telegram var names ---"
grep -n "scheduler\|add_job\|APScheduler\|TELEGRAM\|BOT_TOKEN\|CHAT_ID" "$WBAGENT_PY" | head -30
echo "  --- Command handler pattern ---"
grep -n "elif text\|elif msg\|/start\|/morning\|/brief\|command\|cmd" "$WBAGENT_PY" | head -30

echo ""
echo "=== Step 6: Patching wbagent.py ==="
python3 - <<'PATCHER'
import re, sys, shutil, datetime
from pathlib import Path

wbagent_path = Path.home() / "wbagent" / "wbagent.py"
backup_path  = Path.home() / "wbagent" / f"wbagent.py.bak_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"

src = wbagent_path.read_text()

# ── Backup ──────────────────────────────────────────────────────────────────
shutil.copy(wbagent_path, backup_path)
print(f"  Backup written: {backup_path}")

changes = []

# ── 1. Import block ──────────────────────────────────────────────────────────
IMPORT_LINE = "from wb_social_tracker import run_weekly_social_report, parse_manual_update, load_cache, save_cache, refresh_ig_token"
if "wb_social_tracker" in src:
    print("  [SKIP] wb_social_tracker import already present")
else:
    # Find last import line and insert after it
    lines = src.splitlines()
    last_import_idx = -1
    for i, line in enumerate(lines):
        if line.startswith(("import ", "from ")) and not line.strip().startswith("#"):
            last_import_idx = i
    if last_import_idx == -1:
        print("  ERROR: Could not find any import lines in wbagent.py")
        sys.exit(1)
    lines.insert(last_import_idx + 1, IMPORT_LINE)
    src = "\n".join(lines)
    changes.append("import")
    print(f"  [ADD] Import added after line {last_import_idx+1}")

# ── 2. Scheduler jobs ────────────────────────────────────────────────────────
SCHEDULER_BLOCK = '''
scheduler.add_job(
    lambda: run_weekly_social_report(send_telegram_fn=send_message),
    trigger="cron",
    day_of_week="sun",
    hour=8,
    minute=0,
    timezone="Asia/Jakarta",
    id="weekly_social_report",
    replace_existing=True,
    misfire_grace_time=3600,
)
scheduler.add_job(
    refresh_ig_token,
    trigger="cron",
    day="1-7",
    day_of_week="sun",
    hour=7,
    minute=45,
    timezone="Asia/Jakarta",
    id="ig_token_refresh",
    replace_existing=True,
)'''

if "weekly_social_report" in src:
    print("  [SKIP] weekly_social_report job already present")
else:
    # Find the last scheduler.add_job( block — locate its closing ) at the end
    # Strategy: find all "scheduler.add_job(" positions, take the last one,
    # then walk forward to find the balanced closing paren + any trailing comma/newline
    positions = [m.start() for m in re.finditer(r'scheduler\.add_job\s*\(', src)]
    if not positions:
        print("  ERROR: No scheduler.add_job() call found in wbagent.py")
        sys.exit(1)
    last_pos = positions[-1]
    # Walk forward from last_pos to find the matching closing paren
    depth = 0
    insert_at = -1
    for i in range(last_pos, len(src)):
        if src[i] == '(':
            depth += 1
        elif src[i] == ')':
            depth -= 1
            if depth == 0:
                insert_at = i + 1
                break
    if insert_at == -1:
        print("  ERROR: Could not find closing paren for last scheduler.add_job()")
        sys.exit(1)
    # Skip trailing whitespace / newline on that line
    end = insert_at
    while end < len(src) and src[end] in (' ', '\t'):
        end += 1
    src = src[:end] + "\n" + SCHEDULER_BLOCK + src[end:]
    changes.append("scheduler")
    print(f"  [ADD] Scheduler jobs inserted after last scheduler.add_job() at offset {insert_at}")

# ── 3. Telegram command handlers ─────────────────────────────────────────────
CMD_BLOCK = '''
    elif text == "/socialnow":
        await send_message(chat_id, "⏳ Fetching social media data... (~10 seconds)")
        try:
            run_weekly_social_report(send_telegram_fn=send_message)
        except Exception as e:
            await send_message(chat_id, f"❌ Report failed: {e}")

    elif text.startswith("/updatesocial"):
        payload = text.replace("/updatesocial", "").strip()
        if not payload:
            help_text = (
                "📝 *Manual Social Update*\\n\\nFormat:\\n`/updatesocial`\\n"
                "`yt_subs=21350`\\n`tt_followers=1480`\\n`tt_likes=10800`\\n"
                "`tt_views=52000`\\n`ig_followers=4820`\\n`fb_followers=3950`\\n"
                "`yt_rev=2100000`\\n`adsense=680000`\\n\\n_All optional. Revenue in IDR._"
            )
            await send_message(chat_id, help_text, parse_mode="Markdown")
        else:
            cache = load_cache()
            updated = parse_manual_update(payload, cache)
            cache["current"] = updated
            save_cache(cache)
            await send_message(chat_id, "✅ Social data updated. Run `/socialnow` to generate report.")

    elif text == "/socialcache":
        cache = load_cache()
        current = cache.get("current", {})
        yt = current.get("youtube", {}); ig = current.get("instagram", {})
        tt = current.get("tiktok", {}); fb = current.get("facebook", {})
        summary = (
            f"📊 *Cached Social Data*\\nLast updated: {cache.get('last_updated','never')}\\n\\n"
            f"▶️ YT: `{yt.get('subscribers','—')} subs`\\n"
            f"📸 IG: `{ig.get('followers','—')} followers`\\n"
            f"🎵 TT: `{tt.get('followers','—')} followers`\\n"
            f"📘 FB: `{fb.get('followers','—')} followers`\\n"
            f"Weeks stored: {len(cache.get('weeks',[]))}/8"
        )
        await send_message(chat_id, summary, parse_mode="Markdown")
'''

if "/socialnow" in src:
    print("  [SKIP] /socialnow command already present")
else:
    # Find a good insertion point: last "elif text ==" or "elif text.startswith" line
    # within the command handler function. We look for the pattern and insert after
    # the last matching block's closing statement before the next elif/else/return.
    #
    # Simpler approach: find the last "elif text ==" occurrence and insert before
    # any trailing else/return that closes the handler.
    #
    # Best anchor: find the LAST elif/else that ends the command chain,
    # then insert the new commands just BEFORE that final else (if present),
    # or just after the last elif block.

    # Find all "elif text" occurrences
    elif_matches = list(re.finditer(r'(\s+)elif text', src))
    if not elif_matches:
        print("  ERROR: No 'elif text' patterns found in wbagent.py — cannot auto-patch commands")
        print("  Please manually add the /socialnow, /updatesocial, /socialcache handlers.")
    else:
        last_elif = elif_matches[-1]
        # Find the end of this last elif block: scan forward for next same-indent elif/else/return
        indent = last_elif.group(1)  # leading whitespace of the elif
        start = last_elif.start()
        # Find position just before the next line at same-or-lower indent that is elif/else/return
        # We do this by scanning line by line after the match
        lines_after = src[last_elif.end():].splitlines(keepends=True)
        # skip first partial line (rest of 'elif text...' line)
        offset = len(src[last_elif.end():].splitlines(keepends=True)[0]) if lines_after else 0
        insert_offset = last_elif.end() + offset  # after the elif's own first line
        depth = 0
        accumulated = 0
        first_line = True
        for line in lines_after[1:]:  # skip the elif line itself
            stripped = line.lstrip()
            line_indent = len(line) - len(stripped)
            if first_line:
                first_line = False
                accumulated += len(line)
                continue
            # If we're back to same indent and hit another elif/else/except/return/pass
            if line_indent <= len(indent) and stripped and not stripped.startswith('#'):
                break
            accumulated += len(line)

        insert_at = insert_offset + accumulated
        src = src[:insert_at] + CMD_BLOCK + src[insert_at:]
        changes.append("commands")
        print(f"  [ADD] /socialnow, /updatesocial, /socialcache handlers inserted")

# ── Write patched file ────────────────────────────────────────────────────────
if changes:
    wbagent_path.write_text(src)
    print(f"\n  Patched wbagent.py ({', '.join(changes)} blocks added)")
else:
    print("\n  No changes needed — all blocks already present")

PATCHER

echo ""
echo "=== Step 7: Syntax check ==="
python3 -m py_compile "$WBAGENT_PY" && echo "  ✅ wbagent.py syntax OK"
python3 -m py_compile "$WBAGENT_DIR/wb_social_tracker.py" && echo "  ✅ wb_social_tracker.py syntax OK"

echo ""
echo "=== Step 8: Standalone test of wb_social_tracker.py ==="
cd "$WBAGENT_DIR"
set +e  # don't abort on test failure
env $(grep -v '^#' "$ENV_FILE" | xargs) python3 wb_social_tracker.py
TEST_EXIT=$?
set -e
if [[ $TEST_EXIT -eq 0 ]]; then
    echo "  ✅ Standalone test passed"
else
    echo "  ⚠️  Standalone test exited with code $TEST_EXIT — check output above"
fi

echo ""
echo "=== Step 9: Restarting WBAgent ==="
pkill -f "python3.*wbagent.py" 2>/dev/null && echo "  Old process killed" || echo "  No existing process found"
sleep 2

# Load env vars and start
set -o allexport
source "$ENV_FILE"
set +o allexport

nohup python3 "$WBAGENT_PY" > "$WBAGENT_DIR/wbagent.log" 2>&1 &
WPID=$!
echo "  WBAgent started (PID $WPID)"
sleep 4

echo ""
echo "=== Step 10: Verifying log ==="
tail -30 "$WBAGENT_DIR/wbagent.log"

echo ""
echo "==================================================================="
echo " DEPLOYMENT COMPLETE"
echo "==================================================================="
echo " Scheduler jobs expected in log:"
echo "   weekly_social_report  — every Sunday 08:00 WIB"
echo "   ig_token_refresh      — first Sunday each month 07:45 WIB"
echo ""
echo " Telegram commands to test now:"
echo "   /socialnow      → triggers a live report (~10s)"
echo "   /socialcache    → shows cached data"
echo "   /updatesocial   → shows help for manual update"
echo "==================================================================="
