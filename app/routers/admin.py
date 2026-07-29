from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Admin,
    Course,
    Employer,
    Enrollment,
    HouseOwner,
    Instructor,
    Job,
    Registration,
)
from app.routers.auth import require_admin
from app.schemas import (
    AdminDirectoryUserOut,
    AdminMemberOut,
    AdminOverviewOut,
    AdminStatsOut,
    AuthUserOut,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/overview", response_model=AdminOverviewOut)
def admin_overview(
    _: AuthUserOut = Depends(require_admin),
    db: Session = Depends(get_db),
):
    members = db.query(Registration).order_by(Registration.created_at.desc()).limit(100).all()
    instructors = db.query(Instructor).order_by(Instructor.created_at.desc()).all()
    house_owners = db.query(HouseOwner).order_by(HouseOwner.created_at.desc()).all()
    employers = db.query(Employer).order_by(Employer.created_at.desc()).all()
    admins = db.query(Admin).order_by(Admin.created_at.desc()).all()

    recent = (
        db.query(Enrollment)
        .order_by(Enrollment.enrolled_at.desc())
        .limit(12)
        .all()
    )

    stats = AdminStatsOut(
        members=db.query(Registration).count(),
        instructors=db.query(Instructor).count(),
        house_owners=db.query(HouseOwner).count(),
        employers=db.query(Employer).count(),
        admins=db.query(Admin).count(),
        courses=db.query(Course).count(),
        enrollments=db.query(Enrollment).count(),
        jobs=db.query(Job).count(),
    )

    return AdminOverviewOut(
        stats=stats,
        members=[
            AdminMemberOut(
                id=m.id,
                full_name=m.full_name,
                email=m.email,
                phone=m.phone,
                zip_code=m.zip_code,
                skill_level=m.skill_level,
                experience=m.experience,
                trades=[t.trade_name for t in m.trades],
                created_at=m.created_at,
            )
            for m in members
        ],
        instructors=[
            AdminDirectoryUserOut(
                id=i.id,
                full_name=i.full_name,
                email=i.email,
                role="instructor",
                detail=i.specialty,
                city=i.city,
                created_at=i.created_at,
                is_active=i.is_active,
            )
            for i in instructors
        ],
        house_owners=[
            AdminDirectoryUserOut(
                id=h.id,
                full_name=h.full_name,
                email=h.email,
                role="house_owner",
                detail=f"{h.project_count} projects",
                city=h.city,
                created_at=h.created_at,
                is_active=h.is_active,
            )
            for h in house_owners
        ],
        employers=[
            AdminDirectoryUserOut(
                id=e.id,
                full_name=e.company_name,
                email=e.email,
                role="employer",
                detail="Construction company",
                city=None,
                created_at=e.created_at,
                is_active=True,
            )
            for e in employers
        ],
        admins=[
            AdminDirectoryUserOut(
                id=a.id,
                full_name=a.full_name,
                email=a.email,
                role="admin",
                detail="Platform administrator",
                city=None,
                created_at=a.created_at,
                is_active=a.is_active,
            )
            for a in admins
        ],
        recent_enrollments=[
            {
                "id": e.id,
                "course_id": e.course_id,
                "course_title": e.course.title if e.course else "",
                "member_id": e.registration_id,
                "status": e.status,
                "enrolled_at": e.enrolled_at.isoformat(),
            }
            for e in recent
        ],
    )
