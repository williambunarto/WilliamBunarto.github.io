#!/usr/bin/env python3
"""
Notification reliability patch for WBAgent bot.py + portfolio.py.

Root cause (2026-08-03 incident, "Open pulse failed: Timed out"):
ApplicationBuilder() had no custom HTTPXRequest, so python-telegram-bot
used its default ~5s connect/read/write/pool timeouts for ALL Bot API
calls. A transient slow response from api.telegram.org while sending the
08:05 WIB open-pulse message raised telegram.error.TimedOut ("Timed out"),
which scheduled_open_pulse caught and forwarded verbatim to the admin with
no retry.

Fixes applied (idempotent):
  1. ApplicationBuilder: 30s connect/read/write/pool timeouts.
  2. scheduled_open_pulse: retry-wrapped send (_send_admin_message) +
     degraded-but-useful fallback message on failure.
  3. scheduler.add_job (open_pulse, eod_report): misfire_grace_time=300,
     max_instances=1 to prevent overlapping runs.
  4. health.log entry (SUCCESS/FAILED) after every open_pulse run.
  5. portfolio.py: explicit timeout=10 on the yfinance .history() calls
     used by get_prices()/get_ticker_signal() (no timeout was set before).
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


# ─────────────────────────────────────────────────────────────────────────
# bot.py
# ─────────────────────────────────────────────────────────────────────────
with open(BOT_PATH, "r", encoding="utf-8") as f:
    bot = f.read()

if "_send_admin_message" in bot:
    print("bot.py already patched -- nothing to do.")
else:
    # 1. Harden ApplicationBuilder timeouts (the actual root cause fix)
    old_app = 'app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()'
    new_app = (
        "app = (\n"
        "        ApplicationBuilder()\n"
        "        .token(BOT_TOKEN)\n"
        "        .connect_timeout(30)\n"
        "        .read_timeout(30)\n"
        "        .write_timeout(30)\n"
        "        .pool_timeout(30)\n"
        "        .post_init(post_init)\n"
        "        .build()\n"
        "    )"
    )
    if old_app not in bot:
        print("ERROR: ApplicationBuilder line not found -- aborting bot.py patch.")
        sys.exit(1)
    bot = bot.replace(old_app, new_app, 1)

    # 2. Insert retry-send + health-log helpers before scheduled_open_pulse
    helper_marker = "async def scheduled_open_pulse(app):"
    if helper_marker not in bot:
        print("ERROR: scheduled_open_pulse def not found -- aborting bot.py patch.")
        sys.exit(1)
    helpers = (
        'HEALTH_LOG_PATH = "/home/ubuntu/wbagent/logs/health.log"\n'
        "\n"
        "\n"
        "def _log_health(job_name, status):\n"
        "    try:\n"
        "        import os as _os\n"
        "        _os.makedirs(_os.path.dirname(HEALTH_LOG_PATH), exist_ok=True)\n"
        '        with open(HEALTH_LOG_PATH, "a") as f:\n'
        '            f.write(f"{datetime.now()} | {job_name} | {status}\\n")\n'
        "    except Exception:\n"
        "        pass\n"
        "\n"
        "\n"
        "async def _send_admin_message(app, text, parse_mode=None, retries=3, delay=5):\n"
        '    """Send a message to ADMIN_ID with retry on transient failures (e.g. TimedOut)."""\n'
        "    for attempt in range(retries):\n"
        "        try:\n"
        "            await app.bot.send_message(chat_id=ADMIN_ID, text=text, parse_mode=parse_mode)\n"
        "            return True\n"
        "        except Exception as e:\n"
        '            log.warning(f"[notify] send attempt {attempt + 1}/{retries} failed: {e}")\n'
        "            if attempt < retries - 1:\n"
        "                await asyncio.sleep(delay)\n"
        "    return False\n"
        "\n"
        "\n"
    )
    bot = bot.replace(helper_marker, helpers + helper_marker, 1)

    # 3. scheduled_open_pulse: retry-wrapped send, health log, useful fallback
    old_tail = (
        '        await app.bot.send_message(chat_id=ADMIN_ID, text=msg, parse_mode="Markdown")\n'
        '        log.info("[portfolio] Open pulse sent.")\n'
        "    except Exception as e:\n"
        '        log.error(f"[portfolio] Open pulse error: {e}")\n'
        "        try:\n"
        '            await app.bot.send_message(chat_id=ADMIN_ID, text=f"\u26a0\ufe0f Open pulse failed: {e}")\n'
        "        except Exception:\n"
        "            pass"
    )
    if old_tail not in bot:
        print("ERROR: scheduled_open_pulse send/except block not found -- aborting bot.py patch.")
        sys.exit(1)
    new_tail = (
        '        sent = await _send_admin_message(app, msg, parse_mode="Markdown")\n'
        "        if not sent:\n"
        '            raise RuntimeError("send_message failed after retries")\n'
        '        log.info("[portfolio] Open pulse sent.")\n'
        '        _log_health("open_pulse", "SUCCESS")\n'
        "    except Exception as e:\n"
        '        log.error(f"[portfolio] Open pulse error: {e}")\n'
        '        _log_health("open_pulse", f"FAILED | {e}")\n'
        "        fallback = (\n"
        "            f\"\\U0001F4CA Open Pulse \\u2014 {datetime.now(TZ).strftime('%-d %B %Y')}\\n\"\n"
        '            f"\\u26A0\\uFE0F Data sebagian tidak tersedia pagi ini (koneksi timeout).\\n"\n'
        '            f"Screener akan coba lagi otomatis besok jam 08:05 WIB.\\n"\n'
        '            f"_Error: {type(e).__name__}: {e}_"\n'
        "        )\n"
        "        try:\n"
        "            # No parse_mode: fallback embeds raw, unescaped exception text --\n"
        "            # Markdown mode would risk a \"can't parse entities\" send failure.\n"
        '            await _send_admin_message(app, fallback, retries=2, delay=3)\n'
        "        except Exception:\n"
        "            pass"
    )
    bot = bot.replace(old_tail, new_tail, 1)

    # 4. Scheduler overlap protection
    old_open_job = (
        "    scheduler.add_job(\n"
        "        scheduled_open_pulse, args=[app],\n"
        '        trigger="cron", hour=8, minute=5\n'
        "    )"
    )
    new_open_job = (
        "    scheduler.add_job(\n"
        "        scheduled_open_pulse, args=[app],\n"
        '        trigger="cron", hour=8, minute=5,\n'
        "        misfire_grace_time=300, max_instances=1,\n"
        '        id="open_pulse", replace_existing=True\n'
        "    )"
    )
    if old_open_job not in bot:
        print("ERROR: open_pulse scheduler.add_job block not found -- aborting bot.py patch.")
        sys.exit(1)
    bot = bot.replace(old_open_job, new_open_job, 1)

    old_eod_job = (
        "    scheduler.add_job(\n"
        "        scheduled_eod_report, args=[app],\n"
        '        trigger="cron", hour=16, minute=0\n'
        "    )"
    )
    new_eod_job = (
        "    scheduler.add_job(\n"
        "        scheduled_eod_report, args=[app],\n"
        '        trigger="cron", hour=16, minute=0,\n'
        "        misfire_grace_time=300, max_instances=1,\n"
        '        id="eod_report", replace_existing=True\n'
        "    )"
    )
    if old_eod_job not in bot:
        print("ERROR: eod_report scheduler.add_job block not found -- aborting bot.py patch.")
        sys.exit(1)
    bot = bot.replace(old_eod_job, new_eod_job, 1)

    tmp_bot = compile_check(BOT_PATH, bot)
    import os
    os.replace(tmp_bot, BOT_PATH)
    print("bot.py patched OK: ApplicationBuilder timeouts, retry+fallback open pulse, "
          "scheduler overlap protection, health logging.")

# ─────────────────────────────────────────────────────────────────────────
# portfolio.py
# ─────────────────────────────────────────────────────────────────────────
with open(PORTFOLIO_PATH, "r", encoding="utf-8") as f:
    pf = f.read()

if 'history(period="3d", timeout=10)' in pf:
    print("portfolio.py already patched -- nothing to do.")
else:
    old1 = '            df = tk.history(period="3d")'
    new1 = '            df = tk.history(period="3d", timeout=10)'
    if old1 not in pf:
        print("ERROR: get_prices yfinance call not found -- aborting portfolio.py patch.")
        sys.exit(1)
    pf = pf.replace(old1, new1, 1)

    old2 = '        df     = yf.Ticker(yf_sym).history(period="35d")'
    new2 = '        df     = yf.Ticker(yf_sym).history(period="35d", timeout=10)'
    if old2 not in pf:
        print("ERROR: get_ticker_signal yfinance call not found -- aborting portfolio.py patch.")
        sys.exit(1)
    pf = pf.replace(old2, new2, 1)

    tmp_pf = compile_check(PORTFOLIO_PATH, pf)
    import os
    os.replace(tmp_pf, PORTFOLIO_PATH)
    print("portfolio.py patched OK: explicit timeout=10 on yfinance .history() calls.")

print("Patch complete.")
