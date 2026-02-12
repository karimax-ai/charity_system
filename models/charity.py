# app/models/charity.py
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, func, ForeignKey, Float, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import uuid
from models.base import Base


class Charity(Base):
    __tablename__ = "charities"

    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    name = Column(String(200), nullable=False)
    description = Column(Text)
    logo_url = Column(String(500))
    website = Column(String(500))
    phone = Column(String(20))
    email = Column(String(255))
    address = Column(Text)
    registration_number = Column(String(100))  # شماره ثبت خیریه
    verified = Column(Boolean, default=False)
    active = Column(Boolean, default=True)

    # مدیر خیریه (User)
    manager_id = Column(Integer, ForeignKey("users.id"))
    manager = relationship(
        "User",
        backref="managed_charities",
        foreign_keys=[manager_id],
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    needs = relationship("NeedAd", back_populates="charity")
    donations = relationship("Donation", back_populates="charity")
    products = relationship("Product", back_populates="charity")
    verifications = relationship(
        "NeedVerification",
        back_populates="charity",
        cascade="all, delete-orphan",
    )

