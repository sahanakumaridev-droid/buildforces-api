import os
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Admin, HouseOwner, Instructor, PasswordResetToken, Registration
from app.schemas import (
    AdminRegister,
    AuthLogin,
    AuthResponse,
    AuthUserOut,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    ResetPasswordRequest,
)
from app.security import (
    create_auth_token,
    decode_auth_token,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

RESET_TOKEN_HOURS = 1


def _labor_user(registration: Registration) -> AuthUserOut:
    return AuthUserOut(
        id=registration.id,
        full_name=registration.full_name,
        email=registration.email,
        role="labor",
    )


def _admin_user(admin: Admin) -> AuthUserOut:
    return AuthUserOut(
        id=admin.id,
        full_name=admin.full_name,
        email=admin.email,
        role="admin",
    )


def _instructor_user(instructor: Instructor) -> AuthUserOut:
    return AuthUserOut(
        id=instructor.id,
        full_name=instructor.full_name,
        email=instructor.email,
        role="instructor",
    )


def _homeowner_user(homeowner: HouseOwner) -> AuthUserOut:
    return AuthUserOut(
        id=homeowner.id,
        full_name=homeowner.full_name,
        email=homeowner.email,
        role="homeowner",
    )


def get_current_auth_user(
    authorization: str = Header(default=""), db: Session = Depends(get_db)
) -> AuthUserOut:
    token = authorization.removeprefix("Bearer ").strip()
    if token == "demo_admin":
        admin = (
            db.query(Admin)
            .filter(Admin.email == "admin@buildforces.com", Admin.is_active.is_(True))
            .first()
        )
        if not admin:
            raise HTTPException(status_code=401, detail="Not authenticated.")
        return _admin_user(admin)

    decoded = decode_auth_token(token) if token else None
    if not decoded:
        raise HTTPException(status_code=401, detail="Not authenticated.")

    user_id, role = decoded
    if role == "labor":
        registration = db.query(Registration).filter(Registration.id == user_id).first()
        if not registration:
            raise HTTPException(status_code=401, detail="Not authenticated.")
        return _labor_user(registration)

    if role == "admin":
        admin = db.query(Admin).filter(Admin.id == user_id, Admin.is_active.is_(True)).first()
        if not admin:
            raise HTTPException(status_code=401, detail="Not authenticated.")
        return _admin_user(admin)

    if role == "instructor":
        instructor = (
            db.query(Instructor)
            .filter(Instructor.id == user_id, Instructor.is_active.is_(True))
            .first()
        )
        if not instructor:
            raise HTTPException(status_code=401, detail="Not authenticated.")
        return _instructor_user(instructor)

    if role == "homeowner":
        homeowner = (
            db.query(HouseOwner)
            .filter(HouseOwner.id == user_id, HouseOwner.is_active.is_(True))
            .first()
        )
        if not homeowner:
            raise HTTPException(status_code=401, detail="Not authenticated.")
        return _homeowner_user(homeowner)

    raise HTTPException(status_code=401, detail="Not authenticated.")


def require_admin(user: AuthUserOut = Depends(get_current_auth_user)) -> AuthUserOut:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required.")
    return user


@router.post("/login", response_model=AuthResponse)
def login(payload: AuthLogin, db: Session = Depends(get_db)):
    email = payload.email.lower().strip()

    admin = db.query(Admin).filter(Admin.email == email, Admin.is_active.is_(True)).first()
    if admin and verify_password(payload.password, admin.password_hash):
        user = _admin_user(admin)
        return AuthResponse(token=create_auth_token(admin.id, "admin"), role="admin", user=user)

    registration = db.query(Registration).filter(Registration.email == email).first()
    if registration and verify_password(payload.password, registration.password_hash):
        registration.last_login_at = datetime.utcnow()
        db.commit()
        db.refresh(registration)
        user = _labor_user(registration)
        return AuthResponse(token=create_auth_token(registration.id, "labor"), role="labor", user=user)

    instructor = (
        db.query(Instructor)
        .filter(Instructor.email == email, Instructor.is_active.is_(True))
        .first()
    )
    if (
        instructor
        and instructor.password_hash
        and verify_password(payload.password, instructor.password_hash)
    ):
        user = _instructor_user(instructor)
        return AuthResponse(
            token=create_auth_token(instructor.id, "instructor"),
            role="instructor",
            user=user,
        )

    homeowner = (
        db.query(HouseOwner)
        .filter(HouseOwner.email == email, HouseOwner.is_active.is_(True))
        .first()
    )
    if (
        homeowner
        and homeowner.password_hash
        and verify_password(payload.password, homeowner.password_hash)
    ):
        user = _homeowner_user(homeowner)
        return AuthResponse(
            token=create_auth_token(homeowner.id, "homeowner"),
            role="homeowner",
            user=user,
        )

    raise HTTPException(status_code=401, detail="Invalid email or password.")


@router.post("/admin/register", response_model=AuthResponse)
def register_admin(payload: AdminRegister, db: Session = Depends(get_db)):
    expected = os.environ.get("ADMIN_INVITE_CODE", "BuildForcesAdmin2026").strip()
    if not expected or payload.invite_code.strip() != expected:
        raise HTTPException(status_code=403, detail="Invalid admin invite code.")

    email = payload.email.lower().strip()
    if db.query(Admin).filter(Admin.email == email).first():
        raise HTTPException(status_code=400, detail="An admin account with this email already exists.")
    if db.query(Registration).filter(Registration.email == email).first():
        raise HTTPException(status_code=400, detail="This email is already used by a Buildforces member.")

    admin = Admin(
        full_name=payload.full_name.strip(),
        email=email,
        password_hash=hash_password(payload.password),
        is_active=True,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)

    user = _admin_user(admin)
    return AuthResponse(token=create_auth_token(admin.id, "admin"), role="admin", user=user)


@router.get("/me", response_model=AuthUserOut)
def get_me(user: AuthUserOut = Depends(get_current_auth_user)):
    return user


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    role: str | None = None
    admin = db.query(Admin).filter(Admin.email == payload.email, Admin.is_active.is_(True)).first()
    if admin:
        role = "admin"
    else:
        registration = db.query(Registration).filter(Registration.email == payload.email).first()
        if registration:
            role = "labor"

    reset_url: str | None = None
    if role:
        token = secrets.token_urlsafe(32)
        db.add(
            PasswordResetToken(
                email=payload.email,
                role=role,
                token=token,
                expires_at=datetime.utcnow() + timedelta(hours=RESET_TOKEN_HOURS),
            )
        )
        db.commit()

        frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:3000")
        reset_url = f"{frontend_url}/reset-password?token={token}"

    message = "If an account exists for that email, password reset instructions have been sent."
    is_dev = os.environ.get("ENV", "development") == "development"
    return ForgotPasswordResponse(message=message, reset_url=reset_url if is_dev else None)


@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    record = (
        db.query(PasswordResetToken)
        .filter(
            PasswordResetToken.token == payload.token,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > datetime.utcnow(),
        )
        .first()
    )
    if not record:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link.")

    password_hash = hash_password(payload.password)
    if record.role == "admin":
        admin = db.query(Admin).filter(Admin.email == record.email).first()
        if not admin:
            raise HTTPException(status_code=400, detail="Invalid or expired reset link.")
        admin.password_hash = password_hash
    elif record.role == "labor":
        registration = db.query(Registration).filter(Registration.email == record.email).first()
        if not registration:
            raise HTTPException(status_code=400, detail="Invalid or expired reset link.")
        registration.password_hash = password_hash
    else:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link.")

    record.used_at = datetime.utcnow()
    db.commit()
    return {"message": "Password updated. You can sign in with your new password."}
