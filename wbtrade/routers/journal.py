from fastapi import APIRouter, Depends, Form
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date as date_type, datetime
from database import get_db, DailyBias, MonthlyReview

router = APIRouter(prefix="/api/journal", tags=["journal"])


@router.get("/daily")
def list_daily(limit: int = 30, db: Session = Depends(get_db)):
    rows = db.query(DailyBias).order_by(DailyBias.date.desc()).limit(limit).all()
    return [{"id": r.id, "date": str(r.date), "pre_market_bias": r.pre_market_bias,
             "key_levels": r.key_levels, "macro_notes": r.macro_notes,
             "system_state_snapshot": r.system_state_snapshot,
             "post_session_notes": r.post_session_notes, "day_rating": r.day_rating}
            for r in rows]


@router.post("/daily")
def upsert_daily(
    entry_date:            str            = Form(...),
    pre_market_bias:       Optional[str]  = Form(None),
    key_levels:            Optional[str]  = Form(None),
    macro_notes:           Optional[str]  = Form(None),
    post_session_notes:    Optional[str]  = Form(None),
    day_rating:            Optional[str]  = Form(None),
    db: Session = Depends(get_db),
):
    d = date_type.fromisoformat(entry_date)
    row = db.query(DailyBias).filter(DailyBias.date == d).first()
    if not row:
        row = DailyBias(date=d)
        db.add(row)
    if pre_market_bias is not None:    row.pre_market_bias = pre_market_bias
    if key_levels is not None:         row.key_levels = key_levels
    if macro_notes is not None:        row.macro_notes = macro_notes
    if post_session_notes is not None: row.post_session_notes = post_session_notes
    if day_rating is not None:         row.day_rating = day_rating
    db.commit()
    return {"ok": True, "date": str(d)}


@router.get("/monthly")
def list_monthly(db: Session = Depends(get_db)):
    rows = db.query(MonthlyReview).order_by(
        MonthlyReview.year.desc(), MonthlyReview.month.desc()).all()
    return [{"id": r.id, "year": r.year, "month": r.month,
             "start_balance": r.start_balance, "end_balance": r.end_balance,
             "goals_set": r.goals_set, "goals_achieved": r.goals_achieved,
             "lessons": r.lessons, "next_goals": r.next_goals,
             "emotional_pattern": r.emotional_pattern} for r in rows]


@router.post("/monthly")
def upsert_monthly(
    year:              int            = Form(...),
    month:             int            = Form(...),
    start_balance:     Optional[float] = Form(None),
    end_balance:       Optional[float] = Form(None),
    goals_set:         Optional[str]  = Form(None),
    goals_achieved:    Optional[str]  = Form(None),
    lessons:           Optional[str]  = Form(None),
    next_goals:        Optional[str]  = Form(None),
    emotional_pattern: Optional[str]  = Form(None),
    db: Session = Depends(get_db),
):
    row = db.query(MonthlyReview).filter_by(year=year, month=month).first()
    if not row:
        row = MonthlyReview(year=year, month=month)
        db.add(row)
    for f, v in [("start_balance", start_balance), ("end_balance", end_balance),
                 ("goals_set", goals_set), ("goals_achieved", goals_achieved),
                 ("lessons", lessons), ("next_goals", next_goals),
                 ("emotional_pattern", emotional_pattern)]:
        if v is not None: setattr(row, f, v)
    db.commit()
    return {"ok": True}
