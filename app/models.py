from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
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
    state: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    county: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    promo_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    skill_level: Mapped[str] = mapped_column(String(50))
    experience: Mapped[str] = mapped_column(String(20))
    agreed_to_terms: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    trades: Mapped[list["RegistrationTrade"]] = relationship(
        back_populates="registration", cascade="all, delete-orphan"
    )


class RegistrationTrade(Base):
    __tablename__ = "registration_trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    registration_id: Mapped[int] = mapped_column(ForeignKey("registrations.id"))
    category: Mapped[str] = mapped_column(String(100))
    trade_name: Mapped[str] = mapped_column(String(150))

    registration: Mapped["Registration"] = relationship(back_populates="trades")
