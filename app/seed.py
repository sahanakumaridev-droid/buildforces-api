"""Idempotent seed data for local/demo use.

Jobs are real, currently-listed California public-works postings pulled from
official agency job boards (LA County, Riverside, Orange County, Fresno,
Sacramento — all via governmentjobs.com/CalCareers). Pay, requirements, and
apply_url are copied from the live posting. We don't run our own ATS, so
"apply" always links out to the agency's official application page — these
postings can close or expire like any real job board, so this data needs
periodic refreshing, not a one-time seed. Courses mix the real programs
pulled from the reference site with a set of in-house, sub-$50 options as
requested.

Run with: python -m app.seed
"""

from datetime import datetime, timedelta

from sqlalchemy import text

from app.database import Base, SessionLocal, engine
from app.models import (
    Admin,
    Course,
    CourseSession,
    Employer,
    HouseOwner,
    Instructor,
    Job,
)
from app.security import hash_password


def ensure_schema_columns():
    """Idempotent ALTER TABLE for Phase 1 fields (safe on existing prod DBs)."""
    statements = [
        "ALTER TABLE instructors ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255)",
        "ALTER TABLE house_owners ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255)",
        "ALTER TABLE registrations ADD COLUMN IF NOT EXISTS work_authorized BOOLEAN DEFAULT FALSE",
        "ALTER TABLE registrations ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMP",
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS state VARCHAR(100)",
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS wage_type VARCHAR(20)",
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS wage_display VARCHAR(100)",
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS working_hours VARCHAR(100)",
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS job_duration VARCHAR(100)",
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS start_date TIMESTAMP",
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS end_date TIMESTAMP",
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS description TEXT",
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
    ]
    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))


def ensure_course_columns():
    ensure_schema_columns()


# Topic-matched lesson embeds (one distinct video per program — not stock fillers).
COURSE_MEDIA = {
    "Labour Skills & Safety Training": {
        "title": "Jobsite Skills & Safety Training",
        "video_url": "https://www.youtube.com/embed/lfoTLeFooR4",
        "illustration": "/illustrations/safety-training.svg",
        "image": "/programs/training-jobsite-v2.jpg",
    },
    "Jobsite Skills & Safety Training": {
        # Construction safety orientation covering PPE, tools, equipment, fall hazards
        "video_url": "https://www.youtube.com/embed/lfoTLeFooR4",
        "illustration": "/illustrations/safety-training.svg",
        "image": "/programs/training-jobsite-v2.jpg",
    },
    "Blueprint Reading & Construction Estimating": {
        "video_url": "https://www.youtube.com/embed/DSuP4YkaJ40",
        "illustration": "/illustrations/blueprint.svg",
        "image": "/programs/training-blueprint-v2.jpg",
    },
    "Heavy Equipment Operator Training": {
        "video_url": "https://www.youtube.com/embed/aoe_hMMs0DY",
        "illustration": "/illustrations/heavy-equipment.svg",
        "image": "/programs/training-heavy-v2.jpg",
    },
    "Construction Safety Fundamentals (OSHA 10 Equivalent)": {
        "title": "Construction Safety Fundamentals",
        "video_url": "https://www.youtube.com/embed/4AaDzjO887o",
        "illustration": "/illustrations/osha-safety.svg",
        "image": "/programs/training-osha-v2.jpg",
    },
    "Construction Safety Fundamentals": {
        # Introduction to OSHA / construction workplace safety
        "video_url": "https://www.youtube.com/embed/4AaDzjO887o",
        "illustration": "/illustrations/osha-safety.svg",
        "image": "/programs/training-osha-v2.jpg",
    },
    "Basic Jobsite Safety Orientation": {
        # Construction site safety induction / new-hire orientation
        "video_url": "https://www.youtube.com/embed/nybnFsIItPk",
        "illustration": "/illustrations/orientation.svg",
        "image": "/programs/training-orientation-v2.jpg",
    },
    "Hand & Power Tool Safety": {
        "video_url": "https://www.youtube.com/embed/3Ev2L3yoxpI",
        "illustration": "/illustrations/tools.svg",
        "image": "/programs/training-tools-v2.jpg",
    },
    "PPE & Hazard Awareness": {
        "video_url": "https://www.youtube.com/embed/4nRQBL1-bUo",
        "illustration": "/illustrations/ppe.svg",
        "image": "/programs/training-ppe-v2.jpg",
    },
    "Ladder & Fall Prevention Basics": {
        "video_url": "https://www.youtube.com/embed/Rcwwi7JVA5M",
        "illustration": "/illustrations/ladder.svg",
        "image": "/programs/training-ladder-v2.jpg",
    },
}

