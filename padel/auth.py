"""Session-based auth helpers for the padel app.

Uses Starlette's cookie SessionMiddleware (signed, not encrypted — fine for
storing a user id + role, nothing sensitive). Secret key comes from the
PADEL_SECRET_KEY env var; a random one is generated per-process if unset
(fine for local dev, but means logins won't survive a restart in prod —
set PADEL_SECRET_KEY in the systemd unit for real deployments).
"""
from fastapi import Depends, HTTPException, Request, status

from database import SessionLocal, User, ROLE_SUPER_ADMIN


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(request: Request, db=Depends(get_db)) -> User:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    user = db.get(User, user_id)
    if not user:
        request.session.clear()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user


def require_super_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != ROLE_SUPER_ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="super_admin only")
    return user
