from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Registration, RegistrationTrade
from app.schemas import RegistrationCreate, RegistrationOut
from app.security import hash_password

router = APIRouter(prefix="/api/register", tags=["register"])


@router.post("", response_model=RegistrationOut, status_code=201)
def create_registration(payload: RegistrationCreate, db: Session = Depends(get_db)):
    existing = db.query(Registration).filter(Registration.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    registration = Registration(
        full_name=payload.full_name,
        email=payload.email,
        phone=payload.phone,
        password_hash=hash_password(payload.password),
        language=payload.language,
        zip_code=payload.zip_code,
        state=payload.state,
        county=payload.county,
        promo_code=payload.promo_code,
        skill_level=payload.skill_level,
        experience=payload.experience,
        agreed_to_terms=payload.agreed_to_terms,
    )
    registration.trades = [
        RegistrationTrade(category=t.category, trade_name=t.trade_name) for t in payload.trades
    ]

    db.add(registration)
    db.commit()
    db.refresh(registration)
    return registration
