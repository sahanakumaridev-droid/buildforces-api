from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import LaborMessage, LaborNotification, Registration
from app.routers.auth import require_labor
from app.schemas import (
    AuthUserOut,
    LaborMessageCreate,
    LaborMessageOut,
    LaborNotificationOut,
)

router = APIRouter(prefix="/api/labor", tags=["labor"])


def _member(user: AuthUserOut, db: Session) -> Registration:
    member = db.query(Registration).filter(Registration.id == user.id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Labor profile not found.")
    if bool(getattr(member, "is_blocked", False)):
        raise HTTPException(status_code=403, detail="Account is blocked.")
    return member


@router.get("/notifications", response_model=list[LaborNotificationOut])
def list_notifications(
    user: AuthUserOut = Depends(require_labor),
    db: Session = Depends(get_db),
):
    member = _member(user, db)
    rows = (
        db.query(LaborNotification)
        .filter(LaborNotification.registration_id == member.id)
        .order_by(LaborNotification.created_at.desc())
        .limit(100)
        .all()
    )
    if not rows:
        # Seed a helpful first alert so the Alerts page is never a dead end.
        welcome = LaborNotification(
            registration_id=member.id,
            title="Welcome to BUILD FORCES alerts",
            body="You will see course reminders, job updates, and admin notes here.",
            kind="system",
            is_read=False,
        )
        db.add(welcome)
        db.commit()
        db.refresh(welcome)
        rows = [welcome]
    return rows


@router.post("/notifications/{notification_id}/read", response_model=LaborNotificationOut)
def mark_notification_read(
    notification_id: int,
    user: AuthUserOut = Depends(require_labor),
    db: Session = Depends(get_db),
):
    member = _member(user, db)
    row = (
        db.query(LaborNotification)
        .filter(
            LaborNotification.id == notification_id,
            LaborNotification.registration_id == member.id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Alert not found.")
    row.is_read = True
    db.commit()
    db.refresh(row)
    return row


@router.get("/messages", response_model=list[LaborMessageOut])
def list_messages(
    user: AuthUserOut = Depends(require_labor),
    db: Session = Depends(get_db),
):
    member = _member(user, db)
    rows = (
        db.query(LaborMessage)
        .filter(LaborMessage.registration_id == member.id)
        .order_by(LaborMessage.created_at.desc())
        .limit(200)
        .all()
    )
    if not rows:
        seed = LaborMessage(
            registration_id=member.id,
            peer_name="BUILD FORCES Support",
            peer_role="support",
            subject="How can we help?",
            body="Send a message any time. Our team will reply here.",
            direction="inbound",
            created_at=datetime.utcnow(),
        )
        db.add(seed)
        db.commit()
        db.refresh(seed)
        rows = [seed]
    return rows


@router.post("/messages", response_model=LaborMessageOut, status_code=201)
def send_message(
    payload: LaborMessageCreate,
    user: AuthUserOut = Depends(require_labor),
    db: Session = Depends(get_db),
):
    member = _member(user, db)
    row = LaborMessage(
        registration_id=member.id,
        peer_name=(payload.peer_name or "BUILD FORCES Support").strip() or "BUILD FORCES Support",
        peer_role="support",
        subject=(payload.subject or "").strip() or "Message",
        body=payload.body.strip(),
        direction="outbound",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
