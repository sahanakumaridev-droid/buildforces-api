from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


class ContactMessageCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    phone: Optional[str] = None
    topic: Optional[str] = None
    message: str = Field(min_length=1)


class ContactMessageOut(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    phone: Optional[str]
    topic: Optional[str]
    message: str
    created_at: datetime

    class Config:
        from_attributes = True


class SelectedTrade(BaseModel):
    category: str
    trade_name: str

    class Config:
        from_attributes = True


class RegistrationCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    phone: str = Field(min_length=1)
    password: str = Field(min_length=6)

    language: str
    zip_code: str = Field(min_length=1)
    promo_code: Optional[str] = None

    trades: List[SelectedTrade] = Field(min_length=1)

    skill_level: str
    experience: str
    work_authorized: bool
    agreed_to_terms: bool

    @field_validator("agreed_to_terms")
    @classmethod
    def must_agree_to_terms(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Terms and Privacy Policy must be accepted.")
        return value

    @field_validator("work_authorized")
    @classmethod
    def must_be_work_authorized(cls, value: bool) -> bool:
        if not value:
            raise ValueError("You must be authorized to work in the USA to register.")
        return value


class RegistrationOut(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    phone: str
    language: str
    zip_code: str
    state: Optional[str]
    county: Optional[str]
    skill_level: str
    experience: str
    work_authorized: bool = False
    created_at: datetime

    class Config:
        from_attributes = True


class RegistrationLookup(BaseModel):
    email: EmailStr
    password: str


class DocumentOut(BaseModel):
    id: int
    doc_type: str
    original_filename: str
    uploaded_at: datetime

    class Config:
        from_attributes = True


class RegistrationDetail(RegistrationOut):
    trades: List[SelectedTrade]
    documents: List[DocumentOut] = []


class RegistrationAuthResponse(BaseModel):
    token: str
    registration: RegistrationDetail


class GoogleAuthRequest(BaseModel):
    access_token: str = Field(min_length=1)
    phone: Optional[str] = None
    language: str = "en"
    zip_code: str = Field(min_length=1)
    trades: List[SelectedTrade] = Field(min_length=1)
    skill_level: str
    experience: str


class EmployerCreate(BaseModel):
    company_name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    password: str = Field(min_length=6)


class EmployerLogin(BaseModel):
    email: EmailStr
    password: str


class EmployerOut(BaseModel):
    id: int
    company_name: str
    email: EmailStr
    created_at: datetime
    is_blocked: bool = False
    is_verified: bool = False
    rank_label: Optional[str] = None

    class Config:
        from_attributes = True


class EmployerAuthResponse(BaseModel):
    token: str
    employer: EmployerOut


class EmployerOverviewOut(BaseModel):
    company_name: str
    email: EmailStr
    on_site: int = 0
    reports_today: int = 0
    tasks: int = 0
    open_cpm: int = 0
    is_verified: bool = False
    rank_label: Optional[str] = None
    labour_active: int = 0
    enrollments: int = 0
    certificates: int = 0


class EmployerReportOut(BaseModel):
    company_name: str
    period_label: str
    generated_at: datetime
    labour_active: int
    enrolments: int
    certificates_issued: int
    jobs_active: int
    applications: int
    rows: List[dict]


class AdminOut(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    created_at: datetime

    class Config:
        from_attributes = True


class DemoOtpLogin(BaseModel):
    phone: str
    code: str
    role: str = "labor"


class AuthLogin(BaseModel):
    email: EmailStr
    password: str


class AdminRegister(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    password: str = Field(min_length=6)
    invite_code: str = Field(min_length=1, max_length=100)


class InstructorRegister(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    password: str = Field(min_length=6)
    specialty: str = Field(min_length=1, max_length=150)
    city: str = Field(min_length=1, max_length=100)


class HomeownerRegister(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    password: str = Field(min_length=6)
    city: str = Field(min_length=1, max_length=100)
    zip_code: str = Field(default="", max_length=20)


class AuthUserOut(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    role: str


class AuthResponse(BaseModel):
    token: str
    role: str
    user: AuthUserOut


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    message: str
    reset_url: Optional[str] = None
    email_sent: bool = False


class ResetPasswordRequest(BaseModel):
    token: str
    password: str = Field(min_length=6)


class LaborNotificationOut(BaseModel):
    id: int
    title: str
    body: str
    kind: str
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True


class LaborMessageOut(BaseModel):
    id: int
    peer_name: str
    peer_role: str
    subject: str
    body: str
    direction: str
    created_at: datetime

    class Config:
        from_attributes = True


class LaborMessageCreate(BaseModel):
    peer_name: str = Field(default="BUILD FORCES Support", max_length=200)
    subject: str = Field(default="", max_length=200)
    body: str = Field(min_length=1)


class MemberReminderIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(default="", max_length=4000)


class CompanyFlagIn(BaseModel):
    blocked: Optional[bool] = None
    verified: Optional[bool] = None
    rank_label: Optional[str] = None


class CompanyReviewOut(BaseModel):
    id: int
    employer_id: int
    company_name: Optional[str] = None
    author_name: str
    rating: int
    body: str
    status: str
    created_at: datetime


class CompanyReviewStatusIn(BaseModel):
    status: str = Field(pattern="^(pending|approved|rejected)$")


class InstructorAdminCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    password: str = Field(min_length=6)
    specialty: str = Field(default="General", max_length=150)
    city: str = Field(default="California", max_length=100)


class InstructorAdminUpdate(BaseModel):
    full_name: Optional[str] = None
    specialty: Optional[str] = None
    city: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=6)


class CourseInstructorIn(BaseModel):
    instructor_id: Optional[int] = None


class CertificateGenerateIn(BaseModel):
    course_id: int
    registration_id: int
    title: Optional[str] = None
    notes: Optional[str] = None


class JobAttachmentOut(BaseModel):
    id: int
    job_id: int
    file_kind: str = "file"
    title: Optional[str] = None
    original_filename: str
    stored_filename: str = ""
    file_url: str
    mime_type: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class JobAttachmentCreate(BaseModel):
    title: Optional[str] = None
    file_url: str
    original_filename: str
    stored_filename: Optional[str] = None
    mime_type: Optional[str] = None
    file_kind: Optional[str] = None


class JobOut(BaseModel):
    id: int
    title: str
    agency: str
    trade_category: str
    skills: List[str]
    city: str
    zip_code: str
    pay_min: Optional[float]
    pay_max: Optional[float]
    employment_type: str
    min_experience_years: int
    summary: str
    posted_at: datetime
    apply_url: str
    match_score: Optional[float] = None
    matched_skills: Optional[List[str]] = None
    state: Optional[str] = None
    wage_type: Optional[str] = None
    wage_display: Optional[str] = None
    working_hours: Optional[str] = None
    job_duration: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    description: Optional[str] = None
    is_active: bool = True
    attachments: List[JobAttachmentOut] = []
    house_owner_id: Optional[int] = None
    project_status: Optional[str] = None
    timeline: Optional[str] = None
    cancel_reason: Optional[str] = None
    contact_phone: Optional[str] = None
    applicant_count: int = 0

    class Config:
        from_attributes = True


class JobCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    trade_category: str = Field(min_length=1, max_length=100)
    summary: str = Field(min_length=1)
    description: Optional[str] = None
    city: str = Field(min_length=1, max_length=100)
    state: Optional[str] = Field(default=None, max_length=100)
    zip_code: str = Field(default="", max_length=20)
    wage_display: Optional[str] = Field(default=None, max_length=100)
    wage_type: Optional[str] = Field(default="hourly", max_length=20)
    pay_min: Optional[float] = None
    pay_max: Optional[float] = None
    working_hours: Optional[str] = Field(default=None, max_length=100)
    job_duration: Optional[str] = Field(default=None, max_length=100)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    employment_type: str = Field(default="Full-time", max_length=50)
    agency: str = Field(default="Buildforces", max_length=200)
    skills: List[str] = []
    min_experience_years: int = 0
    apply_url: str = ""
    is_active: bool = True
    attachments: List[JobAttachmentCreate] = []


class JobUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    trade_category: Optional[str] = Field(default=None, min_length=1, max_length=100)
    summary: Optional[str] = None
    description: Optional[str] = None
    city: Optional[str] = Field(default=None, max_length=100)
    state: Optional[str] = Field(default=None, max_length=100)
    zip_code: Optional[str] = Field(default=None, max_length=20)
    wage_display: Optional[str] = Field(default=None, max_length=100)
    wage_type: Optional[str] = Field(default=None, max_length=20)
    pay_min: Optional[float] = None
    pay_max: Optional[float] = None
    working_hours: Optional[str] = Field(default=None, max_length=100)
    job_duration: Optional[str] = Field(default=None, max_length=100)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    employment_type: Optional[str] = Field(default=None, max_length=50)
    agency: Optional[str] = Field(default=None, max_length=200)
    skills: Optional[List[str]] = None
    min_experience_years: Optional[int] = None
    apply_url: Optional[str] = None
    is_active: Optional[bool] = None


class CourseSessionOut(BaseModel):
    id: int
    course_id: int
    title: str
    starts_at: datetime
    ends_at: datetime
    location: str
    seats_left: int
    course_title: Optional[str] = None
    course_image: Optional[str] = None

    class Config:
        from_attributes = True


class CourseContentOut(BaseModel):
    id: int
    module_id: int
    content_kind: str
    title: str
    description: Optional[str] = None
    file_url: Optional[str] = None
    original_filename: Optional[str] = None
    mime_type: Optional[str] = None
    sort_order: int = 0
    created_at: datetime

    class Config:
        from_attributes = True


class CourseModuleOut(BaseModel):
    id: int
    course_id: int
    title: str
    description: Optional[str] = None
    reading_content: Optional[str] = None
    sort_order: int = 0
    contents: List[CourseContentOut] = []

    class Config:
        from_attributes = True


class CourseOut(BaseModel):
    id: int
    title: str
    description: str
    fee: float
    duration: str
    level: str
    category: str
    provider: str
    location: str
    image: Optional[str]
    outcomes: List[str]
    video_url: Optional[str] = None
    illustration: Optional[str] = None
    purchased: bool = False
    sessions: List[CourseSessionOut] = []
    trade: Optional[str] = None
    introduction: Optional[str] = None
    course_date: Optional[datetime] = None
    delivery_type: Optional[str] = None
    content_pattern: Optional[str] = None
    physical_location: Optional[str] = None
    online_info: Optional[str] = None
    is_published: bool = True
    modules: List[CourseModuleOut] = []

    class Config:
        from_attributes = True


class CourseCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    trade: Optional[str] = Field(default=None, max_length=150)
    introduction: Optional[str] = None
    description: Optional[str] = None
    location: str = Field(default="", max_length=100)
    course_date: Optional[datetime] = None
    duration: str = Field(default="", max_length=50)
    fee: float = 0
    delivery_type: Optional[str] = Field(default="onsite", max_length=20)
    content_pattern: Optional[str] = Field(default=None, max_length=20)
    physical_location: Optional[str] = None
    online_info: Optional[str] = None
    level: str = Field(default="Beginner", max_length=50)
    category: str = Field(default="in_house", max_length=20)
    provider: str = Field(default="Buildforces", max_length=150)
    outcomes: List[str] = []
    image: Optional[str] = None
    video_url: Optional[str] = None
    is_published: bool = True


class CourseUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    trade: Optional[str] = Field(default=None, max_length=150)
    introduction: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = Field(default=None, max_length=100)
    course_date: Optional[datetime] = None
    duration: Optional[str] = Field(default=None, max_length=50)
    fee: Optional[float] = None
    delivery_type: Optional[str] = Field(default=None, max_length=20)
    content_pattern: Optional[str] = Field(default=None, max_length=20)
    physical_location: Optional[str] = None
    online_info: Optional[str] = None
    level: Optional[str] = Field(default=None, max_length=50)
    category: Optional[str] = Field(default=None, max_length=20)
    provider: Optional[str] = Field(default=None, max_length=150)
    outcomes: Optional[List[str]] = None
    image: Optional[str] = None
    video_url: Optional[str] = None
    is_published: Optional[bool] = None


class CourseModuleCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    reading_content: Optional[str] = None
    sort_order: Optional[int] = None


class CourseModuleUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    reading_content: Optional[str] = None
    sort_order: Optional[int] = None


class ModuleReorderItem(BaseModel):
    id: int
    sort_order: int


class ModuleReorderPayload(BaseModel):
    modules: List[ModuleReorderItem]


class CourseContentCreate(BaseModel):
    content_kind: str = Field(min_length=1, max_length=20)
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    file_url: Optional[str] = None
    original_filename: Optional[str] = None
    stored_filename: Optional[str] = None
    mime_type: Optional[str] = None
    sort_order: Optional[int] = None


class CourseContentUpdate(BaseModel):
    content_kind: Optional[str] = Field(default=None, max_length=20)
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    file_url: Optional[str] = None
    original_filename: Optional[str] = None
    stored_filename: Optional[str] = None
    mime_type: Optional[str] = None
    sort_order: Optional[int] = None


class CertificateOut(BaseModel):
    id: int
    course_id: int
    course_title: Optional[str] = None
    registration_id: Optional[int] = None
    member_name: Optional[str] = None
    member_email: Optional[str] = None
    title: Optional[str] = None
    original_filename: str
    file_url: str
    mime_type: Optional[str] = None
    notes: Optional[str] = None
    uploaded_by_admin_id: Optional[int] = None
    uploaded_at: datetime
    verification_code: Optional[str] = None
    expires_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CertificateCreate(BaseModel):
    course_id: int
    registration_id: Optional[int] = None
    title: Optional[str] = None
    file_url: str
    original_filename: str
    stored_filename: Optional[str] = None
    mime_type: Optional[str] = None
    notes: Optional[str] = None


class CertificateUpdate(BaseModel):
    course_id: Optional[int] = None
    registration_id: Optional[int] = None
    title: Optional[str] = None
    file_url: Optional[str] = None
    original_filename: Optional[str] = None
    stored_filename: Optional[str] = None
    mime_type: Optional[str] = None
    notes: Optional[str] = None


class MediaUploadOut(BaseModel):
    file_url: str
    original_filename: str
    stored_filename: str
    mime_type: Optional[str] = None
    size_bytes: int


class EnrollmentOut(BaseModel):
    id: int
    course_id: int
    status: str
    enrolled_at: datetime
    course: CourseOut
    progress_pct: int = 0
    grade: Optional[str] = None

    class Config:
        from_attributes = True


class AdminStatsOut(BaseModel):
    members: int
    instructors: int
    house_owners: int
    employers: int
    admins: int
    courses: int
    enrollments: int
    jobs: int


class AdminMemberOut(BaseModel):
    id: int
    full_name: str
    email: str
    phone: str
    language: str
    zip_code: str
    state: Optional[str] = None
    county: Optional[str] = None
    promo_code: Optional[str] = None
    skill_level: str
    experience: str
    work_authorized: bool = False
    agreed_to_terms: bool = False
    trades: List[SelectedTrade]
    documents: List[DocumentOut] = []
    created_at: datetime
    last_login_at: Optional[datetime] = None
    is_blocked: bool = False

    class Config:
        from_attributes = True


class MemberBlockIn(BaseModel):
    blocked: bool


class AdminDirectoryUserOut(BaseModel):
    id: int
    full_name: str
    email: str
    role: str
    detail: str
    city: Optional[str] = None
    created_at: datetime
    is_active: bool = True
    is_blocked: bool = False
    is_verified: bool = False
    rank_label: Optional[str] = None


class AdminOverviewOut(BaseModel):
    stats: AdminStatsOut
    members: List[AdminMemberOut]
    instructors: List[AdminDirectoryUserOut]
    house_owners: List[AdminDirectoryUserOut]
    employers: List[AdminDirectoryUserOut]
    admins: List[AdminDirectoryUserOut]
    recent_enrollments: List[dict]


class HomeownerJobCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    trade_category: str = Field(min_length=1, max_length=100)
    summary: str = Field(min_length=1)
    description: Optional[str] = None
    city: str = Field(min_length=1, max_length=100)
    state: Optional[str] = "California"
    zip_code: str = Field(default="", max_length=20)
    budget: Optional[str] = None
    timeline: Optional[str] = None
    pay_min: Optional[float] = None
    pay_max: Optional[float] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    skills: List[str] = []
    contact_phone: Optional[str] = Field(default=None, max_length=50)


class HomeownerJobUpdate(BaseModel):
    title: Optional[str] = None
    trade_category: Optional[str] = None
    summary: Optional[str] = None
    description: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    budget: Optional[str] = None
    timeline: Optional[str] = None
    pay_min: Optional[float] = None
    pay_max: Optional[float] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    skills: Optional[List[str]] = None
    project_status: Optional[str] = None
    cancel_reason: Optional[str] = None
    contact_phone: Optional[str] = Field(default=None, max_length=50)


class ApplicantOut(BaseModel):
    id: int
    job_id: int
    status: str
    applied_at: datetime
    note: Optional[str] = None
    member_id: int
    full_name: str
    email: str
    phone: str
    zip_code: str
    skill_level: str
    experience: str
    trades: List[str] = []
    verified: bool = False
    rating: Optional[float] = None


class JobReviewIn(BaseModel):
    registration_id: int
    rating_quality: int = Field(ge=1, le=5)
    rating_punctuality: int = Field(ge=1, le=5)
    rating_professionalism: int = Field(ge=1, le=5)
    comment: str = Field(min_length=1)


class JobReviewOut(BaseModel):
    id: int
    job_id: int
    registration_id: int
    rating_quality: int
    rating_punctuality: int
    rating_professionalism: int
    comment: str
    created_at: datetime


class JobMessageIn(BaseModel):
    body: str = Field(min_length=1)


class JobMessageOut(BaseModel):
    id: int
    job_id: int
    sender_role: str
    sender_id: int
    sender_name: str
    body: str
    created_at: datetime


class HomeownerOverviewOut(BaseModel):
    active_projects: int
    open_jobs: int
    applicants: int
    completed: int
    jobs: List[JobOut]


class InstructorStudentOut(BaseModel):
    enrollment_id: int
    member_id: int
    full_name: str
    email: str
    course_id: int
    course_title: str
    status: str
    progress_pct: int
    grade: Optional[str] = None
    enrolled_at: datetime
    certificate_id: Optional[int] = None
    certificate_pending: bool = False


class InstructorOverviewOut(BaseModel):
    courses: int
    students: int
    pending_grades: int
    pending_certificates: int
    revenue: float
    sessions: int


class GradeIn(BaseModel):
    grade: str = Field(min_length=1, max_length=40)
    progress_pct: Optional[int] = Field(default=None, ge=0, le=100)