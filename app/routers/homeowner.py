from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import HouseOwner, Job, JobApplication, JobMessage, JobReview, Registration
from app.routers.auth import require_homeowner
from app.routers.jobs import _job_to_out
from app.schemas import (
    ApplicantOut,
    AuthUserOut,
    HomeownerJobCreate,
    HomeownerJobUpdate,
    HomeownerOverviewOut,
    JobMessageIn,
    JobMessageOut,
    JobOut,
    JobReviewIn,
    JobReviewOut,
)

router = APIRouter(prefix="/api/homeowner", tags=["homeowner"])

STATUSES = {"posted", "hired", "in_progress", "completed", "cancelled"}


def _owner(user: AuthUserOut, db: Session) -> HouseOwner:
    owner = db.query(HouseOwner).filter(HouseOwner.id == user.id).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Homeowner account not found.")
    return owner


def _owned_job(job_id: int, owner: HouseOwner, db: Session) -> Job:
    job = db.query(Job).filter(Job.id == job_id, Job.house_owner_id == owner.id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


def _applicant_out(row: JobApplication) -> ApplicantOut:
    member = row.registration
    trades = [t.trade_name for t in (member.trades if member else [])]
    verified = bool(member and any(d.doc_type == "government_id" for d in (member.documents or [])))
    return ApplicantOut(
        id=row.id,
        job_id=row.job_id,
        status=row.status,
        applied_at=row.applied_at,
        note=row.note,
        member_id=member.id if member else row.registration_id,
        full_name=member.full_name if member else "Unknown",
        email=member.email if member else "",
        phone=member.phone if member else "",
        zip_code=member.zip_code if member else "",
        skill_level=member.skill_level if member else "",
        experience=member.experience if member else "",
        trades=trades,
        verified=verified,
    )


@router.get("/overview", response_model=HomeownerOverviewOut)
def overview(user: AuthUserOut = Depends(require_homeowner), db: Session = Depends(get_db)):
    owner = _owner(user, db)
    jobs = (
        db.query(Job)
        .options(joinedload(Job.applications), joinedload(Job.attachments))
        .filter(Job.house_owner_id == owner.id)
        .order_by(Job.posted_at.desc())
        .all()
    )
    applicants = sum(len(job.applications or []) for job in jobs)
    return HomeownerOverviewOut(
        active_projects=sum(1 for job in jobs if job.project_status in {"hired", "in_progress"}),
        open_jobs=sum(1 for job in jobs if job.project_status == "posted" and job.is_active),
        applicants=applicants,
        completed=sum(1 for job in jobs if job.project_status == "completed"),
        jobs=[_job_to_out(job) for job in jobs],
    )


@router.get("/jobs", response_model=list[JobOut])
def list_jobs(user: AuthUserOut = Depends(require_homeowner), db: Session = Depends(get_db)):
    owner = _owner(user, db)
    jobs = (
        db.query(Job)
        .options(joinedload(Job.applications), joinedload(Job.attachments))
        .filter(Job.house_owner_id == owner.id)
        .order_by(Job.posted_at.desc())
        .all()
    )
    return [_job_to_out(job) for job in jobs]


@router.post("/jobs", response_model=JobOut)
def create_job(
    payload: HomeownerJobCreate,
    user: AuthUserOut = Depends(require_homeowner),
    db: Session = Depends(get_db),
):
    owner = _owner(user, db)
    job = Job(
        title=payload.title.strip(),
        agency=owner.full_name,
        trade_category=payload.trade_category.strip(),
        skills=",".join(payload.skills),
        city=payload.city.strip(),
        zip_code=payload.zip_code.strip(),
        pay_min=payload.pay_min,
        pay_max=payload.pay_max,
        employment_type="Residential",
        min_experience_years=0,
        summary=payload.summary.strip(),
        description=payload.description,
        state=payload.state,
        wage_display=payload.budget,
        job_duration=payload.timeline,
        timeline=payload.timeline,
        start_date=payload.start_date,
        end_date=payload.end_date,
        is_active=True,
        apply_url="",
        house_owner_id=owner.id,
        project_status="posted",
        contact_phone=(payload.contact_phone or "").strip() or None,
    )
    db.add(job)
    owner.project_count = (owner.project_count or 0) + 1
    db.commit()
    db.refresh(job)
    return _job_to_out(job)


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: int, user: AuthUserOut = Depends(require_homeowner), db: Session = Depends(get_db)):
    owner = _owner(user, db)
    return _job_to_out(_owned_job(job_id, owner, db))


