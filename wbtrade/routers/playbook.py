from fastapi import APIRouter, Depends, Form, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
import json, os, shutil
from datetime import datetime
from database import get_db, Playbook

router = APIRouter(prefix="/api/playbook", tags=["playbook"])
UPLOAD_DIR = os.environ.get("WBTRADE_UPLOADS", "/home/ubuntu/wbtrade/uploads")


def _pb_dict(p):
    return {
        "id": p.id, "name": p.name, "description": p.description,
        "conditions": json.loads(p.conditions) if p.conditions else [],
        "volume_behavior": p.volume_behavior, "funding_context": p.funding_context,
        "best_market_state": p.best_market_state,
        "screenshot_paths": json.loads(p.screenshot_paths) if p.screenshot_paths else [],
    }


@router.get("/")
def list_setups(db: Session = Depends(get_db)):
    return [_pb_dict(p) for p in db.query(Playbook).all()]


@router.post("/")
async def create_setup(
    name:              str  = Form(...),
    description:       Optional[str] = Form(None),
    conditions:        Optional[str] = Form(None),
    volume_behavior:   Optional[str] = Form(None),
    funding_context:   Optional[str] = Form(None),
    best_market_state: Optional[str] = Form(None),
    screenshot:        Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    conds = [c.strip().lstrip('-').strip() for c in (conditions or '').split('\n') if c.strip()]
    paths = []
    if screenshot and screenshot.filename:
        fname = f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{screenshot.filename}"
        fpath = os.path.join(UPLOAD_DIR, fname)
        with open(fpath, "wb") as f:
            shutil.copyfileobj(screenshot.file, f)
        paths.append(f"/trade/uploads/{fname}")

    p = Playbook(name=name, description=description,
                 conditions=json.dumps(conds), volume_behavior=volume_behavior,
                 funding_context=funding_context, best_market_state=best_market_state,
                 screenshot_paths=json.dumps(paths))
    db.add(p); db.commit(); db.refresh(p)
    return _pb_dict(p)


@router.delete("/{pid}")
def delete_setup(pid: int, db: Session = Depends(get_db)):
    p = db.get(Playbook, pid)
    if not p: raise HTTPException(404)
    db.delete(p); db.commit()
    return {"ok": True}
