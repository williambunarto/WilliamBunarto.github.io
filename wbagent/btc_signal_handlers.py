"""
btc_signal_handlers.py — Telegram command handlers for the BTC/USDT signal feature.
Call register_btc_handlers(application) from bot.py to activate.
Compatible with python-telegram-bot v20+ (async).
"""

import logging
import os
import re
import time
from datetime import datetime

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from btc_signal import (
    WIB,
    _load_state,
    _save_state,
    format_signal_message,
    log_trade_to_wbtrade,
    run_scan,
)

log = logging.getLogger("btc_signal")


# ---------------------------------------------------------------------------
# /btcsignal — on-demand scan (always returns result for testing)
# ---------------------------------------------------------------------------
async def cmd_btcsignal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Scanning BTC/USDT... please wait.")
    try:
        sig = run_scan(force=True)
        if sig:
            await update.message.reply_text(format_signal_message(sig))
        else:
            await update.message.reply_text("⚠️ Data fetch failed — check server logs.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


# ---------------------------------------------------------------------------
# /setaccount <amount>
# ---------------------------------------------------------------------------
async def cmd_setaccount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        state = _load_state()
        cur = state.get("account_size", 1000)
        await update.message.reply_text(
            f"Current account size: ${cur:,.2f}\n"
            f"Usage: /setaccount 2000"
        )
        return

    try:
        amount = float(args[0].replace(",", "").replace("$", ""))
        if amount <= 0:
            raise ValueError("must be positive")
    except ValueError:
        await update.message.reply_text("❌ Invalid amount. Example: /setaccount 2000")
        return

    state = _load_state()
    state["account_size"] = amount
    _save_state(state)

    # Best-effort .env update
    env_path = "/home/ubuntu/.env"
    try:
        if os.path.exists(env_path):
            with open(env_path) as f:
                lines = f.readlines()
            found = False
            new_lines = []
            for line in lines:
                if line.startswith("TRADING_ACCOUNT_SIZE="):
                    new_lines.append(f"TRADING_ACCOUNT_SIZE={amount:.2f}\n")
                    found = True
                else:
                    new_lines.append(line)
            if not found:
                new_lines.append(f"\nTRADING_ACCOUNT_SIZE={amount:.2f}\n")
            with open(env_path, "w") as f:
                f.writelines(new_lines)
    except Exception:
        pass

    await update.message.reply_text(
        f"✅ Account size set to ${amount:,.2f}\n"
        f"2% risk per trade = ${amount * 0.02:,.2f} USDT"
    )


# ---------------------------------------------------------------------------
# /tradehistory — last 10 signals with outcomes
# ---------------------------------------------------------------------------
async def cmd_tradehistory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state   = _load_state()
    history = state.get("signal_history", []) + state.get("signals_today", [])

    if not history:
        await update.message.reply_text("No signal history yet.")
        return

    recent = history[-10:][::-1]
    lines  = ["📋 <b>Last signals:</b>\n"]
    for s in recent:
        outcome = s.get("outcome", "open")
        icon    = {"win": "✅", "loss": "❌", "skip": "⏭️"}.get(outcome, "⏳")
        pnl_str = ""
        if outcome in ("win", "loss") and "pnl_usdt" in s:
            pnl     = s["pnl_usdt"]
            pnl_str = f" | {'+' if pnl >= 0 else ''}{pnl:.2f} USDT"
        ts_str  = datetime.fromtimestamp(s.get("ts", 0), tz=WIB).strftime("%m/%d %H:%M")
        lines.append(
            f"{icon} [{ts_str}] {s.get('direction','?')} "
            f"| Score {s.get('score','?')}{pnl_str}"
        )

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


# ---------------------------------------------------------------------------
# /todaypnl
# ---------------------------------------------------------------------------
async def cmd_todaypnl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state   = _load_state()
    history = state.get("signal_history", []) + state.get("signals_today", [])

    today_str = datetime.now(WIB).strftime("%Y-%m-%d")
    today = [
        s for s in history
        if datetime.fromtimestamp(s.get("ts", 0), tz=WIB).strftime("%Y-%m-%d") == today_str
        and s.get("outcome") in ("win", "loss")
    ]

    if not today:
        await update.message.reply_text("No completed trades today.")
        return

    wins      = [s for s in today if s.get("outcome") == "win"]
    losses    = [s for s in today if s.get("outcome") == "loss"]
    total_pnl = sum(s.get("pnl_usdt", 0) for s in today)
    sign      = "+" if total_pnl >= 0 else ""

    await update.message.reply_text(
        f"📈 <b>Today's P&L</b>\n"
        f"━━━━━━━━━━━━\n"
        f"Trades : {len(wins)}W / {len(losses)}L\n"
        f"Total  : {sign}{total_pnl:.2f} USDT\n"
        f"Account: ${state.get('account_size', 1000):,.2f}",
        parse_mode="HTML",
    )


# ---------------------------------------------------------------------------
# /signalstatus
# ---------------------------------------------------------------------------
async def cmd_signalstatus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state       = _load_state()
    count_today = len(state.get("signals_today", []))
    account     = state.get("account_size", 1000)

    last_scan = "not yet"
    log_file  = "/home/ubuntu/wbagent/logs/btc_signal.log"
    try:
        if os.path.exists(log_file):
            with open(log_file) as f:
                lines = f.readlines()
            scan_lines = [l for l in lines if "Starting scan" in l]
            if scan_lines:
                last_scan = scan_lines[-1][:19]
    except Exception:
        pass

    await update.message.reply_text(
        f"🔧 <b>BTC Signal Scanner</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"Signals today : {count_today} / 5\n"
        f"Account size  : ${account:,.2f}\n"
        f"Last scan     : {last_scan}\n"
        f"Min score     : 8.5 / 10\n"
        f"Scan interval : every 7 min",
        parse_mode="HTML",
    )


# ---------------------------------------------------------------------------
# /wintrade_<id>  /losstrade_<id>  /skiptrade_<id>
# ---------------------------------------------------------------------------
async def cmd_wintrade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m = re.search(r'/wintrade_([a-f0-9]+)', update.message.text)
    if not m:
        return
    signal_id = m.group(1)
    context.user_data["awaiting_pnl"]  = signal_id
    context.user_data["pnl_outcome"]   = "win"
    await update.message.reply_text(
        f"✅ Signal <code>{signal_id}</code> — enter your profit:\n"
        f"Examples: <code>250</code> (USDT) or <code>5.2%</code>",
        parse_mode="HTML",
    )


async def cmd_losstrade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m = re.search(r'/losstrade_([a-f0-9]+)', update.message.text)
    if not m:
        return
    signal_id = m.group(1)
    context.user_data["awaiting_pnl"]  = signal_id
    context.user_data["pnl_outcome"]   = "loss"
    await update.message.reply_text(
        f"📝 Signal <code>{signal_id}</code> — enter your loss:\n"
        f"Examples: <code>200</code> (USDT) or <code>2%</code>",
        parse_mode="HTML",
    )


async def cmd_skiptrade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m = re.search(r'/skiptrade_([a-f0-9]+)', update.message.text)
    if not m:
        return
    signal_id = m.group(1)
    _record_outcome(signal_id, "skip", 0.0, 0.0)
    await update.message.reply_text(f"⏭️ Signal <code>{signal_id}</code> logged as skipped.", parse_mode="HTML")


# ---------------------------------------------------------------------------
# PnL reply handler
# ---------------------------------------------------------------------------
async def handle_pnl_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    signal_id = context.user_data.get("awaiting_pnl")
    outcome   = context.user_data.get("pnl_outcome")
    if not signal_id or not outcome:
        return

    text    = update.message.text.strip()
    state   = _load_state()
    account = state.get("account_size", 1000.0)

    try:
        if text.endswith("%"):
            pnl_pct  = float(text[:-1])
            pnl_usdt = round(account * pnl_pct / 100, 2)
        else:
            pnl_usdt = float(text.replace("$", "").replace(",", ""))
            pnl_pct  = round(pnl_usdt / account * 100, 2)
        if outcome == "loss":
            pnl_usdt = -abs(pnl_usdt)
            pnl_pct  = -abs(pnl_pct)
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid amount. Enter e.g. <code>250</code> or <code>5.2%</code>",
            parse_mode="HTML",
        )
        return

    _record_outcome(signal_id, outcome, pnl_usdt, pnl_pct)
    context.user_data.pop("awaiting_pnl", None)
    context.user_data.pop("pnl_outcome", None)

    # Count today's W/L
    state   = _load_state()
    history = state.get("signal_history", []) + state.get("signals_today", [])
    today   = datetime.now(WIB).strftime("%Y-%m-%d")
    tw = sum(1 for s in history if s.get("outcome") == "win"
             and datetime.fromtimestamp(s.get("ts", 0), tz=WIB).strftime("%Y-%m-%d") == today)
    tl = sum(1 for s in history if s.get("outcome") == "loss"
             and datetime.fromtimestamp(s.get("ts", 0), tz=WIB).strftime("%Y-%m-%d") == today)

    icon = "🏆" if outcome == "win" else "💸"
    sign = "+" if pnl_pct >= 0 else ""
    await update.message.reply_text(
        f"✅ Trade logged to dashboard\n"
        f"{icon} {outcome.upper()} — {sign}{pnl_pct:.2f}% (${pnl_usdt:+.2f})\n"
        f"Running today: {tw}W / {tl}L"
    )

    # Log to wbtrade
    sig = next(
        (s for s in history if s.get("signal_id") == signal_id),
        None,
    )
    if sig:
        log_trade_to_wbtrade(sig, outcome, pnl_usdt)


