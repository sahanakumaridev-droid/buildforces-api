import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from sqlalchemy import text

from app.database import Base, engine
from app.routers import admin, admin_manage, auth, catalog, contact, courses, documents, employers, geo, homeowner, instructor, jobs, labor_inbox, register

load_dotenv()

Base.metadata.create_all(bind=engine)


def _ensure_auth_columns() -> None:
    """Add login columns for instructor/homeowner portals without a full migration tool."""
    statements = [
        "ALTER TABLE instructors ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255)",
        "ALTER TABLE house_owners ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255)",
        "ALTER TABLE house_owners ADD COLUMN IF NOT EXISTS zip_code VARCHAR(20) DEFAULT ''",
        "ALTER TABLE registrations ADD COLUMN IF NOT EXISTS work_authorized BOOLEAN DEFAULT FALSE",
        "ALTER TABLE registrations ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMP",
        # Phase 1 job fields
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS state VARCHAR(100)",
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS wage_type VARCHAR(20)",
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS wage_display VARCHAR(100)",
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS working_hours VARCHAR(100)",
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS job_duration VARCHAR(100)",
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS start_date TIMESTAMP",
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS end_date TIMESTAMP",
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS description TEXT",
        # Phase 1 course fields
        "ALTER TABLE courses ADD COLUMN IF NOT EXISTS trade VARCHAR(150)",
        "ALTER TABLE courses ADD COLUMN IF NOT EXISTS introduction TEXT",
        "ALTER TABLE courses ADD COLUMN IF NOT EXISTS course_date TIMESTAMP",
        "ALTER TABLE courses ADD COLUMN IF NOT EXISTS delivery_type VARCHAR(20)",
        "ALTER TABLE courses ADD COLUMN IF NOT EXISTS content_pattern VARCHAR(20)",
        "ALTER TABLE courses ADD COLUMN IF NOT EXISTS physical_location VARCHAR(255)",
        "ALTER TABLE courses ADD COLUMN IF NOT EXISTS online_info TEXT",
        "ALTER TABLE courses ADD COLUMN IF NOT EXISTS is_published BOOLEAN DEFAULT TRUE",
        "ALTER TABLE courses ADD COLUMN IF NOT EXISTS video_url VARCHAR(500)",
        "ALTER TABLE courses ADD COLUMN IF NOT EXISTS illustration VARCHAR(255)",
        "ALTER TABLE registrations ADD COLUMN IF NOT EXISTS is_paid BOOLEAN DEFAULT FALSE",
        "ALTER TABLE registrations ADD COLUMN IF NOT EXISTS is_blocked BOOLEAN DEFAULT FALSE",
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS house_owner_id INTEGER",
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS project_status VARCHAR(30) DEFAULT 'posted'",
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS timeline VARCHAR(200)",
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS cancel_reason TEXT",
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS contact_phone VARCHAR(50)",
        "ALTER TABLE certificates ADD COLUMN IF NOT EXISTS verification_code VARCHAR(64)",
        "ALTER TABLE certificates ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP",
        "ALTER TABLE courses ADD COLUMN IF NOT EXISTS instructor_id INTEGER",
        "ALTER TABLE enrollments ADD COLUMN IF NOT EXISTS progress_pct INTEGER DEFAULT 0",
        "ALTER TABLE enrollments ADD COLUMN IF NOT EXISTS grade VARCHAR(40)",
        "ALTER TABLE employers ADD COLUMN IF NOT EXISTS is_blocked BOOLEAN DEFAULT FALSE",
        "ALTER TABLE employers ADD COLUMN IF NOT EXISTS is_verified BOOLEAN DEFAULT FALSE",
        "ALTER TABLE employers ADD COLUMN IF NOT EXISTS rank_label VARCHAR(50)",
        "ALTER TABLE catalog_assignments ADD COLUMN IF NOT EXISTS video_url VARCHAR(2000)",
        "ALTER TABLE catalog_assignments ADD COLUMN IF NOT EXISTS lesson_youtube_ids TEXT",
    ]
    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))


_ensure_auth_columns()


