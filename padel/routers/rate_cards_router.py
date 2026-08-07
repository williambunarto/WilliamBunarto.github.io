from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from database import User, RateCard, DAY_WEEKDAY, DAY_WEEKEND
from auth import get_db, get_current_user, require_super_admin

router = APIRouter(prefix="/api/rate-cards", tags=["rate_cards"])

VALID_DAY_TYPES = {DAY_WEEKDAY, DAY_WEEKEND}


class RateCardBody(BaseModel):
    location: str
    day_type: str
    time_band: str
    time_start: str  # "HH:MM"
    time_end: str    # "HH:MM"
    sell_price_per_hour: float


def _validate(body: RateCardBody):
    if body.day_type not in VALID_DAY_TYPES:
        raise HTTPException(status_code=400, detail=f"day_type must be one of {sorted(VALID_DAY_TYPES)}")


@router.get("")
def list_rate_cards(db=Depends(get_db), user: User = Depends(get_current_user)):
    cards = db.query(RateCard).order_by(RateCard.location.asc(), RateCard.day_type.asc(),
                                         RateCard.time_start.asc()).all()
    return [c.to_dict() for c in cards]


@router.post("")
def create_rate_card(body: RateCardBody, db=Depends(get_db), user: User = Depends(require_super_admin)):
    _validate(body)
    card = RateCard(
        location=body.location.strip(), day_type=body.day_type, time_band=body.time_band,
        time_start=body.time_start, time_end=body.time_end, sell_price_per_hour=body.sell_price_per_hour,
    )
    db.add(card)
    db.commit()
    db.refresh(card)
    return card.to_dict()


@router.put("/{card_id}")
def update_rate_card(card_id: int, body: RateCardBody, db=Depends(get_db),
                      user: User = Depends(require_super_admin)):
    _validate(body)
    card = db.get(RateCard, card_id)
    if not card:
        raise HTTPException(status_code=404, detail="Rate card not found")
    # Mutating in place is intentional per spec: rate_cards is mutable, sessions
    # keep their own price snapshot so past sessions are unaffected.
    card.location = body.location.strip()
    card.day_type = body.day_type
    card.time_band = body.time_band
    card.time_start = body.time_start
    card.time_end = body.time_end
    card.sell_price_per_hour = body.sell_price_per_hour
    db.commit()
    return card.to_dict()
