from sqlalchemy import Column, Integer, String, DateTime, func
from sqlalchemy.orm import relationship

from models.association_tables import role_permissions
from models.base import Base

class Permission(Base):
    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True)
    code = Column(String(100), unique=True, index=True, nullable=False)
    title = Column(String(150), nullable=False)
    description = Column(String(255), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    roles = relationship(
        "Role",
        secondary=role_permissions,
        lazy="selectin",
        back_populates="permissions",
    )

