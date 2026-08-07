from datetime import date as date_cls
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from database import (
    User, PlaySession, SessionHourSlot, SlotParticipant, RateCard, Player, Location,
    EquipmentCharge, STATUS_ACTIVE, STATUS_CANCELLED, MAX_PLAYERS_PER_HOUR,
)
from auth import get_db, get_current_user
from logic import (
    day_type_for, add_hours, allocate_hours_fifo, recompute_slot_cost_shares,
    sync_payments_for_session, session_profit, full_cancel_session,
)

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


class CreateSessionBody(BaseModel):
    date: date_cls
    location_id: int
    start_time: str  # "HH:MM"
    total_hours: int
    rate_card_id: Optional[int] = None
    # optional: participants for each hour, e.g. [[1,2,3,4],[1,2,3,4],[..]] for a 3-hour session.
    # Each hour's list must have at most MAX_PLAYERS_PER_HOUR (12) players; the UI defaults to
    # 4 per hour but this isn't enforced as a hard minimum server-side (a session can be
    # created before all players are confirmed and filled in later via add_participant).
    participants_by_hour: Optional[List[List[int]]] = None


class AddParticipantBody(BaseModel):
    player_id: int


class EquipmentBody(BaseModel):
    item: str
    amount: float


def _resolve_rate_card(db, body: CreateSessionBody) -> RateCard:
    if body.rate_card_id:
        card = db.get(RateCard, body.rate_card_id)
        if not card:
            raise HTTPException(status_code=404, detail="rate_card_id not found")
        return card

    day_type = day_type_for(body.date)
    candidates = (
        db.query(RateCard)
        .filter(RateCard.location_id == body.location_id, RateCard.day_type == day_type)
        .all()
    )
    for card in candidates:
        if card.time_start <= body.start_time < card.time_end:
            return card
    location = db.get(Location, body.location_id)
    loc_name = location.name if location else body.location_id
    raise HTTPException(
        status_code=400,
        detail=(
            f"No rate card found for {loc_name}/{day_type} covering {body.start_time}. "
            "Add a rate card for this location first (Data > Locations)."
        ),
    )


def _validate_hour_participants(player_ids: List[int]):
    if len(player_ids) > MAX_PLAYERS_PER_HOUR:
        raise HTTPException(
            status_code=400,
            detail=f"An hour can have at most {MAX_PLAYERS_PER_HOUR} players (got {len(player_ids)})",
        )
    if len(player_ids) != len(set(player_ids)):
        raise HTTPException(status_code=400, detail="Duplicate player in the same hour")


def _session_detail(db, session: PlaySession) -> dict:
    data = session.to_dict()
    data["hour_slots"] = [s.to_dict() for s in session.hour_slots]
    data["equipment_charges"] = [e.to_dict() for e in session.equipment_charges]
    data["profit"] = session_profit(db, session)
    return data


@router.get("")
def list_sessions(status_filter: Optional[str] = None, db=Depends(get_db),
                   user: User = Depends(get_current_user)):
    q = db.query(PlaySession)
    if status_filter:
        q = q.filter(PlaySession.status == status_filter)
    sessions = q.order_by(PlaySession.date.desc(), PlaySession.id.desc()).all()
    return [_session_detail(db, s) for s in sessions]


