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

    class Config:
        from_attributes = True


class EmployerAuthResponse(BaseModel):
    token: str
    employer: EmployerOut


class AdminOut(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    created_at: datetime

    class Config:
        from_attributes = True


class AuthLogin(BaseModel):
    email: EmailStr
    password: str


class AdminRegister(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    password: str = Field(min_length=6)
    invite_code: str = Field(min_length=1, max_length=100)


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


class ResetPasswordRequest(BaseModel):
    token: str
    password: str = Field(min_length=6)


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

    class Config:
        from_attributes = True


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

    class Config:
        from_attributes = True


class EnrollmentOut(BaseModel):
    id: int
    course_id: int
    status: str
    enrolled_at: datetime
    course: CourseOut

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

    class Config:
        from_attributes = True


class AdminDirectoryUserOut(BaseModel):
    id: int
    full_name: str
    email: str
    role: str
    detail: str
    city: Optional[str] = None
    created_at: datetime
    is_active: bool = True


class AdminOverviewOut(BaseModel):
    stats: AdminStatsOut
    members: List[AdminMemberOut]
    instructors: List[AdminDirectoryUserOut]
    house_owners: List[AdminDirectoryUserOut]
    employers: List[AdminDirectoryUserOut]
    admins: List[AdminDirectoryUserOut]
    recent_enrollments: List[dict]