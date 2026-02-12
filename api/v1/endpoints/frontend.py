# app/api/v1/endpoints/frontend.py
from fastapi import APIRouter, Request, Form, Depends, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import httpx
from typing import Optional
import os

router = APIRouter()

# تنظیمات
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
TEMPLATES_DIR = os.path.join(BASE_DIR, "frontend", "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

API_URL = "http://localhost:8000/api/v1"


# ==================== صفحات فرانت‌اند ====================

@router.get("/", response_class=HTMLResponse)
async def home_page(request: Request):
    """صفحه اصلی"""
    return templates.TemplateResponse("home.html", {"request": request})


# ==================== ثبت‌نام ====================

@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    """صفحه ثبت‌نام"""
    roles = [
        {"key": "USER", "name": "👤 کاربر عادی"},
        {"key": "DONOR", "name": "💰 خیر کمک‌کننده"},
        {"key": "NEEDY", "name": "🆘 نیازمند"},
        {"key": "VENDOR", "name": "🏪 فروشنده/فروشگاه"},
        {"key": "CHARITY", "name": "🏛️ خیریه"},
        {"key": "VOLUNTEER", "name": "🤝 داوطلب"}
    ]
    return templates.TemplateResponse("auth/register.html", {
        "request": request,
        "roles": roles
    })


@router.post("/register")
async def register_submit(
        request: Request,
        full_name: str = Form(...),
        email: str = Form(...),
        phone: str = Form(...),
        password: str = Form(...),
        confirm_password: str = Form(...),
        role: str = Form(...)
):
    """ثبت‌نام کاربر جدید"""
    if password != confirm_password:
        return templates.TemplateResponse("auth/register.html", {
            "request": request,
            "error": "رمز عبور و تأیید آن مطابقت ندارند",
            "form_data": {
                "full_name": full_name,
                "email": email,
                "phone": phone,
                "role": role
            }
        })

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{API_URL}/auth/register",
                json={
                    "email": email,
                    "password": password,
                    "username": full_name,
                    "phone": phone,
                    "role_key": role
                },
                timeout=30.0
            )

            if response.status_code == 200:
                data = response.json()

                # بررسی وضعیت کاربر
                if data.get("status") == "NEED_VERIFICATION":
                    return templates.TemplateResponse("auth/verification_pending.html", {
                        "request": request,
                        "message": "✅ ثبت‌نام موفق! حساب شما نیاز به تأیید مدیریت دارد. پس از تأیید، می‌توانید وارد شوید.",
                        "user_type": "نیازمند" if role == "NEEDY" else "فروشنده"
                    })

                # ذخیره توکن و ریدایرکت
                resp = RedirectResponse("/dashboard", status_code=303)
                if data.get("access_token"):
                    resp.set_cookie(
                        key="access_token",
                        value=data["access_token"],
                        httponly=True,
                        max_age=24 * 60 * 60,
                        secure=False,
                        samesite="lax"
                    )
                return resp
            else:
                error_data = response.json()
                return templates.TemplateResponse("auth/register.html", {
                    "request": request,
                    "error": error_data.get("detail", "خطا در ثبت‌نام"),
                    "form_data": {
                        "full_name": full_name,
                        "email": email,
                        "phone": phone,
                        "role": role
                    }
                })

        except Exception as e:
            return templates.TemplateResponse("auth/register.html", {
                "request": request,
                "error": f"خطا در ارتباط با سرور: {str(e)}",
                "form_data": {
                    "full_name": full_name,
                    "email": email,
                    "phone": phone,
                    "role": role
                }
            })


# ==================== ورود ====================

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """صفحه ورود"""
    return templates.TemplateResponse("auth/login.html", {"request": request})


