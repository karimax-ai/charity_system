# app/schemas/notification.py
from pydantic import BaseModel, Field, validator, EmailStr
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class NotificationType(str, Enum):
    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"
    SYSTEM = "system"
    URGENT = "urgent"


class NotificationStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"
    CANCELLED = "cancelled"


class NotificationPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class NotificationCreate(BaseModel):
    user_id: int
    type: NotificationType
    title: str = Field(..., max_length=200)
    message: str = Field(..., max_length=1000)
    priority: NotificationPriority = NotificationPriority.NORMAL
    template_name: Optional[str] = None
    data: Dict[str, Any] = {}
    metadata: Dict[str, Any] = {}
    recipient_email: Optional[EmailStr] = None
    recipient_phone: Optional[str] = None
    recipient_device_token: Optional[str] = None
    scheduled_for: Optional[datetime] = None
    expires_at: Optional[datetime] = None


class NotificationBulkCreate(BaseModel):
    user_ids: List[int]
    type: NotificationType
    title: str
    message: str
    priority: NotificationPriority = NotificationPriority.NORMAL
    data: Dict[str, Any] = {}
    scheduled_for: Optional[datetime] = None


class NotificationUpdate(BaseModel):
    title: Optional[str] = None
    message: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    scheduled_for: Optional[datetime] = None


class NotificationStatusUpdate(BaseModel):
    status: NotificationStatus
    external_id: Optional[str] = None
    delivery_receipt: Optional[Dict[str, Any]] = None


class NotificationRead(BaseModel):
    id: int
    uuid: str
    user_id: int
    type: NotificationType
    status: NotificationStatus
    priority: NotificationPriority
    title: str
    message: str
    data: Dict[str, Any]
    metadata: Dict[str, Any]
    recipient_email: Optional[str]
    recipient_phone: Optional[str]
    scheduled_for: Optional[datetime]
    sent_at: Optional[datetime]
    delivered_at: Optional[datetime]
    read_at: Optional[datetime]
    created_at: datetime

    class Config:
        orm_mode = True


class NotificationDetail(NotificationRead):
    external_id: Optional[str]
    delivery_receipt: Optional[Dict[str, Any]]
    retry_count: int = 0
    expires_at: Optional[datetime]

    class Config:
        orm_mode = True


class NotificationFilter(BaseModel):
    user_id: Optional[int] = None
    type: Optional[NotificationType] = None
    status: Optional[NotificationStatus] = None
    priority: Optional[NotificationPriority] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    search_text: Optional[str] = None
    unread_only: bool = False
    scheduled_only: bool = False
    sort_by: str = "created_at"
    sort_order: str = "desc"


class NotificationTemplateCreate(BaseModel):
    name: str
    description: Optional[str] = None
    template_type: NotificationType
    language: str = "fa"
    subject_template: Optional[str] = None
    title_template: Optional[str] = None
    body_template: str
    html_template: Optional[str] = None
    variables: List[str] = []
    default_data: Dict[str, Any] = {}


class NotificationTemplateUpdate(BaseModel):
    description: Optional[str] = None
    subject_template: Optional[str] = None
    title_template: Optional[str] = None
    body_template: Optional[str] = None
    html_template: Optional[str] = None
    variables: Optional[List[str]] = None
    default_data: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class NotificationTemplateRead(BaseModel):
    id: int
    name: str
    description: Optional[str]
    template_type: NotificationType
    language: str
    subject_template: Optional[str]
    title_template: Optional[str]
    body_template: str
    html_template: Optional[str]
    variables: List[str]
    default_data: Dict[str, Any]
    is_active: bool
    version: int
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


class NotificationPreferenceUpdate(BaseModel):
    email_enabled: Optional[bool] = None
    sms_enabled: Optional[bool] = None
    push_enabled: Optional[bool] = None
    system_enabled: Optional[bool] = None
    event_settings: Optional[Dict[str, Dict[str, bool]]] = None
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None
    quiet_hours_enabled: Optional[bool] = None
    digest_enabled: Optional[bool] = None
    digest_frequency: Optional[str] = None


class NotificationPreferenceRead(BaseModel):
    id: int
    user_id: int
    email_enabled: bool
    sms_enabled: bool
    push_enabled: bool
    system_enabled: bool
    event_settings: Dict[str, Dict[str, bool]]
    quiet_hours_start: Optional[str]
    quiet_hours_end: Optional[str]
    quiet_hours_enabled: bool
    digest_enabled: bool
    digest_frequency: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True