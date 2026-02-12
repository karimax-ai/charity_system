# services/notification_service.py
import asyncio
import aiohttp
import json
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc, asc, update, case
from fastapi import HTTPException, status, BackgroundTasks
import logging
import uuid

from models.notification import Notification, NotificationType, NotificationStatus, NotificationPriority
from models.notification_template import NotificationTemplate
from models.notification_preference import NotificationPreference
from models.user import User
from schemas.notification import (
    NotificationCreate, NotificationBulkCreate, NotificationUpdate,
    NotificationStatusUpdate, NotificationFilter
)

# تنظیمات logging
logger = logging.getLogger(__name__)


class NotificationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = self._load_settings()

        # Providers configuration
        self.providers = {
            "email": self._send_email,
            "sms": self._send_sms,
            "push": self._send_push,
            "system": self._send_system,
            "urgent": self._send_urgent
        }

        # Event handlers
        self.event_handlers = {
            "need_created": self._handle_need_created,
            "need_approved": self._handle_need_approved,
            "need_urgent": self._handle_need_urgent,
            "donation_received": self._handle_donation_received,
            "donation_completed": self._handle_donation_completed,
            "user_registered": self._handle_user_registered,
            "user_verified": self._handle_user_verified,
            "charity_verified": self._handle_charity_verified,
            "payment_failed": self._handle_payment_failed,
            "order_shipped": self._handle_order_shipped,
            "crisis_alert": self._handle_crisis_alert
        }

    async def send_notification(
            self,
            notification_data: NotificationCreate,
            background_tasks: Optional[BackgroundTasks] = None
    ) -> Notification:
        """ارسال نوتیفیکیشن جدید"""

        # بررسی کاربر
        user = await self._get_user(notification_data.user_id)

        # بررسی تنظیمات کاربر
        if not await self._check_user_preferences(user, notification_data.type):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"User has disabled {notification_data.type} notifications"
            )

        # بررسی ساعات آرام
        if await self._is_quiet_hours(user):
            if notification_data.priority != NotificationPriority.URGENT:
                # زمان‌بندی برای بعد
                scheduled_for = self._get_next_available_time()
                notification_data.scheduled_for = scheduled_for

        # آماده‌سازی داده‌های گیرنده
        recipient_data = await self._prepare_recipient_data(user, notification_data)

        # ایجاد نوتیفیکیشن
        notification = Notification(
            user_id=notification_data.user_id,
            type=notification_data.type,
            priority=notification_data.priority,
            title=notification_data.title,
            message=notification_data.message,
            template_name=notification_data.template_name,
            data=notification_data.data,
            metadata=notification_data.metadata,
            recipient_email=recipient_data.get("email"),
            recipient_phone=recipient_data.get("phone"),
            recipient_device_token=recipient_data.get("device_token"),
            scheduled_for=notification_data.scheduled_for,
            expires_at=notification_data.expires_at
        )

        self.db.add(notification)
        await self.db.commit()
        await self.db.refresh(notification)

        # ارسال فوری یا زمان‌بندی شده
        if background_tasks and not notification.scheduled_for:
            # ارسال در پس‌زمینه
            background_tasks.add_task(
                self._process_notification,
                notification.id
            )
        elif notification.scheduled_for:
            # زمان‌بندی برای آینده
            await self._schedule_notification(notification.id)
        else:
            # ارسال همزمان
            await self._process_notification(notification.id)

        return notification

    async def send_bulk_notifications(
            self,
            bulk_data: NotificationBulkCreate,
            background_tasks: BackgroundTasks
    ) -> Dict[str, Any]:
        """ارسال نوتیفیکیشن گروهی"""

        created_count = 0
        failed_users = []

        for user_id in bulk_data.user_ids:
            try:
                # ایجاد داده‌های نوتیفیکیشن برای هر کاربر
                notification_data = NotificationCreate(
                    user_id=user_id,
                    type=bulk_data.type,
                    title=bulk_data.title,
                    message=bulk_data.message,
                    data=bulk_data.data,
                    priority=bulk_data.priority,
                    scheduled_for=bulk_data.scheduled_for
                )

                # ارسال (در پس‌زمینه)
                background_tasks.add_task(
                    self._send_individual_notification,
                    notification_data
                )

                created_count += 1

            except Exception as e:
                logger.error(f"Failed to create notification for user {user_id}: {str(e)}")
                failed_users.append({
                    "user_id": user_id,
                    "error": str(e)
                })

        return {
            "total_users": len(bulk_data.user_ids),
            "notifications_created": created_count,
            "failed_users": failed_users,
            "message": f"Notifications scheduled for {created_count} users"
        }

    async def send_event_notification(
            self,
            event_name: str,
            user_id: int,
            event_data: Dict[str, Any],
            background_tasks: BackgroundTasks
    ) -> List[Notification]:
        """ارسال نوتیفیکیشن بر اساس رویداد"""

        if event_name not in self.event_handlers:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown event: {event_name}"
            )

        # اجرای هندلر رویداد
        handler = self.event_handlers[event_name]
        notifications_data = await handler(user_id, event_data)

        # ارسال نوتیفیکیشن‌ها
        sent_notifications = []
        for notification_data in notifications_data:
            try:
                notification = await self.send_notification(
                    notification_data,
                    background_tasks
                )
                sent_notifications.append(notification)
            except Exception as e:
                logger.error(f"Failed to send {event_name} notification: {str(e)}")

        return sent_notifications

    async def get_notification(
            self,
            notification_id: int,
            user: Optional[User] = None
    ) -> Notification:
        """دریافت یک نوتیفیکیشن"""

        notification = await self._get_notification(notification_id)

        # بررسی دسترسی
        if user and notification.user_id != user.id:
            # بررسی اگر ادمین است
            user_roles = [r.key for r in user.roles]
            if "ADMIN" not in user_roles and "CHARITY_MANAGER" not in user_roles:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not authorized to view this notification"
                )

        return notification

    async def list_notifications(
            self,
            filters: NotificationFilter,
            user: Optional[User] = None,
            page: int = 1,
            limit: int = 20
    ) -> Dict[str, Any]:
        """لیست نوتیفیکیشن‌ها با فیلتر"""

        query = select(Notification)

        # اعمال فیلترهای پایه
        conditions = []

        if filters.user_id:
            conditions.append(Notification.user_id == filters.user_id)
        elif user:
            # اگر کاربر مشخص نشده و user جاری وجود دارد، فقط نوتیفیکیشن‌های خودش
            conditions.append(Notification.user_id == user.id)

        if filters.type:
            conditions.append(Notification.type == filters.type)

        if filters.status:
            conditions.append(Notification.status == filters.status)

        if filters.priority:
            conditions.append(Notification.priority == filters.priority)

        if filters.start_date:
            conditions.append(Notification.created_at >= filters.start_date)

        if filters.end_date:
            conditions.append(Notification.created_at <= filters.end_date)

        if filters.search_text:
            conditions.append(
                or_(
                    Notification.title.ilike(f"%{filters.search_text}%"),
                    Notification.message.ilike(f"%{filters.search_text}%")
                )
            )

        if filters.unread_only:
            conditions.append(Notification.read_at.is_(None))

        if filters.scheduled_only:
            conditions.append(Notification.scheduled_for.is_not(None))
            conditions.append(Notification.scheduled_for > datetime.utcnow())

        if conditions:
            query = query.where(and_(*conditions))

        # مرتب‌سازی
        sort_column = getattr(Notification, filters.sort_by, Notification.created_at)
        if filters.sort_order == "desc":
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())

        # شمارش کل
        total_query = select(func.count()).select_from(query.subquery())
        total = await self.db.scalar(total_query)

        # صفحه‌بندی
        offset = (page - 1) * limit
        query = query.offset(offset).limit(limit)

        # اجرای کوئری
        result = await self.db.execute(query)
        notifications = result.scalars().all()

        return {
            "items": notifications,
            "total": total or 0,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit if total > 0 else 0
        }

    async def update_notification_status(
            self,
            notification_id: int,
            status_data: NotificationStatusUpdate,
            user: Optional[User] = None
    ) -> Notification:
        """تغییر وضعیت نوتیفیکیشن"""

        notification = await self._get_notification(notification_id)

        # بررسی دسترسی
        if user and notification.user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to update this notification"
            )

        old_status = notification.status
        notification.status = status_data.status

        # به‌روزرسانی زمان‌ها بر اساس وضعیت جدید
        if status_data.status == NotificationStatus.SENT:
            notification.sent_at = datetime.utcnow()
        elif status_data.status == NotificationStatus.DELIVERED:
            notification.delivered_at = datetime.utcnow()
        elif status_data.status == NotificationStatus.READ:
            notification.read_at = datetime.utcnow()

        # ذخیره اطلاعات خارجی
        if status_data.external_id:
            notification.external_id = status_data.external_id

        if status_data.delivery_receipt:
            notification.delivery_receipt = status_data.delivery_receipt

        self.db.add(notification)
        await self.db.commit()
        await self.db.refresh(notification)

        # ثبت لاگ
        logger.info(f"Notification {notification_id} status changed from {old_status} to {status_data.status}")

        return notification

    async def mark_as_read(
            self,
            notification_id: int,
            user: User
    ) -> Notification:
        """علامت‌گذاری نوتیفیکیشن به عنوان خوانده شده"""

        notification = await self._get_notification(notification_id)

        if notification.user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized"
            )

        if not notification.read_at:
            notification.status = NotificationStatus.READ
            notification.read_at = datetime.utcnow()
            self.db.add(notification)
            await self.db.commit()

        return notification

    async def mark_all_as_read(
            self,
            user: User,
            notification_type: Optional[NotificationType] = None
    ) -> Dict[str, Any]:
        """علامت‌گذاری همه نوتیفیکیشن‌های کاربر به عنوان خوانده شده"""

        query = select(Notification).where(
            and_(
                Notification.user_id == user.id,
                Notification.read_at.is_(None)
            )
        )

        if notification_type:
            query = query.where(Notification.type == notification_type)

        result = await self.db.execute(query)
        notifications = result.scalars().all()

        updated_count = 0
        for notification in notifications:
            notification.status = NotificationStatus.READ
            notification.read_at = datetime.utcnow()
            self.db.add(notification)
            updated_count += 1

        await self.db.commit()

        return {
            "user_id": user.id,
            "updated_count": updated_count,
            "notification_type": notification_type,
            "message": f"Marked {updated_count} notifications as read"
        }

    async def get_notification_stats(
            self,
            start_date: Optional[datetime] = None,
            end_date: Optional[datetime] = None,
            user_id: Optional[int] = None,
            notification_type: Optional[NotificationType] = None
    ) -> Dict[str, Any]:
        """آمار نوتیفیکیشن‌ها"""

        query = select(Notification)

        conditions = []

        if start_date:
            conditions.append(Notification.created_at >= start_date)
        if end_date:
            conditions.append(Notification.created_at <= end_date)
        if user_id:
            conditions.append(Notification.user_id == user_id)
        if notification_type:
            conditions.append(Notification.type == notification_type)

        if conditions:
            query = query.where(and_(*conditions))

        result = await self.db.execute(query)
        notifications = result.scalars().all()

        # محاسبات آماری
        total_count = len(notifications)

        if total_count == 0:
            return {
                "total": 0,
                "by_type": {},
                "by_status": {},
                "by_priority": {},
                "success_rate": 0,
                "delivery_rate": 0,
                "read_rate": 0
            }

        stats = {
            "total": total_count,
            "by_type": {},
            "by_status": {},
            "by_priority": {},
            "sent_count": 0,
            "delivered_count": 0,
            "read_count": 0,
            "failed_count": 0
        }

        for notification in notifications:
            # شمارش بر اساس نوع
            type_key = notification.type.value
            stats["by_type"][type_key] = stats["by_type"].get(type_key, 0) + 1

            # شمارش بر اساس وضعیت
            status_key = notification.status.value
            stats["by_status"][status_key] = stats["by_status"].get(status_key, 0) + 1

            # شمارش بر اساس اولویت
            priority_key = notification.priority.value
            stats["by_priority"][priority_key] = stats["by_priority"].get(priority_key, 0) + 1

            # شمارش برای نرخ‌ها
            if notification.status == NotificationStatus.SENT:
                stats["sent_count"] += 1
            if notification.status == NotificationStatus.DELIVERED:
                stats["delivered_count"] += 1
            if notification.status == NotificationStatus.READ:
                stats["read_count"] += 1
            if notification.status == NotificationStatus.FAILED:
                stats["failed_count"] += 1

        # محاسبه نرخ‌ها
        stats["success_rate"] = (stats["sent_count"] / total_count) * 100 if total_count > 0 else 0
        stats["delivery_rate"] = (stats["delivered_count"] / stats["sent_count"]) * 100 if stats[
                                                                                               "sent_count"] > 0 else 0
        stats["read_rate"] = (stats["read_count"] / stats["delivered_count"]) * 100 if stats[
                                                                                           "delivered_count"] > 0 else 0

        return stats

    async def retry_failed_notifications(
            self,
            hours_ago: int = 24,
            background_tasks: Optional[BackgroundTasks] = None
    ) -> Dict[str, Any]:
        """تلاش مجدد برای نوتیفیکیشن‌های ناموفق"""

        cutoff_time = datetime.utcnow() - timedelta(hours=hours_ago)

        query = select(Notification).where(
            and_(
                Notification.status == NotificationStatus.FAILED,
                Notification.created_at >= cutoff_time,
                Notification.retry_count < self.settings.get("max_retries", 3)
            )
        )

        result = await self.db.execute(query)
        failed_notifications = result.scalars().all()

        retried_count = 0
        results = []

        for notification in failed_notifications:
            try:
                if background_tasks:
                    # تلاش مجدد در پس‌زمینه
                    background_tasks.add_task(
                        self._retry_notification,
                        notification.id
                    )
                else:
                    # تلاش مجدد همزمان
                    await self._retry_notification(notification.id)

                retried_count += 1
                results.append({
                    "notification_id": notification.id,
                    "success": True,
                    "message": "Retry scheduled"
                })

            except Exception as e:
                logger.error(f"Failed to schedule retry for notification {notification.id}: {str(e)}")
                results.append({
                    "notification_id": notification.id,
                    "success": False,
                    "error": str(e)
                })

        return {
            "total_failed": len(failed_notifications),
            "retried": retried_count,
            "results": results
        }

    async def get_user_unread_count(self, user: User) -> Dict[str, Any]:
        """تعداد نوتیفیکیشن‌های خوانده نشده کاربر"""

        query = select(func.count(Notification.id)).where(
            and_(
                Notification.user_id == user.id,
                Notification.read_at.is_(None)
            )
        )

        total_unread = await self.db.scalar(query)

        # بر اساس نوع
        type_query = select(
            Notification.type,
            func.count(Notification.id).label("count")
        ).where(
            and_(
                Notification.user_id == user.id,
                Notification.read_at.is_(None)
            )
        ).group_by(Notification.type)

        type_result = await self.db.execute(type_query)
        by_type = {row.type.value: row.count for row in type_result.all()}

        return {
            "user_id": user.id,
            "total_unread": total_unread or 0,
            "by_type": by_type
        }

    # ---------- Event Handlers ----------

    async def _handle_need_created(self, user_id: int, data: Dict[str, Any]) -> List[NotificationCreate]:
        """هندلر برای ایجاد نیاز جدید"""
        need_title = data.get("title", "یک نیاز جدید")
        charity_name = data.get("charity_name", "یک خیریه")

        notifications = []

        # نوتیفیکیشن برای مدیر خیریه
        notification = NotificationCreate(
            user_id=user_id,  # مدیر خیریه
            type=NotificationType.SYSTEM,
            title="نیاز جدید ثبت شد",
            message=f"نیاز «{need_title}» در خیریه شما ثبت شده و در انتظار تأیید است.",
            priority=NotificationPriority.HIGH,
            data={
                "need_id": data.get("need_id"),
                "charity_id": data.get("charity_id"),
                "action_url": f"/needs/{data.get('need_id')}/review"
            }
        )
        notifications.append(notification)

        return notifications

    async def _handle_need_urgent(self, user_id: int, data: Dict[str, Any]) -> List[NotificationCreate]:
        """هندلر برای نیاز فوری/بحران"""
        need_title = data.get("title", "یک نیاز فوری")
        emergency_type = data.get("emergency_type", "بحران")

        notifications = []

        # نوتیفیکیشن فوری برای همه خیرین فعال
        notification = NotificationCreate(
            user_id=user_id,  # در واقع به گروهی از کاربران ارسال می‌شود
            type=NotificationType.URGENT,
            title=f"‼️ نیاز فوری: {emergency_type}",
            message=f"نیاز فوری «{need_title}» ثبت شده است. برای کمک فوری اقدام کنید.",
            priority=NotificationPriority.URGENT,
            data={
                "need_id": data.get("need_id"),
                "emergency_type": emergency_type,
                "is_urgent": True,
                "action_url": f"/needs/{data.get('need_id')}"
            }
        )
        notifications.append(notification)

        # همچنین SMS ارسال کن
        sms_notification = NotificationCreate(
            user_id=user_id,
            type=NotificationType.SMS,
            title="نیاز فوری",
            message=f"نیاز فوری {need_title}. لطفا بررسی کنید.",
            priority=NotificationPriority.URGENT,
            data=data
        )
        notifications.append(sms_notification)

        return notifications

    async def _handle_donation_received(self, user_id: int, data: Dict[str, Any]) -> List[NotificationCreate]:
        """هندلر برای دریافت کمک"""
        amount = data.get("amount", 0)
        donor_name = data.get("donor_name", "یک خیر")
        need_title = data.get("need_title", "یک نیاز")

        notifications = []

        # برای نیازمند
        notification = NotificationCreate(
            user_id=user_id,
            type=NotificationType.SYSTEM,
            title="🎉 کمک جدید دریافت شد",
            message=f"{donor_name} مبلغ {amount:,} تومان به نیاز «{need_title}» کمک کرد.",
            priority=NotificationPriority.NORMAL,
            data={
                "donation_id": data.get("donation_id"),
                "amount": amount,
                "donor_name": donor_name,
                "action_url": f"/donations/{data.get('donation_id')}"
            }
        )
        notifications.append(notification)

        # برای خیر (اگر ایمیل دارد)
        if data.get("donor_email"):
            email_notification = NotificationCreate(
                user_id=data.get("donor_id"),  # ID خیر
                type=NotificationType.EMAIL,
                title="قدردانی از کمک شما",
                message=f"با تشکر از کمک {amount:,} تومانی شما به نیاز «{need_title}».",
                recipient_email=data.get("donor_email"),
                priority=NotificationPriority.NORMAL,
                data={
                    "donation_id": data.get("donation_id"),
                    "receipt_url": f"/receipts/{data.get('donation_id')}"
                }
            )
            notifications.append(email_notification)

        return notifications

    # هندلرهای دیگر...

    async def _handle_crisis_alert(self, user_id: int, data: Dict[str, Any]) -> List[NotificationCreate]:
        """هندلر برای هشدار بحران (زلزله، سیل، ...)"""
        crisis_type = data.get("crisis_type", "بحران")
        location = data.get("location", "یک منطقه")

        notifications = []

        # ارسال به همه کاربران در منطقه (در واقع bulk notification)
        notification = NotificationCreate(
            user_id=user_id,  # representative user
            type=NotificationType.URGENT,
            title=f"🚨 هشدار {crisis_type}",
            message=f"{crisis_type} در {location} گزارش شده است. برای کمک‌های اضطراری اقدام کنید.",
            priority=NotificationPriority.URGENT,
            data={
                "crisis_type": crisis_type,
                "location": location,
                "timestamp": datetime.utcnow().isoformat(),
                "action_url": "/crisis"
            }
        )
        notifications.append(notification)

        return notifications

    # ---------- Helper Methods ----------

    async def _get_user(self, user_id: int) -> User:
        """دریافت کاربر"""
        from models.user import User
        user = await self.db.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user

    async def _get_notification(self, notification_id: int) -> Notification:
        """دریافت نوتیفیکیشن"""
        notification = await self.db.get(Notification, notification_id)
        if not notification:
            raise HTTPException(status_code=404, detail="Notification not found")
        return notification

    async def _check_user_preferences(self, user: User, notification_type: NotificationType) -> bool:
        """بررسی تنظیمات نوتیفیکیشن کاربر"""

        # دریافت تنظیمات کاربر
        result = await self.db.execute(
            select(NotificationPreference).where(
                NotificationPreference.user_id == user.id
            )
        )
        preference = result.scalar_one_or_none()

        if not preference:
            # اگر تنظیمات وجود ندارد، پیش‌فرض‌ها را ایجاد کن
            return True

        # بررسی بر اساس نوع
        if notification_type == NotificationType.EMAIL:
            return preference.email_enabled
        elif notification_type == NotificationType.SMS:
            return preference.sms_enabled
        elif notification_type == NotificationType.PUSH:
            return preference.push_enabled
        elif notification_type == NotificationType.SYSTEM:
            return preference.system_enabled
        elif notification_type == NotificationType.URGENT:
            # نوتیفیکیشن‌های فوری همیشه ارسال می‌شوند
            return True

        return True

    async def _is_quiet_hours(self, user: User) -> bool:
        """بررسی ساعات آرام کاربر"""

        result = await self.db.execute(
            select(NotificationPreference).where(
                NotificationPreference.user_id == user.id
            )
        )
        preference = result.scalar_one_or_none()

        if not preference or not preference.quiet_hours_enabled:
            return False

        now = datetime.utcnow()
        current_time = now.strftime("%H:%M")

        if preference.quiet_hours_start and preference.quiet_hours_end:
            return preference.quiet_hours_start <= current_time <= preference.quiet_hours_end

        return False

    async def _prepare_recipient_data(self, user: User, notification_data: NotificationCreate) -> Dict[str, Any]:
        """آماده‌سازی داده‌های گیرنده"""

        recipient_data = {}

        # ایمیل
        if notification_data.type == NotificationType.EMAIL:
            recipient_data["email"] = notification_data.recipient_email or user.email

        # SMS
        elif notification_data.type == NotificationType.SMS:
            recipient_data["phone"] = notification_data.recipient_phone or user.phone

        # Push
        elif notification_data.type == NotificationType.PUSH:
            # در حالت واقعی از جدول user_devices خوانده می‌شود
            recipient_data["device_token"] = notification_data.recipient_device_token

        return recipient_data

    async def _process_notification(self, notification_id: int):
        """پردازش و ارسال نوتیفیکیشن"""

        notification = await self._get_notification(notification_id)

        try:
            # بررسی اگر قبلاً ارسال شده
            if notification.status != NotificationStatus.PENDING:
                return

            # بررسی انقضا
            if notification.expires_at and notification.expires_at < datetime.utcnow():
                notification.status = NotificationStatus.CANCELLED
                self.db.add(notification)
                await self.db.commit()
                return

            # انتخاب provider بر اساس نوع
            provider = self.providers.get(notification.type.value)
            if not provider:
                raise Exception(f"No provider for notification type: {notification.type}")

            # ارسال
            success, result = await provider(notification)

            if success:
                notification.status = NotificationStatus.SENT
                notification.sent_at = datetime.utcnow()
                notification.sent_via = result.get("provider")
                notification.external_id = result.get("external_id")
                notification.delivery_receipt = result
            else:
                notification.status = NotificationStatus.FAILED

                # افزایش شمارش تلاش‌ها
                if not hasattr(notification, 'retry_count'):
                    notification.retry_count = 0
                notification.retry_count += 1

            self.db.add(notification)
            await self.db.commit()

            logger.info(f"Notification {notification_id} processed: {notification.status}")

        except Exception as e:
            logger.error(f"Failed to process notification {notification_id}: {str(e)}")

            notification.status = NotificationStatus.FAILED
            self.db.add(notification)
            await self.db.commit()

    async def _schedule_notification(self, notification_id: int):
        """زمان‌بندی نوتیفیکیشن برای آینده"""
        # در حالت واقعی از celery یا RQ استفاده می‌شود
        # اینجا فقط لاگ می‌کنیم
        logger.info(f"Notification {notification_id} scheduled for future delivery")

    async def _send_individual_notification(self, notification_data: NotificationCreate):
        """ارسال نوتیفیکیشن جداگانه (برای bulk)"""
        try:
            await self.send_notification(notification_data)
        except Exception as e:
            logger.error(f"Failed to send individual notification: {str(e)}")

    async def _retry_notification(self, notification_id: int):
        """تلاش مجدد برای نوتیفیکیشن ناموفق"""
        notification = await self._get_notification(notification_id)

        if notification.status == NotificationStatus.FAILED:
            # بازنشانی وضعیت
            notification.status = NotificationStatus.PENDING
            self.db.add(notification)
            await self.db.commit()

            # پردازش مجدد
            await self._process_notification(notification_id)

    def _get_next_available_time(self) -> datetime:
        """زمان بعدی قابل دسترس (بعد از ساعات آرام)"""
        now = datetime.utcnow()
        # فرض می‌کنیم ساعات آرام تا ساعت 7 صبح است
        if now.hour < 7:
            # اگر قبل از 7 صبح است، برای 7 صبح زمان‌بندی کن
            next_time = now.replace(hour=7, minute=0, second=0, microsecond=0)
        else:
            # برای فردا 7 صبح
            next_time = (now + timedelta(days=1)).replace(hour=7, minute=0, second=0, microsecond=0)

        return next_time

    def _load_settings(self) -> Dict[str, Any]:
        """بارگذاری تنظیمات"""
        import os
        return {
            "max_retries": int(os.getenv("NOTIFICATION_MAX_RETRIES", 3)),
            "email_provider": os.getenv("EMAIL_PROVIDER", "console"),
            "sms_provider": os.getenv("SMS_PROVIDER", "console"),
            "push_provider": os.getenv("PUSH_PROVIDER", "console"),
            "api_keys": {
                "kavenegar": os.getenv("KAVENEGAR_API_KEY"),
                "twilio_sid": os.getenv("TWILIO_ACCOUNT_SID"),
                "twilio_token": os.getenv("TWILIO_AUTH_TOKEN"),
                "firebase": os.getenv("FIREBASE_SERVER_KEY")
            }
        }

    # ---------- Provider Implementations ----------

    async def _send_email(self, notification: Notification) -> Tuple[bool, Dict[str, Any]]:
        """ارسال ایمیل"""

        # در حالت واقعی با SMTP یا سرویس ایمیل ارسال می‌شود
        # اینجا یک پیاده‌سازی نمونه

        provider = self.settings["email_provider"]

        if provider == "console":
            # فقط لاگ کنسول
            logger.info(f"📧 Email to {notification.recipient_email}: {notification.title}")
            logger.info(f"Message: {notification.message}")

            return True, {
                "provider": "console",
                "external_id": str(uuid.uuid4()),
                "timestamp": datetime.utcnow().isoformat()
            }

        elif provider == "smtp":
            # ارسال واقعی با SMTP
            try:
                # import smtplib
                # from email.mime.text import MIMEText
                # ...
                pass
            except Exception as e:
                logger.error(f"Failed to send email: {str(e)}")
                return False, {"error": str(e)}

        return False, {"error": "Email provider not configured"}

    async def _send_sms(self, notification: Notification) -> Tuple[bool, Dict[str, Any]]:
        """ارسال SMS"""

        provider = self.settings["sms_provider"]

        if provider == "console":
            # فقط لاگ کنسول
            logger.info(f"📱 SMS to {notification.recipient_phone}: {notification.message}")

            return True, {
                "provider": "console",
                "external_id": str(uuid.uuid4()),
                "timestamp": datetime.utcnow().isoformat()
            }

        elif provider == "kavenegar":
            # ارسال با Kavenegar API
            api_key = self.settings["api_keys"].get("kavenegar")
            if not api_key:
                return False, {"error": "Kavenegar API key not configured"}

            try:
                # async with aiohttp.ClientSession() as session:
                #     async with session.post(...)
                pass
            except Exception as e:
                logger.error(f"Failed to send SMS via Kavenegar: {str(e)}")
                return False, {"error": str(e)}

        return False, {"error": "SMS provider not configured"}

    async def _send_push(self, notification: Notification) -> Tuple[bool, Dict[str, Any]]:
        """ارسال Push Notification"""

        provider = self.settings["push_provider"]

        if provider == "console":
            logger.info(f"📲 Push to device {notification.recipient_device_token}: {notification.title}")

            return True, {
                "provider": "console",
                "external_id": str(uuid.uuid4()),
                "timestamp": datetime.utcnow().isoformat()
            }

        return False, {"error": "Push provider not configured"}

    async def _send_system(self, notification: Notification) -> Tuple[bool, Dict[str, Any]]:
        """ارسال نوتیفیکیشن سیستم"""
        # نوتیفیکیشن‌های سیستم فقط در دیتابیس ذخیره می‌شوند
        logger.info(f"🔔 System notification for user {notification.user_id}: {notification.title}")

        return True, {
            "provider": "system",
            "timestamp": datetime.utcnow().isoformat()
        }

    async def _send_urgent(self, notification: Notification) -> Tuple[bool, Dict[str, Any]]:
        """ارسال نوتیفیکیشن فوری"""
        # نوتیفیکیشن‌های فوری از چندین کانال ارسال می‌شوند

        results = []

        # 1. سیستم
        system_success, system_result = await self._send_system(notification)
        results.append({"type": "system", "success": system_success, "result": system_result})

        # 2. ایمیل (اگر کاربر ایمیل دارد و اجازه داده)
        if notification.recipient_email:
            email_success, email_result = await self._send_email(notification)
            results.append({"type": "email", "success": email_success, "result": email_result})

        # 3. SMS (اگر کاربر شماره دارد و اجازه داده)
        if notification.recipient_phone:
            sms_success, sms_result = await self._send_sms(notification)
            results.append({"type": "sms", "success": sms_success, "result": sms_result})

        # اگر حداقل یک کانال موفق بود
        overall_success = any(r["success"] for r in results)

        return overall_success, {
            "provider": "multi-channel",
            "results": results,
            "timestamp": datetime.utcnow().isoformat()
        }