@router.post("/login")
async def login_submit(
        request: Request,
        email: str = Form(...),
        password: str = Form(...),
        remember_me: Optional[str] = Form(None)
):
    """ورود کاربر"""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{API_URL}/auth/login",
                json={"email": email, "password": password},
                timeout=30.0
            )

            if response.status_code == 200:
                data = response.json()

                # بررسی نیاز به 2FA
                if data.get("status") == "2FA_REQUIRED":
                    resp = RedirectResponse("/2fa-verify", status_code=303)
                    resp.set_cookie(key="pending_auth", value=email, httponly=True)
                    return resp

                # بررسی نیاز به تأیید
                if data.get("status") == "NEED_VERIFICATION":
                    return templates.TemplateResponse("auth/verification_pending.html", {
                        "request": request,
                        "message": "حساب شما هنوز توسط مدیریت تأیید نشده است. لطفاً منتظر تأیید بمانید."
                    })

                # ورود موفق
                resp = RedirectResponse("/dashboard", status_code=303)
                max_age = 30 * 24 * 60 * 60 if remember_me else 24 * 60 * 60
                resp.set_cookie(
                    key="access_token",
                    value=data["access_token"],
                    httponly=True,
                    max_age=max_age,
                    secure=False,
                    samesite="lax"
                )
                return resp
            else:
                error_data = response.json()
                return templates.TemplateResponse("auth/login.html", {
                    "request": request,
                    "error": error_data.get("detail", "ایمیل یا رمز عبور نامعتبر است"),
                    "email": email
                })

        except Exception as e:
            return templates.TemplateResponse("auth/login.html", {
                "request": request,
                "error": f"خطا در ارتباط با سرور: {str(e)}",
                "email": email
            })


# ==================== ورود با OTP ====================

@router.get("/login/otp", response_class=HTMLResponse)
async def otp_login_page(request: Request):
    """ورود با کد یکبار مصرف"""
    return templates.TemplateResponse("auth/otp_login.html", {"request": request})


@router.post("/request-otp")
async def request_otp_submit(
        request: Request,
        phone: str = Form(...)
):
    """درخواست کد OTP"""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{API_URL}/auth/otp/request",
                json={"phone": phone}
            )

            if response.status_code == 200:
                return templates.TemplateResponse("auth/otp_verify.html", {
                    "request": request,
                    "phone": phone,
                    "success": "✅ کد تأیید ۶ رقمی به شماره شما ارسال شد",
                    "timer": 300  # 5 دقیقه
                })
            else:
                return templates.TemplateResponse("auth/otp_login.html", {
                    "request": request,
                    "phone": phone,
                    "error": "خطا در ارسال کد تأیید"
                })

        except Exception as e:
            return templates.TemplateResponse("auth/otp_login.html", {
                "request": request,
                "phone": phone,
                "error": f"خطا در ارتباط با سرور: {str(e)}"
            })


@router.post("/verify-otp")
async def verify_otp_submit(
        request: Request,
        phone: str = Form(...),
        code: str = Form(...)
):
    """تأیید کد OTP"""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{API_URL}/auth/otp/verify",
                json={"phone": phone, "code": code}
            )

            if response.status_code == 200:
                data = response.json()
                resp = RedirectResponse("/dashboard", status_code=303)
                resp.set_cookie(
                    key="access_token",
                    value=data["access_token"],
                    httponly=True,
                    max_age=24 * 60 * 60,
                    secure=False,
                    samesite="lax"
                )
                return resp
            else:
                error_data = response.json()
                return templates.TemplateResponse("auth/otp_verify.html", {
                    "request": request,
                    "phone": phone,
                    "error": error_data.get("detail", "کد تأیید نامعتبر است")
                })

        except Exception as e:
            return templates.TemplateResponse("auth/otp_verify.html", {
                "request": request,
                "phone": phone,
                "error": f"خطا در ارتباط با سرور: {str(e)}"
            })


# ==================== 2FA ====================