STANDARD_COURSES = [
    {
        "title": "Jobsite Skills & Safety Training",
        "description": "Practical knowledge, technical skills, and professional habits needed to work safely and efficiently on construction sites.",
        "fee": 50,
        "duration": "12 hours",
        "level": "Intermediate",
        "category": "standard",
        "provider": "Buildforces Partner Network",
        "location": "California",
        "image": "/images/jobs-hero.jpg",
        "outcomes": "Proper manual handling and safe tool operation\nPPE selection, use, and hazard identification\nEmergency response and fire safety awareness\nWorkplace ethics, attendance, and quality standards",
    },
    {
        "title": "Blueprint Reading & Construction Estimating",
        "description": "Read architectural and structural blueprints, take accurate field measurements, and produce reliable estimates.",
        "fee": 84,
        "duration": "10 hours",
        "level": "Intermediate",
        "category": "standard",
        "provider": "Buildforces Partner Network",
        "location": "Los Angeles",
        "image": "/programs/heavy-equipment.jpg",
        "outcomes": "Read architectural and structural drawings\nTake accurate field measurements\nProduce material and labor cost estimates\nSpot discrepancies between plans and site conditions",
    },
    {
        "title": "Heavy Equipment Operator Training",
        "description": "Hands-on instruction on safe operation of excavators, loaders, and compactors.",
        "fee": 50,
        "duration": "5 Weeks",
        "level": "Beginner",
        "category": "standard",
        "provider": "Buildforces Partner Network",
        "location": "Los Angeles",
        "image": "/programs/blueprint-estimating.jpg",
        "outcomes": "Pre-operation inspection and safety checks\nSafe operation of excavators, loaders, and compactors\nSite hazard awareness around heavy equipment\nIndustry-standard operating procedures",
    },
    {
        "title": "Construction Safety Fundamentals",
        "description": "Foundational safety course covering fall protection, electrical hazards, scaffolding, and PPE.",
        "fee": 50,
        "duration": "13 hours",
        "level": "Beginner",
        "category": "standard",
        "provider": "Buildforces Partner Network",
        "location": "Sacramento",
        "image": "/programs/safety-fundamentals.jpg",
        "outcomes": "Fall protection fundamentals\nElectrical hazard awareness\nScaffolding safety basics\nPPE requirements on active job sites",
    },
]

IN_HOUSE_COURSES = [
    {
        "title": "Basic Jobsite Safety Orientation",
        "description": "A short, affordable orientation covering site hazards, PPE basics, and emergency procedures.",
        "fee": 25,
        "duration": "4 hours",
        "level": "Beginner",
        "category": "in_house",
        "provider": "Buildforces Training",
        "location": "California (online)",
        "image": None,
        "outcomes": "Identify common jobsite hazards\nBasic PPE selection and use\nWhat to do in a jobsite emergency",
    },
    {
        "title": "Hand & Power Tool Safety",
        "description": "Safe operation and maintenance of common hand and power tools used on job sites.",
        "fee": 30,
        "duration": "6 hours",
        "level": "Beginner",
        "category": "in_house",
        "provider": "Buildforces Training",
        "location": "California (online)",
        "image": None,
        "outcomes": "Safe operation of common hand and power tools\nRoutine tool maintenance and inspection\nRecognizing and reporting damaged equipment",
    },
    {
        "title": "PPE & Hazard Awareness",
        "description": "Personal protective equipment selection, use, and hazard identification fundamentals.",
        "fee": 20,
        "duration": "3 hours",
        "level": "Beginner",
        "category": "in_house",
        "provider": "Buildforces Training",
        "location": "California (online)",
        "image": None,
        "outcomes": "Selecting the right PPE for the task\nProper fit and wear of protective equipment\nHazard identification fundamentals",
    },
    {
        "title": "Ladder & Fall Prevention Basics",
        "description": "Core fall-prevention practices for ladder, scaffold, and elevated work.",
        "fee": 35,
        "duration": "5 hours",
        "level": "Beginner",
        "category": "in_house",
        "provider": "Buildforces Training",
        "location": "California (online)",
        "image": None,
        "outcomes": "Safe ladder setup and use\nFall-prevention practices for elevated work\nScaffold safety fundamentals",
    },
]

