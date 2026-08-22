from calendar import monthrange
from datetime import datetime, time

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Certificate, Employer, Enrollment, Job, JobApplication, Registration
from app.routers.auth import email_in_use
from app.schemas import (
    EmployerAuthResponse,
    EmployerCreate,
    EmployerLogin,
    EmployerOut,
    EmployerOverviewOut,
    EmployerReportOut,
)
from app.security import create_employer_token, decode_employer_token, hash_password, verify_password

router = APIRouter(prefix="/api/employers", tags=["employers"])


@router.post("/register", response_model=EmployerAuthResponse, status_code=201)
def register_employer(payload: EmployerCreate, db: Session = Depends(get_db)):
    if email_in_use(db, payload.email):
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    employer = Employer(
        company_name=payload.company_name.strip(),
        email=payload.email.lower().strip(),
        password_hash=hash_password(payload.password),
    )
    db.add(employer)
    db.commit()
    db.refresh(employer)

    return EmployerAuthResponse(token=create_employer_token(employer.id), employer=employer)


@router.post("/login", response_model=EmployerAuthResponse)
def login_employer(payload: EmployerLogin, db: Session = Depends(get_db)):
    employer = db.query(Employer).filter(Employer.email == payload.email.lower().strip()).first()
    if not employer or not verify_password(payload.password, employer.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    if bool(getattr(employer, "is_blocked", False)):
        raise HTTPException(
            status_code=403,
            detail="This company account is blocked. Contact BUILD FORCES support.",
        )

    return EmployerAuthResponse(token=create_employer_token(employer.id), employer=employer)


def get_current_employer(
    authorization: str = Header(default=""), db: Session = Depends(get_db)
) -> Employer:
    token = authorization.removeprefix("Bearer ").strip()
    employer_id = decode_employer_token(token) if token else None
    if not employer_id:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    employer = db.query(Employer).filter(Employer.id == employer_id).first()
    if not employer:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    if bool(getattr(employer, "is_blocked", False)):
        raise HTTPException(status_code=403, detail="This company account is blocked.")
    return employer


def _employer_out(employer: Employer) -> EmployerOut:
    return EmployerOut(
        id=employer.id,
        company_name=employer.company_name,
        email=employer.email,
        created_at=employer.created_at,
        is_blocked=bool(getattr(employer, "is_blocked", False)),
        is_verified=bool(getattr(employer, "is_verified", False)),
        rank_label=getattr(employer, "rank_label", None),
    )


@router.get("/me", response_model=EmployerOut)
def get_me(employer: Employer = Depends(get_current_employer)):
    return _employer_out(employer)


@router.get("/overview", response_model=EmployerOverviewOut)
def overview(employer: Employer = Depends(get_current_employer), db: Session = Depends(get_db)):
    labour_active = (
        db.query(Registration).filter(Registration.is_blocked.is_(False)).count()
    )
    enrollments = db.query(Enrollment).count()
    certificates = db.query(Certificate).count()
    return EmployerOverviewOut(
        company_name=employer.company_name,
        email=employer.email,
        on_site=labour_active,
        reports_today=0,
        tasks=0,
        open_cpm=0,
        is_verified=bool(getattr(employer, "is_verified", False)),
        rank_label=getattr(employer, "rank_label", None),
        labour_active=labour_active,
        enrollments=enrollments,
        certificates=certificates,
    )


def _build_report(
    db: Session,
    employer: Employer,
    start: datetime,
    end: datetime,
    period_label: str,
) -> EmployerReportOut:
    labour_active = (
        db.query(Registration).filter(Registration.is_blocked.is_(False)).count()
    )
    enrolments = (
        db.query(Enrollment)
        .filter(Enrollment.enrolled_at >= start, Enrollment.enrolled_at <= end)
        .count()
    )
    certificates = (
        db.query(Certificate)
        .filter(Certificate.uploaded_at >= start, Certificate.uploaded_at <= end)
        .count()
    )
    jobs_active = db.query(Job).filter(Job.is_active.is_(True)).count()
    applications = (
        db.query(JobApplication)
        .filter(JobApplication.applied_at >= start, JobApplication.applied_at <= end)
        .count()
    )

    enrollment_rows = (
        db.query(Enrollment)
        .filter(Enrollment.enrolled_at >= start, Enrollment.enrolled_at <= end)
        .order_by(Enrollment.enrolled_at.desc())
        .limit(200)
        .all()
    )
    member_ids = {e.registration_id for e in enrollment_rows}
    members = {
        m.id: m
        for m in db.query(Registration).filter(Registration.id.in_(member_ids or [-1])).all()
    }
    rows = []
    for e in enrollment_rows:
        member = members.get(e.registration_id)
        rows.append(
            {
                "type": "enrollment",
                "member": member.full_name if member else f"#{e.registration_id}",
                "email": member.email if member else "",
                "course": e.course.title if e.course else "",
                "status": e.status,
                "progress_pct": getattr(e, "progress_pct", 0) or 0,
                "at": e.enrolled_at.isoformat(),
            }
        )

    cert_rows = (
        db.query(Certificate)
        .filter(Certificate.uploaded_at >= start, Certificate.uploaded_at <= end)
        .order_by(Certificate.uploaded_at.desc())
        .limit(100)
        .all()
    )
    for c in cert_rows:
        rows.append(
            {
                "type": "certificate",
                "member": c.registration.full_name if c.registration else "",
                "email": c.registration.email if c.registration else "",
                "course": c.course.title if c.course else "",
                "status": "issued",
                "progress_pct": 100,
                "at": c.uploaded_at.isoformat(),
            }
        )

    return EmployerReportOut(
        company_name=employer.company_name,
        period_label=period_label,
        generated_at=datetime.utcnow(),
        labour_active=labour_active,
        enrolments=enrolments,
        certificates_issued=certificates,
        jobs_active=jobs_active,
        applications=applications,
        rows=rows,
    )


@router.get("/reports/daily", response_model=EmployerReportOut)
def daily_report(
    date: str = Query(..., description="YYYY-MM-DD"),
    employer: Employer = Depends(get_current_employer),
    db: Session = Depends(get_db),
):
    try:
        day = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD") from exc
    start = datetime.combine(day, time.min)
    end = datetime.combine(day, time.max)
    return _build_report(db, employer, start, end, f"Daily {day.isoformat()}")


@router.get("/reports/monthly", response_model=EmployerReportOut)
def monthly_report(
    year: int = Query(..., ge=2020, le=2100),
    month: int = Query(..., ge=1, le=12),
    employer: Employer = Depends(get_current_employer),
    db: Session = Depends(get_db),
):
    last_day = monthrange(year, month)[1]
    start = datetime(year, month, 1, 0, 0, 0)
    end = datetime(year, month, last_day, 23, 59, 59)
    return _build_report(db, employer, start, end, f"Monthly {year}-{month:02d}")


@router.get("/reports/monthly.xlsx")
def monthly_report_xlsx(
    year: int = Query(..., ge=2020, le=2100),
    month: int = Query(..., ge=1, le=12),
    employer: Employer = Depends(get_current_employer),
    db: Session = Depends(get_db),
):
    last_day = monthrange(year, month)[1]
    start = datetime(year, month, 1, 0, 0, 0)
    end = datetime(year, month, last_day, 23, 59, 59)
    report = _build_report(db, employer, start, end, f"Monthly {year}-{month:02d}")

    # Minimal XLSX (Office Open XML) without extra dependencies.
    import io
    import zipfile

    def sheet_xml(rows: list[list[str]]) -> str:
        cells = []
        for r_idx, row in enumerate(rows, start=1):
            parts = []
            for c_idx, value in enumerate(row):
                col = chr(ord("A") + c_idx)
                safe = (
                    str(value)
                    .replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                )
                parts.append(
                    f'<c r="{col}{r_idx}" t="inlineStr"><is><t>{safe}</t></is></c>'
                )
            cells.append(f'<row r="{r_idx}">{"".join(parts)}</row>')
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<sheetData>{"".join(cells)}</sheetData></worksheet>'
        )

    header = [
        "Type",
        "Member",
        "Email",
        "Course",
        "Status",
        "Progress %",
        "Timestamp",
    ]
    data_rows = [
        header,
        [
            "SUMMARY",
            report.company_name,
            report.period_label,
            f"labour={report.labour_active}",
            f"enrolments={report.enrolments}",
            f"certs={report.certificates_issued}",
            f"apps={report.applications}",
        ],
    ]
    for row in report.rows:
        data_rows.append(
            [
                str(row.get("type", "")),
                str(row.get("member", "")),
                str(row.get("email", "")),
                str(row.get("course", "")),
                str(row.get("status", "")),
                str(row.get("progress_pct", "")),
                str(row.get("at", "")),
            ]
        )

    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>"""
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""
    workbook = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="Monthly Report" sheetId="1" r:id="rId1"/></sheets>
</workbook>"""
    workbook_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>"""

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("xl/workbook.xml", workbook)
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml(data_rows))
    payload = buf.getvalue()
    filename = f"buildforces-monthly-{year}-{month:02d}.xlsx"
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
