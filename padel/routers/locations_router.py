from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from database import User, Location
from auth import get_db, get_current_user

router = APIRouter(prefix="/api/locations", tags=["locations"])


class LocationBody(BaseModel):
    name: str
    notes: Optional[str] = None


@router.get("")
def list_locations(db=Depends(get_db), user: User = Depends(get_current_user)):
    return [l.to_dict() for l in db.query(Location).order_by(Location.name.asc()).all()]


@router.post("")
def create_location(body: LocationBody, db=Depends(get_db), user: User = Depends(get_current_user)):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Location name is required")
    if db.query(Location).filter(Location.name == name).first():
        raise HTTPException(status_code=400, detail=f"Location '{name}' already exists")
    loc = Location(name=name, notes=body.notes)
    db.add(loc)
    db.commit()
    db.refresh(loc)
    return loc.to_dict()


@router.put("/{location_id}")
def update_location(location_id: int, body: LocationBody, db=Depends(get_db),
                     user: User = Depends(get_current_user)):
    loc = db.get(Location, location_id)
    if not loc:
        raise HTTPException(status_code=404, detail="Location not found")
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Location name is required")
    dup = db.query(Location).filter(Location.name == name, Location.id != location_id).first()
    if dup:
        raise HTTPException(status_code=400, detail=f"Location '{name}' already exists")
    loc.name = name
    loc.notes = body.notes
    db.commit()
    return loc.to_dict()
