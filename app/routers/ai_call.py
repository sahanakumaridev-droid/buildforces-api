import json
import secrets
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.ai_engine import answer_query, ensure_seed_pairs
from app.database import get_db
from app.models import AiCallSession, AiCallTurn, AiStoredPair, Registration
from app.routers.auth import get_current_auth_user
from app.schemas import (
    AiCallStartIn,
    AiCallTurnIn,
    AiCallTurnResponse,
    AiRelatedOut,
    AiSessionOut,
    AiTurnOut,
    AuthUserOut,
)

router = APIRouter(prefix="/api/ai", tags=["ai"])


def optional_user(
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
) -> Optional[AuthUserOut]:
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        return None
    try:
        return get_current_auth_user(authorization, db)
    except HTTPException:
        return None


def _related_out(pairs):
    return [
        AiRelatedOut(id=pair.id, question=pair.question, answer=pair.answer, score=score)
        for pair, score in pairs
    ]


def _parse_related(raw: str):
    try:
        data = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    out: list[AiRelatedOut] = []
    for item in data:
        try:
            out.append(AiRelatedOut(**item))
        except Exception:
            continue
    return out


def _session_out(session: AiCallSession) -> AiSessionOut:
    turns = sorted(session.turns, key=lambda t: t.created_at)
    return AiSessionOut(
        id=session.id,
        guest_key=session.guest_key,
        status=session.status,
        started_at=session.started_at,
        ended_at=session.ended_at,
        turns=[
            AiTurnOut(
                id=turn.id,
                role=turn.role,
                content=turn.content,
                related=_parse_related(turn.related_json),
                created_at=turn.created_at,
            )
            for turn in turns
        ],
    )


def _get_or_create_session(
    db: Session,
    guest_key: str,
    session_id: Optional[int],
    user: Optional[AuthUserOut],
) -> AiCallSession:
    session = None
    if session_id:
        session = db.query(AiCallSession).filter(AiCallSession.id == session_id).first()
        if not session or session.guest_key != guest_key:
            raise HTTPException(status_code=404, detail="Call session not found.")
    else:
        session = (
            db.query(AiCallSession)
            .filter(
                AiCallSession.guest_key == guest_key,
                AiCallSession.status == "active",
            )
            .order_by(AiCallSession.id.desc())
            .first()
        )
    if not session:
        session = AiCallSession(
            guest_key=guest_key,
            registration_id=user.id if user and user.role == "labor" else None,
            user_role=user.role if user else None,
            status="active",
        )
        db.add(session)
        db.commit()
        db.refresh(session)
    elif user and user.role == "labor" and not session.registration_id:
        member = db.query(Registration).filter(Registration.id == user.id).first()
        if member:
            session.registration_id = member.id
            session.user_role = "labor"
            db.commit()
            db.refresh(session)
    return session


@router.post("/call/start", response_model=AiSessionOut)
def start_call(
    payload: AiCallStartIn,
    db: Session = Depends(get_db),
    user: Optional[AuthUserOut] = Depends(optional_user),
):
    ensure_seed_pairs(db)
    guest_key = (payload.guest_key or "").strip() or secrets.token_hex(16)
    prior = (
        db.query(AiCallSession)
        .filter(AiCallSession.guest_key == guest_key, AiCallSession.status == "active")
        .order_by(AiCallSession.id.desc())
        .all()
    )
    for row in prior:
        row.status = "ended"
        row.ended_at = datetime.utcnow()
    session = AiCallSession(
        guest_key=guest_key,
        registration_id=user.id if user and user.role == "labor" else None,
        user_role=user.role if user else None,
        status="active",
    )
    db.add(session)
    greeting = (
        "Hi, this is Maya with Build Forces. I am so glad you called. "
        "I can walk you through training, jobs, portals, or getting started. What can I help with?"
    )
    db.add(
        AiCallTurn(
            session=session,
            role="assistant",
            content=greeting,
            related_json="[]",
        )
    )
    db.commit()
    db.refresh(session)
    return _session_out(session)


@router.post("/call/turn", response_model=AiCallTurnResponse)
def call_turn(
    payload: AiCallTurnIn,
    db: Session = Depends(get_db),
    user: Optional[AuthUserOut] = Depends(optional_user),
):
    session = _get_or_create_session(db, payload.guest_key.strip(), payload.session_id, user)
    if session.status != "active":
        raise HTTPException(status_code=400, detail="This call has ended. Start a new call.")

    history = [f"{t.role}: {t.content}" for t in sorted(session.turns, key=lambda x: x.created_at)]
    user_turn = AiCallTurn(session_id=session.id, role="user", content=payload.message.strip())
    db.add(user_turn)
    db.flush()

    reply, related = answer_query(db, payload.message.strip(), history)
    related_payload = [
        {"id": pair.id, "question": pair.question, "answer": pair.answer, "score": score}
        for pair, score in related
    ]
    assistant_turn = AiCallTurn(
        session_id=session.id,
        role="assistant",
        content=reply,
        related_json=json.dumps(related_payload),
    )
    db.add(assistant_turn)
    stored_answer = related[0][0].answer if related else reply.split(" Also related:")[0].strip()
    db.add(
        AiStoredPair(
            question=payload.message.strip(),
            answer=stored_answer,
            source="call",
            session_id=session.id,
        )
    )
    db.commit()
    db.refresh(session)
    return AiCallTurnResponse(session=_session_out(session), reply=reply, related=_related_out(related))


@router.get("/call/{session_id}", response_model=AiSessionOut)
def get_call(session_id: int, guest_key: str, db: Session = Depends(get_db)):
    session = db.query(AiCallSession).filter(AiCallSession.id == session_id).first()
    if not session or session.guest_key != guest_key:
        raise HTTPException(status_code=404, detail="Call session not found.")
    return _session_out(session)


@router.get("/calls", response_model=list[AiSessionOut])
def list_calls(
    guest_key: str,
    db: Session = Depends(get_db),
    user: Optional[AuthUserOut] = Depends(optional_user),
):
    q = db.query(AiCallSession).order_by(AiCallSession.id.desc())
    if user and user.role == "labor":
        q = q.filter(AiCallSession.registration_id == user.id)
    else:
        q = q.filter(AiCallSession.guest_key == guest_key)
    rows = q.limit(20).all()
    return [_session_out(row) for row in rows]


@router.post("/call/{session_id}/end", response_model=AiSessionOut)
def end_call(session_id: int, payload: AiCallStartIn, db: Session = Depends(get_db)):
    guest_key = (payload.guest_key or "").strip()
    session = db.query(AiCallSession).filter(AiCallSession.id == session_id).first()
    if not session or session.guest_key != guest_key:
        raise HTTPException(status_code=404, detail="Call session not found.")
    session.status = "ended"
    session.ended_at = datetime.utcnow()
    db.commit()
    db.refresh(session)
    return _session_out(session)
