from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CatalogAssignment, Course, Enrollment, Registration
from app.routers.auth import get_current_auth_user, require_admin, require_labor
from app.schemas import AuthUserOut

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


class PaidMemberOut(BaseModel):
    id: str
    name: str
    email: str
    trade: str
    online: bool = True
    last_seen_at: Optional[str] = None


class CatalogAssignIn(BaseModel):
    slug: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=255)
    image: str = ""
    emails: list[EmailStr] = Field(min_length=1)


class CatalogPurchaseIn(BaseModel):
    slug: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=255)
    image: str = ""


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


def upsert_catalog_assignment(
    db: Session,
    *,
    slug: str,
    title: str,
    image: str,
    member: Registration,
) -> CatalogAssignment:
    email = member.email.lower().strip()
    row = (
        db.query(CatalogAssignment)
        .filter(CatalogAssignment.slug == slug, CatalogAssignment.member_email == email)
        .first()
    )
    if row:
        row.title = title
        row.image = image or row.image
        row.registration_id = member.id
        row.published_at = datetime.utcnow()
    else:
        row = CatalogAssignment(
            slug=slug,
            title=title,
            image=image or "",
            member_email=email,
            registration_id=member.id,
            published_at=datetime.utcnow(),
        )
        db.add(row)
    member.is_paid = True
    db.flush()
    return row


def enroll_matching_course(db: Session, member: Registration, title: str) -> None:
    """If an API Course shares this catalog title, mark it purchased too."""
    course = db.query(Course).filter(Course.title.ilike(title.strip())).first()
    if not course:
        return
    existing = (
        db.query(Enrollment)
        .filter(Enrollment.registration_id == member.id, Enrollment.course_id == course.id)
        .first()
    )
    if existing:
        existing.status = "purchased"
        return
    db.add(
        Enrollment(
            registration_id=member.id,
            course_id=course.id,
            status="purchased",
        )
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
        row = upsert_catalog_assignment(
            db,
            slug=payload.slug,
            title=payload.title,
            image=payload.image,
            member=member,
        )
        created.append(_assignment_out(row, member.full_name))
    if not created:
        raise HTTPException(
            status_code=400,
            detail="None of the selected people are paid Build Forces members on the server.",
        )
    db.commit()
    return created


@router.post("/purchase", response_model=CatalogAssignmentOut)
def purchase_catalog_course(
    payload: CatalogPurchaseIn,
    user: AuthUserOut = Depends(require_labor),
    db: Session = Depends(get_db),
):
    member = db.query(Registration).filter(Registration.id == user.id).first()
    if not member:
        raise HTTPException(status_code=401, detail="Member sign-in required.")
    row = upsert_catalog_assignment(
        db,
        slug=payload.slug.strip(),
        title=payload.title.strip(),
        image=payload.image or "",
        member=member,
    )
    enroll_matching_course(db, member, payload.title)
    db.commit()
    db.refresh(row)
    return _assignment_out(row, member.full_name)


@router.get("/my-courses", response_model=list[CatalogAssignmentOut])
def my_catalog_courses(
    user: AuthUserOut = Depends(get_current_auth_user),
    db: Session = Depends(get_db),
):
    email = user.email.lower().strip()
    filters = [CatalogAssignment.member_email == email]
    if user.role == "labor":
        filters.append(CatalogAssignment.registration_id == user.id)
    rows = (
        db.query(CatalogAssignment)
        .filter(or_(*filters))
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
