# app/models/role.py
from sqlalchemy import Column, Integer, String, Boolean, DateTime, func, Table, ForeignKey
from sqlalchemy.orm import relationship

from models.association_tables import role_permissions, user_roles
from models.base import Base
from models.permission import Permission



class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True)
    key = Column(String(50), unique=True, index=True, nullable=False)
    title = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)
    is_system = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    permissions = relationship(
        "Permission",
        secondary=role_permissions,
        lazy="selectin",
        back_populates="roles",
    )

    users = relationship(
        "User",
        secondary=user_roles,
        lazy="selectin",
        back_populates="roles",
    )