JOBS = [
    dict(title="Public Works Laborer, Temporary", agency="Los Angeles County Department of Public Works",
         trade_category="earth-work-excavation",
         skills="Underground Laborer,Utility Laborer,Trench Laborer,Traffic Control Laborer",
         city="Los Angeles", zip_code="90012",
         pay_min=23.52, pay_max=26.93, employment_type="Temporary", min_experience_years=0,
         summary="Entry-level manual labor on county road, sewer, and flood-control projects — breaking concrete, digging trenches, and prepping job sites. No prior experience required; open to the general public.",
         apply_url="https://www.governmentjobs.com/careers/lacounty/jobs/4111152"),
    dict(title="Cement and Concrete Finisher", agency="Los Angeles County Internal Services Department",
         trade_category="concrete",
         skills="Cement Mason,Concrete Finisher,Concrete Laborer",
         city="Los Angeles", zip_code="90012",
         pay_min=34.39, pay_max=34.39, employment_type="Full-time", min_experience_years=3,
         summary="Journey-level concrete work on county facilities — forming, pouring, and finishing concrete to grade, plus laying out and placing reinforcing steel.",
         apply_url="https://www.governmentjobs.com/careers/lacounty/jobs/2118826"),
    dict(title="Traffic Signal Electrician, Public Works", agency="Los Angeles County Department of Public Works",
         trade_category="traffic-signal-electrical",
         skills="Traffic Signal Electrician,Journeyman Electrician,Signal Technician,Cabinet Technician",
         city="Los Angeles", zip_code="90012",
         pay_min=52.03, pay_max=52.03, employment_type="Full-time", min_experience_years=4,
         summary="Install, maintain, and repair traffic signal systems and highway lighting across LA County while supervising technician crews, per National Electrical Code standards.",
         apply_url="https://www.governmentjobs.com/careers/lacounty/jobs/4247268"),
    dict(title="Utilities Welder/Pipe Fitter", agency="City of Riverside Public Utilities Department",
         trade_category="sewer-storm-water",
         skills="Water Pipe Layer,Waterline Foreman,Valve Installer,Testing / Chlorination Technician",
         city="Riverside", zip_code="92501",
         pay_min=29.03, pay_max=35.30, employment_type="Full-time", min_experience_years=3,
         summary="Skilled welding and pipefitting for water system construction — building pump stations, welding pipelines, and installing water services, with emergency on-call response.",
         apply_url="https://www.governmentjobs.com/careers/cityofriversideca/jobs/624322"),
    dict(title="Equipment Welder", agency="Orange County Public Works",
         trade_category="metal-fabrication",
         skills="Welder,Fabricator",
         city="Santa Ana", zip_code="92701",
         pay_min=27.77, pay_max=33.50, employment_type="Full-time", min_experience_years=4,
         summary="Journey-level arc/stick, MIG, and TIG welding plus plasma cutting to fabricate and repair heavy equipment and vehicles for OC Public Works and Fleet Services.",
         apply_url="https://www.governmentjobs.com/careers/oc/jobs/2390077"),
    dict(title="Traffic Maintenance Worker I", agency="City of Fresno Public Works Department",
         trade_category="thermoplastic-striping",
         skills="Striping Laborer,Traffic Control Laborer,Pre-marker / Layout Worker,Handliner Operator",
         city="Fresno", zip_code="93701",
         pay_min=22.45, pay_max=27.27, employment_type="Full-time", min_experience_years=0,
         summary="Entry-level position fabricating, assembling, and installing traffic control signs and pavement markings on city streets.",
         apply_url="https://www.governmentjobs.com/careers/cityoffresno/jobs/5112031"),
    dict(title="Utilities Operations & Maintenance Serviceworker Apprentice", agency="City of Sacramento Utilities Department",
         trade_category="sewer-storm-water",
         skills="Pipe Layer Helper,Underground Laborer,Testing Technician",
         city="Sacramento", zip_code="95814",
         pay_min=20.41, pay_max=24.75, employment_type="Full-time", min_experience_years=0,
         summary="Two-year paid apprenticeship learning to install, maintain, and repair water distribution, wastewater collection, and storm drainage systems.",
         apply_url="https://www.governmentjobs.com/careers/saccity/jobs/3513968"),
]


