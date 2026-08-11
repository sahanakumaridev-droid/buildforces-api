import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from sqlalchemy import text

from app.database import Base, engine
from app.routers import admin, admin_manage, auth, contact, courses, documents, employers, jobs, register

load_dotenv()

Base.metadata.create_all(bind=engine)


def _ensure_auth_columns() -> None:
    """Add login columns for instructor/homeowner portals without a full migration tool."""
    statements = [
        "ALTER TABLE instructors ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255)",
        "ALTER TABLE house_owners ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255)",
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
app.include_router(contact.router)
app.include_router(register.router)
app.include_router(documents.router)
app.include_router(employers.router)
app.include_router(jobs.router)
app.include_router(courses.router)


@app.get("/api/health")
def health_check():
    return {"status": "ok"}
