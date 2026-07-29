from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Employer
from app.schemas import EmployerAuthResponse, EmployerCreate, EmployerLogin, EmployerOut
from app.security import create_employer_token, decode_employer_token, hash_password, verify_password

router = APIRouter(prefix="/api/employers", tags=["employers"])


@router.post("/register", response_model=EmployerAuthResponse, status_code=201)
def register_employer(payload: EmployerCreate, db: Session = Depends(get_db)):
    existing = db.query(Employer).filter(Employer.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=409, detail="An employer account with this email already exists.")

    employer = Employer(
        company_name=payload.company_name,
        email=payload.email,
        password_hash=hash_password(payload.password),
    )
    db.add(employer)
    db.commit()
    db.refresh(employer)

    return EmployerAuthResponse(token=create_employer_token(employer.id), employer=employer)


@router.post("/login", response_model=EmployerAuthResponse)
def login_employer(payload: EmployerLogin, db: Session = Depends(get_db)):
    employer = db.query(Employer).filter(Employer.email == payload.email).first()
    if not employer or not verify_password(payload.password, employer.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    return EmployerAuthResponse(token=create_employer_token(employer.id), employer=employer)


def get_current_employer(
    authorization: str = Header(default=""), db: Session = Depends(get_db)
) -> Employer:
    token = authorization.removeprefix("Bearer ").strip()
    employer_id = decode_employer_token(token) if token else None
    if not employer_id:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    employer = db.query(Employer).filter(Employer.id == employer_id).first()
    if not employer:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    return employer


@router.get("/me", response_model=EmployerOut)
def get_me(employer: Employer = Depends(get_current_employer)):
    return employer
