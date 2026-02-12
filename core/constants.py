# constants.py

ROLES = {
    "SUPER_ADMIN": "Super admin (full access)",
    "CHARITY_MANAGER": "Charity manager",
    "CHARITY": "Charity organization",
    "DONOR": "Donor",
    "NEEDY": "Needy user",
    "VENDOR": "Vendor",
    "SHOP_MANAGER": "Shop manager",
    "VOLUNTEER": "Volunteer",
    "USER": "Normal user",
    "GUEST": "Guest user (unauthenticated)",  # ✅ اینو اضافه کن
}

PERMISSIONS = {
    # Users
    "user.read": "Read users",
    "user.create": "Create user",
    "user.update": "Update user",
    "user.delete": "Delete user",

    # Needs
    "need.create": "Create need advertisement",
    "need.update": "Update need",
    "need.delete": "Delete need",
    "need.approve": "Approve need",
    "need.view_private": "View private need",

    # Donations
    "donation.create": "Create donation",
    "donation.view": "View donations",

    # Reports
    "report.view": "View reports",

    # Products / Shop
    "product.create": "Create product",
    "product.sell": "Sell product",
}
