from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from database import User, ROLE_SUPER_ADMIN, ROLE_ADMIN
from auth import get_db, require_super_admin

router = APIRouter(prefix="/api/users", tags=["users"])

VALID_ROLES = {ROLE_SUPER_ADMIN, ROLE_ADMIN}


class CreateUserBody(BaseModel):
    name: str
    username: str
    password: str
    role: str


class UpdateUserBody(BaseModel):
    name: str
    username: str
    role: str
    password: Optional[str] = None  # leave blank to keep the existing password


@router.get("")
def list_users(db=Depends(get_db), user: User = Depends(require_super_admin)):
    return [u.to_dict() for u in db.query(User).order_by(User.username.asc()).all()]


@router.post("")
def create_user(body: CreateUserBody, db=Depends(get_db), user: User = Depends(require_super_admin)):
    if body.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"role must be one of {sorted(VALID_ROLES)}")
    username = body.username.strip()
    if not username or not body.password:
        raise HTTPException(status_code=400, detail="username and password are required")
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=400, detail=f"Username '{username}' already taken")
    new_user = User(name=body.name.strip(), username=username, role=body.role)
    new_user.set_password(body.password)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user.to_dict()


@router.put("/{user_id}")
def update_user(user_id: int, body: UpdateUserBody, db=Depends(get_db),
                 user: User = Depends(require_super_admin)):
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if body.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"role must be one of {sorted(VALID_ROLES)}")
    username = body.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="username is required")
    dup = db.query(User).filter(User.username == username, User.id != user_id).first()
    if dup:
        raise HTTPException(status_code=400, detail=f"Username '{username}' already taken")
    if target.role == ROLE_SUPER_ADMIN and body.role != ROLE_SUPER_ADMIN:
        remaining = db.query(User).filter(User.role == ROLE_SUPER_ADMIN, User.id != user_id).count()
        if remaining == 0:
            raise HTTPException(status_code=400, detail="Cannot demote the last super_admin")
    target.name = body.name.strip()
    target.username = username
    target.role = body.role
    if body.password:
        target.set_password(body.password)
    db.commit()
    return target.to_dict()


@router.delete("/{user_id}")
def delete_user(user_id: int, db=Depends(get_db), user: User = Depends(require_super_admin)):
    if user_id == user.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.role == ROLE_SUPER_ADMIN:
        remaining = db.query(User).filter(User.role == ROLE_SUPER_ADMIN, User.id != user_id).count()
        if remaining == 0:
            raise HTTPException(status_code=400, detail="Cannot delete the last super_admin")
    db.delete(target)
    db.commit()
    return {"ok": True}
