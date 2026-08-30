from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Registration, RegistrationTrade
from app.schemas import (
    RegistrationAuthResponse,
    RegistrationCreate,
    RegistrationDetail,
    RegistrationLookup,
)
from app.security import create_auth_token, decode_worker_token, hash_password, verify_password
from app.zip_lookup import derive_state_county

router = APIRouter(prefix="/api/register", tags=["register"])


@router.post("", response_model=RegistrationAuthResponse, status_code=201)
def create_registration(payload: RegistrationCreate, db: Session = Depends(get_db)):
    existing = db.query(Registration).filter(Registration.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    state, county = derive_state_county(payload.zip_code)

    registration = Registration(
        full_name=payload.full_name,
        email=payload.email,
        phone=payload.phone,
        password_hash=hash_password(payload.password),
        language=payload.language,
        zip_code=payload.zip_code,
        state=state,
        county=county,
        promo_code=payload.promo_code,
        skill_level=payload.skill_level,
        experience=payload.experience,
        work_authorized=payload.work_authorized,
        agreed_to_terms=payload.agreed_to_terms,
        is_paid=False,
    )
    registration.trades = [
        RegistrationTrade(category=t.category, trade_name=t.trade_name) for t in payload.trades
    ]

    registration.last_login_at = datetime.utcnow()
    db.add(registration)
    db.commit()
    db.refresh(registration)
    return RegistrationAuthResponse(token=create_auth_token(registration.id, "labor"), registration=registration)


@router.post("/lookup", response_model=RegistrationAuthResponse)
def lookup_registration(payload: RegistrationLookup, db: Session = Depends(get_db)):
    registration = db.query(Registration).filter(Registration.email == payload.email).first()
    if not registration or not verify_password(payload.password, registration.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    registration.last_login_at = datetime.utcnow()
    db.commit()
    db.refresh(registration)
    return RegistrationAuthResponse(token=create_auth_token(registration.id, "labor"), registration=registration)


def get_current_worker(
    authorization: str = Header(default=""), db: Session = Depends(get_db)
) -> Registration:
    token = authorization.removeprefix("Bearer ").strip()
    registration_id = decode_worker_token(token) if token else None
    if not registration_id:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    registration = db.query(Registration).filter(Registration.id == registration_id).first()
    if not registration:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    return registration


@router.get("/me", response_model=RegistrationDetail)
def get_me(registration: Registration = Depends(get_current_worker)):
    return registration
