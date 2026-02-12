from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from api.v1.api_router import api_router
from routers.pages import router as pages_router


app = FastAPI(
    title="Charity",
    description="",
    version="1.0.0"
)



BASE_DIR = Path(__file__).resolve().parent




templates = Jinja2Templates(directory=BASE_DIR / "templates")
app.state.templates = templates

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.include_router(api_router, prefix="/api/v1")



app.include_router(pages_router)





@app.on_event("shutdown")
async def shutdown_event():
    """عملیات هنگام خاموش شدن سرور"""
    print("👋 سرور نورخیریه خاموش شد")



# ✅ مسیر پیش‌فرض برای تست
@app.get("/health")
async def health_check():
    """بررسی سلامت سرور"""
    return {
        "status": "healthy",
        "message": "نورخیریه فعال است ✅",
        "version": "1.0.0"
    }