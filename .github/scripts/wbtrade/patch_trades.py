import textwrap

with open('/home/ubuntu/wbtrade/routers/trades.py') as f:
    src = f.read()

changed = False

if 'import csv' not in src:
    src = src.replace('import os, shutil, json', 'import os, shutil, json, csv, io')
    changed = True
    print('Added csv/io imports')

if '"trade_datetime"' not in src:
    old = '        "plan_id": t.plan_id,\n    }'
    new = (
        '        "plan_id": t.plan_id,\n'
        '        "market": t.market,\n'
        '        "trade_type": t.trade_type,\n'
        '        "qty": t.qty,\n'
        '        "opening_fee": t.opening_fee,\n'
        '        "closing_fee": t.closing_fee,\n'
        '        "funding_fee": t.funding_fee,\n'
        '        "trade_datetime": t.trade_datetime.isoformat() if t.trade_datetime else None,\n'
        '    }'
    )
    if old in src:
        src = src.replace(old, new)
        changed = True
        print('_trade_dict updated')
    else:
        print('WARNING: _trade_dict end not found - check manually')

if '"/import"' not in src:
    import_ep = '''

@router.post("/import")
async def import_bybit_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Import trades from Bybit All Perp Closed PnL CSV."""
    content_bytes = await file.read()
    text = content_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
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
            from datetime import datetime as _dt
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

if changed:
    with open('/home/ubuntu/wbtrade/routers/trades.py', 'w') as f:
        f.write(src)
    print('trades.py saved')
else:
    print('trades.py no changes needed')