@router.get("/{session_id}")
def get_session(session_id: int, db=Depends(get_db), user: User = Depends(get_current_user)):
    session = db.get(PlaySession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return _session_detail(db, session)


@router.post("")
def create_session(body: CreateSessionBody, db=Depends(get_db), user: User = Depends(get_current_user)):
    if body.total_hours <= 0:
        raise HTTPException(status_code=400, detail="total_hours must be positive")
    if not db.get(Location, body.location_id):
        raise HTTPException(status_code=404, detail="location_id not found")
    if body.participants_by_hour is not None and len(body.participants_by_hour) != body.total_hours:
        raise HTTPException(status_code=400, detail="participants_by_hour length must equal total_hours")
    if body.participants_by_hour:
        for hour_players in body.participants_by_hour:
            _validate_hour_participants(hour_players)

    rate_card = _resolve_rate_card(db, body)

    # Packages are optional: allocation fills as many hours as active packages
    # cover (FIFO, oldest first) and leaves the rest unbacked (None) rather
    # than blocking session creation.
    allocation = allocate_hours_fifo(db, body.location_id, body.total_hours)

    session = PlaySession(
        date=body.date,
        location_id=body.location_id,
        start_time=body.start_time,
        end_time=add_hours(body.start_time, body.total_hours),
        total_hours=body.total_hours,
        rate_card_id=rate_card.id,
        sell_price_per_hour_snapshot=rate_card.sell_price_per_hour,
        status=STATUS_ACTIVE,
        created_by=user.id,
    )
    db.add(session)
    db.flush()  # get session.id

    for i in range(body.total_hours):
        pkg = allocation[i]
        if pkg is not None:
            pkg.hours_remaining -= 1
            if pkg.hours_remaining <= 0:
                pkg.is_active = False

        slot = SessionHourSlot(
            session_id=session.id,
            hour_index=i + 1,
            start_time=add_hours(body.start_time, i),
            end_time=add_hours(body.start_time, i + 1),
            package_id=pkg.id if pkg is not None else None,
        )
        db.add(slot)
        db.flush()

        player_ids = body.participants_by_hour[i] if body.participants_by_hour else []
        for player_id in player_ids:
            if not db.get(Player, player_id):
                raise HTTPException(status_code=404, detail=f"player_id {player_id} not found")
            db.add(SlotParticipant(hour_slot_id=slot.id, player_id=player_id, cost_share=0,
                                    status=STATUS_ACTIVE))
        db.flush()
        recompute_slot_cost_shares(slot, session.sell_price_per_hour_snapshot)

    sync_payments_for_session(db, session)
    db.commit()
    db.refresh(session)
    return _session_detail(db, session)


@router.post("/{session_id}/slots/{slot_id}/participants")
def add_participant(session_id: int, slot_id: int, body: AddParticipantBody, db=Depends(get_db),
                     user: User = Depends(get_current_user)):
    session = db.get(PlaySession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.status != STATUS_ACTIVE:
        raise HTTPException(status_code=400, detail="Session is cancelled")
    slot = db.get(SessionHourSlot, slot_id)
    if not slot or slot.session_id != session_id:
        raise HTTPException(status_code=404, detail="Hour slot not found")
    if not db.get(Player, body.player_id):
        raise HTTPException(status_code=404, detail="Player not found")
    active = [p for p in slot.participants if p.status == STATUS_ACTIVE]
    if any(p.player_id == body.player_id for p in active):
        raise HTTPException(status_code=400, detail="Player already active in this hour slot")
    if len(active) >= MAX_PLAYERS_PER_HOUR:
        raise HTTPException(status_code=400,
                             detail=f"This hour already has the max of {MAX_PLAYERS_PER_HOUR} players")

    # Append via the relationship (not a bare hour_slot_id= FK assignment) so the
    # in-memory slot.participants collection — already cached by the duplicate
    # check above — actually includes the new row when recompute reads it below.
    slot.participants.append(SlotParticipant(player_id=body.player_id, cost_share=0,
                                               status=STATUS_ACTIVE))
    db.flush()
    recompute_slot_cost_shares(slot, session.sell_price_per_hour_snapshot)
    sync_payments_for_session(db, session)
    db.commit()
    return _session_detail(db, session)


@router.post("/{session_id}/participants/{participant_id}/cancel")
def cancel_participant(session_id: int, participant_id: int, db=Depends(get_db),
                        user: User = Depends(get_current_user)):
    """Partial cancel: one player backs out of one hour slot. The session
    keeps running (per spec, hours already allocated are NOT returned) and
    the hour's cost is re-split across whoever is left active in that slot.
    """
    session = db.get(PlaySession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.status != STATUS_ACTIVE:
        raise HTTPException(status_code=400, detail="Session is cancelled")
    participant = db.get(SlotParticipant, participant_id)
    if not participant or participant.hour_slot.session_id != session_id:
        raise HTTPException(status_code=404, detail="Participant not found in this session")
    if participant.status == STATUS_CANCELLED:
        return _session_detail(db, session)

    participant.status = STATUS_CANCELLED
    slot = participant.hour_slot
    recompute_slot_cost_shares(slot, session.sell_price_per_hour_snapshot)
    sync_payments_for_session(db, session)
    db.commit()
    return _session_detail(db, session)


@router.post("/{session_id}/cancel")
def cancel_session(session_id: int, db=Depends(get_db), user: User = Depends(get_current_user)):
    """Full cancel: nobody played. Hours go back to their court_packages."""
    session = db.get(PlaySession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.status == STATUS_CANCELLED:
        return _session_detail(db, session)
    full_cancel_session(db, session)
    db.commit()
    return _session_detail(db, session)


@router.post("/{session_id}/equipment")
def add_equipment(session_id: int, body: EquipmentBody, db=Depends(get_db),
                   user: User = Depends(get_current_user)):
    session = db.get(PlaySession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    charge = EquipmentCharge(session_id=session_id, item=body.item.strip(), amount=body.amount,
                              absorbed_by="owner")
    db.add(charge)
    db.commit()
    return _session_detail(db, session)
