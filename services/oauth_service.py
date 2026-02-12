# app/services/oauth_service.py
from fastapi import HTTPException, status
import httpx

class GoogleOAuthService:
    GOOGLE_TOKEN_INFO_URL = "https://oauth2.googleapis.com/tokeninfo"

    @staticmethod
    async def verify_token(token: str) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{GoogleOAuthService.GOOGLE_TOKEN_INFO_URL}?id_token={token}")
            if resp.status_code != 200:
                raise HTTPException(status_code=400, detail="Invalid Google token")
            data = resp.json()
            return {"email": data["email"], "name": data.get("name")}
