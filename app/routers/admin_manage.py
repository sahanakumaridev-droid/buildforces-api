"""Admin CRUD for jobs, courses (modules/content), certificates, and media uploads."""

from __future__ import annotations

import os
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import (
    Certificate,
    Course,
    CourseContent,
    CourseModule,
    Job,
    JobAttachment,
    Registration,
)
from app.routers.auth import require_admin
from app.routers.courses import _course_to_out
from app.routers.jobs import _attachment_kind, _job_to_out
from app.schemas import (
    AuthUserOut,
    CertificateCreate,
    CertificateOut,
    CertificateUpdate,
    CourseContentCreate,
    CourseContentOut,
    CourseContentUpdate,
    CourseCreate,
    CourseModuleCreate,
    CourseModuleOut,
    CourseModuleUpdate,
    CourseOut,
    CourseUpdate,
    JobAttachmentCreate,
    JobAttachmentOut,
    JobCreate,
    JobOut,
    JobUpdate,
    MediaUploadOut,
    ModuleReorderPayload,
)

router = APIRouter(prefix="/api/admin", tags=["admin-manage"])

UPLOAD_DIR = os.path.abspath(
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "uploads")
)
os.makedirs(UPLOAD_DIR, exist_ok=True)

MEDIA_ALLOWED = {
    "application/pdf",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "video/mp4",
    "video/webm",
    "video/quicktime",
    "audio/mpeg",
    "audio/mp4",
    "audio/wav",
    "audio/x-wav",
    "audio/webm",
    "audio/ogg",
}
# Extension fallback when browsers send opaque mime types
MEDIA_EXTENSIONS = {
    ".pdf",
    ".ppt",
    ".pptx",
    ".doc",
    ".docx",
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".heic",
    ".mp4",
    ".webm",
    ".mov",
    ".mp3",
    ".m4a",
    ".wav",
    ".ogg",
}
MAX_MEDIA_SIZE = 200 * 1024 * 1024  # 200 MB for video/audio
MAX_CERT_SIZE = 20 * 1024 * 1024


def _file_url(stored_filename: str) -> str:
    return f"/uploads/{stored_filename}"


def _certificate_out(row: Certificate) -> CertificateOut:
    return CertificateOut(
        id=row.id,
        course_id=row.course_id,
        course_title=row.course.title if row.course else None,
        registration_id=row.registration_id,
        member_name=row.registration.full_name if row.registration else None,
        member_email=row.registration.email if row.registration else None,
        title=row.title,
        original_filename=row.original_filename,
        file_url=row.file_url,
        mime_type=row.mime_type,
        notes=row.notes,
        uploaded_by_admin_id=row.uploaded_by_admin_id,
        uploaded_at=row.uploaded_at,
    )


def _module_out(module: CourseModule) -> CourseModuleOut:
    contents = sorted(module.contents or [], key=lambda c: c.sort_order)
    return CourseModuleOut(
        id=module.id,
        course_id=module.course_id,
        title=module.title,
        description=module.description,
        reading_content=module.reading_content,
        sort_order=module.sort_order,
        contents=[
            CourseContentOut(
                id=c.id,
                module_id=c.module_id,
                content_kind=c.content_kind,
                title=c.title,
                description=c.description,
                file_url=c.file_url,
                original_filename=c.original_filename,
                mime_type=c.mime_type,
                sort_order=c.sort_order,
                created_at=c.created_at,
            )
            for c in contents
        ],
    )


# ---------------------------------------------------------------------------
# Media upload
# ---------------------------------------------------------------------------


