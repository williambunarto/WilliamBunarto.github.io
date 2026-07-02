"""
billpay.py — /billpay command for WBAgent Telegram bot

Usage:   /billpay <cardname> <amount>
Example: /billpay jenius 1000000

Writes to the current month tab in Google Sheet:
  - Adds <amount> to Paid column (cumulative)
  - Sets Date Paid to today
  - Recomputes Status: ✓ Paid / ◑ Partial / ✗ Unpaid
"""

import asyncio
import re
import logging
from datetime import date

import gspread
from google.oauth2.service_account import Credentials
from telegram import Update
from telegram.ext import ContextTypes

log = logging.getLogger(__name__)

SHEET_ID   = "1zBx1FcJq7PSjMjYujNCAwaNiX5ulWPe6"
CREDS_FILE = "/home/ubuntu/wbagent/gsheets-creds.json"
SCOPES     = ["https://www.googleapis.com/auth/spreadsheets"]

_SECTIONS = {"credit cards", "ewallet-paylater", "ewallet", "paylater",
             "fixed expenses", "fixed", "expenses"}
_TOTALS   = {"total", "subtotal", "grand", "jumlah", "summary"}


def _gc():
    creds = Credentials.from_service_account_file(CREDS_FILE, scopes=SCOPES)
    return gspread.authorize(creds)


def _tab():
    return date.today().strftime("%B %Y")  # e.g. "July 2026"


def _master_names(sp):
    """Flat list of canonical card/account names from MASTER DATA tab."""
    try:
        ws = sp.worksheet("MASTER DATA")
        out = []
        for row in ws.get_all_values():
            for cell in row:
                c  = cell.strip()
                cl = c.lower()
                if c and cl not in _SECTIONS and cl not in _TOTALS \
                        and cl not in {"name", "nama", "card", "account", ""}:
                    out.append(c)
        return out
    except Exception:
        return []


def _col(headers, *kws):
    """Return 0-based column index matching any keyword, else -1."""
    for i, h in enumerate(headers):
        hl = h.lower().strip()
        for kw in kws:
            if kw.lower() in hl:
                return i
    return -1


def _num(val):
    """Parse IDR-formatted string to float.
    Handles: '1.500.000', '1,500,000', '1500000', 'Rp 1.000.000'.
    """
    s = re.sub(r"[Rp\sIDR]", "", str(val))
    if re.search(r"\.\d{3}(?:[.,]|$)", s):   # dot-thousands separator
        s = s.replace(".", "")
    s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _is_data_row(row, nc):
    """True if row is a real data row, not a section header or total."""
    if nc >= len(row):
        return False
    c  = row[nc].strip()
    cl = c.lower()
    return bool(c) and cl not in _SECTIONS and not any(tw in cl for tw in _TOTALS)


# ── core logic ────────────────────────────────────────────────────────────────

