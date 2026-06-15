from fastapi import APIRouter, Depends, Form as FForm
from sqlalchemy.orm import Session
from database import get_db, Trade, Setting
from collections import defaultdict

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/summary")
def get_summary(db: Session = Depends(get_db)):
    trades = db.query(Trade).filter(Trade.outcome.isnot(None)).all()
    if not trades:
        return {"total": 0, "wins": 0, "losses": 0, "win_rate": 0,
                "total_pnl": 0, "avg_r": 0, "best_trade": 0, "worst_trade": 0}

    wins   = [t for t in trades if t.outcome == "win"]
    losses = [t for t in trades if t.outcome == "loss"]
    pnls   = [t.pnl_usdt for t in trades if t.pnl_usdt is not None]
    rs     = [t.r_multiple for t in trades if t.r_multiple is not None]

    return {
        "total":      len(trades),
        "wins":       len(wins),
        "losses":     len(losses),
        "win_rate":   round(len(wins) / len(trades) * 100, 1),
        "total_pnl":  round(sum(pnls), 2),
        "avg_r":      round(sum(rs) / len(rs), 2) if rs else 0,
        "best_trade": round(max(pnls), 2) if pnls else 0,
        "worst_trade": round(min(pnls), 2) if pnls else 0,
    }


@router.get("/by-setup")
def stats_by_setup(db: Session = Depends(get_db)):
    trades = db.query(Trade).filter(Trade.outcome.isnot(None)).all()
    buckets = defaultdict(lambda: {"total": 0, "wins": 0, "pnl": 0.0, "r_sum": 0.0, "r_count": 0})
    for t in trades:
        tag = t.setup_tag or "untagged"
        buckets[tag]["total"] += 1
        if t.outcome == "win": buckets[tag]["wins"] += 1
        if t.pnl_usdt:         buckets[tag]["pnl"]  += t.pnl_usdt
        if t.r_multiple:
            buckets[tag]["r_sum"]   += t.r_multiple
            buckets[tag]["r_count"] += 1
    result = []
    for tag, b in buckets.items():
        result.append({
            "setup": tag,
            "total": b["total"],
            "win_rate": round(b["wins"] / b["total"] * 100, 1),
            "total_pnl": round(b["pnl"], 2),
            "avg_r": round(b["r_sum"] / b["r_count"], 2) if b["r_count"] else 0,
        })
    return sorted(result, key=lambda x: x["total_pnl"], reverse=True)


@router.get("/by-psychology")
def stats_by_psychology(db: Session = Depends(get_db)):
    trades = db.query(Trade).filter(Trade.outcome.isnot(None)).all()
    buckets = defaultdict(lambda: {"total": 0, "wins": 0, "pnl": 0.0})
    for t in trades:
        tag = t.psychology_tag or "untagged"
        buckets[tag]["total"] += 1
        if t.outcome == "win": buckets[tag]["wins"] += 1
        if t.pnl_usdt:         buckets[tag]["pnl"]  += t.pnl_usdt
    return [{"psychology": tag, "total": b["total"],
             "win_rate": round(b["wins"] / b["total"] * 100, 1),
             "total_pnl": round(b["pnl"], 2)}
            for tag, b in buckets.items()]


@router.get("/equity-curve")
def equity_curve(db: Session = Depends(get_db)):
    trades = db.query(Trade).filter(
        Trade.pnl_usdt.isnot(None)
    ).order_by(Trade.created_at).all()
    curve = []
    cumulative = 0.0
    for t in trades:
        cumulative += t.pnl_usdt
        curve.append({
            "date": t.created_at.strftime("%Y-%m-%d") if t.created_at else "",
            "pnl": round(t.pnl_usdt, 2),
            "cumulative": round(cumulative, 2),
        })
    return curve


@router.get("/monthly-pnl")
def monthly_pnl(db: Session = Depends(get_db)):
    trades = db.query(Trade).filter(Trade.pnl_usdt.isnot(None)).all()
    buckets = defaultdict(float)
    for t in trades:
        if t.created_at:
            key = t.created_at.strftime("%Y-%m")
            buckets[key] += t.pnl_usdt
    return [{"month": k, "pnl": round(v, 2)}
            for k, v in sorted(buckets.items())]


settings_router = APIRouter(prefix="/api/settings", tags=["settings"])


@settings_router.get("/")
def get_settings(db: Session = Depends(get_db)):
    rows = db.query(Setting).all()
    safe = {}
    for r in rows:
        if r.key in ("grok_api_key", "telegram_bot_token"):
            safe[r.key] = "***" if r.value else ""
        else:
            safe[r.key] = r.value
    return safe


@settings_router.put("/")
def update_settings(
    account_balance:       str = FForm(None),
    risk_percent:          str = FForm(None),
    telegram_chat_id:      str = FForm(None),
    grok_api_key:          str = FForm(None),
    telegram_bot_token:    str = FForm(None),
    alert_max_per_day:     str = FForm(None),
    alert_cooldown_hours:  str = FForm(None),
    db: Session = Depends(get_db),
):
    updates = {
        "account_balance": account_balance,
        "risk_percent": risk_percent,
        "telegram_chat_id": telegram_chat_id,
        "grok_api_key": grok_api_key,
        "telegram_bot_token": telegram_bot_token,
        "alert_max_per_day": alert_max_per_day,
        "alert_cooldown_hours": alert_cooldown_hours,
    }
    for k, v in updates.items():
        if v is not None and v != "***":
            row = db.get(Setting, k)
            if row:
                row.value = v
            else:
                db.add(Setting(key=k, value=v))
    db.commit()
    return {"ok": True}