@router.put("/jobs/{job_id}", response_model=JobOut)
def update_job(
    job_id: int,
    payload: HomeownerJobUpdate,
    user: AuthUserOut = Depends(require_homeowner),
    db: Session = Depends(get_db),
):
    owner = _owner(user, db)
    job = _owned_job(job_id, owner, db)
    data = payload.model_dump(exclude_unset=True)
    if "skills" in data and data["skills"] is not None:
        job.skills = ",".join(data.pop("skills"))
    if "budget" in data:
        job.wage_display = data.pop("budget")
    if "timeline" in data:
        job.timeline = data["timeline"]
        job.job_duration = data.pop("timeline")
    if "project_status" in data and data["project_status"] not in STATUSES:
        raise HTTPException(status_code=400, detail="Invalid project status.")
    if data.get("project_status") == "cancelled" and not (data.get("cancel_reason") or job.cancel_reason):
        raise HTTPException(status_code=400, detail="A cancellation reason is required.")
    if data.get("project_status") == "cancelled":
        job.is_active = False
    for key, value in data.items():
        setattr(job, key, value)
    db.commit()
    db.refresh(job)
    return _job_to_out(job)


@router.delete("/jobs/{job_id}")
def delete_job(
    job_id: int,
    payload: HomeownerJobUpdate,
    user: AuthUserOut = Depends(require_homeowner),
    db: Session = Depends(get_db),
):
    owner = _owner(user, db)
    job = _owned_job(job_id, owner, db)
    reason = (payload.cancel_reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="A cancellation reason is required.")
    job.project_status = "cancelled"
    job.cancel_reason = reason
    job.is_active = False
    db.commit()
    return {"ok": True}


@router.get("/jobs/{job_id}/applications", response_model=list[ApplicantOut])
def list_applications(
    job_id: int,
    user: AuthUserOut = Depends(require_homeowner),
    db: Session = Depends(get_db),
):
    owner = _owner(user, db)
    _owned_job(job_id, owner, db)
    rows = (
        db.query(JobApplication)
        .options(joinedload(JobApplication.registration).joinedload(Registration.trades))
        .filter(JobApplication.job_id == job_id)
        .order_by(JobApplication.applied_at.desc())
        .all()
    )
    return [_applicant_out(row) for row in rows]


@router.post("/jobs/{job_id}/hire/{application_id}", response_model=ApplicantOut)
def hire_worker(
    job_id: int,
    application_id: int,
    user: AuthUserOut = Depends(require_homeowner),
    db: Session = Depends(get_db),
):
    owner = _owner(user, db)
    job = _owned_job(job_id, owner, db)
    application = (
        db.query(JobApplication)
        .filter(JobApplication.id == application_id, JobApplication.job_id == job.id)
        .first()
    )
    if not application:
        raise HTTPException(status_code=404, detail="Application not found.")
    for row in job.applications:
        row.status = "hired" if row.id == application.id else "rejected"
    job.project_status = "hired"
    db.commit()
    db.refresh(application)
    return _applicant_out(application)


