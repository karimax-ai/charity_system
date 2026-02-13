# app/api/v1/router.py
from fastapi import APIRouter
from api.v1.endpoints import (

    # ========= Auth & Users =========
    auth,
    roles,

    # ========= Charity & Needs =========
    charity,
    need_ad,
    need_emergency,
    need_attachments,

    # ========= Donations & Payments =========
    donation,

    # ========= Shop & Orders =========
    shop,
    product,
    order,

    # ========= Dashboard & Reports =========
    dashboard,
    report,
    export,

    # ========= Notifications & Files =========
    notification,
    files,

    # ========= Campaigns =========
    campaign,

    # ========= Frontend =========
)

api_router = APIRouter()

# ======================================================
# 1️⃣ Authentication & Authorization
# ======================================================
api_router.include_router(
    auth.router,
    prefix="/auth",
    tags=["Authentication"]
)

api_router.include_router(
    roles.router,
    prefix="/roles",
    tags=["Roles & Permissions"]
)

# ======================================================
# 2️⃣ Charities & Needs
# ======================================================
api_router.include_router(
    charity.router,
    prefix="/charities",
    tags=["Charities"]
)

api_router.include_router(
    need_ad.router,
    prefix="/needs",
    tags=["Needs"]
)

api_router.include_router(
    need_emergency.router,
    prefix="/needs/emergency",
    tags=["Needs - Emergency"]
)

api_router.include_router(
    need_attachments.router,
    prefix="/needs/attachments",
    tags=["Needs - Attachments"]
)

# ======================================================
# 3️⃣ Donations & Payments
# ======================================================
api_router.include_router(
    donation.router,
    prefix="/donations",
    tags=["Donations & Payments"]
)

# ======================================================
# 4️⃣ Shops, Products & Orders
# ======================================================
api_router.include_router(
    shop.router,
    prefix="/shops",
    tags=["Shops"]
)

api_router.include_router(
    product.router,
    prefix="/products",
    tags=["Products"]
)

api_router.include_router(
    order.router,
    prefix="/orders",
    tags=["Orders"]
)

# ======================================================
# 5️⃣ Dashboard, Reports & Export
# ======================================================
api_router.include_router(
    dashboard.router,
    prefix="/dashboard",
    tags=["Dashboard"]
)

api_router.include_router(
    report.router,
    prefix="/reports",
    tags=["Reports"]
)

api_router.include_router(
    export.router,
    prefix="/exports",
    tags=["Export"]
)

# ======================================================
# 6️⃣ Notifications & Files
# ======================================================
api_router.include_router(
    notification.router,
    prefix="/notifications",
    tags=["Notifications"]
)

api_router.include_router(
    files.router,
    prefix="/files",
    tags=["Files"]
)

# ======================================================
# 7️⃣ Campaigns (Peer-to-Peer)
# ======================================================
api_router.include_router(
    campaign.router,
    prefix="/campaigns",
    tags=["Campaigns"]
)

