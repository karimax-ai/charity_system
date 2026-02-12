from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, func, ForeignKey, JSON, Enum
from sqlalchemy.orm import relationship
import uuid

from models.base import Base
from models.association_tables import shop_vendors


class Shop(Base):
    __tablename__ = "shops"

    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))

    name = Column(String(200), nullable=False)
    description = Column(Text)
    logo_url = Column(String(500))
    website = Column(String(500))

    phone = Column(String(20))
    email = Column(String(255))
    address = Column(Text)

    verified = Column(Boolean, default=False)
    active = Column(Boolean, default=True)

    shop_type = Column(
        Enum("individual", "company", "charity_shop", name="shop_type"),
        default="individual"
    )

    settings = Column(JSON, default=dict)

    manager_id = Column(Integer, ForeignKey("users.id"))

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # relationships
    manager = relationship("User", foreign_keys=[manager_id])

    products = relationship(
        "Product",
        back_populates="shop",
        cascade="all, delete-orphan",
    )

    vendors = relationship(
        "User",
        secondary=shop_vendors,
        back_populates="shops",
    )