@router.post("/jobs/{job_id}/status", response_model=JobOut)
def set_status(
    job_id: int,
    payload: HomeownerJobUpdate,
    user: AuthUserOut = Depends(require_homeowner),
    db: Session = Depends(get_db),
):
    owner = _owner(user, db)
    job = _owned_job(job_id, owner, db)
    status = payload.project_status
    if status not in STATUSES:
        raise HTTPException(status_code=400, detail="Invalid project status.")
    if status == "cancelled" and not (payload.cancel_reason or "").strip():
        raise HTTPException(status_code=400, detail="A cancellation reason is required.")
    job.project_status = status
    if payload.cancel_reason:
        job.cancel_reason = payload.cancel_reason.strip()
    if status == "cancelled":
        job.is_active = False
    db.commit()
    db.refresh(job)
    return _job_to_out(job)


@router.get("/jobs/{job_id}/reviews", response_model=list[JobReviewOut])
def list_reviews(
    job_id: int,
    user: AuthUserOut = Depends(require_homeowner),
    db: Session = Depends(get_db),
):
    owner = _owner(user, db)
    _owned_job(job_id, owner, db)
    rows = db.query(JobReview).filter(JobReview.job_id == job_id).order_by(JobReview.created_at.desc()).all()
    return [
        JobReviewOut(
            id=row.id,
            job_id=row.job_id,
            registration_id=row.registration_id,
            rating_quality=row.rating_quality,
            rating_punctuality=row.rating_punctuality,
            rating_professionalism=row.rating_professionalism,
            comment=row.comment,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.post("/jobs/{job_id}/reviews", response_model=JobReviewOut)
def create_review(
    job_id: int,
    payload: JobReviewIn,
    user: AuthUserOut = Depends(require_homeowner),
    db: Session = Depends(get_db),
):
    owner = _owner(user, db)
    job = _owned_job(job_id, owner, db)
    if job.project_status != "completed":
        raise HTTPException(status_code=400, detail="Mark the job completed before leaving a review.")
    hired = (
        db.query(JobApplication)
        .filter(
            JobApplication.job_id == job.id,
            JobApplication.registration_id == payload.registration_id,
            JobApplication.status == "hired",
        )
        .first()
    )
    if not hired:
        raise HTTPException(status_code=400, detail="Reviews are only for the hired worker.")
    review = JobReview(
        job_id=job.id,
        house_owner_id=owner.id,
        registration_id=payload.registration_id,
        rating_quality=payload.rating_quality,
        rating_punctuality=payload.rating_punctuality,
        rating_professionalism=payload.rating_professionalism,
        comment=payload.comment.strip(),
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    return JobReviewOut(
        id=review.id,
        job_id=review.job_id,
        registration_id=review.registration_id,
        rating_quality=review.rating_quality,
        rating_punctuality=review.rating_punctuality,
        rating_professionalism=review.rating_professionalism,
        comment=review.comment,
        created_at=review.created_at,
    )


@router.get("/jobs/{job_id}/messages", response_model=list[JobMessageOut])
def list_messages(
    job_id: int,
    user: AuthUserOut = Depends(require_homeowner),
    db: Session = Depends(get_db),
):
    owner = _owner(user, db)
    _owned_job(job_id, owner, db)
    rows = db.query(JobMessage).filter(JobMessage.job_id == job_id).order_by(JobMessage.created_at.asc()).all()
    return [
        JobMessageOut(
            id=row.id,
            job_id=row.job_id,
            sender_role=row.sender_role,
            sender_id=row.sender_id,
            sender_name=row.sender_name,
            body=row.body,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.post("/jobs/{job_id}/messages", response_model=JobMessageOut)
def send_message(
    job_id: int,
    payload: JobMessageIn,
    user: AuthUserOut = Depends(require_homeowner),
    db: Session = Depends(get_db),
):
    owner = _owner(user, db)
    job = _owned_job(job_id, owner, db)
    row = JobMessage(
        job_id=job.id,
        sender_role="homeowner",
        sender_id=owner.id,
        sender_name=owner.full_name,
        body=payload.body.strip(),
        created_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return JobMessageOut(
        id=row.id,
        job_id=row.job_id,
        sender_role=row.sender_role,
        sender_id=row.sender_id,
        sender_name=row.sender_name,
        body=row.body,
        created_at=row.created_at,
    )
