from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CatalogAssignment, Course, CourseSession, Enrollment, Registration
from app.schemas import CourseContentOut, CourseModuleOut, CourseOut, CourseSessionOut, EnrollmentOut
from app.security import decode_auth_token

try:
    from app.models import CatalogMedia
except ImportError:  # production image may predate CatalogMedia
    CatalogMedia = None  # type: ignore

router = APIRouter(prefix="/api/courses", tags=["courses"])


def parse_course_id(course_id: str) -> Optional[int]:
    raw = (course_id or "").strip()
    lowered = raw.lower()
    if lowered.startswith("course-"):
        raw = raw.split("-", 1)[1]
    if raw.isdigit():
        return int(raw)
    return None


def resolve_course(db: Session, course_id: str) -> Optional[Course]:
    numeric = parse_course_id(course_id)
    if numeric is not None:
        return db.query(Course).filter(Course.id == numeric).first()
    slug = (course_id or "").strip()
    title = None
    if CatalogMedia is not None:
        media = db.query(CatalogMedia).filter(CatalogMedia.slug == slug).first()
        title = media.title if media else None
    if not title:
        assignment = db.query(CatalogAssignment).filter(CatalogAssignment.slug == slug).first()
        title = assignment.title if assignment else None
    if not title:
        return None
    return db.query(Course).filter(Course.title.ilike(title.strip())).first()


def _optional_member_id(authorization: str = Header(default="")) -> Optional[int]:
    token = authorization.removeprefix("Bearer ").strip()
    decoded = decode_auth_token(token) if token else None
    if not decoded:
        return None
    user_id, role = decoded
    return user_id if role == "labor" else None


def _require_member(
    authorization: str = Header(default=""), db: Session = Depends(get_db)
) -> Registration:
    token = authorization.removeprefix("Bearer ").strip()
    decoded = decode_auth_token(token) if token else None
    if not decoded or decoded[1] != "labor":
        raise HTTPException(status_code=401, detail="Member sign-in required.")
    registration = db.query(Registration).filter(Registration.id == decoded[0]).first()
    if not registration:
        raise HTTPException(status_code=401, detail="Member sign-in required.")
    return registration


def _session_out(session: CourseSession) -> CourseSessionOut:
    return CourseSessionOut(
        id=session.id,
        course_id=session.course_id,
        title=session.title,
        starts_at=session.starts_at,
        ends_at=session.ends_at,
        location=session.location,
        seats_left=session.seats_left,
        course_title=session.course.title if session.course else None,
        course_image=session.course.image if session.course else None,
    )


def _content_out(content) -> CourseContentOut:
    return CourseContentOut(
        id=content.id,
        module_id=content.module_id,
        content_kind=content.content_kind,
        title=content.title,
        description=content.description,
        file_url=content.file_url,
        original_filename=content.original_filename,
        mime_type=content.mime_type,
        sort_order=content.sort_order,
        created_at=content.created_at,
    )


def _module_out(module) -> CourseModuleOut:
    contents = sorted(module.contents or [], key=lambda c: c.sort_order)
    return CourseModuleOut(
        id=module.id,
        course_id=module.course_id,
        title=module.title,
        description=module.description,
        reading_content=module.reading_content,
        sort_order=module.sort_order,
        contents=[_content_out(c) for c in contents],
    )


def _course_to_out(
    course: Course,
    purchased: bool = False,
    include_sessions: bool = True,
    include_modules: bool = False,
) -> CourseOut:
    sessions = []
    if include_sessions:
        upcoming = sorted(
            [s for s in course.sessions if s.starts_at >= datetime.utcnow()],
            key=lambda s: s.starts_at,
        )
        sessions = [_session_out(s) for s in upcoming[:8]]
    modules = []
    if include_modules:
        modules = [
            _module_out(m)
            for m in sorted(course.modules or [], key=lambda m: m.sort_order)
        ]
    return CourseOut(
        id=course.id,
        title=course.title,
        description=course.description,
        fee=float(course.fee),
        duration=course.duration,
        level=course.level,
        category=course.category,
        provider=course.provider,
        location=course.location,
        image=course.image,
        outcomes=[line.strip() for line in (course.outcomes or "").split("\n") if line.strip()],
        video_url=course.video_url,
        illustration=course.illustration,
        purchased=purchased,
        sessions=sessions,
        trade=course.trade,
        introduction=course.introduction,
        course_date=course.course_date,
        delivery_type=course.delivery_type,
        content_pattern=course.content_pattern,
        physical_location=course.physical_location,
        online_info=course.online_info,
        is_published=bool(course.is_published) if course.is_published is not None else True,
        modules=modules,
    )


