from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

router = APIRouter()

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def render(request, template):
    return request.app.state.templates.TemplateResponse(
        template,
        {"request": request}
    )



# ---------- main ----------
@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return render(request, "index.html")


# ---------- auth ----------
@router.get("/login", response_class=HTMLResponse)
async def login(request: Request):
    return render(request, "auth/login.html")


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    return render(request, "dashboard/admin/dashboard.html")

@router.get("/dashboard_ch", response_class=HTMLResponse)
async def dashboard_need(request: Request):
    return render(request, "dashboard/admin/need_ch_dashboard.html")


@router.get("/report", response_class=HTMLResponse)
async def report(request: Request):
    return render(request, "dashboard/admin/report.html")

@router.get("/shop", response_class=HTMLResponse)
async def shop(request: Request):
    return render(request, "dashboard/admin/shop.html")


@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot(request: Request):
    return render(request, "auth/forgot-password.html")


@router.get("/reset-password", response_class=HTMLResponse)
async def reset(request: Request):
    return render(request, "auth/reset_password.html")


@router.get("/2fa/setup", response_class=HTMLResponse)
async def setup_2fa(request: Request):
    return render(request, "auth/2fa-setup.html")


@router.get("/2fa/verify", response_class=HTMLResponse)
async def verify_2fa(request: Request):
    return render(request, "auth/2fa/verify.html")


# ---------- dashboard ----------

