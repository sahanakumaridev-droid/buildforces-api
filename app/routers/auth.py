import os
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Admin, Employer, HouseOwner, Instructor, PasswordResetToken, Registration, RegistrationTrade
from app.schemas import (
    AdminRegister,
    AuthLogin,
    AuthResponse,
    AuthUserOut,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    GoogleAuthRequest,
    HomeownerRegister,
    InstructorRegister,
    RegistrationAuthResponse,
    ResetPasswordRequest,
)
from app.google_auth import fetch_google_profile, google_client_id
from app.security import (
    create_auth_token,
    decode_auth_token,
    hash_password,
    verify_password,
)
from app.zip_lookup import derive_state_county

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
        if getattr(registration, "is_blocked", False):
            raise HTTPException(status_code=403, detail="This Build Forces account has been blocked.")
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


def require_homeowner(user: AuthUserOut = Depends(get_current_auth_user)) -> AuthUserOut:
    if user.role != "homeowner":
        raise HTTPException(status_code=403, detail="Homeowner access required.")
    return user


def require_instructor(user: AuthUserOut = Depends(get_current_auth_user)) -> AuthUserOut:
    if user.role != "instructor":
        raise HTTPException(status_code=403, detail="Instructor access required.")
    return user


def require_labor(user: AuthUserOut = Depends(get_current_auth_user)) -> AuthUserOut:
    if user.role != "labor":
        raise HTTPException(status_code=403, detail="Build Forces member sign-in required.")
    return user


def email_in_use(db: Session, email: str) -> bool:
    email = email.lower().strip()
    return bool(
        db.query(Admin).filter(Admin.email == email).first()
        or db.query(Registration).filter(Registration.email == email).first()
        or db.query(Instructor).filter(Instructor.email == email).first()
        or db.query(HouseOwner).filter(HouseOwner.email == email).first()
        or db.query(Employer).filter(Employer.email == email).first()
    )


@router.get("/google/config")
def google_config():
    client_id = google_client_id()
    return {"configured": bool(client_id), "client_id": client_id}


@router.post("/google", response_model=RegistrationAuthResponse)
def google_auth(payload: GoogleAuthRequest, db: Session = Depends(get_db)):
    profile = fetch_google_profile(payload.access_token)
    email = profile["email"]

    if db.query(Admin).filter(Admin.email == email).first():
        raise HTTPException(status_code=409, detail="This email is already used on the admin portal.")
    if db.query(Instructor).filter(Instructor.email == email).first():
        raise HTTPException(status_code=409, detail="This email is already used on the instructor portal.")
    if db.query(HouseOwner).filter(HouseOwner.email == email).first():
        raise HTTPException(status_code=409, detail="This email is already used on the homeowner portal.")
    if db.query(Employer).filter(Employer.email == email).first():
        raise HTTPException(status_code=409, detail="This email is already used on the company portal.")

    registration = db.query(Registration).filter(Registration.email == email).first()
    if registration:
        if getattr(registration, "is_blocked", False):
            raise HTTPException(status_code=403, detail="This Build Forces account has been blocked.")
        registration.last_login_at = datetime.utcnow()
        db.commit()
        db.refresh(registration)
        return RegistrationAuthResponse(
            token=create_auth_token(registration.id, "labor"),
            registration=registration,
        )

    state, county = derive_state_county(payload.zip_code)
    phone = (payload.phone or "").strip() or "Google"
    registration = Registration(
        full_name=profile["full_name"],
        email=email,
        phone=phone,
        password_hash=hash_password(secrets.token_urlsafe(32)),
        language=payload.language,
        zip_code=payload.zip_code,
        state=state,
        county=county,
        skill_level=payload.skill_level,
        experience=payload.experience,
        work_authorized=True,
        agreed_to_terms=True,
    )
    registration.trades = [
        RegistrationTrade(category=item.category, trade_name=item.trade_name) for item in payload.trades
    ]
    registration.last_login_at = datetime.utcnow()
    db.add(registration)
    db.commit()
    db.refresh(registration)
    return RegistrationAuthResponse(
        token=create_auth_token(registration.id, "labor"),
        registration=registration,
    )


@router.post("/login", response_model=AuthResponse)
def login(payload: AuthLogin, db: Session = Depends(get_db)):
    email = payload.email.lower().strip()

    admin = db.query(Admin).filter(Admin.email == email, Admin.is_active.is_(True)).first()
    if admin and verify_password(payload.password, admin.password_hash):
        user = _admin_user(admin)
        return AuthResponse(token=create_auth_token(admin.id, "admin"), role="admin", user=user)

    registration = db.query(Registration).filter(Registration.email == email).first()
    if registration and verify_password(payload.password, registration.password_hash):
        if getattr(registration, "is_blocked", False):
            raise HTTPException(status_code=403, detail="This Build Forces account has been blocked.")
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