def billpay_sync(card_q: str, amount: int):
    """Execute billpay logic synchronously. Returns (reply_str, err_str)."""
    gc = _gc()
    sp = gc.open_by_key(SHEET_ID)
    tab = _tab()

    try:
        ws = sp.worksheet(tab)
    except gspread.exceptions.WorksheetNotFound:
        tabs = [w.title for w in sp.worksheets()]
        return None, f"Tab '{tab}' not found.\nAvailable: {', '.join(tabs)}"

    master = _master_names(sp)
    rows   = ws.get_all_values()

    # Find header row (first row with a name-ish AND a bill/paid column)
    hdr_i, hdr = -1, []
    for i, row in enumerate(rows):
        j = " ".join(row).lower()
        if ("name" in j or "nama" in j) and \
                ("bill" in j or "paid" in j or "tagihan" in j or "bayar" in j):
            hdr_i, hdr = i, row
            break

    if hdr_i < 0:
        return None, (
            "Cannot find header row in monthly tab.\n"
            f"First 3 rows: {rows[:3]}"
        )

    nc = _col(hdr, "name", "nama", "card", "account")
    bc = _col(hdr, "bill", "tagihan", "limit", "amount due", "total bill")
    pc = _col(hdr, "paid ↓", "paid↓", "paid", "bayar", "payment")
    dc = _col(hdr, "date paid", "tanggal bayar", "date", "tanggal")
    sc = _col(hdr, "status")

    missing = [n for n, c in [("Name", nc), ("Bill", bc), ("Paid", pc)] if c < 0]
    if missing:
        return None, f"Cannot find columns: {', '.join(missing)}\nHeader found: {hdr}"

    # Search for matching row
    query = card_q.lower().strip()
    matches = []
    for ri in range(hdr_i + 1, len(rows)):
        row = rows[ri]
        if _is_data_row(row, nc) and query in row[nc].lower():
            matches.append({"ri": ri, "name": row[nc].strip(), "row": row})

    # Fallback: search via master names then re-look in sheet
    if not matches and master:
        for mn in master:
            if query in mn.lower():
                for ri in range(hdr_i + 1, len(rows)):
                    row = rows[ri]
                    if _is_data_row(row, nc) and \
                            (mn.lower() in row[nc].lower() or
                             row[nc].lower() in mn.lower()):
                        matches.append({"ri": ri, "name": row[nc].strip(), "row": row})
                break

    if not matches:
        avail = ", ".join(master[:20]) or "(no master data loaded)"
        return None, f"No match for '{card_q}' in {tab}.\nKnown names: {avail}"

    # Deduplicate by name
    seen, dedup = set(), []
    for m in matches:
        if m["name"].lower() not in seen:
            seen.add(m["name"].lower())
            dedup.append(m)

    if len(dedup) > 1:
        opts = "\n".join(f"• {m['name']}" for m in dedup)
        return None, f"Multiple matches for '{card_q}':\n{opts}\n\nBe more specific."

    m    = dedup[0]
    ri   = m["ri"]
    row  = m["row"]
    name = m["name"]
    sr   = ri + 1   # gspread uses 1-based row index

    bill      = _num(row[bc] if bc < len(row) else "")
    prev_paid = _num(row[pc] if pc < len(row) else "")
    new_paid  = prev_paid + amount
    remaining = max(0.0, bill - new_paid)

    if new_paid <= 0:
        new_status = "✗ Unpaid"
    elif bill > 0 and new_paid >= bill:
        new_status = "✓ Paid"
    else:
        new_status = "◑ Partial"

    today = date.today().strftime("%d/%m/%Y")

    ws.update_cell(sr, pc + 1, int(new_paid))
    if dc >= 0:
        ws.update_cell(sr, dc + 1, today)
    if sc >= 0:
        ws.update_cell(sr, sc + 1, new_status)

    util_pct  = (new_paid / bill * 100) if bill > 0 else 0.0
    util_warn = "\n⚠️ Utilization still >30%" if (util_pct > 30 and new_status != "✓ Paid") else ""

    def fmt(n):
        return f"Rp {int(n):,}".replace(",", ".")

    reply = (
        f"✅ *{name}* — Payment recorded\n\n"
        f"\U0001f4b8 Paid now:     {fmt(amount)}\n"
        f"\U0001f4ca Total paid:   {fmt(int(new_paid))} / {fmt(int(bill))}\n"
        f"\U0001f4b0 Remaining:    {fmt(int(remaining))}\n"
        f"\U0001f4c8 Utilization:  {util_pct:.1f}%\n"
        f"\U0001f4cc Status:       {new_status}\n"
        f"\U0001f4c5 Date:         {today}"
        f"{util_warn}"
    )
    return reply, None


# ── Telegram handler ──────────────────────────────────────────────────────────

async def cmd_billpay(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args or []
    if len(args) < 2:
        await update.message.reply_text(
            "Usage: /billpay <cardname> <amount>\n"
            "Example: /billpay jenius 1000000"
        )
        return

    card_q = args[0]
    try:
        amount = int(re.sub(r"[,.]", "", args[1]))
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid amount — use digits only\n"
            "Example: /billpay jenius 1000000"
        )
        return

    status_msg = await update.message.reply_text("⏳ Processing payment…")
    try:
        loop = asyncio.get_event_loop()
        reply, err = await loop.run_in_executor(None, billpay_sync, card_q, amount)
        if err:
            await status_msg.edit_text(f"❌ {err}")
        else:
            await status_msg.edit_text(reply, parse_mode="Markdown")
    except Exception as exc:
        log.exception("billpay error")
        await status_msg.edit_text(f"❌ Unexpected error: {exc}")
