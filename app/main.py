import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy import text

from app.database import Base, engine
from app.routers import admin, auth, contact, courses, documents, employers, jobs, register

load_dotenv()

Base.metadata.create_all(bind=engine)


def _ensure_auth_columns() -> None:
    """Add login columns for instructor/homeowner portals without a full migration tool."""
    statements = [
        "ALTER TABLE instructors ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255)",
        "ALTER TABLE house_owners ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255)",
        "ALTER TABLE registrations ADD COLUMN IF NOT EXISTS work_authorized BOOLEAN DEFAULT FALSE",
        "ALTER TABLE registrations ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMP",
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

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(contact.router)
app.include_router(register.router)
app.include_router(documents.router)
app.include_router(employers.router)
app.include_router(jobs.router)
app.include_router(courses.router)


@app.get("/api/health")
def health_check():
    return {"status": "ok"}
