# 1️⃣ app/schemas/need_emergency.py
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class EmergencyType(str, Enum):
    EARTHQUAKE = "earthquake"
    FLOOD = "flood"
    FIRE = "fire"
    ACCIDENT = "accident"
    STORM = "storm"
    DROUGHT = "drought"
    WAR = "war"
    PANDEMIC = "pandemic"
    OTHER = "other"


class EmergencySeverity(str, Enum):
    CRITICAL = "critical"
    SEVERE = "severe"
    MODERATE = "moderate"
    LOW = "low"


class EmergencyStatus(str, Enum):
    ACTIVE = "active"
    RESPONDING = "responding"
    STABILIZED = "stabilized"
    RECOVERING = "recovering"
    CLOSED = "closed"


class NeedEmergencyCreate(BaseModel):
    emergency_type: EmergencyType
    severity: EmergencySeverity = EmergencySeverity.MODERATE
    affected_area: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    radius_km: Optional[float] = None
    estimated_affected_people: Optional[int] = None
    estimated_damage_cost: Optional[float] = None
    death_toll: Optional[int] = 0
    injured_count: Optional[int] = 0
    displaced_count: Optional[int] = 0
    government_reference_number: Optional[str] = None
    declared_by: Optional[str] = None
    occurred_at: datetime
    media_attachments: List[Dict[str, Any]] = []
    news_links: List[str] = []
    notify_all_users: bool = True
    notify_sms: bool = True
    notify_email: bool = True
    notify_push: bool = True


class NeedEmergencyUpdate(BaseModel):
    severity: Optional[EmergencySeverity] = None
    status: Optional[EmergencyStatus] = None
    estimated_affected_people: Optional[int] = None
    estimated_damage_cost: Optional[float] = None
    death_toll: Optional[int] = None
    injured_count: Optional[int] = None
    displaced_count: Optional[int] = None
    expected_end_date: Optional[datetime] = None


class NeedEmergencyRead(BaseModel):
    id: int
    uuid: str
    need_id: int
    emergency_type: EmergencyType
    severity: EmergencySeverity
    status: EmergencyStatus
    affected_area: str
    latitude: Optional[float]
    longitude: Optional[float]
    radius_km: Optional[float]
    estimated_affected_people: Optional[int]
    estimated_damage_cost: Optional[float]
    death_toll: int
    injured_count: int
    displaced_count: int
    government_reference_number: Optional[str]
    declared_by: Optional[str]
    occurred_at: datetime
    declared_at: datetime
    expected_end_date: Optional[datetime]
    closed_at: Optional[datetime]
    media_attachments: List[Dict[str, Any]]
    news_links: List[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True