from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from database import User, Payment, PAY_PENDING, PAY_CONFIRMED
from auth import get_db, get_current_user

router = APIRouter(prefix="/api/payments", tags=["payments"])


class ConfirmBody(BaseModel):
    amount_paid: Optional[float] = None
    proof_note: Optional[str] = None


@router.get("")
def list_payments(status_filter: Optional[str] = None, player_id: Optional[int] = None,
                   db=Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(Payment)
    if status_filter:
        q = q.filter(Payment.status == status_filter)
    if player_id:
        q = q.filter(Payment.player_id == player_id)
    payments = q.order_by(Payment.created_at.desc()).all()
    return [p.to_dict() for p in payments]


@router.post("/{payment_id}/confirm")
def confirm_payment(payment_id: int, body: ConfirmBody, db=Depends(get_db),
                     user: User = Depends(get_current_user)):
    """Admin/JC checklist confirmation once the manual transfer has been seen
    in the JC/admin bank account (per spec, players never pay the owner directly).
    """
    payment = db.get(Payment, payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment.status != PAY_PENDING:
        raise HTTPException(status_code=400, detail=f"Payment is already {payment.status}")

    payment.amount_paid = body.amount_paid if body.amount_paid is not None else payment.amount_due
    payment.status = PAY_CONFIRMED
    payment.confirmed_by = user.id
    payment.confirmed_at = datetime.utcnow()
    payment.proof_note = body.proof_note
    db.commit()
    return payment.to_dict()


@router.post("/{payment_id}/unconfirm")
def unconfirm_payment(payment_id: int, db=Depends(get_db), user: User = Depends(get_current_user)):
    """Undo an accidental confirmation."""
    payment = db.get(Payment, payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment.status != PAY_CONFIRMED:
        raise HTTPException(status_code=400, detail="Payment is not confirmed")
    payment.status = PAY_PENDING
    payment.amount_paid = 0
    payment.confirmed_by = None
    payment.confirmed_at = None
    db.commit()
    return payment.to_dict()
