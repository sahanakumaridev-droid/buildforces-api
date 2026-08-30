from datetime import datetime
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CatalogAssignment, CatalogMedia, Course, Enrollment, Registration
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
    video_url: str = ""
    lesson_youtube_ids: list[str] = Field(default_factory=list)
    emails: list[EmailStr] = Field(min_length=1)


class CatalogPurchaseIn(BaseModel):
    slug: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=255)
    image: str = ""
    video_url: str = ""
    lesson_youtube_ids: list[str] = Field(default_factory=list)


class CatalogMediaIn(BaseModel):
    slug: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=255)
    image: str = ""
    video_url: str = ""
    lesson_youtube_ids: list[str] = Field(default_factory=list)


class CatalogAssignmentOut(BaseModel):
    slug: str
    title: str
    image: str
    video_url: str = ""
    lesson_youtube_ids: list[str] = Field(default_factory=list)
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


def _ids_from_row(raw: Optional[str]) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    except json.JSONDecodeError:
        pass
    return [part.strip() for part in raw.split(",") if part.strip()]


def _assignment_out(
    row: CatalogAssignment,
    name: str,
    media: Optional[CatalogMedia] = None,
) -> CatalogAssignmentOut:
    clip = (row.video_url or (media.video_url if media else "") or "").strip()
    ids = _ids_from_row(row.lesson_youtube_ids) or _ids_from_row(
        media.lesson_youtube_ids if media else None
    )
    return CatalogAssignmentOut(
        slug=row.slug,
        title=row.title,
        image=row.image or (media.image if media else "") or "",
        video_url=clip,
        lesson_youtube_ids=ids,
        member_email=row.member_email,
        member_name=name,
        member_id=str(row.registration_id or row.member_email),
        published_at=row.published_at.isoformat() if row.published_at else datetime.utcnow().isoformat(),
    )


def upsert_catalog_media(
    db: Session,
    *,
    slug: str,
    title: str,
    image: str,
    video_url: str,
    lesson_youtube_ids: list[str],
) -> CatalogMedia:
    ids_json = json.dumps([item.strip() for item in lesson_youtube_ids if item.strip()])
    row = db.query(CatalogMedia).filter(CatalogMedia.slug == slug).first()
    if row:
        row.title = title
        row.image = image or row.image
        if video_url:
            row.video_url = video_url
        if lesson_youtube_ids:
            row.lesson_youtube_ids = ids_json
    else:
        row = CatalogMedia(
            slug=slug,
            title=title,
            image=image or "",
            video_url=video_url or None,
            lesson_youtube_ids=ids_json if lesson_youtube_ids else None,
        )
        db.add(row)
    db.flush()
    course = db.query(Course).filter(Course.title.ilike(title.strip())).first()
    clip = (video_url or (row.video_url or "")).strip()
    if not course:
        course = Course(
            title=title.strip(),
            description=title.strip(),
            fee=0,
            duration="",
            level="Core",
            category="standard",
            provider="Build Forces",
            location="Online",
            image=image or None,
            outcomes="",
            video_url=clip or None,
            is_published=True,
        )
        db.add(course)
        db.flush()
    elif clip:
        course.video_url = clip
        if image:
            course.image = image
    for assignment in db.query(CatalogAssignment).filter(CatalogAssignment.slug == slug).all():
        assignment.title = title
        if image:
            assignment.image = image
        if clip:
            assignment.video_url = clip
        if lesson_youtube_ids:
            assignment.lesson_youtube_ids = ids_json
    return row


