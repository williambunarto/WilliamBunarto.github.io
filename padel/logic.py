"""Core business logic: FIFO hour allocation, cost splitting, cancellation, profit.

Kept separate from the routers so the rules from the spec live in one
reviewable place.
"""
import math
from datetime import datetime, timedelta, date as date_cls

from sqlalchemy.orm import Session as OrmSession

from database import (
    CourtPackage, RateCard, PlaySession, SessionHourSlot, SlotParticipant,
    Payment, EquipmentCharge, Player,
    STATUS_ACTIVE, STATUS_CANCELLED, PAY_PENDING, PAY_CANCELLED,
    DAY_WEEKDAY, DAY_WEEKEND,
)


def day_type_for(d: date_cls) -> str:
    """Sat/Sun = weekend, everything else = weekday."""
    return DAY_WEEKEND if d.weekday() >= 5 else DAY_WEEKDAY


def add_hours(hhmm: str, hours: int) -> str:
    t = datetime.strptime(hhmm, "%H:%M")
    t = t + timedelta(hours=hours)
    return t.strftime("%H:%M")


class InsufficientHoursError(Exception):
    pass


def allocate_hours_fifo(db: OrmSession, location: str, hours_needed: int):
    """Pick `hours_needed` single-hour allocations from active court_packages
    at `location`, oldest purchase first, rolling over to the next package
    as each one runs out. Returns a list of CourtPackage (len == hours_needed).
    Caller is responsible for decrementing hours_remaining once slots are
    actually persisted.
    """
    packages = (
        db.query(CourtPackage)
        .filter(CourtPackage.location == location, CourtPackage.is_active.is_(True),
                CourtPackage.hours_remaining > 0)
        .order_by(CourtPackage.purchase_date.asc(), CourtPackage.id.asc())
        .all()
    )
    allocation = []
    remaining_by_pkg = {p.id: p.hours_remaining for p in packages}
    for pkg in packages:
        while remaining_by_pkg[pkg.id] > 0 and len(allocation) < hours_needed:
            allocation.append(pkg)
            remaining_by_pkg[pkg.id] -= 1
    if len(allocation) < hours_needed:
        have = len(allocation)
        raise InsufficientHoursError(
            f"Only {have} active hour(s) available across packages at '{location}', "
            f"need {hours_needed}. Buy another package or reduce session length."
        )
    return allocation


def split_cost_ceil(total: float, n: int):
    """Ceil-round split so the rounding remainder becomes extra margin,
    never a shortfall the owner has to absorb. Returns list of per-player shares.
    """
    if n <= 0:
        return []
    share = math.ceil(total / n)
    return [share] * n


def recompute_slot_cost_shares(slot: SessionHourSlot, sell_price_per_hour: float):
    """Recompute cost_share for all *active* participants of an hour slot.
    Cancelled participants keep their historical cost_share and are excluded
    from the split going forward.
    """
    active = [p for p in slot.participants if p.status == STATUS_ACTIVE]
    shares = split_cost_ceil(sell_price_per_hour, len(active))
    for participant, share in zip(active, shares):
        participant.cost_share = share


def sync_payments_for_session(db: OrmSession, session: PlaySession):
    """Recompute per-player amount_due for a session from its currently-active
    slot participants, creating Payment rows as needed. Confirmed payments are
    never touched here (money already confirmed doesn't get clawed back
    automatically). Pending payments that no longer have any active
    participation are zeroed out and marked cancelled.
    """
    totals = {}
    for slot in session.hour_slots:
        for p in slot.participants:
            if p.status == STATUS_ACTIVE:
                totals[p.player_id] = totals.get(p.player_id, 0) + p.cost_share

    existing = {
        pay.player_id: pay
        for pay in db.query(Payment).filter(Payment.session_id == session.id).all()
    }

    for player_id, amount_due in totals.items():
        pay = existing.get(player_id)
        if pay:
            if pay.status == PAY_PENDING:
                pay.amount_due = amount_due
            # confirmed/cancelled payments are left untouched
        else:
            db.add(Payment(
                player_id=player_id, session_id=session.id,
                amount_due=amount_due, amount_paid=0, status=PAY_PENDING,
            ))

    for player_id, pay in existing.items():
        if player_id not in totals and pay.status == PAY_PENDING:
            pay.amount_due = 0
            pay.status = PAY_CANCELLED


def session_profit(db: OrmSession, session: PlaySession) -> dict:
    """Profit per session per spec:
    Σ(confirmed cost_share) − (hours used × cost_per_hour of allocated package)
      − Σ equipment_charges
    Also reports a profit_incl_pending figure (counts unconfirmed cost_share
    too) so the dashboard can show both a conservative and an optimistic view.
    """
    revenue_confirmed = 0.0
    revenue_pending = 0.0
    for slot in session.hour_slots:
        for p in slot.participants:
            if p.status != STATUS_ACTIVE:
                continue
            payment = (
                db.query(Payment)
                .filter(Payment.session_id == session.id, Payment.player_id == p.player_id)
                .first()
            )
            if payment and payment.status == "confirmed":
                revenue_confirmed += p.cost_share
            else:
                revenue_pending += p.cost_share

    cost = 0.0
    hours_used = 0
    for slot in session.hour_slots:
        if slot.package_id:
            hours_used += 1
            cost += slot.package.cost_per_hour

    equipment_total = sum(e.amount for e in session.equipment_charges)

    return {
        "session_id": session.id,
        "revenue_confirmed": round(revenue_confirmed, 2),
        "revenue_pending": round(revenue_pending, 2),
        "hours_used": hours_used,
        "package_cost": round(cost, 2),
        "equipment_cost": round(equipment_total, 2),
        "profit_confirmed": round(revenue_confirmed - cost - equipment_total, 2),
        "profit_incl_pending": round(revenue_confirmed + revenue_pending - cost - equipment_total, 2),
    }


def full_cancel_session(db: OrmSession, session: PlaySession):
    """Full cancel: session never happened. Return allocated hours to their
    packages, cancel all participants, void unpaid payments. Confirmed
    payments are left untouched (money already collected/confirmed needs a
    manual refund decision, not an automatic reversal).
    """
    for slot in session.hour_slots:
        if slot.package_id:
            pkg = slot.package
            pkg.hours_remaining = min(pkg.total_hours, pkg.hours_remaining + 1)
            if pkg.hours_remaining > 0:
                pkg.is_active = True
            slot.package_id = None
        for participant in slot.participants:
            participant.status = STATUS_CANCELLED

    for payment in db.query(Payment).filter(Payment.session_id == session.id).all():
        if payment.status == PAY_PENDING:
            payment.status = PAY_CANCELLED

    session.status = STATUS_CANCELLED
    session.cancelled_at = datetime.utcnow()
