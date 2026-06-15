from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db, MarketState

router = APIRouter(prefix="/api/market", tags=["market"])


@router.get("/state")
def get_latest_state(db: Session = Depends(get_db)):
    row = db.query(MarketState).order_by(MarketState.id.desc()).first()
    if not row:
        return {"state": "neutral", "label": "Neutral", "score": 0,
                "reason": "No data yet — computing on next hourly cycle.",
                "risk_note": "", "btc_price": 0, "fng_value": 50,
                "funding_rate": 0, "timestamp": None}
    return {
        "state":         row.state,
        "label":         row.state.replace("_", " ").title(),
        "score":         row.score,
        "ema_score":     row.ema_score,
        "volume_score":  row.volume_score,
        "funding_score": row.funding_score,
        "fng_score":     row.fng_score,
        "funding_rate":  row.funding_rate,
        "fng_value":     row.fng_value,
        "btc_price":     row.btc_price,
        "reason":        row.reason,
        "risk_note":     row.risk_note,
        "timestamp":     row.timestamp.isoformat() + "Z" if row.timestamp else None,
    }


@router.get("/history")
def get_state_history(limit: int = 24, db: Session = Depends(get_db)):
    rows = db.query(MarketState).order_by(MarketState.id.desc()).limit(limit).all()
    return [{"state": r.state, "score": r.score, "btc_price": r.btc_price,
             "timestamp": r.timestamp.isoformat() + "Z"} for r in reversed(rows)]
