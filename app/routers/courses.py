from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Course, CourseSession, Enrollment, Registration
from app.schemas import CourseOut, CourseSessionOut, EnrollmentOut
from app.security import decode_auth_token

router = APIRouter(prefix="/api/courses", tags=["courses"])


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


def _course_to_out(
    course: Course, purchased: bool = False, include_sessions: bool = True
) -> CourseOut:
    sessions = []
    if include_sessions:
        upcoming = sorted(
            [s for s in course.sessions if s.starts_at >= datetime.utcnow()],
            key=lambda s: s.starts_at,
        )
        sessions = [_session_out(s) for s in upcoming[:8]]
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
        .filter(Enrollment.registration_id == registration.id)
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
    course_id: int,
    db: Session = Depends(get_db),
    member_id: Optional[int] = Depends(_optional_member_id),
):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found.")
    purchased = False
    if member_id:
        purchased = (
            db.query(Enrollment)
            .filter(
                Enrollment.registration_id == member_id,
                Enrollment.course_id == course_id,
                Enrollment.status == "purchased",
            )
            .first()
            is not None
        )
    return _course_to_out(course, purchased=purchased)


@router.post("/{course_id}/enroll", response_model=EnrollmentOut)
def enroll_course(
    course_id: int,
    registration: Registration = Depends(_require_member),
    db: Session = Depends(get_db),
):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found.")

    existing = (
        db.query(Enrollment)
        .filter(
            Enrollment.registration_id == registration.id,
            Enrollment.course_id == course_id,
        )
        .first()
    )
    if existing:
        existing.status = "purchased"
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
        course_id=course_id,
        status="purchased",
    )
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
