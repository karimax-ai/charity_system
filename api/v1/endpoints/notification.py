# api/v1/endpoints/notifications.py
from typing import Optional, List, Dict, Any
from fastapi import Request

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta

from core.permissions import *
from schemas.notification import *
from schemas.user import UserRead
from services.notification_service import NotificationService
from utils.pagination import PaginatedResponse
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------- مدیریت نوتیفیکیشن‌ها ----------
@router.post("/notifications", response_model=NotificationRead, status_code=http_status.HTTP_201_CREATED)
async def create_notification(
        notification_data: NotificationCreate,
        background_tasks: BackgroundTasks,
        current_user: UserRead = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    ایجاد و ارسال نوتیفیکیشن جدید

    **نقش‌های مجاز**: همه کاربران (برای خودشان) + ادمین/مدیر (برای دیگران)
    """
    # بررسی دسترسی
    if current_user.id != notification_data.user_id:
        # بررسی اگر کاربر ادمین یا مدیر است
        user_roles = [role.key for role in current_user.roles]
        allowed_roles = ["ADMIN", "CHARITY_MANAGER", "CHARITY_ADMIN"]
        if not any(role in user_roles for role in allowed_roles):
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="Not authorized to send notifications to other users"
            )

    service = NotificationService(db)
    return await service.send_notification(notification_data, background_tasks)


@router.post("/notifications/bulk", response_model=Dict[str, Any])
async def create_bulk_notifications(
        bulk_data: NotificationBulkCreate,
        background_tasks: BackgroundTasks,
        current_user: UserRead = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    ارسال نوتیفیکیشن گروهی به چندین کاربر

    **نقش‌های مجاز**: ADMIN, CHARITY_MANAGER
    """
    # بررسی دسترسی
    user_roles = [role.key for role in current_user.roles]
    allowed_roles = ["ADMIN", "CHARITY_MANAGER"]
    if not any(role in user_roles for role in allowed_roles):
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Not authorized to send bulk notifications"
        )

    service = NotificationService(db)
    return await service.send_bulk_notifications(bulk_data, background_tasks)