@router.post("/media/upload", response_model=MediaUploadOut, status_code=201)
async def upload_media(
    file: UploadFile = File(...),
    _: AuthUserOut = Depends(require_admin),
):
    original = file.filename or "upload.bin"
    extension = os.path.splitext(original)[1].lower()
    mime = file.content_type or "application/octet-stream"

    if mime not in MEDIA_ALLOWED and extension not in MEDIA_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Use PDF, slides, images, video (mp4/webm/mov), or audio (mp3/wav/m4a).",
        )

    contents = await file.read()
    if len(contents) > MAX_MEDIA_SIZE:
        raise HTTPException(status_code=400, detail="File must be under 200 MB.")

    stored = f"{uuid.uuid4().hex}{extension}"
    with open(os.path.join(UPLOAD_DIR, stored), "wb") as handle:
        handle.write(contents)

    return MediaUploadOut(
        file_url=_file_url(stored),
        original_filename=original,
        stored_filename=stored,
        mime_type=mime,
        size_bytes=len(contents),
    )


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------


@router.get("/jobs", response_model=list[JobOut])
def admin_list_jobs(
    _: AuthUserOut = Depends(require_admin),
    db: Session = Depends(get_db),
):
    jobs = db.query(Job).order_by(Job.posted_at.desc()).all()
    return [_job_to_out(job) for job in jobs]


@router.get("/jobs/{job_id}", response_model=JobOut)
def admin_get_job(
    job_id: int,
    _: AuthUserOut = Depends(require_admin),
    db: Session = Depends(get_db),
):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return _job_to_out(job)


def _add_job_attachments(db: Session, job: Job, items: list[JobAttachmentCreate]) -> None:
    for item in items:
        kind = item.file_kind or _attachment_kind(item.mime_type, item.original_filename)
        db.add(
            JobAttachment(
                job_id=job.id,
                file_kind=kind,
                title=item.title,
                original_filename=item.original_filename,
                stored_filename=item.stored_filename or "",
                file_url=item.file_url,
                mime_type=item.mime_type,
            )
        )


@router.post("/jobs", response_model=JobOut, status_code=201)
def admin_create_job(
    payload: JobCreate,
    _: AuthUserOut = Depends(require_admin),
    db: Session = Depends(get_db),
):
    job = Job(
        title=payload.title.strip(),
        agency=payload.agency.strip() or "Buildforces",
        trade_category=payload.trade_category.strip(),
        skills=",".join(s.strip() for s in payload.skills if s.strip()),
        city=payload.city.strip(),
        state=payload.state.strip() if payload.state else None,
        zip_code=payload.zip_code.strip() if payload.zip_code else "",
        pay_min=payload.pay_min,
        pay_max=payload.pay_max,
        employment_type=payload.employment_type,
        min_experience_years=payload.min_experience_years,
        summary=payload.summary.strip(),
        description=payload.description.strip() if payload.description else None,
        wage_type=payload.wage_type,
        wage_display=payload.wage_display,
        working_hours=payload.working_hours,
        job_duration=payload.job_duration,
        start_date=payload.start_date,
        end_date=payload.end_date,
        apply_url=payload.apply_url or "",
        is_active=payload.is_active,
        posted_at=datetime.utcnow(),
    )
    db.add(job)
    db.flush()
    if payload.attachments:
        _add_job_attachments(db, job, payload.attachments)
    db.commit()
    db.refresh(job)
    return _job_to_out(job)


@router.put("/jobs/{job_id}", response_model=JobOut)
def admin_update_job(
    job_id: int,
    payload: JobUpdate,
    _: AuthUserOut = Depends(require_admin),
    db: Session = Depends(get_db),
):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    data = payload.model_dump(exclude_unset=True)
    if "skills" in data and data["skills"] is not None:
        data["skills"] = ",".join(s.strip() for s in data["skills"] if s and s.strip())
    for key, value in data.items():
        setattr(job, key, value)
    db.commit()
    db.refresh(job)
    return _job_to_out(job)


