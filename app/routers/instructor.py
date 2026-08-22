from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import Certificate, Course, CourseSession, Enrollment, Instructor, Registration
from app.routers.auth import require_instructor
from app.schemas import AuthUserOut, GradeIn, InstructorOverviewOut, InstructorStudentOut

router = APIRouter(prefix="/api/instructor", tags=["instructor"])


def _instructor(user: AuthUserOut, db: Session) -> Instructor:
    row = db.query(Instructor).filter(Instructor.id == user.id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Instructor account not found.")
    return row


def _course_scope(instructor: Instructor, db: Session):
    owned = db.query(Course).filter(Course.instructor_id == instructor.id)
    if owned.count():
        return owned
    return db.query(Course)


@router.get("/overview", response_model=InstructorOverviewOut)
def overview(user: AuthUserOut = Depends(require_instructor), db: Session = Depends(get_db)):
    instructor = _instructor(user, db)
    courses = _course_scope(instructor, db).all()
    course_ids = [course.id for course in courses]
    enrollments = (
        db.query(Enrollment).filter(Enrollment.course_id.in_(course_ids)).all() if course_ids else []
    )
    sessions = (
        db.query(CourseSession).filter(CourseSession.course_id.in_(course_ids)).count() if course_ids else 0
    )
    pending_certs = (
        db.query(Certificate)
        .filter(Certificate.course_id.in_(course_ids), Certificate.registration_id.isnot(None))
        .count()
        if course_ids
        else 0
    )
    revenue = sum(float(course.fee or 0) for course in courses for _ in range(
        sum(1 for row in enrollments if row.course_id == course.id)
    ))
    return InstructorOverviewOut(
        courses=len(courses),
        students=len(enrollments),
        pending_grades=sum(1 for row in enrollments if not row.grade),
        pending_certificates=pending_certs,
        revenue=revenue,
        sessions=sessions,
    )


@router.get("/students", response_model=list[InstructorStudentOut])
def students(user: AuthUserOut = Depends(require_instructor), db: Session = Depends(get_db)):
    instructor = _instructor(user, db)
    courses = _course_scope(instructor, db).all()
    course_ids = [course.id for course in courses]
    if not course_ids:
        return []
    rows = (
        db.query(Enrollment)
        .options(joinedload(Enrollment.course))
        .filter(Enrollment.course_id.in_(course_ids))
        .order_by(Enrollment.enrolled_at.desc())
        .all()
    )
    certs = (
        db.query(Certificate)
        .filter(Certificate.course_id.in_(course_ids), Certificate.registration_id.isnot(None))
        .all()
    )
    cert_map = {(c.course_id, c.registration_id): c for c in certs}
    members = {
        m.id: m
        for m in db.query(Registration)
        .filter(Registration.id.in_({row.registration_id for row in rows}))
        .all()
    }
    out = []
    for row in rows:
        member = members.get(row.registration_id)
        cert = cert_map.get((row.course_id, row.registration_id))
        out.append(
            InstructorStudentOut(
                enrollment_id=row.id,
                member_id=row.registration_id,
                full_name=member.full_name if member else "Unknown",
                email=member.email if member else "",
                course_id=row.course_id,
                course_title=row.course.title if row.course else "",
                status=row.status,
                progress_pct=int(getattr(row, "progress_pct", 0) or 0),
                grade=getattr(row, "grade", None),
                enrolled_at=row.enrolled_at,
                certificate_id=cert.id if cert else None,
                certificate_pending=bool(cert),
            )
        )
    return out


@router.post("/enrollments/{enrollment_id}/grade", response_model=InstructorStudentOut)
def grade_student(
    enrollment_id: int,
    payload: GradeIn,
    user: AuthUserOut = Depends(require_instructor),
    db: Session = Depends(get_db),
):
    instructor = _instructor(user, db)
    row = db.query(Enrollment).options(joinedload(Enrollment.course)).filter(Enrollment.id == enrollment_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Enrollment not found.")
    course_ids = [c.id for c in _course_scope(instructor, db).all()]
    if row.course_id not in course_ids:
        raise HTTPException(status_code=403, detail="Not your student.")
    row.grade = payload.grade.strip()
    if payload.progress_pct is not None:
        row.progress_pct = payload.progress_pct
    elif not row.progress_pct:
        row.progress_pct = 100
    db.commit()
    member = db.query(Registration).filter(Registration.id == row.registration_id).first()
    return InstructorStudentOut(
        enrollment_id=row.id,
        member_id=row.registration_id,
        full_name=member.full_name if member else "Unknown",
        email=member.email if member else "",
        course_id=row.course_id,
        course_title=row.course.title if row.course else "",
        status=row.status,
        progress_pct=int(row.progress_pct or 0),
        grade=row.grade,
        enrolled_at=row.enrolled_at,
        certificate_id=None,
        certificate_pending=False,
    )
