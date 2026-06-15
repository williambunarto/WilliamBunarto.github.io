from fastapi import APIRouter, Depends, Form, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from database import get_db, TradePlan

router = APIRouter(prefix="/api/plans", tags=["plans"])


@router.get("/")
def list_plans(db: Session = Depends(get_db)):
    rows = db.query(TradePlan).order_by(TradePlan.id.desc()).all()
    return [{"id": r.id, "created_at": r.created_at.isoformat() if r.created_at else None,
             "direction": r.direction, "thesis": r.thesis,
             "entry_zone_low": r.entry_zone_low, "entry_zone_high": r.entry_zone_high,
             "stop_loss": r.stop_loss, "tp1": r.tp1, "tp2": r.tp2,
             "position_size_usdt": r.position_size_usdt, "invalidation": r.invalidation,
             "market_state_at_plan": r.market_state_at_plan, "status": r.status}
            for r in rows]


@router.post("/")
def create_plan(
    direction:            str            = Form(...),
    thesis:               str            = Form(...),
    entry_zone_low:       float          = Form(...),
    entry_zone_high:      float          = Form(...),
    stop_loss:            float          = Form(...),
    tp1:                  Optional[float] = Form(None),
    tp2:                  Optional[float] = Form(None),
    position_size_usdt:   Optional[float] = Form(None),
    invalidation:         Optional[str]  = Form(None),
    market_state_at_plan: Optional[str]  = Form(None),
    db: Session = Depends(get_db),
):
    p = TradePlan(direction=direction, thesis=thesis,
                  entry_zone_low=entry_zone_low, entry_zone_high=entry_zone_high,
                  stop_loss=stop_loss, tp1=tp1, tp2=tp2,
                  position_size_usdt=position_size_usdt, invalidation=invalidation,
                  market_state_at_plan=market_state_at_plan)
    db.add(p); db.commit(); db.refresh(p)
    return {"id": p.id, "status": p.status}


@router.put("/{plan_id}/status")
def update_plan_status(plan_id: int, status: str = Form(...), db: Session = Depends(get_db)):
    p = db.get(TradePlan, plan_id)
    if not p: raise HTTPException(404, "Plan not found")
    p.status = status; db.commit()
    return {"ok": True}
