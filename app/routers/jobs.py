from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Job
from app.routers.auth import require_labor
from app.schemas import AuthUserOut, JobAttachmentOut, JobOut

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

EXPERIENCE_YEARS = {
    "1-3": 2,
    "3-5": 4,
    "5-10": 7,
    "10+": 12,
}


def _attachment_kind(mime: Optional[str], filename: str = "") -> str:
    mime = (mime or "").lower()
    name = filename.lower()
    if mime.startswith("video/") or name.endswith((".mp4", ".webm", ".mov")):
        return "video"
    if mime.startswith("image/") or name.endswith((".jpg", ".jpeg", ".png", ".webp", ".heic")):
        return "image"
    if mime == "application/pdf" or name.endswith(".pdf"):
        return "pdf"
    return "file"


def _job_to_out(job: Job, match_score: Optional[float] = None, matched_skills: Optional[list[str]] = None) -> JobOut:
    attachments = []
    for row in getattr(job, "attachments", None) or []:
        attachments.append(
            JobAttachmentOut(
                id=row.id,
                job_id=row.job_id,
                file_kind=row.file_kind,
                title=row.title,
                original_filename=row.original_filename,
                stored_filename=row.stored_filename or "",
                file_url=row.file_url,
                mime_type=row.mime_type,
                created_at=row.created_at,
            )
        )
    return JobOut(
        id=job.id,
        title=job.title,
        agency=job.agency,
        trade_category=job.trade_category,
        skills=[s.strip() for s in job.skills.split(",") if s.strip()],
        city=job.city,
        zip_code=job.zip_code,
        pay_min=float(job.pay_min) if job.pay_min is not None else None,
        pay_max=float(job.pay_max) if job.pay_max is not None else None,
        employment_type=job.employment_type,
        min_experience_years=job.min_experience_years,
        summary=job.summary,
        posted_at=job.posted_at,
        apply_url=job.apply_url,
        match_score=match_score,
        matched_skills=matched_skills,
        state=job.state,
        wage_type=job.wage_type,
        wage_display=job.wage_display,
        working_hours=job.working_hours,
        job_duration=job.job_duration,
        start_date=job.start_date,
        end_date=job.end_date,
        description=job.description,
        is_active=bool(job.is_active),
        attachments=attachments,
        house_owner_id=getattr(job, "house_owner_id", None),
        project_status=getattr(job, "project_status", None),
        timeline=getattr(job, "timeline", None),
        cancel_reason=getattr(job, "cancel_reason", None),
        applicant_count=len(getattr(job, "applications", None) or []),
    )


@router.get("", response_model=list[JobOut])
def search_jobs(
    q: Optional[str] = Query(default=None, description="Free-text search: skills, trade, or job title"),
    zip_code: Optional[str] = Query(default=None),
    experience: Optional[str] = Query(default=None, description="One of 1-3, 3-5, 5-10, 10+"),
    skills: Optional[str] = Query(default=None, description="Comma-separated skills from the user's profile"),
    db: Session = Depends(get_db),
):
    jobs = db.query(Job).filter(Job.is_active == True).all()  # noqa: E712

    query_terms = set()
    if q:
        query_terms.update(t.strip().lower() for t in q.split() if t.strip())
    profile_skills = set()
    if skills:
        profile_skills.update(t.strip().lower() for t in skills.split(",") if t.strip())

    user_years = EXPERIENCE_YEARS.get(experience or "", None)

    scored = []
    for job in jobs:
        job_skills = [s.strip() for s in job.skills.split(",") if s.strip()]
        job_skills_lower = {s.lower() for s in job_skills}

        matched = set()
        score = 0.0

        for term in query_terms:
            if term in job_skills_lower:
                score += 4
                matched.update(s for s in job_skills if s.lower() == term)
            elif any(term in s for s in job_skills_lower):
                score += 3
                matched.update(s for s in job_skills if term in s.lower())
            elif term in job.title.lower() or term in job.trade_category.lower():
                score += 2.5

        for skill in profile_skills:
            if skill in job_skills_lower:
                score += 3
                matched.update(s for s in job_skills if s.lower() == skill)

        if zip_code:
            if job.zip_code == zip_code:
                score += 2
            elif job.zip_code[:3] == zip_code[:3]:
                score += 1

        if user_years is not None:
            if user_years >= job.min_experience_years:
                score += 1
            elif job.min_experience_years - user_years > 2:
                score -= 2

        # If no search/profile signal was provided at all, keep neutral score so
        # every active job still shows up, most-recent first.
        scored.append((score, job, sorted(matched)))

    has_query_signal = bool(query_terms or profile_skills or zip_code or user_years is not None)
    if has_query_signal:
        scored.sort(key=lambda item: (item[0], item[1].posted_at), reverse=True)
    else:
        scored.sort(key=lambda item: item[1].posted_at, reverse=True)

    return [
        _job_to_out(job, match_score=score if has_query_signal else None, matched_skills=matched or None)
        for score, job, matched in scored
    ]


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return _job_to_out(job)


@router.post("/{job_id}/apply")
def apply_to_job(
    job_id: int,
    user: AuthUserOut = Depends(require_labor),
    db: Session = Depends(get_db),
):
    from app.models import JobApplication

    job = db.query(Job).filter(Job.id == job_id, Job.is_active == True).first()  # noqa: E712
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    existing = (
        db.query(JobApplication)
        .filter(JobApplication.job_id == job_id, JobApplication.registration_id == user.id)
        .first()
    )
    if existing:
        return {"ok": True, "id": existing.id, "status": existing.status, "already_applied": True}
    application = JobApplication(job_id=job_id, registration_id=user.id, status="applied")
    db.add(application)
    db.commit()
    db.refresh(application)
    return {"ok": True, "id": application.id, "status": application.status, "already_applied": False}
