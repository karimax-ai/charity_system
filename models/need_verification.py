import enum
from sqlalchemy import Column, Integer, ForeignKey, Enum, Text, DateTime, func
from sqlalchemy.orm import relationship

from models.base import Base


class VerificationStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class NeedVerification(Base):
    __tablename__ = "need_verifications"

    id = Column(Integer, primary_key=True)

    need_id = Column(
        Integer,
        ForeignKey("need_ads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    charity_id = Column(
        Integer,
        ForeignKey("charities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    status = Column(
        Enum(VerificationStatus, name="verification_status"),
        default=VerificationStatus.PENDING,
        nullable=False,
    )

    comment = Column(Text, nullable=True)

    verified_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # relationships
    need = relationship("NeedAd", back_populates="verifications")
    charity = relationship("Charity", back_populates="verifications")
