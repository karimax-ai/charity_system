from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


class PermissionBase(BaseModel):
    code: str
    title: str
    description: Optional[str] = None


class Permission(PermissionBase):
    id: int
    created_at: datetime

    class Config:
        orm_mode = True


class RoleBase(BaseModel):
    key: str
    title: str
    description: Optional[str] = None
    is_system: bool = False


class RoleCreate(RoleBase):
    permission_codes: List[str] = []


class RoleUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    permission_codes: Optional[List[str]] = None


class RoleSchema(RoleBase):
    id: int
    created_at: datetime
    permissions: List[Permission] = []

    class Config:
        orm_mode = True


class UserRoleAssignment(BaseModel):
    user_id: int
    role_key: str