def _record_outcome(signal_id: str, outcome: str, pnl_usdt: float, pnl_pct: float):
    state = _load_state()
    for bucket in ("signals_today", "signal_history"):
        for s in state.get(bucket, []):
            if s.get("signal_id") == signal_id:
                s["outcome"]  = outcome
                s["pnl_usdt"] = pnl_usdt
                s["pnl_pct"]  = pnl_pct
    _save_state(state)


# ---------------------------------------------------------------------------
# APScheduler job (runs every 7 minutes inside the bot process)
# ---------------------------------------------------------------------------
async def _auto_scan_job(context: ContextTypes.DEFAULT_TYPE):
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not chat_id:
        return
    try:
        sig = run_scan(force=False)
        if sig:
            await context.bot.send_message(chat_id=chat_id, text=format_signal_message(sig))
    except Exception as e:
        log.error(f"Auto-scan job error: {e}")


# ---------------------------------------------------------------------------
# Registration entrypoint — called from bot.py
# ---------------------------------------------------------------------------
def register_btc_handlers(application: Application):
    """Register all BTC signal commands and the 7-minute scheduler."""

    application.add_handler(CommandHandler("btcsignal",    cmd_btcsignal))
    application.add_handler(CommandHandler("setaccount",   cmd_setaccount))
    application.add_handler(CommandHandler("tradehistory", cmd_tradehistory))
    application.add_handler(CommandHandler("todaypnl",     cmd_todaypnl))
    application.add_handler(CommandHandler("signalstatus", cmd_signalstatus))

    # Dynamic command pattern handlers (/wintrade_XXXX, etc.)
    application.add_handler(
        MessageHandler(filters.Regex(r'^/wintrade_[a-f0-9]+'),  cmd_wintrade)
    )
    application.add_handler(
        MessageHandler(filters.Regex(r'^/losstrade_[a-f0-9]+'), cmd_losstrade)
    )
    application.add_handler(
        MessageHandler(filters.Regex(r'^/skiptrade_[a-f0-9]+'), cmd_skiptrade)
    )

    # PnL reply — plain text when we're awaiting input
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_pnl_reply),
        group=1,  # lower priority than existing screener handlers
    )

    # 7-minute auto-scan scheduler
    try:
        if application.job_queue:
            application.job_queue.run_repeating(
                _auto_scan_job, interval=420, first=90
            )
            log.info("BTC signal scheduler registered (7-min interval)")
        else:
            log.warning("job_queue not available — auto-scan disabled")
    except Exception as e:
        log.warning(f"Scheduler setup failed: {e}")

    log.info("BTC signal handlers registered")
