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


class RegistrationCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    phone: str = Field(min_length=1)
    password: str = Field(min_length=6)

    language: str
    zip_code: str = Field(min_length=1)
    state: Optional[str] = None
    county: Optional[str] = None
    promo_code: Optional[str] = None

    trades: List[SelectedTrade] = Field(min_length=1)

    skill_level: str
    experience: str
    agreed_to_terms: bool

    @field_validator("agreed_to_terms")
    @classmethod
    def must_agree_to_terms(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Terms and Privacy Policy must be accepted.")
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
    created_at: datetime

    class Config:
        from_attributes = True
