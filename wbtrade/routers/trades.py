from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from database import get_db, Trade, MarketState
from typing import Optional
from datetime import datetime
import os, shutil, json, csv, io

router = APIRouter(prefix="/api/trades", tags=["trades"])
UPLOAD_DIR = os.environ.get("WBTRADE_UPLOADS", "/home/ubuntu/wbtrade/uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


def _trade_dict(t: Trade):
    return {
        "id": t.id,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "direction": t.direction,
        "entry_price": t.entry_price,
        "exit_price": t.exit_price,
        "position_size_usdt": t.position_size_usdt,
        "leverage": t.leverage,
        "stop_loss": t.stop_loss,
        "take_profit": t.take_profit,
        "outcome": t.outcome,
        "pnl_usdt": t.pnl_usdt,
        "r_multiple": t.r_multiple,
        "setup_tag": t.setup_tag,
        "volume_tag": t.volume_tag,
        "market_state_id": t.market_state_id,
        "psychology_tag": t.psychology_tag,
        "rule_violations": json.loads(t.rule_violations) if t.rule_violations else [],
        "screenshot_path": t.screenshot_path,
        "notes": t.notes,
        "plan_id": t.plan_id,
        "market": t.market,
        "trade_type": t.trade_type,
        "qty": t.qty,
        "opening_fee": t.opening_fee,
        "closing_fee": t.closing_fee,
        "funding_fee": t.funding_fee,
        "trade_datetime": t.trade_datetime.isoformat() if t.trade_datetime else None,
    }


@router.get("/")
def list_trades(limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    rows = db.query(Trade).order_by(Trade.id.desc()).offset(offset).limit(limit).all()
    return [_trade_dict(t) for t in rows]


@router.get("/{trade_id}")
def get_trade(trade_id: int, db: Session = Depends(get_db)):
    t = db.get(Trade, trade_id)
    if not t:
        raise HTTPException(404, "Trade not found")
    return _trade_dict(t)


@router.post("/")
async def create_trade(
    direction:          str   = Form(...),
    entry_price:        float = Form(...),
    exit_price:         Optional[float] = Form(None),
    position_size_usdt: float = Form(...),
    leverage:           int   = Form(1),
    stop_loss:          Optional[float] = Form(None),
    take_profit:        Optional[float] = Form(None),
    outcome:            Optional[str]   = Form(None),
    setup_tag:          Optional[str]   = Form(None),
    volume_tag:         Optional[str]   = Form(None),
    psychology_tag:     Optional[str]   = Form(None),
    rule_violations:    Optional[str]   = Form("[]"),
    notes:              Optional[str]   = Form(None),
    plan_id:            Optional[int]   = Form(None),
    screenshot:         Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    pnl_usdt   = None
    r_multiple = None

    if exit_price and entry_price and position_size_usdt:
        if direction == "long":
            pnl_usdt = (exit_price - entry_price) / entry_price * position_size_usdt * leverage
        else:
            pnl_usdt = (entry_price - exit_price) / entry_price * position_size_usdt * leverage

    if stop_loss and entry_price and exit_price:
        risk_per_unit = abs(entry_price - stop_loss)
        gain_per_unit = abs(exit_price - entry_price)
        r_multiple = round(gain_per_unit / risk_per_unit, 2) if risk_per_unit > 0 else None
        if outcome == "loss":
            r_multiple = -abs(r_multiple) if r_multiple else -1.0

    screenshot_path = None
    if screenshot and screenshot.filename:
        fname = f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{screenshot.filename}"
        fpath = os.path.join(UPLOAD_DIR, fname)
        with open(fpath, "wb") as f:
            shutil.copyfileobj(screenshot.file, f)
        screenshot_path = f"/trade/uploads/{fname}"

    ms = db.query(MarketState).order_by(MarketState.id.desc()).first()

    t = Trade(
        direction=direction, entry_price=entry_price, exit_price=exit_price,
        position_size_usdt=position_size_usdt, leverage=leverage,
        stop_loss=stop_loss, take_profit=take_profit, outcome=outcome,
        pnl_usdt=round(pnl_usdt, 4) if pnl_usdt is not None else None,
        r_multiple=r_multiple, setup_tag=setup_tag, volume_tag=volume_tag,
        market_state_id=ms.id if ms else None,
        psychology_tag=psychology_tag,
        rule_violations=rule_violations or "[]",
        screenshot_path=screenshot_path, notes=notes, plan_id=plan_id,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return _trade_dict(t)


@router.put("/{trade_id}")
async def update_trade(
    trade_id:           int,
    exit_price:         Optional[float] = Form(None),
    outcome:            Optional[str]   = Form(None),
    pnl_usdt:           Optional[float] = Form(None),
    psychology_tag:     Optional[str]   = Form(None),
    rule_violations:    Optional[str]   = Form(None),
    notes:              Optional[str]   = Form(None),
    screenshot:         Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    t = db.get(Trade, trade_id)
    if not t:
        raise HTTPException(404, "Trade not found")

    if exit_price is not None:   t.exit_price = exit_price
    if outcome is not None:      t.outcome = outcome
    if pnl_usdt is not None:     t.pnl_usdt = pnl_usdt
    if psychology_tag is not None: t.psychology_tag = psychology_tag
    if rule_violations is not None: t.rule_violations = rule_violations
    if notes is not None:        t.notes = notes

    if screenshot and screenshot.filename:
        fname = f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{screenshot.filename}"
        fpath = os.path.join(UPLOAD_DIR, fname)
        with open(fpath, "wb") as f:
            shutil.copyfileobj(screenshot.file, f)
        t.screenshot_path = f"/trade/uploads/{fname}"

    db.commit()
    return _trade_dict(t)


@router.delete("/{trade_id}")
def delete_trade(trade_id: int, db: Session = Depends(get_db)):
    t = db.get(Trade, trade_id)
    if not t:
        raise HTTPException(404, "Trade not found")
    db.delete(t)
    db.commit()
    return {"ok": True}


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
            trade_dt = datetime.strptime(tstr, "%H:%M %Y-%m-%d")
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
