from fastapi import APIRouter, Depends, Form
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date as date_type, datetime
from database import get_db, SpotEntry, SpotTarget

router = APIRouter(prefix="/api/spot", tags=["spot"])


def _spot_dict(s): return {
    "id": s.id, "date": str(s.date), "action": s.action,
    "btc_amount": s.btc_amount, "price_usdt": s.price_usdt,
    "usdt_spent": s.usdt_spent, "thesis_tag": s.thesis_tag, "notes": s.notes,
}


@router.get("/entries")
def list_entries(db: Session = Depends(get_db)):
    rows = db.query(SpotEntry).order_by(SpotEntry.id).all()
    total_btc = 0; total_usdt = 0
    result = []
    for r in rows:
        if r.action == "buy":
            total_btc   += r.btc_amount
            total_usdt  += r.usdt_spent
        else:
            total_btc   -= r.btc_amount
            total_usdt  -= r.usdt_spent
        avg = total_usdt / total_btc if total_btc > 0 else 0
        d = _spot_dict(r)
        d.update({"running_avg": round(avg, 2), "running_btc": round(total_btc, 8)})
        result.append(d)
    return result


@router.post("/entries")
def add_entry(
    action:      str   = Form(...),
    btc_amount:  float = Form(...),
    price_usdt:  float = Form(...),
    usdt_spent:  float = Form(...),
    thesis_tag:  Optional[str] = Form(None),
    notes:       Optional[str] = Form(None),
    entry_date:  Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    d = date_type.fromisoformat(entry_date) if entry_date else datetime.utcnow().date()
    row = SpotEntry(date=d, action=action, btc_amount=btc_amount,
                    price_usdt=price_usdt, usdt_spent=usdt_spent,
                    thesis_tag=thesis_tag, notes=notes)
    db.add(row); db.commit(); db.refresh(row)
    return _spot_dict(row)


@router.get("/targets")
def list_targets(db: Session = Depends(get_db)):
    return [{"id": t.id, "label": t.label, "price_usdt": t.price_usdt,
             "btc_percent_to_sell": t.btc_percent_to_sell, "status": t.status}
            for t in db.query(SpotTarget).all()]


@router.post("/targets")
def add_target(
    label:               str   = Form(...),
    price_usdt:          float = Form(...),
    btc_percent_to_sell: float = Form(...),
    db: Session = Depends(get_db),
):
    t = SpotTarget(label=label, price_usdt=price_usdt,
                   btc_percent_to_sell=btc_percent_to_sell)
    db.add(t); db.commit()
    return {"id": t.id, "label": t.label, "price_usdt": t.price_usdt,
            "btc_percent_to_sell": t.btc_percent_to_sell, "status": t.status}


@router.put("/targets/{tid}")
def update_target_status(tid: int, status: str = Form(...), db: Session = Depends(get_db)):
    t = db.get(SpotTarget, tid)
    if t: t.status = status; db.commit()
    return {"ok": True}
