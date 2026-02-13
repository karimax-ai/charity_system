# constants.py - جایگزین کامل

ROLES = {
    "SUPER_ADMIN": "ادمین اصلی (دسترسی کامل)",
    "CHARITY_MANAGER": "مدیر خیریه‌ها - مدیریت چندین خیریه",
    "CHARITY": "خیریه - سازمان خیریه مستقل",
    "DONOR": "خیر کمک‌کننده - اهداکننده کمک‌های نقدی و غیرنقدی",
    "NEEDY": "نیازمند - دریافت‌کننده کمک",
    "VENDOR": "فروشنده - ارائه‌دهنده محصولات با مشارکت خیریه",
    "SHOP_MANAGER": "مدیر فروشگاه - نظارت بر فروشنده‌ها و محصولات",
    "VOLUNTEER": "داوطلب - کمک در مدیریت آگهی‌ها بدون دسترسی کامل",
    "USER": "کاربر عادی - ثبت‌نام‌کرده بدون نقش خاص",
}

PERMISSIONS = {
    # Users
    "user.read": "مشاهده کاربران",
    "user.create": "ایجاد کاربر",
    "user.update": "ویرایش کاربر",
    "user.delete": "حذف کاربر",

    # Needs
    "need.create": "ایجاد آگهی نیاز",
    "need.update": "ویرایش آگهی نیاز",
    "need.delete": "حذف آگهی نیاز",
    "need.approve": "تأیید آگهی نیاز",
    "need.view_private": "مشاهده آگهی‌های خصوصی",
    "need.view_public": "مشاهده آگهی‌های عمومی",  # ✅ جدید برای GUEST

    # Donations
    "donation.create": "ایجاد کمک",
    "donation.view": "مشاهده کمک‌ها",

    # Products / Shop
    "product.create": "ایجاد محصول",
    "product.sell": "فروش محصول",
    "shop.manage": "مدیریت فروشگاه",  # ✅ جدید
    "shop.charity_percentage": "تنظیم درصد مشارکت خیریه",  # ✅ جدید

    # Verification
    "verification.review": "بررسی مدارک احراز هویت",  # ✅ جدید
    "verification.bypass": "احراز هویت بدون مدرک",  # ✅ جدید

    # Reports
    "report.view": "مشاهده گزارشات",

    # Volunteer
    "need.manage_as_volunteer": "مدیریت آگهی‌ها به عنوان داوطلب",  # ✅ جدید
}