@router.post("/jobs/{job_id}/attachments", response_model=JobAttachmentOut, status_code=201)
def admin_add_job_attachment(
    job_id: int,
    payload: JobAttachmentCreate,
    _: AuthUserOut = Depends(require_admin),
    db: Session = Depends(get_db),
):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    kind = payload.file_kind or _attachment_kind(payload.mime_type, payload.original_filename)
    row = JobAttachment(
        job_id=job.id,
        file_kind=kind,
        title=payload.title,
        original_filename=payload.original_filename,
        stored_filename=payload.stored_filename or "",
        file_url=payload.file_url,
        mime_type=payload.mime_type,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return JobAttachmentOut(
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


@router.post("/jobs/{job_id}/attachments/upload", response_model=JobAttachmentOut, status_code=201)
async def admin_upload_job_attachment(
    job_id: int,
    file: UploadFile = File(...),
    title: Optional[str] = Form(default=None),
    _: AuthUserOut = Depends(require_admin),
    db: Session = Depends(get_db),
):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    original = file.filename or "upload.bin"
    extension = os.path.splitext(original)[1].lower()
    mime = file.content_type or "application/octet-stream"
    if mime not in MEDIA_ALLOWED and extension not in MEDIA_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Use images, video, PDF, or slides.",
        )
    contents = await file.read()
    if len(contents) > MAX_MEDIA_SIZE:
        raise HTTPException(status_code=400, detail="File must be under 200 MB.")

    stored = f"job_{uuid.uuid4().hex}{extension}"
    with open(os.path.join(UPLOAD_DIR, stored), "wb") as handle:
        handle.write(contents)

    row = JobAttachment(
        job_id=job.id,
        file_kind=_attachment_kind(mime, original),
        title=title,
        original_filename=original,
        stored_filename=stored,
        file_url=_file_url(stored),
        mime_type=mime,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return JobAttachmentOut(
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


@router.delete("/jobs/{job_id}/attachments/{attachment_id}")
def admin_delete_job_attachment(
    job_id: int,
    attachment_id: int,
    _: AuthUserOut = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = (
        db.query(JobAttachment)
        .filter(JobAttachment.id == attachment_id, JobAttachment.job_id == job_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Attachment not found.")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.delete("/jobs/{job_id}")
def admin_delete_job(
    job_id: int,
    _: AuthUserOut = Depends(require_admin),
    db: Session = Depends(get_db),
):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    db.delete(job)
    db.commit()
    return {"ok": True}


@router.post("/jobs/{job_id}/publish", response_model=JobOut)
def admin_publish_job(
    job_id: int,
    _: AuthUserOut = Depends(require_admin),
    db: Session = Depends(get_db),
):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    job.is_active = True
    db.commit()
    db.refresh(job)
    return _job_to_out(job)


@router.post("/jobs/{job_id}/unpublish", response_model=JobOut)
def admin_unpublish_job(
    job_id: int,
    _: AuthUserOut = Depends(require_admin),
    db: Session = Depends(get_db),
):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    job.is_active = False
    db.commit()
    db.refresh(job)
    return _job_to_out(job)


# ---------------------------------------------------------------------------
# Courses
# ---------------------------------------------------------------------------


def _load_course(db: Session, course_id: int) -> Course:
    course = (
        db.query(Course)
        .options(
            joinedload(Course.modules).joinedload(CourseModule.contents),
            joinedload(Course.sessions),
        )
        .filter(Course.id == course_id)
        .first()
    )
    if not course:
        raise HTTPException(status_code=404, detail="Course not found.")
    return course


@router.get("/courses", response_model=list[CourseOut])
def admin_list_courses(
    _: AuthUserOut = Depends(require_admin),
    db: Session = Depends(get_db),
):
    courses = (
        db.query(Course)
        .options(joinedload(Course.modules).joinedload(CourseModule.contents))
        .order_by(Course.id.desc())
        .all()
    )
    return [_course_to_out(c, include_modules=True) for c in courses]


@router.get("/courses/{course_id}", response_model=CourseOut)
def admin_get_course(
    course_id: int,
    _: AuthUserOut = Depends(require_admin),
    db: Session = Depends(get_db),
):
    course = _load_course(db, course_id)
    return _course_to_out(course, include_modules=True)


@router.post("/courses", response_model=CourseOut, status_code=201)
def admin_create_course(
    payload: CourseCreate,
    _: AuthUserOut = Depends(require_admin),
    db: Session = Depends(get_db),
):
    description = (payload.description or payload.introduction or "").strip()
    if not description:
        description = payload.title.strip()

    course = Course(
        title=payload.title.strip(),
        description=description,
        fee=payload.fee,
        duration=payload.duration or "",
        level=payload.level,
        category=payload.category,
        provider=payload.provider,
        location=payload.location or "",
        image=payload.image,
        outcomes="\n".join(payload.outcomes) if payload.outcomes else "",
        video_url=payload.video_url,
        trade=payload.trade,
        introduction=payload.introduction or description,
        course_date=payload.course_date,
        delivery_type=payload.delivery_type,
        content_pattern=payload.content_pattern,
        physical_location=payload.physical_location,
        online_info=payload.online_info,
        is_published=payload.is_published,
    )
    db.add(course)
    db.commit()
    course = _load_course(db, course.id)
    return _course_to_out(course, include_modules=True)


@router.put("/courses/{course_id}", response_model=CourseOut)
def admin_update_course(
    course_id: int,
    payload: CourseUpdate,
    _: AuthUserOut = Depends(require_admin),
    db: Session = Depends(get_db),
):
    course = _load_course(db, course_id)
    data = payload.model_dump(exclude_unset=True)
    if "outcomes" in data and data["outcomes"] is not None:
        data["outcomes"] = "\n".join(data["outcomes"])
    if "introduction" in data and data["introduction"] and "description" not in data:
        # Keep public description in sync when only introduction is updated
        if not course.description or course.description == (course.introduction or ""):
            data["description"] = data["introduction"]
    for key, value in data.items():
        setattr(course, key, value)
    db.commit()
    course = _load_course(db, course_id)
    return _course_to_out(course, include_modules=True)


@router.delete("/courses/{course_id}")
def admin_delete_course(
    course_id: int,
    _: AuthUserOut = Depends(require_admin),
    db: Session = Depends(get_db),
):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found.")
    db.delete(course)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Modules
# ---------------------------------------------------------------------------


@router.post("/courses/{course_id}/modules", response_model=CourseModuleOut, status_code=201)
def admin_create_module(
    course_id: int,
    payload: CourseModuleCreate,
    _: AuthUserOut = Depends(require_admin),
    db: Session = Depends(get_db),
):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found.")

    max_order = (
        db.query(CourseModule)
        .filter(CourseModule.course_id == course_id)
        .count()
    )
    module = CourseModule(
        course_id=course_id,
        title=payload.title.strip(),
        description=payload.description,
        reading_content=payload.reading_content,
        sort_order=payload.sort_order if payload.sort_order is not None else max_order,
    )
    db.add(module)
    db.commit()
    db.refresh(module)
    return _module_out(module)


@router.put("/modules/{module_id}", response_model=CourseModuleOut)
def admin_update_module(
    module_id: int,
    payload: CourseModuleUpdate,
    _: AuthUserOut = Depends(require_admin),
    db: Session = Depends(get_db),
):
    module = (
        db.query(CourseModule)
        .options(joinedload(CourseModule.contents))
        .filter(CourseModule.id == module_id)
        .first()
    )
    if not module:
        raise HTTPException(status_code=404, detail="Module not found.")
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(module, key, value)
    db.commit()
    db.refresh(module)
    return _module_out(module)


@router.delete("/modules/{module_id}")
def admin_delete_module(
    module_id: int,
    _: AuthUserOut = Depends(require_admin),
    db: Session = Depends(get_db),
):
    module = db.query(CourseModule).filter(CourseModule.id == module_id).first()
    if not module:
        raise HTTPException(status_code=404, detail="Module not found.")
    db.delete(module)
    db.commit()
    return {"ok": True}


@router.post("/courses/{course_id}/modules/reorder", response_model=list[CourseModuleOut])
def admin_reorder_modules(
    course_id: int,
    payload: ModuleReorderPayload,
    _: AuthUserOut = Depends(require_admin),
    db: Session = Depends(get_db),
):
    course = _load_course(db, course_id)
    order_map = {item.id: item.sort_order for item in payload.modules}
    for module in course.modules:
        if module.id in order_map:
            module.sort_order = order_map[module.id]
    db.commit()
    course = _load_course(db, course_id)
    return [_module_out(m) for m in sorted(course.modules, key=lambda m: m.sort_order)]


# ---------------------------------------------------------------------------
# Content
# ---------------------------------------------------------------------------


@router.post("/modules/{module_id}/contents", response_model=CourseContentOut, status_code=201)
def admin_create_content(
    module_id: int,
    payload: CourseContentCreate,
    _: AuthUserOut = Depends(require_admin),
    db: Session = Depends(get_db),
):
    module = db.query(CourseModule).filter(CourseModule.id == module_id).first()
    if not module:
        raise HTTPException(status_code=404, detail="Module not found.")

    count = db.query(CourseContent).filter(CourseContent.module_id == module_id).count()
    content = CourseContent(
        module_id=module_id,
        content_kind=payload.content_kind.strip().lower(),
        title=payload.title.strip(),
        description=payload.description,
        file_url=payload.file_url,
        original_filename=payload.original_filename,
        stored_filename=payload.stored_filename,
        mime_type=payload.mime_type,
        sort_order=payload.sort_order if payload.sort_order is not None else count,
    )
    db.add(content)
    db.commit()
    db.refresh(content)
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


@router.put("/contents/{content_id}", response_model=CourseContentOut)
def admin_update_content(
    content_id: int,
    payload: CourseContentUpdate,
    _: AuthUserOut = Depends(require_admin),
    db: Session = Depends(get_db),
):
    content = db.query(CourseContent).filter(CourseContent.id == content_id).first()
    if not content:
        raise HTTPException(status_code=404, detail="Content not found.")
    data = payload.model_dump(exclude_unset=True)
    if "content_kind" in data and data["content_kind"]:
        data["content_kind"] = data["content_kind"].strip().lower()
    for key, value in data.items():
        setattr(content, key, value)
    db.commit()
    db.refresh(content)
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


@router.delete("/contents/{content_id}")
def admin_delete_content(
    content_id: int,
    _: AuthUserOut = Depends(require_admin),
    db: Session = Depends(get_db),
):
    content = db.query(CourseContent).filter(CourseContent.id == content_id).first()
    if not content:
        raise HTTPException(status_code=404, detail="Content not found.")
    db.delete(content)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Certificates
# ---------------------------------------------------------------------------


@router.get("/certificates", response_model=list[CertificateOut])
def admin_list_certificates(
    course_id: Optional[int] = None,
    _: AuthUserOut = Depends(require_admin),
    db: Session = Depends(get_db),
):
    query = db.query(Certificate).options(
        joinedload(Certificate.course),
        joinedload(Certificate.registration),
    )
    if course_id is not None:
        query = query.filter(Certificate.course_id == course_id)
    rows = query.order_by(Certificate.uploaded_at.desc()).all()
    return [_certificate_out(row) for row in rows]


@router.post("/certificates", response_model=CertificateOut, status_code=201)
def admin_create_certificate(
    payload: CertificateCreate,
    admin: AuthUserOut = Depends(require_admin),
    db: Session = Depends(get_db),
):
    course = db.query(Course).filter(Course.id == payload.course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found.")
    if payload.registration_id is not None:
        member = db.query(Registration).filter(Registration.id == payload.registration_id).first()
        if not member:
            raise HTTPException(status_code=404, detail="Member not found.")

    row = Certificate(
        course_id=payload.course_id,
        registration_id=payload.registration_id,
        title=payload.title,
        original_filename=payload.original_filename,
        stored_filename=payload.stored_filename or "",
        mime_type=payload.mime_type,
        file_url=payload.file_url,
        notes=payload.notes,
        uploaded_by_admin_id=admin.id,
    )
    db.add(row)
    db.commit()
    row = (
        db.query(Certificate)
        .options(joinedload(Certificate.course), joinedload(Certificate.registration))
        .filter(Certificate.id == row.id)
        .first()
    )
    return _certificate_out(row)


@router.post("/certificates/upload", response_model=CertificateOut, status_code=201)
async def admin_upload_certificate(
    course_id: int = Form(...),
    registration_id: Optional[int] = Form(default=None),
    title: Optional[str] = Form(default=None),
    notes: Optional[str] = Form(default=None),
    file: UploadFile = File(...),
    admin: AuthUserOut = Depends(require_admin),
    db: Session = Depends(get_db),
):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found.")
    if registration_id is not None:
        member = db.query(Registration).filter(Registration.id == registration_id).first()
        if not member:
            raise HTTPException(status_code=404, detail="Member not found.")

    original = file.filename or "certificate.pdf"
    extension = os.path.splitext(original)[1].lower()
    mime = file.content_type or "application/octet-stream"
    allowed = {
        "application/pdf",
        "image/jpeg",
        "image/png",
        "image/webp",
    }
    if mime not in allowed and extension not in {".pdf", ".jpg", ".jpeg", ".png", ".webp"}:
        raise HTTPException(status_code=400, detail="Certificates must be PDF or image files.")

    contents = await file.read()
    if len(contents) > MAX_CERT_SIZE:
        raise HTTPException(status_code=400, detail="Certificate file must be under 20 MB.")

    stored = f"cert_{uuid.uuid4().hex}{extension}"
    with open(os.path.join(UPLOAD_DIR, stored), "wb") as handle:
        handle.write(contents)

    row = Certificate(
        course_id=course_id,
        registration_id=registration_id,
        title=title,
        original_filename=original,
        stored_filename=stored,
        mime_type=mime,
        file_url=_file_url(stored),
        notes=notes,
        uploaded_by_admin_id=admin.id,
    )
    db.add(row)
    db.commit()
    row = (
        db.query(Certificate)
        .options(joinedload(Certificate.course), joinedload(Certificate.registration))
        .filter(Certificate.id == row.id)
        .first()
    )
    return _certificate_out(row)


@router.put("/certificates/{certificate_id}", response_model=CertificateOut)
def admin_update_certificate(
    certificate_id: int,
    payload: CertificateUpdate,
    _: AuthUserOut = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = db.query(Certificate).filter(Certificate.id == certificate_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Certificate not found.")
    data = payload.model_dump(exclude_unset=True)
    if "course_id" in data and data["course_id"] is not None:
        if not db.query(Course).filter(Course.id == data["course_id"]).first():
            raise HTTPException(status_code=404, detail="Course not found.")
    if "registration_id" in data and data["registration_id"] is not None:
        if not db.query(Registration).filter(Registration.id == data["registration_id"]).first():
            raise HTTPException(status_code=404, detail="Member not found.")
    for key, value in data.items():
        setattr(row, key, value)
    db.commit()
    row = (
        db.query(Certificate)
        .options(joinedload(Certificate.course), joinedload(Certificate.registration))
        .filter(Certificate.id == certificate_id)
        .first()
    )
    return _certificate_out(row)


@router.delete("/certificates/{certificate_id}")
def admin_delete_certificate(
    certificate_id: int,
    _: AuthUserOut = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = db.query(Certificate).filter(Certificate.id == certificate_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Certificate not found.")
    db.delete(row)
    db.commit()
    return {"ok": True}
