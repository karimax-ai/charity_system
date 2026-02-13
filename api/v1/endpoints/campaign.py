# app/api/v1/endpoints/campaign.py
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any

from core.database import get_db
from core.permissions import get_current_user, require_roles
from models.user import User
from services.campaign_service import CampaignService
from schemas.campaign import (
    CampaignCreate, CampaignUpdate, CampaignRead, CampaignDetail,
    CampaignDonate, CampaignDonationRead, CampaignShareCreate,
    CampaignShareRead, CampaignCommentCreate, CampaignCommentRead,
    CampaignFilter
)

router = APIRouter()


@router.post("/", response_model=CampaignRead)
async def create_campaign(
        campaign_data: CampaignCreate,
        background_tasks: BackgroundTasks,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """ایجاد کمپین جدید"""
    service = CampaignService(db)
    campaign = await service.create_campaign(campaign_data, current_user, background_tasks)
    return await service.get_campaign(campaign.id, current_user)


@router.post("/{campaign_id}/publish", response_model=CampaignRead)
async def publish_campaign(
        campaign_id: int,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """انتشار کمپین"""
    service = CampaignService(db)
    campaign = await service.publish_campaign(campaign_id, current_user)
    return await service.get_campaign(campaign.id, current_user)


@router.get("/", response_model=Dict[str, Any])
async def list_campaigns(
        status: Optional[str] = Query(None),
        campaign_type: Optional[str] = Query(None),
        charity_id: Optional[int] = Query(None),
        need_id: Optional[int] = Query(None),
        is_featured: Optional[bool] = Query(None),
        search_text: Optional[str] = Query(None),
        sort_by: str = Query("created_at"),
        sort_order: str = Query("desc"),
        page: int = Query(1, ge=1),
        limit: int = Query(20, ge=1, le=100),
        current_user: Optional[User] = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """لیست کمپین‌ها"""
    filters = CampaignFilter(
        status=status,
        campaign_type=campaign_type,
        charity_id=charity_id,
        need_id=need_id,
        is_featured=is_featured,
        search_text=search_text,
        sort_by=sort_by,
        sort_order=sort_order
    )
    service = CampaignService(db)
    return await service.list_campaigns(filters, current_user, page, limit)


@router.get("/by-slug/{slug}", response_model=CampaignDetail)
async def get_campaign_by_slug(
        slug: str,
        current_user: Optional[User] = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """دریافت کمپین با slug"""
    service = CampaignService(db)
    return await service.get_campaign_by_slug(slug, current_user)


@router.get("/{campaign_id}", response_model=CampaignDetail)
async def get_campaign(
        campaign_id: int,
        current_user: Optional[User] = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """دریافت جزئیات کمپین"""
    service = CampaignService(db)
    return await service.get_campaign(campaign_id, current_user)


@router.put("/{campaign_id}", response_model=CampaignRead)
async def update_campaign(
        campaign_id: int,
        update_data: CampaignUpdate,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """ویرایش کمپین"""
    service = CampaignService(db)
    campaign = await service._get_campaign_with_permission(campaign_id, current_user)

    for key, value in update_data.dict(exclude_unset=True).items():
        setattr(campaign, key, value)

    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)

    return await service.get_campaign(campaign.id, current_user)


@router.post("/{campaign_id}/donate", response_model=CampaignDonationRead)
async def donate_to_campaign(
        campaign_id: int,
        donate_data: CampaignDonate,
        background_tasks: BackgroundTasks,
        current_user: Optional[User] = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """کمک به کمپین"""
    donate_data.campaign_id = campaign_id
    service = CampaignService(db)
    donation = await service.donate_to_campaign(donate_data, current_user, background_tasks)

    return {
        "id": donation.id,
        "campaign_id": donation.campaign_id,
        "donor_id": donation.donor_id,
        "donor_name": current_user.display_name if current_user and not donation.is_anonymous else "ناشناس",
        "amount": donation.amount,
        "currency": donation.currency,
        "message": donation.message,
        "is_anonymous": donation.is_anonymous,
        "shared_by": donation.shared_by,
        "donated_at": donation.donated_at
    }


@router.post("/share", response_model=CampaignShareRead)
async def share_campaign(
        share_data: CampaignShareCreate,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """اشتراک‌گذاری کمپین"""
    service = CampaignService(db)
    return await service.share_campaign(share_data, current_user)


@router.get("/track/{share_code}")
async def track_share_click(
        share_code: str,
        db: AsyncSession = Depends(get_db)
):
    """ردیابی کلیک روی لینک اشتراک"""
    service = CampaignService(db)
    result = await service.track_share_click(share_code)
    return result


@router.post("/comments", response_model=CampaignCommentRead)
async def add_comment(
        comment_data: CampaignCommentCreate,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """افزودن نظر به کمپین"""
    service = CampaignService(db)
    return await service.add_comment(comment_data, current_user)


@router.get("/user/my-campaigns", response_model=Dict[str, Any])
async def get_my_campaigns(
        status: Optional[str] = Query(None),
        page: int = Query(1, ge=1),
        limit: int = Query(20, ge=1, le=100),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """کمپین‌های من"""
    service = CampaignService(db)
    return await service.get_my_campaigns(current_user, status, page, limit)


@router.get("/user/supported", response_model=Dict[str, Any])
async def get_supported_campaigns(
        page: int = Query(1, ge=1),
        limit: int = Query(20, ge=1, le=100),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """کمپین‌هایی که حمایت کردم"""
    service = CampaignService(db)
    return await service.get_supported_campaigns(current_user, page, limit)


@router.get("/{campaign_id}/stats")
async def get_campaign_stats(
        campaign_id: int,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """آمار کمپین"""
    service = CampaignService(db)
    return await service.get_campaign_stats(campaign_id, current_user)