# app/models/donation.py
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, func, ForeignKey, Float, Enum, JSON
from sqlalchemy.orm import relationship
import uuid
from models.base import Base


class Donation(Base):
    __tablename__ = "donations"

    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))

    # اطلاعات پرداخت
    amount = Column(Float, nullable=False)
    currency = Column(String(3), default="IRR")
    payment_method = Column(
        Enum("direct_transfer", "court", "digital_wallet", "bank_gateway", "product_sale",
             name="payment_method")
    )

    # وضعیت
    status = Column(
        Enum("pending", "processing", "completed", "failed", "refunded", name="donation_status"),
        default="pending"
    )

    # اطلاعات پرداخت
    transaction_id = Column(String(255))  # شماره تراکنش بانکی
    tracking_code = Column(String(100))  # کد رهگیری داخلی
    receipt_number = Column(String(100))  # شماره رسید مالیاتی

    # مکان و زمان
    donor_ip = Column(String(45))
    donor_user_agent = Column(Text)

    # Foreign Keys
    donor_id = Column(Integer, ForeignKey("users.id"))
    need_id = Column(Integer, ForeignKey("need_ads.id"))
    charity_id = Column(Integer, ForeignKey("charities.id"))
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    donor = relationship("User", foreign_keys=[donor_id])
    need = relationship("NeedAd", back_populates="donations")
    charity = relationship("Charity", back_populates="donations")
    product = relationship("Product", back_populates="donations")