def _ensure_fixed_admin() -> None:
    """Keep a known demo admin login so operators can always open the control center."""
    from app.database import SessionLocal
    from app.models import Admin
    from app.security import hash_password

    fixed = [
        ("admin@buildforces.com", "Buildforces Admin"),
        ("admin@buildforce.com", "Buildforces Admin"),
    ]
    password = "Admin123!"
    db = SessionLocal()
    try:
        for email, full_name in fixed:
            admin = db.query(Admin).filter(Admin.email == email).first()
            if not admin:
                db.add(
                    Admin(
                        full_name=full_name,
                        email=email,
                        password_hash=hash_password(password),
                        is_active=True,
                    )
                )
            else:
                admin.full_name = full_name
                admin.password_hash = hash_password(password)
                admin.is_active = True
        db.commit()
    finally:
        db.close()


_ensure_fixed_admin()


def _ensure_paid_demo_labor() -> None:
    """Keep known paid labor logins so catalog publishes and QA land on a real dashboard."""
    from app.database import SessionLocal
    from app.models import Registration, RegistrationTrade
    from app.security import hash_password

    accounts = [
        ("sahanakumari@buildforces.com", "Welcome123!", "Sahana Kumari", "415-555-0148"),
        ("sahanakumari@buildforce.com", "Labor123!", "Sahana Kumari", "415-555-0148"),
    ]
    db = SessionLocal()
    try:
        for email, password, full_name, phone in accounts:
            member = db.query(Registration).filter(Registration.email == email).first()
            if not member:
                member = Registration(
                    full_name=full_name,
                    email=email,
                    phone=phone,
                    password_hash=hash_password(password),
                    language="en",
                    zip_code="94103",
                    state="CA",
                    county="San Francisco",
                    skill_level="skilled",
                    experience="3-5",
                    work_authorized=True,
                    agreed_to_terms=True,
                    is_paid=True,
                    is_blocked=False,
                )
                member.trades = [
                    RegistrationTrade(category="General", trade_name="Construction"),
                ]
                db.add(member)
            else:
                member.full_name = member.full_name or full_name
                member.password_hash = hash_password(password)
                member.is_paid = True
                member.is_blocked = False
                member.work_authorized = True
                member.agreed_to_terms = True
        db.flush()
        from app.seed import ensure_demo_labor_courses

        ensure_demo_labor_courses(db)
        db.commit()
    finally:
        db.close()


_ensure_paid_demo_labor()


def _ensure_demo_employers() -> None:
    """Keep company-portal demo logins unblocked so QA and the mobile APK can sign in."""
    from app.database import SessionLocal
    from app.models import Employer
    from app.security import hash_password

    accounts = [
        ("crew@baycivil.demo", "Bay Area Civil Works"),
        ("hiring@pacificcrest.demo", "Pacific Crest Builders"),
        ("company@buildforces.com", "Build Forces Demo Co"),
        ("mobile.company@buildforces.com", "Pacific Crest Builders"),
    ]
    db = SessionLocal()
    try:
        for email, company_name in accounts:
            row = db.query(Employer).filter(Employer.email == email).first()
            if not row:
                db.add(
                    Employer(
                        company_name=company_name,
                        email=email,
                        password_hash=hash_password("Employer123!"),
                        is_blocked=False,
                    )
                )
            else:
                row.password_hash = hash_password("Employer123!")
                row.is_blocked = False
                if not row.company_name:
                    row.company_name = company_name
        db.commit()
    finally:
        db.close()


_ensure_demo_employers()

app = FastAPI(title="Buildforces API")

origins = os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "uploads"))
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(admin_manage.router)
app.include_router(labor_inbox.router)
app.include_router(contact.router)
app.include_router(register.router)
app.include_router(documents.router)
app.include_router(employers.router)
app.include_router(jobs.router)
app.include_router(homeowner.router)
app.include_router(instructor.router)
app.include_router(courses.router)
app.include_router(catalog.router)
app.include_router(geo.router)


@app.get("/api/health")
def health_check():
    return {"status": "ok"}
