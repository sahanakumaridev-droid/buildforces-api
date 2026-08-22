from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.mailer import send_email
from app.models import (
    Admin,
    CompanyReview,
    Course,
    Employer,
    Enrollment,
    HouseOwner,
    Instructor,
    Job,
    LaborMessage,
    LaborNotification,
    PasswordResetToken,
    Registration,
)
from app.routers.auth import require_admin
from app.schemas import (
    AdminDirectoryUserOut,
    AdminMemberOut,
    AdminOverviewOut,
    AdminStatsOut,
    AuthUserOut,
    CompanyFlagIn,
    CompanyReviewOut,
    CompanyReviewStatusIn,
    MemberBlockIn,
    MemberReminderIn,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _member_out(m: Registration) -> AdminMemberOut:
    return AdminMemberOut(
        id=m.id,
        full_name=m.full_name,
        email=m.email,
        phone=m.phone,
        language=m.language,
        zip_code=m.zip_code,
        state=m.state,
        county=m.county,
        promo_code=m.promo_code,
        skill_level=m.skill_level,
        experience=m.experience,
        work_authorized=bool(m.work_authorized),
        agreed_to_terms=bool(m.agreed_to_terms),
        trades=[{"category": t.category, "trade_name": t.trade_name} for t in m.trades],
        documents=[
            {
                "id": d.id,
                "doc_type": d.doc_type,
                "original_filename": d.original_filename,
                "uploaded_at": d.uploaded_at,
            }
            for d in m.documents
        ],
        created_at=m.created_at,
        last_login_at=m.last_login_at,
        is_blocked=bool(getattr(m, "is_blocked", False)),
    )


def _employer_out(e: Employer) -> AdminDirectoryUserOut:
    bits = []
    if bool(getattr(e, "is_verified", False)):
        bits.append("Verified")
    if getattr(e, "rank_label", None):
        bits.append(str(e.rank_label))
    if bool(getattr(e, "is_blocked", False)):
        bits.append("Blocked")
    detail = " · ".join(bits) if bits else "Construction company"
    return AdminDirectoryUserOut(
        id=e.id,
        full_name=e.company_name,
        email=e.email,
        role="employer",
        detail=detail,
        city=None,
        created_at=e.created_at,
        is_active=not bool(getattr(e, "is_blocked", False)),
        is_blocked=bool(getattr(e, "is_blocked", False)),
        is_verified=bool(getattr(e, "is_verified", False)),
        rank_label=getattr(e, "rank_label", None),
    )


@router.get("/overview", response_model=AdminOverviewOut)
def admin_overview(
    _: AuthUserOut = Depends(require_admin),
    db: Session = Depends(get_db),
):
    members = db.query(Registration).order_by(Registration.created_at.desc()).all()
    instructors = db.query(Instructor).order_by(Instructor.created_at.desc()).all()
    house_owners = db.query(HouseOwner).order_by(HouseOwner.created_at.desc()).all()
    employers = db.query(Employer).order_by(Employer.created_at.desc()).all()
    admins = db.query(Admin).order_by(Admin.created_at.desc()).all()

    recent = db.query(Enrollment).order_by(Enrollment.enrolled_at.desc()).limit(12).all()

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
        members=[_member_out(m) for m in members],
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
        employers=[_employer_out(e) for e in employers],
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


@router.post("/members/{member_id}/block", response_model=AdminMemberOut)
def block_member(
    member_id: int,
    payload: MemberBlockIn,
    _: AuthUserOut = Depends(require_admin),
    db: Session = Depends(get_db),
):
    member = db.query(Registration).filter(Registration.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found.")
    member.is_blocked = payload.blocked
    db.commit()
    db.refresh(member)
    return _member_out(member)


@router.delete("/members/{member_id}")
def delete_member(
    member_id: int,
    _: AuthUserOut = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Permanently delete a labour account so the same email/phone can register again."""
    member = db.query(Registration).filter(Registration.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found.")
    if not bool(getattr(member, "is_blocked", False)):
        raise HTTPException(
            status_code=400,
            detail="Block the labour account before permanent delete.",
        )
    email = member.email
    db.query(LaborNotification).filter(LaborNotification.registration_id == member_id).delete()
    db.query(LaborMessage).filter(LaborMessage.registration_id == member_id).delete()
    db.query(PasswordResetToken).filter(PasswordResetToken.email == email).delete()
    from app.models import CatalogAssignment, Certificate, Document, Enrollment, JobApplication, RegistrationTrade

    db.query(Enrollment).filter(Enrollment.registration_id == member_id).delete()
    db.query(Certificate).filter(Certificate.registration_id == member_id).delete(synchronize_session=False)
    try:
        db.query(CatalogAssignment).filter(CatalogAssignment.registration_id == member_id).delete(
            synchronize_session=False
        )
    except Exception:
        pass
    db.query(JobApplication).filter(JobApplication.registration_id == member_id).delete(
        synchronize_session=False
    )
    db.query(Document).filter(Document.registration_id == member_id).delete(synchronize_session=False)
    db.query(RegistrationTrade).filter(RegistrationTrade.registration_id == member_id).delete(
        synchronize_session=False
    )
    db.delete(member)
    db.commit()
    return {"ok": True, "deleted_id": member_id, "email_freed": email}


@router.post("/members/{member_id}/reminders")
def send_member_reminder(
    member_id: int,
    payload: MemberReminderIn,
    _: AuthUserOut = Depends(require_admin),
    db: Session = Depends(get_db),
):
    member = db.query(Registration).filter(Registration.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found.")
    note = LaborNotification(
        registration_id=member.id,
        title=payload.title.strip(),
        body=(payload.body or "").strip(),
        kind="reminder",
        is_read=False,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    mail = send_email(
        member.email,
        payload.title.strip(),
        f"<p>{payload.body or payload.title}</p><p>— BUILD FORCES Admin</p>",
        payload.body or payload.title,
    )
    return {
        "ok": True,
        "notification_id": note.id,
        "email_sent": bool(mail.get("sent")),
    }


@router.get("/companies/reviews", response_model=list[CompanyReviewOut])
def list_company_reviews(
    _: AuthUserOut = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rows = db.query(CompanyReview).order_by(CompanyReview.created_at.desc()).all()
    employers = {e.id: e.company_name for e in db.query(Employer).all()}
    return [
        CompanyReviewOut(
            id=r.id,
            employer_id=r.employer_id,
            company_name=employers.get(r.employer_id),
            author_name=r.author_name,
            rating=r.rating,
            body=r.body,
            status=r.status,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.post("/companies/reviews/{review_id}/status", response_model=CompanyReviewOut)
def set_company_review_status(
    review_id: int,
    payload: CompanyReviewStatusIn,
    _: AuthUserOut = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = db.query(CompanyReview).filter(CompanyReview.id == review_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Review not found.")
    row.status = payload.status
    db.commit()
    db.refresh(row)
    employer = db.query(Employer).filter(Employer.id == row.employer_id).first()
    return CompanyReviewOut(
        id=row.id,
        employer_id=row.employer_id,
        company_name=employer.company_name if employer else None,
        author_name=row.author_name,
        rating=row.rating,
        body=row.body,
        status=row.status,
        created_at=row.created_at,
    )


@router.delete("/companies/reviews/{review_id}")
def delete_company_review(
    review_id: int,
    _: AuthUserOut = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = db.query(CompanyReview).filter(CompanyReview.id == review_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Review not found.")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.post("/companies/{company_id}/flags", response_model=AdminDirectoryUserOut)
def set_company_flags(
    company_id: int,
    payload: CompanyFlagIn,
    _: AuthUserOut = Depends(require_admin),
    db: Session = Depends(get_db),
):
    company = db.query(Employer).filter(Employer.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found.")
    if payload.blocked is not None:
        company.is_blocked = payload.blocked
    if payload.verified is not None:
        company.is_verified = payload.verified
    if payload.rank_label is not None:
        label = payload.rank_label.strip()
        company.rank_label = label or None
    db.commit()
    db.refresh(company)
    return _employer_out(company)


@router.get("/email-status")
def admin_email_status(_: AuthUserOut = Depends(require_admin)):
    from app.mailer import email_config_status

    return email_config_status()


@router.post("/email-test")
def admin_email_test(
    payload: dict,
    _: AuthUserOut = Depends(require_admin),
):
    """Send a test email to confirm Gmail/SMTP is live."""
    from app.mailer import send_email

    to = str(payload.get("to") or "").strip().lower()
    if not to:
        raise HTTPException(status_code=400, detail="Provide { to: email }.")
    result = send_email(
        to,
        "BUILD FORCES email test",
        "<p>This is a test email from the BUILD FORCES backend.</p><p>If you received this, Gmail SMTP is live.</p>",
        "This is a test email from the BUILD FORCES backend. If you received this, Gmail SMTP is live.",
    )
    return result
