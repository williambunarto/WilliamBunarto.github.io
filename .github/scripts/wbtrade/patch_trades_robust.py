import re, textwrap

PATH = '/home/ubuntu/wbtrade/routers/trades.py'

with open(PATH) as f:
    src = f.read()

print(f'File size: {len(src)} bytes')
print('=== FIRST 60 LINES ===')
for i, line in enumerate(src.splitlines()[:60], 1):
    print(f'{i:3}: {line}')

changed = False

# 1. Add csv/io imports if missing
if 'csv' not in src:
    src = re.sub(
        r'(import os[^\n]*)',
        lambda m: m.group(0).rstrip() + ', csv, io',
        src, count=1
    )
    changed = True
    print('Added csv/io imports')
else:
    print('csv already imported')

# 2. Add new fields to _trade_dict
if 'trade_datetime' not in src:
    pattern = r'("plan_id"\s*:\s*t\.plan_id,?\s*\n)(\s*\})'
    def add_fields(m):
        indent = '        '
        fields = (
            f'{indent}"market": t.market,\n'
            f'{indent}"trade_type": t.trade_type,\n'
            f'{indent}"qty": t.qty,\n'
            f'{indent}"opening_fee": t.opening_fee,\n'
            f'{indent}"closing_fee": t.closing_fee,\n'
            f'{indent}"funding_fee": t.funding_fee,\n'
            f'{indent}"trade_datetime": (t.trade_datetime.isoformat() if hasattr(t.trade_datetime, "isoformat") else str(t.trade_datetime)) if t.trade_datetime else None,\n'
        )
        plan_line = m.group(1)
        if not plan_line.rstrip().endswith(','):
            plan_line = plan_line.rstrip('\n').rstrip() + ',\n'
        return plan_line + fields + m.group(2)
    new_src = re.sub(pattern, add_fields, src, count=1)
    if new_src != src:
        src = new_src
        changed = True
        print('_trade_dict updated with new fields')
    else:
        print('WARNING: could not find plan_id pattern in _trade_dict')
else:
    print('trade_datetime already in _trade_dict')

# 3. Add import endpoint
if '/import' not in src:
    import_ep = '''

from fastapi import UploadFile, File

@router.post("/import")
async def import_bybit_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Import trades from Bybit All Perp Closed PnL CSV."""
    import csv as _csv, io as _io
    from datetime import datetime as _dt
    content_bytes = await file.read()
    text = content_bytes.decode("utf-8-sig")
    reader = _csv.DictReader(_io.StringIO(text))
    inserted = 0
    skipped = 0
    errors = []
    for row in reader:
        try:
            market = (row.get("Market") or "").strip()
            if not market:
                continue
            qty = float(row.get("Order Quantity") or 0)
            entry = float(row.get("Entry Price") or 0)
            exit_p = float(row.get("Exit Price") or 0)
            open_fee = float(row.get("Opening Fee") or 0)
            close_fee = float(row.get("Closing Fee") or 0)
            fund_fee = float(row.get("Funding Fee") or 0)
            ttype = (row.get("Trade Type") or "Trade").strip()
            pnl = float(row.get("Realized P&L") or 0)
            tstr = (row.get("Trade time") or "").strip()
            trade_dt = _dt.strptime(tstr, "%H:%M %Y-%m-%d")
            direction = "LONG" if exit_p >= entry else "SHORT"
            outcome = "win" if pnl > 0 else "loss"
            existing = db.query(Trade).filter(
                Trade.market == market,
                Trade.trade_datetime == trade_dt,
                Trade.entry_price == entry,
                Trade.qty == qty,
            ).first()
            if existing:
                skipped += 1
                continue
            t = Trade(
                market=market, trade_type=ttype, qty=qty,
                entry_price=entry, exit_price=exit_p,
                opening_fee=open_fee, closing_fee=close_fee, funding_fee=fund_fee,
                pnl_usdt=round(pnl, 8), direction=direction, outcome=outcome,
                trade_datetime=trade_dt,
                position_size_usdt=round(entry * qty, 2),
                leverage=1, rule_violations="[]",
            )
            db.add(t)
            inserted += 1
        except Exception as e:
            errors.append(str(e))
    db.commit()
    return {"inserted": inserted, "skipped": skipped, "errors": errors[:20]}
'''
    src = src + textwrap.dedent(import_ep)
    changed = True
    print('Import endpoint added')
else:
    print('Import endpoint already present')

if changed:
    with open(PATH, 'w') as f:
        f.write(src)
    print(f'trades.py saved ({len(src)} bytes)')
else:
    print('trades.py: no changes needed')
