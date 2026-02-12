# app/models/user.py
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, func, ForeignKey, Float, Enum, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import uuid
import enum
from models.base import Base


class UserStatus(str, enum.Enum):
    """وضعیت کاربر"""
    ACTIVE = "active"  # فعال و تأیید شده
    NEED_VERIFICATION = "need_verification"  # مدارک ارسال شده، تأیید نشده
    SUSPENDED = "suspended"  # مسدود
    REJECTED = "rejected"  # رد شده
    PENDING = "pending"  # در انتظار تأیید


class UserGender(str, enum.Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class User(Base):
    __tablename__ = "users"

    # ---------- شناسه‌ها ----------
    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))

    # ---------- اطلاعات پایه ----------
    email = Column(String(255), unique=True, index=True, nullable=False)
    phone = Column(String(20), unique=True, nullable=True, index=True)
    username = Column(String(50), unique=True, nullable=True, index=True)

    # ---------- نام و نام خانوادگی ----------
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    full_name = Column(String(200), nullable=True)  # برای نمایش سریع
    national_id = Column(String(20), unique=True, nullable=True)  # کد ملی
    gender = Column(Enum(UserGender), nullable=True)
    birth_date = Column(DateTime(timezone=True), nullable=True)

    # ---------- احراز هویت ----------
    hashed_password = Column(String(255), nullable=True)  # nullable برای OAuth
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)  # ایمیل/شماره تأیید شده
    is_superuser = Column(Boolean, default=False, nullable=False)

    # ---------- نقش و وضعیت ----------
    status = Column(
        Enum(UserStatus, name="user_status"),
        default=UserStatus.PENDING,
        nullable=False
    )
    status_reason = Column(String(500), nullable=True)

    # ---------- پروفایل ----------
    avatar_url = Column(String(500), nullable=True)
    bio = Column(Text, nullable=True)  # درباره من
    address = Column(Text, nullable=True)
    city = Column(String(100), nullable=True)
    province = Column(String(100), nullable=True)
    postal_code = Column(String(20), nullable=True)
    website = Column(String(500), nullable=True)

    # ---------- تنظیمات ----------
    language = Column(String(10), default="fa")
    theme = Column(String(20), default="light")
    settings = Column(JSON, default=dict)  # تنظیمات اضافی

    # ---------- 2FA و امنیت ----------
    two_fa_enabled = Column(Boolean, default=False)
    two_fa_secret = Column(String(32), nullable=True)
    two_fa_method = Column(String(20), default="app")  # app, sms, email
    two_fa_backup_codes = Column(JSON, default=list)  # کدهای پشتیبان

    # ---------- امنیت و ضد تقلب ----------
    failed_login_attempts = Column(Integer, default=0)
    last_login_ip = Column(String(45), nullable=True)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    last_login_user_agent = Column(String(500), nullable=True)
    locked_until = Column(DateTime(timezone=True), nullable=True)
    email_verified_at = Column(DateTime(timezone=True), nullable=True)
    phone_verified_at = Column(DateTime(timezone=True), nullable=True)

    # ---------- توکن‌ها ----------
    refresh_token = Column(String(512), nullable=True)
    refresh_token_expires = Column(DateTime(timezone=True), nullable=True)
    email_verification_token = Column(String(255), nullable=True)
    password_reset_token = Column(String(255), nullable=True)
    password_reset_expires = Column(DateTime(timezone=True), nullable=True)

    # ---------- دستگاه‌های معتبر ----------
    trusted_devices = Column(JSON, default=list)  # لیست device_id‌ها
    fcm_tokens = Column(JSON, default=list)  # برای نوتیفیکیشن

    # ---------- احراز هویت با مدارک ----------
    verification_documents = relationship(
        "VerificationDocument",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    verified_at = Column(DateTime(timezone=True), nullable=True)
    verified_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    verification_notes = Column(Text, nullable=True)

    # ---------- شبکه‌های اجتماعی ----------
    social_links = Column(JSON, default=dict)  # {telegram: "...", instagram: "...", ...}

    # ---------- آمار کاربر ----------
    total_donations = Column(Float, default=0.0)
    donations_count = Column(Integer, default=0)
    total_sponsored = Column(Float, default=0.0)  # کفالت
    sponsored_count = Column(Integer, default=0)
    total_needs = Column(Integer, default=0)  # تعداد نیازهای ثبت شده
    completed_needs = Column(Integer, default=0)  # نیازهای تکمیل شده
    trust_score = Column(Float, default=0.0)  # امتیاز اعتماد 0-100
    reputation = Column(Integer, default=0)  # اعتبار اجتماعی

    # ---------- نشان‌ها و افتخارات ----------
    badges = Column(JSON, default=list)  # لیست نشان‌ها
    badge_level = Column(String(20), default="bronze")  # bronze, silver, gold, platinum

    # ---------- زمان‌ها ----------
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)  # soft delete

    # ========== روابط (Relationships) ==========

    # ---------- نقش‌ها و دسترسی‌ها ----------
    roles = relationship(
        "Role",
        secondary="user_roles",
        lazy="selectin",
        back_populates="users"
    )

    # ---------- نیازها ----------
    needs_created = relationship(
        "NeedAd",
        foreign_keys="NeedAd.created_by_id",
        back_populates="creator",
        cascade="all, delete-orphan"
    )

    needs_as_needy = relationship(
        "NeedAd",
        foreign_keys="NeedAd.needy_user_id",
        back_populates="needy_user"
    )

    # ---------- کمک‌ها ----------
    donations_made = relationship(
        "Donation",
        foreign_keys="Donation.donor_id",
        back_populates="donor",
        cascade="all, delete-orphan"
    )

    # ---------- خیریه‌ها ----------
    managed_charities = relationship(
        "Charity",
        foreign_keys="Charity.manager_id",
        back_populates="manager"
    )

    # ---------- فروشگاه‌ها ----------
    shops = relationship(
        "Shop",
        secondary="shop_vendors",
        back_populates="vendors"
    )

    managed_shops = relationship(
        "Shop",
        foreign_keys="Shop.manager_id",
        back_populates="manager"
    )

    # ---------- محصولات ----------
    products = relationship(
        "Product",
        foreign_keys="Product.vendor_id",
        back_populates="vendor",
        cascade="all, delete-orphan"
    )

    # ---------- سفارشات ----------
    orders = relationship(
        "Order",
        foreign_keys="Order.customer_id",
        back_populates="customer",
        cascade="all, delete-orphan"
    )

    # ---------- سبد خرید ----------
    carts = relationship(
        "Cart",
        foreign_keys="Cart.user_id",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    # ---------- نظرات ----------
    need_comments = relationship(
        "NeedComment",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    # ---------- تأییدکننده مدارک ----------
    verified_users = relationship(
        "User",
        foreign_keys=[verified_by],
        remote_side=[id],
        backref="verifier"
    )

    # ---------- کفالت‌ها ----------
    sponsorships_given = relationship(
        "Sponsorship",
        foreign_keys="Sponsorship.sponsor_id",
        back_populates="sponsor",
        cascade="all, delete-orphan"
    )

    sponsorships_received = relationship(
        "Sponsorship",
        foreign_keys="Sponsorship.needy_id",
        back_populates="needy",
        cascade="all, delete-orphan"
    )

    # ---------- نوتیفیکیشن‌ها ----------
    notifications = relationship(
        "Notification",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    notification_preferences = relationship(
        "NotificationPreference",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan"
    )

    # ---------- فایل‌ها ----------
    uploaded_files = relationship(
        "FileAttachment",
        foreign_keys="FileAttachment.uploaded_by",
        back_populates="uploader",
        cascade="all, delete-orphan"
    )

    # ========== متدهای کمکی ==========

    @property
    def display_name(self) -> str:
        """نام نمایشی کاربر"""
        if self.full_name:
            return self.full_name
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        if self.username:
            return self.username
        return self.email.split('@')[0]

    @property
    def is_needy(self) -> bool:
        """آیا کاربر نیازمند است؟"""
        return any(role.key == "NEEDY" for role in self.roles)

    @property
    def is_donor(self) -> bool:
        """آیا کاربر خیر است؟"""
        return any(role.key == "DONOR" for role in self.roles)

    @property
    def is_vendor(self) -> bool:
        """آیا کاربر فروشنده است؟"""
        return any(role.key == "VENDOR" for role in self.roles)

    @property
    def is_charity_manager(self) -> bool:
        """آیا کاربر مدیر خیریه است؟"""
        return any(role.key == "CHARITY_MANAGER" for role in self.roles)

    @property
    def is_admin(self) -> bool:
        """آیا کاربر ادمین است؟"""
        return any(role.key in ["ADMIN", "SUPER_ADMIN"] for role in self.roles)

    @property
    def is_volunteer(self) -> bool:
        """آیا کاربر داوطلب است؟"""
        return any(role.key == "VOLUNTEER" for role in self.roles)

    @property
    def is_shop_manager(self) -> bool:
        """آیا کاربر مدیر فروشگاه است؟"""
        return any(role.key == "SHOP_MANAGER" for role in self.roles)