@router.get("/2fa/enable", response_class=HTMLResponse)
async def enable_2fa_page(
        request: Request,
        access_token: Optional[str] = Cookie(None)
):
    """فعال‌سازی احراز دو مرحله‌ای"""
    if not access_token:
        return RedirectResponse("/login")

    return templates.TemplateResponse("auth/2fa_enable.html", {"request": request})


@router.post("/enable-2fa")
async def enable_2fa_submit(
        request: Request,
        access_token: Optional[str] = Cookie(None)
):
    """فعال‌سازی 2FA"""
    if not access_token:
        return RedirectResponse("/login")

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{API_URL}/auth/2fa/enable",
                headers={"Authorization": f"Bearer {access_token}"}
            )

            if response.status_code == 200:
                data = response.json()
                return templates.TemplateResponse("auth/2fa_show_qr.html", {
                    "request": request,
                    "qr_code": data.get("qr_code"),
                    "secret": data.get("secret")
                })
            else:
                error_data = response.json()
                return templates.TemplateResponse("auth/2fa_enable.html", {
                    "request": request,
                    "error": error_data.get("detail", "خطا در فعال‌سازی 2FA")
                })

        except Exception as e:
            return templates.TemplateResponse("auth/2fa_enable.html", {
                "request": request,
                "error": f"خطا در ارتباط با سرور: {str(e)}"
            })


@router.get("/2fa-verify", response_class=HTMLResponse)
async def verify_2fa_page(request: Request):
    """تأیید کد 2FA"""
    pending_auth = request.cookies.get("pending_auth")
    if not pending_auth:
        return RedirectResponse("/login")

    return templates.TemplateResponse("auth/2fa_verify.html", {
        "request": request,
        "email": pending_auth
    })


@router.post("/verify-2fa")
async def verify_2fa_submit(
        request: Request,
        code: str = Form(...)
):
    """تأیید کد 2FA"""
    pending_auth = request.cookies.get("pending_auth")
    if not pending_auth:
        return RedirectResponse("/login")

    async with httpx.AsyncClient() as client:
        try:
            # ابتدا با رمز عبور وارد شویم تا توکن بگیریم
            login_response = await client.post(
                f"{API_URL}/auth/login",
                json={"email": pending_auth, "password": "dummy"}  # باید ذخیره شده باشد
            )

            if login_response.status_code != 200:
                return RedirectResponse("/login")

            token_data = login_response.json()
            temp_token = token_data.get("access_token")

            # تأیید 2FA
            response = await client.post(
                f"{API_URL}/auth/2fa/verify",
                json={"token": code},
                headers={"Authorization": f"Bearer {temp_token}"}
            )

            if response.status_code == 200:
                resp = RedirectResponse("/dashboard", status_code=303)
                resp.delete_cookie("pending_auth")
                return resp
            else:
                error_data = response.json()
                return templates.TemplateResponse("auth/2fa_verify.html", {
                    "request": request,
                    "email": pending_auth,
                    "error": error_data.get("detail", "کد تأیید نامعتبر است")
                })

        except Exception as e:
            return templates.TemplateResponse("auth/2fa_verify.html", {
                "request": request,
                "email": pending_auth,
                "error": f"خطا در ارتباط با سرور: {str(e)}"
            })


# ==================== بازیابی رمز عبور ====================

@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request):
    """فراموشی رمز عبور"""
    return templates.TemplateResponse("auth/forgot_password.html", {"request": request})


@router.post("/reset-password-request")
async def reset_password_request_submit(
        request: Request,
        email: str = Form(...)
):
    """درخواست بازیابی رمز عبور"""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{API_URL}/auth/password/reset/request",
                json={"email": email}
            )

            if response.status_code == 200:
                return templates.TemplateResponse("auth/reset_password.html", {
                    "request": request,
                    "email": email,
                    "success": "✅ کد بازیابی به ایمیل شما ارسال شد"
                })
            else:
                return templates.TemplateResponse("auth/forgot_password.html", {
                    "request": request,
                    "email": email,
                    "error": "کاربری با این ایمیل یافت نشد"
                })

        except Exception as e:
            return templates.TemplateResponse("auth/forgot_password.html", {
                "request": request,
                "email": email,
                "error": f"خطا در ارتباط با سرور: {str(e)}"
            })


