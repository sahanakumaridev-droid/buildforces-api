from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ContactMessage(Base):
    __tablename__ = "contact_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(255))
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    topic: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Registration(Base):
    __tablename__ = "registrations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    phone: Mapped[str] = mapped_column(String(50))
    password_hash: Mapped[str] = mapped_column(String(255))

    language: Mapped[str] = mapped_column(String(10))
    zip_code: Mapped[str] = mapped_column(String(20))
    # State/county are no longer collected from the user — derived server-side from zip_code.
    state: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    county: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    promo_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    skill_level: Mapped[str] = mapped_column(String(50))
    experience: Mapped[str] = mapped_column(String(20))
    work_authorized: Mapped[bool] = mapped_column(Boolean, default=False)
    agreed_to_terms: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    trades: Mapped[list["RegistrationTrade"]] = relationship(
        back_populates="registration", cascade="all, delete-orphan"
    )
    documents: Mapped[list["Document"]] = relationship(
        back_populates="registration", cascade="all, delete-orphan"
    )


class RegistrationTrade(Base):
    __tablename__ = "registration_trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    registration_id: Mapped[int] = mapped_column(ForeignKey("registrations.id"))
    category: Mapped[str] = mapped_column(String(100))
    trade_name: Mapped[str] = mapped_column(String(150))

    registration: Mapped["Registration"] = relationship(back_populates="trades")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    registration_id: Mapped[int] = mapped_column(ForeignKey("registrations.id"))
    doc_type: Mapped[str] = mapped_column(String(50))
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    registration: Mapped["Registration"] = relationship(back_populates="documents")


class Admin(Base):
    __tablename__ = "admins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), index=True)
    role: Mapped[str] = mapped_column(String(20))  # "labor" | "admin"
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Employer(Base):
    __tablename__ = "employers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    agency: Mapped[str] = mapped_column(String(200))
    trade_category: Mapped[str] = mapped_column(String(100))
    skills: Mapped[str] = mapped_column(Text)  # comma-separated keywords
    city: Mapped[str] = mapped_column(String(100))
    zip_code: Mapped[str] = mapped_column(String(20))
    pay_min: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    pay_max: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    employment_type: Mapped[str] = mapped_column(String(50))
    min_experience_years: Mapped[int] = mapped_column(Integer, default=0)
    summary: Mapped[str] = mapped_column(Text)
    posted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Link to the real hiring agency's application page — we don't run our own ATS,
    # so applying always happens on the agency's official site.
    apply_url: Mapped[str] = mapped_column(String(500), default="")

    # Phase 1 admin job fields (nullable so seeded public-works rows stay valid)
    state: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    wage_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # hourly|daily|weekly|monthly|annual
    wage_display: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # e.g. "$35/hour"
    working_hours: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    job_duration: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    start_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    end_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    attachments: Mapped[list["JobAttachment"]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="JobAttachment.created_at",
    )


class JobAttachment(Base):
    __tablename__ = "job_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    # image | video | pdf | file
    file_kind: Mapped[str] = mapped_column(String(20), default="file")
    title: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_filename: Mapped[str] = mapped_column(String(255))
    file_url: Mapped[str] = mapped_column(String(500))
    mime_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    job: Mapped["Job"] = relationship(back_populates="attachments")


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    fee: Mapped[float] = mapped_column(Numeric(10, 2))
    duration: Mapped[str] = mapped_column(String(50))
    level: Mapped[str] = mapped_column(String(50))
    category: Mapped[str] = mapped_column(String(20))  # "standard" | "in_house"
    provider: Mapped[str] = mapped_column(String(150))
    location: Mapped[str] = mapped_column(String(100))
    image: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    outcomes: Mapped[str] = mapped_column(Text, default="")  # newline-separated "what you'll learn" bullets
    video_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    illustration: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Phase 1 certification / course management fields
    trade: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    introduction: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    course_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    delivery_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # onsite|online|hybrid
    content_pattern: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # video|audio|reading
    physical_location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    online_info: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_published: Mapped[bool] = mapped_column(Boolean, default=True)

    sessions: Mapped[list["CourseSession"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )
    enrollments: Mapped[list["Enrollment"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )
    modules: Mapped[list["CourseModule"]] = relationship(
        back_populates="course",
        cascade="all, delete-orphan",
        order_by="CourseModule.sort_order",
    )
    certificates: Mapped[list["Certificate"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )


class CourseModule(Base):
    __tablename__ = "course_modules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reading_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    course: Mapped["Course"] = relationship(back_populates="modules")
    contents: Mapped[list["CourseContent"]] = relationship(
        back_populates="module",
        cascade="all, delete-orphan",
        order_by="CourseContent.sort_order",
    )


class CourseContent(Base):
    __tablename__ = "course_contents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    module_id: Mapped[int] = mapped_column(ForeignKey("course_modules.id"), index=True)
    # video | audio | pdf | slides | reading
    content_kind: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    file_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    original_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    stored_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    module: Mapped["CourseModule"] = relationship(back_populates="contents")


class Certificate(Base):
    __tablename__ = "certificates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    registration_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("registrations.id"), nullable=True, index=True
    )
    title: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    file_url: Mapped[str] = mapped_column(String(500))
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    uploaded_by_admin_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("admins.id"), nullable=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    course: Mapped["Course"] = relationship(back_populates="certificates")
    registration: Mapped[Optional["Registration"]] = relationship()


class CourseSession(Base):
    __tablename__ = "course_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    title: Mapped[str] = mapped_column(String(200), default="Live session")
    starts_at: Mapped[datetime] = mapped_column(DateTime)
    ends_at: Mapped[datetime] = mapped_column(DateTime)
    location: Mapped[str] = mapped_column(String(200), default="")
    seats_left: Mapped[int] = mapped_column(Integer, default=12)

    course: Mapped["Course"] = relationship(back_populates="sessions")


class Enrollment(Base):
    __tablename__ = "enrollments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    registration_id: Mapped[int] = mapped_column(ForeignKey("registrations.id"), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="purchased")  # purchased | pending
    enrolled_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    course: Mapped["Course"] = relationship(back_populates="enrollments")


class Instructor(Base):
    __tablename__ = "instructors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    specialty: Mapped[str] = mapped_column(String(150))
    city: Mapped[str] = mapped_column(String(100), default="California")
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class HouseOwner(Base):
    __tablename__ = "house_owners"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    city: Mapped[str] = mapped_column(String(100), default="")
    project_count: Mapped[int] = mapped_column(Integer, default=0)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)