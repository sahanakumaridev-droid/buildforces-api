from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CatalogAssignment, Registration
from app.routers.auth import get_current_auth_user, require_admin
from app.schemas import AuthUserOut

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


class PaidMemberOut(BaseModel):
    id: str
    name: str
    email: str
    trade: str
    online: bool = True
    last_seen_at: str | None = None


class CatalogAssignIn(BaseModel):
    slug: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=255)
    image: str = ""
    emails: list[EmailStr] = Field(min_length=1)


class CatalogAssignmentOut(BaseModel):
    slug: str
    title: str
    image: str
    member_email: str
    member_name: str
    member_id: str
    published_at: str


def _trade_name(member: Registration) -> str:
    trade = (
        member.trades[0].trade_name
        if getattr(member, "trades", None)
        else None
    )
    return trade or "Build Forces"


def _assignment_out(row: CatalogAssignment, name: str) -> CatalogAssignmentOut:
    return CatalogAssignmentOut(
        slug=row.slug,
        title=row.title,
        image=row.image or "",
        member_email=row.member_email,
        member_name=name,
        member_id=str(row.registration_id or row.member_email),
        published_at=row.published_at.isoformat() if row.published_at else datetime.utcnow().isoformat(),
    )


@router.get("/paid-members", response_model=list[PaidMemberOut])
def list_paid_members(
    _admin: AuthUserOut = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(Registration)
        .filter(Registration.is_paid.is_(True))
        .order_by(Registration.full_name.asc())
        .all()
    )
    return [
        PaidMemberOut(
            id=f"paid_{row.id}",
            name=row.full_name,
            email=row.email,
            trade=_trade_name(row),
            online=True,
            last_seen_at=row.last_login_at.isoformat() if row.last_login_at else None,
        )
        for row in rows
    ]


@router.post("/assign", response_model=list[CatalogAssignmentOut])
def assign_catalog_course(
    payload: CatalogAssignIn,
    _admin: AuthUserOut = Depends(require_admin),
    db: Session = Depends(get_db),
):
    created: list[CatalogAssignmentOut] = []
    for raw in payload.emails:
        email = str(raw).lower().strip()
        member = db.query(Registration).filter(Registration.email == email).first()
        if not member or not member.is_paid:
            continue
        row = (
            db.query(CatalogAssignment)
            .filter(CatalogAssignment.slug == payload.slug, CatalogAssignment.member_email == email)
            .first()
        )
        if row:
            row.title = payload.title
            row.image = payload.image or row.image
            row.registration_id = member.id
            row.published_at = datetime.utcnow()
        else:
            row = CatalogAssignment(
                slug=payload.slug,
                title=payload.title,
                image=payload.image or "",
                member_email=email,
                registration_id=member.id,
                published_at=datetime.utcnow(),
            )
            db.add(row)
        db.flush()
        created.append(_assignment_out(row, member.full_name))
    if not created:
        raise HTTPException(
            status_code=400,
            detail="None of the selected people are paid Build Forces members on the server.",
        )
    db.commit()
    return created


@router.get("/my-courses", response_model=list[CatalogAssignmentOut])
def my_catalog_courses(
    user: AuthUserOut = Depends(get_current_auth_user),
    db: Session = Depends(get_db),
):
    email = user.email.lower().strip()
    rows = (
        db.query(CatalogAssignment)
        .filter(CatalogAssignment.member_email == email)
        .order_by(CatalogAssignment.published_at.desc())
        .all()
    )
    return [_assignment_out(row, user.full_name) for row in rows]


@router.get("/assignments/{slug}", response_model=list[CatalogAssignmentOut])
def course_assignments(
    slug: str,
    _admin: AuthUserOut = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(CatalogAssignment)
        .filter(CatalogAssignment.slug == slug)
        .order_by(CatalogAssignment.published_at.desc())
        .all()
    )
    emails = {row.member_email for row in rows}
    names = {
        r.email: r.full_name
        for r in db.query(Registration).filter(Registration.email.in_(emails)).all()
    } if emails else {}
    return [_assignment_out(row, names.get(row.member_email, row.member_email)) for row in rows]
