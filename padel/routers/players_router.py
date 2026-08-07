from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from database import User, Player
from auth import get_db, get_current_user

router = APIRouter(prefix="/api/players", tags=["players"])


class PlayerBody(BaseModel):
    name: str
    contact: Optional[str] = None


@router.get("")
def list_players(db=Depends(get_db), user: User = Depends(get_current_user)):
    return [p.to_dict() for p in db.query(Player).order_by(Player.name.asc()).all()]


@router.post("")
def create_player(body: PlayerBody, db=Depends(get_db), user: User = Depends(get_current_user)):
    player = Player(name=body.name.strip(), contact=body.contact)
    db.add(player)
    db.commit()
    db.refresh(player)
    return player.to_dict()


@router.put("/{player_id}")
def update_player(player_id: int, body: PlayerBody, db=Depends(get_db), user: User = Depends(get_current_user)):
    player = db.get(Player, player_id)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    player.name = body.name.strip()
    player.contact = body.contact
    db.commit()
    return player.to_dict()