@router.post("/reset-password")
async def reset_password_submit(
        request: Request,
        email: str = Form(...),
        otp: str = Form(...),
        new_password: str = Form(...),
        confirm_password: str = Form(...)
):
    """تغییر رمز عبور"""
    if new_password != confirm_password:
        return templates.TemplateResponse("auth/reset_password.html", {
            "request": request,
            "email": email,
            "error": "رمز عبور و تأیید آن مطابقت ندارند"
        })

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{API_URL}/auth/password/reset/verify",
                json={
                    "email": email,
                    "otp": otp,
                    "new_password": new_password
                }
            )

            if response.status_code == 200:
                return templates.TemplateResponse("auth/reset_password_success.html", {
                    "request": request,
                    "success": "✅ رمز عبور شما با موفقیت تغییر کرد"
                })
            else:
                error_data = response.json()
                return templates.TemplateResponse("auth/reset_password.html", {
                    "request": request,
                    "email": email,
                    "error": error_data.get("detail", "کد تأیید نامعتبر است")
                })

        except Exception as e:
            return templates.TemplateResponse("auth/reset_password.html", {
                "request": request,
                "email": email,
                "error": f"خطا در ارتباط با سرور: {str(e)}"
            })


# ==================== داشبورد ====================

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(
        request: Request,
        access_token: Optional[str] = Cookie(None)
):
    """داشبورد کاربر"""
    if not access_token:
        return RedirectResponse("/login")

    async with httpx.AsyncClient() as client:
        try:
            # دریافت اطلاعات کاربر
            user_response = await client.get(
                f"{API_URL}/users/me",
                headers={"Authorization": f"Bearer {access_token}"}
            )

            if user_response.status_code != 200:
                resp = RedirectResponse("/login")
                resp.delete_cookie("access_token")
                return resp

            user_data = user_response.json()

            # تشخیص نوع داشبورد بر اساس نقش
            roles = user_data.get("roles", [])

            if "ADMIN" in roles:
                template_name = "dashboard/admin_dashboard.html"
                dashboard_type = "ادمین اصلی"
            elif "CHARITY_MANAGER" in roles:
                template_name = "dashboard/charity_manager_dashboard.html"
                dashboard_type = "مدیر خیریه‌ها"
            elif "CHARITY" in roles:
                template_name = "dashboard/charity_dashboard.html"
                dashboard_type = "خیریه"
            elif "DONOR" in roles:
                template_name = "dashboard/donor_dashboard.html"
                dashboard_type = "خیر"
            elif "NEEDY" in roles:
                template_name = "dashboard/needy_dashboard.html"
                dashboard_type = "نیازمند"
            elif "VENDOR" in roles:
                template_name = "dashboard/vendor_dashboard.html"
                dashboard_type = "فروشنده"
            else:
                template_name = "dashboard/user_dashboard.html"
                dashboard_type = "کاربر"

            return templates.TemplateResponse(template_name, {
                "request": request,
                "user": user_data,
                "dashboard_type": dashboard_type
            })

        except Exception as e:
            return templates.TemplateResponse("error.html", {
                "request": request,
                "error": f"خطا در دریافت اطلاعات: {str(e)}"
            })


# ==================== خروج ====================

@router.get("/logout")
async def logout():
    """خروج از سیستم"""
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("access_token")
    response.delete_cookie("pending_auth")
    return response


# ==================== صفحه تأیید در انتظار ====================

@router.get("/verification-pending", response_class=HTMLResponse)
async def verification_pending_page(request: Request):
    """صفحه انتظار برای تأیید حساب"""
    return templates.TemplateResponse("auth/verification_pending.html", {"request": request})