@router.get("", response_model=list[CourseOut])
def list_courses(
    category: Optional[str] = Query(default=None, description="'standard' or 'in_house'"),
    max_fee: Optional[float] = Query(default=None),
    db: Session = Depends(get_db),
    member_id: Optional[int] = Depends(_optional_member_id),
):
    query = db.query(Course)
    if category:
        query = query.filter(Course.category == category)
    if max_fee is not None:
        query = query.filter(Course.fee <= max_fee)
    courses = query.order_by(Course.fee.asc()).all()

    purchased_ids: set[int] = set()
    if member_id:
        purchased_ids = {
            e.course_id
            for e in db.query(Enrollment)
            .filter(Enrollment.registration_id == member_id, Enrollment.status == "purchased")
            .all()
        }

    return [_course_to_out(c, purchased=c.id in purchased_ids) for c in courses]


@router.get("/sessions/upcoming", response_model=list[CourseSessionOut])
def upcoming_sessions(
    db: Session = Depends(get_db),
    member_id: Optional[int] = Depends(_optional_member_id),
):
    query = (
        db.query(CourseSession)
        .filter(CourseSession.starts_at >= datetime.utcnow())
        .order_by(CourseSession.starts_at.asc())
        .limit(40)
    )
    sessions = query.all()
    if member_id:
        owned = {
            e.course_id
            for e in db.query(Enrollment)
            .filter(Enrollment.registration_id == member_id, Enrollment.status == "purchased")
            .all()
        }
        # Prefer owned sessions first, then the rest
        sessions = sorted(
            sessions,
            key=lambda s: (0 if s.course_id in owned else 1, s.starts_at),
        )
    return [_session_out(s) for s in sessions]


@router.get("/my-enrollments", response_model=list[EnrollmentOut])
def my_enrollments(
    registration: Registration = Depends(_require_member),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(Enrollment)
        .filter(
            Enrollment.registration_id == registration.id,
            Enrollment.status == "purchased",
        )
        .order_by(Enrollment.enrolled_at.desc())
        .all()
    )
    return [
        EnrollmentOut(
            id=row.id,
            course_id=row.course_id,
            status=row.status,
            enrolled_at=row.enrolled_at,
            course=_course_to_out(row.course, purchased=True),
        )
        for row in rows
    ]


@router.get("/{course_id}", response_model=CourseOut)
def get_course(
    course_id: str,
    db: Session = Depends(get_db),
    member_id: Optional[int] = Depends(_optional_member_id),
):
    course = resolve_course(db, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found.")
    purchased = False
    if member_id:
        purchased = (
            db.query(Enrollment)
            .filter(
                Enrollment.registration_id == member_id,
                Enrollment.course_id == course.id,
                Enrollment.status == "purchased",
            )
            .first()
            is not None
        )
    if not purchased and member_id:
        slug = (course_id or "").strip()
        assigned = (
            db.query(CatalogAssignment)
            .filter(
                CatalogAssignment.slug == slug,
                CatalogAssignment.registration_id == member_id,
            )
            .first()
        )
        purchased = assigned is not None
    out = _course_to_out(course, purchased=purchased, include_modules=True)
    if CatalogMedia is not None:
        media = db.query(CatalogMedia).filter(CatalogMedia.slug == (course_id or "").strip()).first()
        if media and media.video_url:
            out.video_url = media.video_url
    return out


@router.post("/{course_id}/enroll", response_model=EnrollmentOut)
def enroll_course(
    course_id: str,
    registration: Registration = Depends(_require_member),
    db: Session = Depends(get_db),
):
    course = resolve_course(db, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found.")

    existing = (
        db.query(Enrollment)
        .filter(
            Enrollment.registration_id == registration.id,
            Enrollment.course_id == course.id,
        )
        .first()
    )
    if existing:
        existing.status = "purchased"
        if float(course.fee or 0) > 0:
            registration.is_paid = True
        db.commit()
        db.refresh(existing)
        return EnrollmentOut(
            id=existing.id,
            course_id=existing.course_id,
            status=existing.status,
            enrolled_at=existing.enrolled_at,
            course=_course_to_out(course, purchased=True),
        )

    enrollment = Enrollment(
        registration_id=registration.id,
        course_id=course.id,
        status="purchased",
    )
    if float(course.fee or 0) > 0:
        registration.is_paid = True
    db.add(enrollment)
    db.commit()
    db.refresh(enrollment)
    return EnrollmentOut(
        id=enrollment.id,
        course_id=enrollment.course_id,
        status=enrollment.status,
        enrolled_at=enrollment.enrolled_at,
        course=_course_to_out(course, purchased=True),
    )
