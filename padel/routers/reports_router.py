from datetime import date as date_cls
from typing import Optional
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from database import (
    User, PlaySession, CourtPackage, Player, SlotParticipant, Payment,
    STATUS_ACTIVE, PAY_CONFIRMED, PAY_PENDING,
)
from auth import get_db, get_current_user
from logic import session_profit

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/dashboard")
def dashboard(month: Optional[str] = None, db=Depends(get_db), user: User = Depends(get_current_user)):
    """Monthly profit + hour utilization. `month` is 'YYYY-MM'; defaults to
    the current month. Utilization = hours used this month across ACTIVE
    sessions vs. total hours purchased across all court_packages to date.
    """
    if month:
        try:
            year, mon = (int(x) for x in month.split("-"))
        except ValueError:
            raise HTTPException(status_code=400, detail="month must be 'YYYY-MM'")
    else:
        today = date_cls.today()
        year, mon = today.year, today.month

    sessions = (
        db.query(PlaySession)
        .filter(PlaySession.status == STATUS_ACTIVE)
        .all()
    )
    month_sessions = [s for s in sessions if s.date.year == year and s.date.month == mon]

    total_profit_confirmed = 0.0
    total_profit_incl_pending = 0.0
    hours_used_month = 0
    by_location = defaultdict(lambda: {"sessions": 0, "hours_used": 0, "profit_confirmed": 0.0})

    for s in month_sessions:
        p = session_profit(db, s)
        total_profit_confirmed += p["profit_confirmed"]
        total_profit_incl_pending += p["profit_incl_pending"]
        hours_used_month += p["hours_used"]
        loc_name = s.location_ref.name if s.location_ref else f"location #{s.location_id}"
        by_location[loc_name]["sessions"] += 1
        by_location[loc_name]["hours_used"] += p["hours_used"]
        by_location[loc_name]["profit_confirmed"] += p["profit_confirmed"]

    packages = db.query(CourtPackage).all()
    hours_purchased_total = sum(pkg.total_hours for pkg in packages)
    hours_remaining_total = sum(pkg.hours_remaining for pkg in packages)
    hours_used_total = hours_purchased_total - hours_remaining_total
    utilization_pct = round((hours_used_total / hours_purchased_total) * 100, 1) if hours_purchased_total else 0

    return {
        "month": f"{year:04d}-{mon:02d}",
        "sessions_count": len(month_sessions),
        "hours_used_this_month": hours_used_month,
        "profit_confirmed": round(total_profit_confirmed, 2),
        "profit_incl_pending": round(total_profit_incl_pending, 2),
        "by_location": by_location,
        "hours_purchased_total": hours_purchased_total,
        "hours_remaining_total": hours_remaining_total,
        "hours_used_total": hours_used_total,
        "utilization_pct": utilization_pct,
    }


def _player_summary(db, player: Player) -> dict:
    participations = (
        db.query(SlotParticipant)
        .join(SlotParticipant.hour_slot)
        .filter(SlotParticipant.player_id == player.id, SlotParticipant.status == STATUS_ACTIVE)
        .all()
    )
    session_ids = {p.hour_slot.session_id for p in participations}
    last_played = None
    if session_ids:
        dates = [db.get(PlaySession, sid).date for sid in session_ids]
        last_played = max(dates).isoformat()

    payments = db.query(Payment).filter(Payment.player_id == player.id).all()
    billable = [p for p in payments if p.status in (PAY_CONFIRMED, PAY_PENDING)]
    total_paid = sum(p.amount_paid for p in payments if p.status == PAY_CONFIRMED)
    outstanding = sum(p.amount_due - p.amount_paid for p in payments if p.status == PAY_PENDING)
    confirmed_count = sum(1 for p in billable if p.status == PAY_CONFIRMED)
    reliability_pct = round((confirmed_count / len(billable)) * 100, 1) if billable else None

    return {
        "player_id": player.id,
        "name": player.name,
        "contact": player.contact,
        "sessions_count": len(session_ids),
        "total_paid": round(total_paid, 2),
        "outstanding": round(outstanding, 2),
        "last_played": last_played,
        "reliability_pct": reliability_pct,
    }


@router.get("/players")
def player_stats(db=Depends(get_db), user: User = Depends(get_current_user)):
    """Per-player history: sessions played, total paid, outstanding, reliability."""
    players = db.query(Player).all()
    results = [_player_summary(db, p) for p in players]
    results.sort(key=lambda r: r["name"].lower())
    return results


@router.get("/players/{player_id}")
def player_detail(player_id: int, db=Depends(get_db), user: User = Depends(get_current_user)):
    """Drill-down for the Payments page: totals (sum paid, sum outstanding,
    reliability) plus the itemized list of every payment for this player,
    so clicking a player shows exactly what they owe and what they've paid.
    """
    player = db.get(Player, player_id)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    summary = _player_summary(db, player)
    payments = (
        db.query(Payment)
        .filter(Payment.player_id == player_id)
        .order_by(Payment.created_at.desc())
        .all()
    )
    items = []
    for pay in payments:
        session = db.get(PlaySession, pay.session_id)
        items.append({
            **pay.to_dict(),
            "session_date": session.date.isoformat() if session else None,
            "session_location": session.location_ref.name if session and session.location_ref else None,
        })

    return {**summary, "payments": items}