def upsert_catalog_assignment(
    db: Session,
    *,
    slug: str,
    title: str,
    image: str,
    member: Registration,
    video_url: str = "",
    lesson_youtube_ids: Optional[list[str]] = None,
) -> CatalogAssignment:
    media = db.query(CatalogMedia).filter(CatalogMedia.slug == slug).first()
    clip = (video_url or (media.video_url if media else "") or "").strip()
    ids = lesson_youtube_ids if lesson_youtube_ids is not None else _ids_from_row(media.lesson_youtube_ids if media else None)
    ids_json = json.dumps(ids) if ids else (media.lesson_youtube_ids if media else None)
    email = member.email.lower().strip()
    row = (
        db.query(CatalogAssignment)
        .filter(CatalogAssignment.slug == slug, CatalogAssignment.member_email == email)
        .first()
    )
    if row:
        row.title = title
        row.image = image or row.image
        if clip:
            row.video_url = clip
        if ids_json:
            row.lesson_youtube_ids = ids_json
        row.registration_id = member.id
        row.published_at = datetime.utcnow()
    else:
        row = CatalogAssignment(
            slug=slug,
            title=title,
            image=image or "",
            video_url=clip or None,
            lesson_youtube_ids=ids_json,
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
    upsert_catalog_media(
        db,
        slug=payload.slug.strip(),
        title=payload.title.strip(),
        image=payload.image or "",
        video_url=payload.video_url or "",
        lesson_youtube_ids=payload.lesson_youtube_ids,
    )
    media = db.query(CatalogMedia).filter(CatalogMedia.slug == payload.slug.strip()).first()
    for raw in payload.emails:
        email = str(raw).lower().strip()
        member = db.query(Registration).filter(Registration.email == email).first()
        if not member or not member.is_paid:
            continue
        row = upsert_catalog_assignment(
            db,
            slug=payload.slug.strip(),
            title=payload.title.strip(),
            image=payload.image,
            member=member,
            video_url=payload.video_url or "",
            lesson_youtube_ids=payload.lesson_youtube_ids,
        )
        enroll_matching_course(db, member, payload.title)
        created.append(_assignment_out(row, member.full_name, media))
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
    upsert_catalog_media(
        db,
        slug=payload.slug.strip(),
        title=payload.title.strip(),
        image=payload.image or "",
        video_url=payload.video_url or "",
        lesson_youtube_ids=payload.lesson_youtube_ids,
    )
    row = upsert_catalog_assignment(
        db,
        slug=payload.slug.strip(),
        title=payload.title.strip(),
        image=payload.image or "",
        member=member,
        video_url=payload.video_url or "",
        lesson_youtube_ids=payload.lesson_youtube_ids,
    )
    enroll_matching_course(db, member, payload.title)
    db.commit()
    db.refresh(row)
    media = db.query(CatalogMedia).filter(CatalogMedia.slug == row.slug).first()
    return _assignment_out(row, member.full_name, media)


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
    slugs = {row.slug for row in rows}
    media_rows = {
        m.slug: m
        for m in db.query(CatalogMedia).filter(CatalogMedia.slug.in_(slugs)).all()
    } if slugs else {}
    return [_assignment_out(row, user.full_name, media_rows.get(row.slug)) for row in rows]


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
    media_rows = {
        m.slug: m
        for m in db.query(CatalogMedia).filter(CatalogMedia.slug == slug).all()
    }
    return [
        _assignment_out(row, names.get(row.member_email, row.member_email), media_rows.get(row.slug))
        for row in rows
    ]


@router.post("/media", response_model=CatalogAssignmentOut)
def publish_catalog_media(
    payload: CatalogMediaIn,
    admin: AuthUserOut = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = upsert_catalog_media(
        db,
        slug=payload.slug.strip(),
        title=payload.title.strip(),
        image=payload.image or "",
        video_url=payload.video_url or "",
        lesson_youtube_ids=payload.lesson_youtube_ids,
    )
    db.commit()
    db.refresh(row)
    return CatalogAssignmentOut(
        slug=row.slug,
        title=row.title,
        image=row.image or "",
        video_url=row.video_url or "",
        lesson_youtube_ids=_ids_from_row(row.lesson_youtube_ids),
        member_email=admin.email,
        member_name=admin.full_name,
        member_id=str(admin.id),
        published_at=datetime.utcnow().isoformat(),
    )