def seed():
    Base.metadata.create_all(bind=engine)
    ensure_course_columns()
    db = SessionLocal()
    try:
        existing_courses = db.query(Course).count()
        if existing_courses == 0:
            for c in [*STANDARD_COURSES, *IN_HOUSE_COURSES]:
                media = COURSE_MEDIA.get(c["title"], {})
                payload = {**c, **{k: v for k, v in media.items() if k != "title"}}
                if media.get("title"):
                    payload["title"] = media["title"]
                db.add(Course(**payload))
            print(f"Seeded {len(STANDARD_COURSES) + len(IN_HOUSE_COURSES)} courses.")
        else:
            print(f"{existing_courses} courses already present, updating media.")
            for course in db.query(Course).all():
                media = COURSE_MEDIA.get(course.title)
                if not media:
                    continue
                if media.get("title"):
                    course.title = media["title"]
                course.video_url = media.get("video_url") or course.video_url
                course.illustration = media.get("illustration") or course.illustration
                if media.get("image"):
                    course.image = media["image"]

        if db.query(Job).count() == 0:
            for j in JOBS:
                db.add(Job(**j))
            print(f"Seeded {len(JOBS)} jobs.")
        else:
            print("Jobs already seeded, skipping.")

        admin_email = "admin@buildforces.com"
        admin_password = "Admin123!"
        existing_admin = db.query(Admin).filter(Admin.email == admin_email).first()
        if not existing_admin:
            db.add(
                Admin(
                    full_name="Buildforces Admin",
                    email=admin_email,
                    password_hash=hash_password(admin_password),
                    is_active=True,
                )
            )
            print(f"Seeded default admin ({admin_email} / {admin_password}).")
        else:
            existing_admin.full_name = "Buildforces Admin"
            existing_admin.password_hash = hash_password(admin_password)
            existing_admin.is_active = True
            print(f"Ensured fixed admin credentials ({admin_email} / {admin_password}).")

        if db.query(Instructor).count() == 0:
            for row in [
                ("Maya Chen", "maya.chen@buildforces.com", "Jobsite Safety", "Los Angeles"),
                ("Diego Alvarez", "diego.alvarez@buildforces.com", "Heavy Equipment", "Sacramento"),
                ("Priya Nair", "priya.nair@buildforces.com", "Blueprint & Estimating", "San Diego"),
            ]:
                db.add(
                    Instructor(
                        full_name=row[0],
                        email=row[1],
                        specialty=row[2],
                        city=row[3],
                        password_hash=hash_password("Instructor123!"),
                    )
                )
            print("Seeded instructors.")
        else:
            for instructor in db.query(Instructor).filter(Instructor.password_hash.is_(None)).all():
                instructor.password_hash = hash_password("Instructor123!")
            print("Ensured instructor login passwords.")

        if db.query(HouseOwner).count() == 0:
            for row in [
                ("Elena Brooks", "elena.brooks@email.com", "Irvine", 2),
                ("Marcus Lee", "marcus.lee@email.com", "Oakland", 1),
                ("Sofia Patel", "sofia.patel@email.com", "Fresno", 3),
            ]:
                db.add(
                    HouseOwner(
                        full_name=row[0],
                        email=row[1],
                        city=row[2],
                        project_count=row[3],
                        password_hash=hash_password("Homeowner123!"),
                    )
                )
            print("Seeded house owners.")
        else:
            for owner in db.query(HouseOwner).filter(HouseOwner.password_hash.is_(None)).all():
                owner.password_hash = hash_password("Homeowner123!")
            print("Ensured homeowner login passwords.")

        if db.query(Employer).count() == 0:
            db.add(
                Employer(
                    company_name="Pacific Crest Builders",
                    email="hiring@pacificcrest.demo",
                    password_hash=hash_password("Employer123!"),
                )
            )
            db.add(
                Employer(
                    company_name="Bay Area Civil Works",
                    email="crew@baycivil.demo",
                    password_hash=hash_password("Employer123!"),
                )
            )
            print("Seeded sample employers.")

        if db.query(CourseSession).count() == 0:
            courses = db.query(Course).order_by(Course.id.asc()).all()
            now = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
            for index, course in enumerate(courses):
                for week in range(1, 5):
                    start = now + timedelta(days=week * 3 + index, hours=9 + (index % 3))
                    db.add(
                        CourseSession(
                            course_id=course.id,
                            title=f"{course.title} — Session {week}",
                            starts_at=start,
                            ends_at=start + timedelta(hours=3),
                            location=course.location,
                            seats_left=8 + ((index + week) % 10),
                        )
                    )
            print("Seeded course sessions.")
        else:
            print("Course sessions already present, skipping.")

        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    seed()
