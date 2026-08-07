from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from database import User, RateCard, Location, DAY_WEEKDAY, DAY_WEEKEND
from auth import get_db, get_current_user

router = APIRouter(prefix="/api/rate-cards", tags=["rate_cards"])

VALID_DAY_TYPES = {DAY_WEEKDAY, DAY_WEEKEND}


class RateCardBody(BaseModel):
    location_id: int
    day_type: str
    time_band: str
    time_start: str  # "HH:MM"
    time_end: str    # "HH:MM"
    sell_price_per_hour: float


def _validate(db, body: RateCardBody):
    if body.day_type not in VALID_DAY_TYPES:
        raise HTTPException(status_code=400, detail=f"day_type must be one of {sorted(VALID_DAY_TYPES)}")
    if not db.get(Location, body.location_id):
        raise HTTPException(status_code=404, detail="location_id not found")


@router.get("")
def list_rate_cards(location_id: Optional[int] = None, db=Depends(get_db),
                     user: User = Depends(get_current_user)):
    q = db.query(RateCard)
    if location_id is not None:
        q = q.filter(RateCard.location_id == location_id)
    cards = q.order_by(RateCard.location_id.asc(), RateCard.day_type.asc(),
                        RateCard.time_start.asc()).all()
    return [c.to_dict() for c in cards]


@router.post("")
def create_rate_card(body: RateCardBody, db=Depends(get_db), user: User = Depends(get_current_user)):
    _validate(db, body)
    card = RateCard(
        location_id=body.location_id, day_type=body.day_type, time_band=body.time_band,
        time_start=body.time_start, time_end=body.time_end, sell_price_per_hour=body.sell_price_per_hour,
    )
    db.add(card)
    db.commit()
    db.refresh(card)
    return card.to_dict()


@router.put("/{card_id}")
def update_rate_card(card_id: int, body: RateCardBody, db=Depends(get_db),
                      user: User = Depends(get_current_user)):
    _validate(db, body)
    card = db.get(RateCard, card_id)
    if not card:
        raise HTTPException(status_code=404, detail="Rate card not found")
    # Mutating in place is intentional per spec: rate_cards is mutable, sessions
    # keep their own price snapshot so past sessions are unaffected.
    card.location_id = body.location_id
    card.day_type = body.day_type
    card.time_band = body.time_band
    card.time_start = body.time_start
    card.time_end = body.time_end
    card.sell_price_per_hour = body.sell_price_per_hour
    db.commit()
    return card.to_dict()


@router.delete("/{card_id}")
def delete_rate_card(card_id: int, db=Depends(get_db), user: User = Depends(get_current_user)):
    card = db.get(RateCard, card_id)
    if not card:
        raise HTTPException(status_code=404, detail="Rate card not found")
    db.delete(card)
    db.commit()
    return {"ok": True}