@router.post("/notifications/event/{event_name}", response_model=List[NotificationRead])
async def trigger_event_notification(
        event_name: str,
        event_data: Dict[str, Any],
        background_tasks: BackgroundTasks,
        user_id: Optional[int] = Query(None),
        current_user: UserRead = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    ارسال نوتیفیکیشن بر اساس رویدادهای سیستم

    **رویدادهای موجود**:
    - need_created: ایجاد نیاز جدید
    - need_approved: تأیید نیاز
    - need_urgent: نیاز فوری/بحران
    - donation_received: دریافت کمک
    - donation_completed: تکمیل کمک
    - user_registered: ثبت‌نام کاربر
    - user_verified: تأیید کاربر
    - charity_verified: تأیید خیریه
    - payment_failed: پرداخت ناموفق
    - order_shipped: ارسال سفارش
    - crisis_alert: هشدار بحران

    **نقش‌های مجاز**: همه کاربران (برای خودشان) + ادمین/مدیر (برای دیگران)
    """
    # تعیین user_id هدف
    target_user_id = user_id or current_user.id

    # بررسی دسترسی
    if target_user_id != current_user.id:
        user_roles = [role.key for role in current_user.roles]
        allowed_roles = ["ADMIN", "CHARITY_MANAGER", "CHARITY_ADMIN"]
        if not any(role in user_roles for role in allowed_roles):
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="Not authorized to trigger events for other users"
            )

    service = NotificationService(db)
    return await service.send_event_notification(
        event_name,
        target_user_id,
        event_data,
        background_tasks
    )


@router.get("/notifications", response_model=PaginatedResponse[NotificationRead])
async def list_notifications(
        filters: NotificationFilter = Depends(),
        page: int = Query(1, ge=1),
        limit: int = Query(20, ge=1, le=100),
        current_user: UserRead = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    مشاهده لیست نوتیفیکیشن‌ها با فیلتر

    **نقش‌های مجاز**:
    - همه کاربران: فقط نوتیفیکیشن‌های خودشان
    - ادمین/مدیر: همه نوتیفیکیشن‌ها
    """
    service = NotificationService(db)

    # اگر ادمین یا مدیر است و user_id مشخص شده، فیلتر می‌تواند کاربر دیگری باشد
    if filters.user_id and filters.user_id != current_user.id:
        user_roles = [role.key for role in current_user.roles]
        allowed_roles = ["ADMIN", "CHARITY_MANAGER"]
        if not any(role in user_roles for role in allowed_roles):
            # کاربر عادی نمی‌تواند نوتیفیکیشن دیگران را ببیند
            filters.user_id = current_user.id

    result = await service.list_notifications(filters, current_user, page, limit)

    return {
        "items": result["items"],
        "total": result["total"],
        "page": result["page"],
        "limit": result["limit"],
        "total_pages": result["total_pages"]
    }


@router.get("/notifications/{notification_id}", response_model=NotificationDetail)
async def get_notification(
        notification_id: int,
        current_user: UserRead = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    مشاهده جزئیات یک نوتیفیکیشن

    **نقش‌های مجاز**: صاحب نوتیفیکیشن + ادمین/مدیر
    """
    service = NotificationService(db)
    return await service.get_notification(notification_id, current_user)


@router.put("/notifications/{notification_id}/status", response_model=NotificationRead)
async def update_notification_status(
        notification_id: int,
        status_data: NotificationStatusUpdate,
        current_user: UserRead = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    تغییر وضعیت نوتیفیکیشن (برای سرویس‌های خارجی)

    **نقش‌های مجاز**: صاحب نوتیفیکیشن + ادمین/مدیر
    """
    service = NotificationService(db)
    return await service.update_notification_status(notification_id, status_data, current_user)


@router.put("/notifications/{notification_id}/read", response_model=NotificationRead)
async def mark_notification_as_read(
        notification_id: int,
        current_user: UserRead = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    علامت‌گذاری نوتیفیکیشن به عنوان خوانده شده

    **نقش‌های مجاز**: صاحب نوتیفیکیشن
    """
    service = NotificationService(db)
    return await service.mark_as_read(notification_id, current_user)


@router.post("/notifications/mark-all-read", response_model=Dict[str, Any])
async def mark_all_notifications_as_read(
        notification_type: Optional[NotificationType] = Query(None),
        current_user: UserRead = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    علامت‌گذاری همه نوتیفیکیشن‌های خوانده نشده کاربر

    **نقش‌های مجاز**: همه کاربران (برای خودشان)
    """
    service = NotificationService(db)
    return await service.mark_all_as_read(current_user, notification_type)


# ---------- آمار و گزارش ----------
@router.get("/notifications/stats", response_model=Dict[str, Any])
async def get_notification_stats(
        start_date: Optional[datetime] = Query(None),
        end_date: Optional[datetime] = Query(None),
        user_id: Optional[int] = Query(None),
        notification_type: Optional[NotificationType] = Query(None),
        current_user: UserRead = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    دریافت آمار نوتیفیکیشن‌ها

    **نقش‌های مجاز**:
    - همه کاربران: فقط آمار خودشان
    - ادمین/مدیر: آمار همه کاربران
    """
    # تنظیم تاریخ پیش‌فرض (۷ روز اخیر)
    if not start_date:
        start_date = datetime.utcnow() - timedelta(days=7)
    if not end_date:
        end_date = datetime.utcnow()

    # بررسی دسترسی برای user_id
    if user_id and user_id != current_user.id:
        user_roles = [role.key for role in current_user.roles]
        allowed_roles = ["ADMIN", "CHARITY_MANAGER"]
        if not any(role in user_roles for role in allowed_roles):
            user_id = current_user.id  # فقط آمار خودش

    service = NotificationService(db)
    return await service.get_notification_stats(start_date, end_date, user_id, notification_type)


@router.get("/notifications/unread-count", response_model=Dict[str, Any])
async def get_unread_notifications_count(
        current_user: UserRead = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    دریافت تعداد نوتیفیکیشن‌های خوانده نشده کاربر

    **نقش‌های مجاز**: همه کاربران (برای خودشان)
    """
    service = NotificationService(db)
    return await service.get_user_unread_count(current_user)


# ---------- عملیات مدیریتی ----------
# ---------- عملیات مدیریتی ----------
@router.post("/notifications/retry-failed", response_model=None)  # ✅ تغییر به None
async def retry_failed_notifications(
        hours_ago: int = Query(24, ge=1, le=168),
        background_tasks: BackgroundTasks = BackgroundTasks(),  # ✅ حذف Optional و مقدار پیش‌فرض
        current_user: UserRead = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    تلاش مجدد برای ارسال نوتیفیکیشن‌های ناموفق

    **نقش‌های مجاز**: ADMIN, CHARITY_MANAGER
    """
    # بررسی دسترسی
    user_roles = [role.key for role in current_user.roles]
    allowed_roles = ["ADMIN", "CHARITY_MANAGER"]
    if not any(role in user_roles for role in allowed_roles):
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Not authorized to retry failed notifications"
        )

    service = NotificationService(db)
    result = await service.retry_failed_notifications(hours_ago, background_tasks)

    return {
        "message": "Retry process started",
        "retry_count": result.get("retry_count", 0),
        "background_task": True
    }

# ---------- مدیریت Templates ----------
@router.post("/notification-templates", response_model=NotificationTemplateRead)
async def create_notification_template(
        template_data: NotificationTemplateCreate,
        current_user: UserRead = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    ایجاد template جدید برای نوتیفیکیشن

    **نقش‌های مجاز**: ADMIN
    """
    # بررسی دسترسی
    user_roles = [role.key for role in current_user.roles]
    if "ADMIN" not in user_roles:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Only admins can create notification templates"
        )

    # بررسی نام تکراری
    from models.notification_template import NotificationTemplate as TemplateModel
    from sqlalchemy import select

    result = await db.execute(
        select(TemplateModel).where(TemplateModel.name == template_data.name)
    )
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"Template with name '{template_data.name}' already exists"
        )

    # ایجاد template
    template = TemplateModel(**template_data.dict())
    db.add(template)
    await db.commit()
    await db.refresh(template)

    return template


@router.get("/notification-templates", response_model=List[NotificationTemplateRead])
async def list_notification_templates(
        is_active: Optional[bool] = Query(None),
        template_type: Optional[NotificationType] = Query(None),
        language: Optional[str] = Query(None),
        current_user: UserRead = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    لیست templates نوتیفیکیشن

    **نقش‌های مجاز**: همه کاربران
    """
    from models.notification_template import NotificationTemplate as TemplateModel
    from sqlalchemy import select

    query = select(TemplateModel)

    # اعمال فیلترها
    if is_active is not None:
        query = query.where(TemplateModel.is_active == is_active)
    if template_type:
        query = query.where(TemplateModel.template_type == template_type)
    if language:
        query = query.where(TemplateModel.language == language)

    query = query.order_by(TemplateModel.name)

    result = await db.execute(query)
    templates = result.scalars().all()

    return templates


@router.get("/notification-templates/{template_id}", response_model=NotificationTemplateRead)
async def get_notification_template(
        template_id: int,
        current_user: UserRead = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    مشاهده جزئیات template

    **نقش‌های مجاز**: همه کاربران
    """
    from models.notification_template import NotificationTemplate as TemplateModel

    template = await db.get(TemplateModel, template_id)
    if not template:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Template not found")

    return template


@router.put("/notification-templates/{template_id}", response_model=NotificationTemplateRead)
async def update_notification_template(
        template_id: int,
        template_data: NotificationTemplateUpdate,
        current_user: UserRead = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    ویرایش template نوتیفیکیشن

    **نقش‌های مجاز**: ADMIN
    """
    # بررسی دسترسی
    user_roles = [role.key for role in current_user.roles]
    if "ADMIN" not in user_roles:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Only admins can update notification templates"
        )

    from models.notification_template import NotificationTemplate as TemplateModel

    template = await db.get(TemplateModel, template_id)
    if not template:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Template not found")

    # به‌روزرسانی فیلدها
    update_data = template_data.dict(exclude_unset=True)

    # افزایش نسخه اگر محتوا تغییر کرده
    if any(key in update_data for key in ['body_template', 'title_template', 'html_template', 'subject_template']):
        template.version += 1

    for key, value in update_data.items():
        setattr(template, key, value)

    db.add(template)
    await db.commit()
    await db.refresh(template)

    return template


@router.delete("/notification-templates/{template_id}")
async def delete_notification_template(
        template_id: int,
        current_user: UserRead = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    حذف template نوتیفیکیشن

    **نقش‌های مجاز**: ADMIN
    """
    # بررسی دسترسی
    user_roles = [role.key for role in current_user.roles]
    if "ADMIN" not in user_roles:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Only admins can delete notification templates"
        )

    from models.notification_template import NotificationTemplate as TemplateModel

    template = await db.get(TemplateModel, template_id)
    if not template:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Template not found")

    # غیرفعال کردن به جای حذف
    template.is_active = False
    db.add(template)
    await db.commit()

    return {"message": f"Template '{template.name}' deactivated successfully"}


# ---------- مدیریت تنظیمات کاربر ----------
@router.get("/notification-preferences", response_model=NotificationPreferenceRead)
async def get_notification_preferences(
        user_id: Optional[int] = Query(None),
        current_user: UserRead = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    دریافت تنظیمات نوتیفیکیشن کاربر

    **نقش‌های مجاز**:
    - همه کاربران: تنظیمات خودشان
    - ادمین/مدیر: تنظیمات کاربران دیگر
    """
    target_user_id = user_id or current_user.id

    # بررسی دسترسی
    if target_user_id != current_user.id:
        user_roles = [role.key for role in current_user.roles]
        allowed_roles = ["ADMIN", "CHARITY_MANAGER"]
        if not any(role in user_roles for role in allowed_roles):
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="Not authorized to view other users' preferences"
            )

    from models.notification_preference import NotificationPreference as PreferenceModel
    from sqlalchemy import select

    result = await db.execute(
        select(PreferenceModel).where(PreferenceModel.user_id == target_user_id)
    )
    preference = result.scalar_one_or_none()

    if not preference:
        # اگر تنظیمات وجود ندارد، ایجاد تنظیمات پیش‌فرض
        preference = PreferenceModel(user_id=target_user_id)
        db.add(preference)
        await db.commit()
        await db.refresh(preference)

    return preference


@router.put("/notification-preferences", response_model=NotificationPreferenceRead)
async def update_notification_preferences(
        preference_data: NotificationPreferenceUpdate,
        user_id: Optional[int] = Query(None),
        current_user: UserRead = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    ویرایش تنظیمات نوتیفیکیشن کاربر

    **نقش‌های مجاز**:
    - همه کاربران: تنظیمات خودشان
    - ادمین/مدیر: تنظیمات کاربران دیگر
    """
    target_user_id = user_id or current_user.id

    # بررسی دسترسی
    if target_user_id != current_user.id:
        user_roles = [role.key for role in current_user.roles]
        allowed_roles = ["ADMIN", "CHARITY_MANAGER"]
        if not any(role in user_roles for role in allowed_roles):
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="Not authorized to update other users' preferences"
            )

    from models.notification_preference import NotificationPreference as PreferenceModel
    from sqlalchemy import select

    result = await db.execute(
        select(PreferenceModel).where(PreferenceModel.user_id == target_user_id)
    )
    preference = result.scalar_one_or_none()

    if not preference:
        # ایجاد تنظیمات جدید
        create_data = preference_data.dict()
        create_data["user_id"] = target_user_id
        preference = PreferenceModel(**create_data)
    else:
        # به‌روزرسانی تنظیمات موجود
        update_data = preference_data.dict(exclude_unset=True)
        for key, value in update_data.items():
            setattr(preference, key, value)

    db.add(preference)
    await db.commit()
    await db.refresh(preference)

    return preference


# ---------- Webhook برای سرویس‌های خارجی ----------
@router.post("/webhooks/notification/{provider}", response_model=None)  # ✅ اضافه کردن response_model=None
async def notification_webhook(
        provider: str,
        request: Request,  # ✅ اضافه کردن Request به عنوان پارامتر
        current_user: UserRead = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    Webhook برای دریافت وضعیت نوتیفیکیشن‌ها از سرویس‌های خارجی

    **Providerهای پشتیبانی شده**: kavenegar, twilio, firebase, email_smtp
    """
    # احراز هویت کاربر
    user_roles = [role.key for role in current_user.roles]
    allowed_roles = ["ADMIN", "CHARITY_MANAGER"]
    if not any(role in user_roles for role in allowed_roles):
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access webhook endpoint"
        )

    try:
        # دریافت داده‌های webhook
        webhook_data = await request.json()
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload"
        )

    # پردازش webhook
    service = NotificationService(db)

    try:
        # استخراج اطلاعات از webhook
        external_id = webhook_data.get("message_id") or webhook_data.get("sid") or webhook_data.get("id")
        status = webhook_data.get("status")

        if not external_id or not status:
            return {"status": "ignored", "message": "Invalid webhook data"}

        # یافتن نوتیفیکیشن مربوطه
        from models.notification import Notification as NotificationModel
        from sqlalchemy import select

        result = await db.execute(
            select(NotificationModel).where(
                NotificationModel.external_id == external_id,
                NotificationModel.sent_via == provider
            )
        )
        notification = result.scalar_one_or_none()

        if not notification:
            logger.warning(f"No notification found for external_id: {external_id}")
            return {"status": "ignored", "message": "Notification not found"}

        # تنظیم وضعیت بر اساس وضعیت دریافتی
        status_mapping = {
            "delivered": NotificationStatus.DELIVERED,
            "sent": NotificationStatus.SENT,
            "failed": NotificationStatus.FAILED,
            "read": NotificationStatus.READ,
        }

        if status in status_mapping:
            notification.status = status_mapping[status]

            if status == "delivered":
                notification.delivered_at = datetime.utcnow()
            elif status == "read":
                notification.read_at = datetime.utcnow()

            db.add(notification)
            await db.commit()

            logger.info(f"Updated notification {notification.id} status to {status} via {provider}")

            return {"status": "success", "notification_id": notification.id}
        else:
            return {"status": "ignored", "message": f"Unknown status: {status}"}

    except Exception as e:
        logger.error(f"Error processing webhook from {provider}: {str(e)}")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Webhook processing failed: {str(e)}"
        )


# ---------- راه‌اندازی و سلامت ----------
@router.get("/notifications/health")
async def check_notification_health(
        db: AsyncSession = Depends(get_db)
):
    """
    بررسی سلامت سرویس نوتیفیکیشن

    این endpoint وضعیت اتصال به دیتابیس و سرویس‌های خارجی را بررسی می‌کند
    """
    from sqlalchemy import text

    health_status = {
        "service": "notification",
        "timestamp": datetime.utcnow().isoformat(),
        "status": "healthy",
        "checks": {}
    }

    try:
        # بررسی اتصال دیتابیس
        await db.execute(text("SELECT 1"))
        health_status["checks"]["database"] = {"status": "healthy"}
    except Exception as e:
        health_status["checks"]["database"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        health_status["status"] = "unhealthy"

    # بررسی سرویس‌های خارجی (اختیاری)
    # در اینجا می‌توانید سرویس‌های ایمیل، SMS و ... را بررسی کنید

    return health_status


@router.post("/notifications/test/{notification_type}")
async def send_test_notification(
        notification_type: NotificationType,
        background_tasks: BackgroundTasks,
        current_user: UserRead = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    ارسال نوتیفیکیشن آزمایشی برای تست تنظیمات

    **نقش‌های مجاز**: همه کاربران (برای خودشان)
    """
    service = NotificationService(db)

    # ایجاد نوتیفیکیشن آزمایشی
    test_notification = NotificationCreate(
        user_id=current_user.id,
        type=notification_type,
        title="📱 تست نوتیفیکیشن",
        message=f"این یک نوتیفیکیشن آزمایشی از نوع {notification_type} است.",
        priority=NotificationPriority.NORMAL,
        data={"test": True, "timestamp": datetime.utcnow().isoformat()}
    )

    # تنظیم اطلاعات گیرنده بر اساس نوع
    if notification_type == NotificationType.EMAIL:
        if not current_user.email:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="User email not set for email notification"
            )
        test_notification.recipient_email = current_user.email

    elif notification_type == NotificationType.SMS:
        if not current_user.phone:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="User phone not set for SMS notification"
            )
        test_notification.recipient_phone = current_user.phone

    try:
        notification = await service.send_notification(test_notification, background_tasks)
        return {
            "success": True,
            "message": f"Test {notification_type} notification sent",
            "notification_id": notification.id
        }
    except Exception as e:
        logger.error(f"Failed to send test notification: {str(e)}")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send test notification: {str(e)}"
        )