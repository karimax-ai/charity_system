# app/schemas/need_log.py
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class NeedAttachmentAccessLog(BaseModel):
    """لاگ دسترسی به فایل پیوست نیاز"""
    attachment_id: int
    file_name: str
    accessed_by: Optional[str]
    accessed_at: datetime
    ip_address: str
    user_agent: str
    action: str
    success: bool

    class Config:
        orm_mode = True


class NeedAccessLogFilter(BaseModel):
    need_id: Optional[int] = None
    attachment_id: Optional[int] = None
    user_id: Optional[int] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    action: Optional[str] = None