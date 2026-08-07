from datetime import date as date_cls
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from database import User, CourtPackage, Location
from auth import get_db, get_current_user

router = APIRouter(prefix="/api/packages", tags=["packages"])


class PackageBody(BaseModel):
    location_id: int
    total_hours: int = 30
    price_paid: float
    purchase_date: Optional[date_cls] = None


@router.get("")
def list_packages(db=Depends(get_db), user: User = Depends(get_current_user)):
    pkgs = db.query(CourtPackage).order_by(CourtPackage.purchase_date.desc(), CourtPackage.id.desc()).all()
    return [p.to_dict() for p in pkgs]


@router.post("")
def create_package(body: PackageBody, db=Depends(get_db), user: User = Depends(get_current_user)):
    if body.total_hours <= 0:
        raise HTTPException(status_code=400, detail="total_hours must be positive")
    if not db.get(Location, body.location_id):
        raise HTTPException(status_code=404, detail="location_id not found")
    pkg = CourtPackage(
        location_id=body.location_id,
        total_hours=body.total_hours,
        price_paid=body.price_paid,
        hours_remaining=body.total_hours,
        purchase_date=body.purchase_date or date_cls.today(),
        is_active=True,
    )
    db.add(pkg)
    db.commit()
    db.refresh(pkg)
    return pkg.to_dict()


@router.post("/{package_id}/deactivate")
def deactivate_package(package_id: int, db=Depends(get_db), user: User = Depends(get_current_user)):
    """Manually retire a package (e.g. it was recorded in error) without deleting history."""
    pkg = db.get(CourtPackage, package_id)
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")
    pkg.is_active = False
    db.commit()
    return pkg.to_dict()