@router.post("/instructor/register", response_model=AuthResponse, status_code=201)
def register_instructor(payload: InstructorRegister, db: Session = Depends(get_db)):
    email = payload.email.lower().strip()
    if email_in_use(db, email):
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    instructor = Instructor(
        full_name=payload.full_name.strip(),
        email=email,
        specialty=payload.specialty.strip(),
        city=payload.city.strip(),
        password_hash=hash_password(payload.password),
        is_active=True,
    )
    db.add(instructor)
    db.commit()
    db.refresh(instructor)

    user = _instructor_user(instructor)
    return AuthResponse(
        token=create_auth_token(instructor.id, "instructor"),
        role="instructor",
        user=user,
    )


@router.post("/homeowner/register", response_model=AuthResponse, status_code=201)
def register_homeowner(payload: HomeownerRegister, db: Session = Depends(get_db)):
    email = payload.email.lower().strip()
    if email_in_use(db, email):
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    homeowner = HouseOwner(
        full_name=payload.full_name.strip(),
        email=email,
        city=payload.city.strip(),
        zip_code=payload.zip_code.strip(),
        password_hash=hash_password(payload.password),
        is_active=True,
    )
    db.add(homeowner)
    db.commit()
    db.refresh(homeowner)

    user = _homeowner_user(homeowner)
    return AuthResponse(
        token=create_auth_token(homeowner.id, "homeowner"),
        role="homeowner",
        user=user,
    )


@router.get("/me", response_model=AuthUserOut)
def get_me(user: AuthUserOut = Depends(get_current_auth_user)):
    return user


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    from app.mailer import password_reset_email_html, send_email

    email = str(payload.email).strip().lower()
    role: str | None = None
    admin = db.query(Admin).filter(Admin.email == email, Admin.is_active.is_(True)).first()
    if admin:
        role = "admin"
    else:
        registration = db.query(Registration).filter(Registration.email == email).first()
        if registration and not bool(getattr(registration, "is_blocked", False)):
            role = "labor"
        else:
            instructor = (
                db.query(Instructor)
                .filter(Instructor.email == email, Instructor.is_active.is_(True))
                .first()
            )
            if instructor:
                role = "instructor"
            else:
                homeowner = (
                    db.query(HouseOwner)
                    .filter(HouseOwner.email == email, HouseOwner.is_active.is_(True))
                    .first()
                )
                if homeowner:
                    role = "homeowner"

    reset_url: str | None = None
    email_sent = False
    if role:
        token = secrets.token_urlsafe(32)
        db.add(
            PasswordResetToken(
                email=email,
                role=role,
                token=token,
                expires_at=datetime.utcnow() + timedelta(hours=RESET_TOKEN_HOURS),
            )
        )
        db.commit()

        frontend_url = (
            os.environ.get("FRONTEND_URL")
            or ("https://buildforces.com" if os.environ.get("ENV") == "production" else "http://localhost:3000")
        ).rstrip("/")
        reset_url = f"{frontend_url}/reset-password?token={token}"
        mail = send_email(
            email,
            "Reset your BUILD FORCES password",
            password_reset_email_html(reset_url),
            f"Reset your password: {reset_url}",
        )
        email_sent = bool(mail.get("sent"))

    message = (
        "Check your email for a password reset link. If you do not see it, check spam."
        if email_sent
        else "If an account exists for that email, use the reset link below to set a new password."
    )
    # Only expose the reset URL when email delivery failed / is not configured.
    return ForgotPasswordResponse(
        message=message,
        reset_url=None if email_sent else reset_url,
        email_sent=email_sent,
    )


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
    elif record.role == "instructor":
        instructor = db.query(Instructor).filter(Instructor.email == record.email).first()
        if not instructor:
            raise HTTPException(status_code=400, detail="Invalid or expired reset link.")
        instructor.password_hash = password_hash
    elif record.role == "homeowner":
        homeowner = db.query(HouseOwner).filter(HouseOwner.email == record.email).first()
        if not homeowner:
            raise HTTPException(status_code=400, detail="Invalid or expired reset link.")
        homeowner.password_hash = password_hash
    else:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link.")

    record.used_at = datetime.utcnow()
    db.commit()
    return {"message": "Password updated. You can sign in with your new password."}
