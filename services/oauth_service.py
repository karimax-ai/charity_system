from fastapi import HTTPException
import httpx
from core.config import settings


class GoogleOAuthService:

    GOOGLE_URL = "https://oauth2.googleapis.com/tokeninfo"

    @staticmethod
    async def verify_token(token: str):

        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(GoogleOAuthService.GOOGLE_URL, params={"id_token": token})

        if r.status_code != 200:
            raise HTTPException(400, "Invalid Google token")

        data = r.json()

        if data["aud"] != settings.GOOGLE_CLIENT_ID:
            raise HTTPException(400, "Invalid audience")

        if data["iss"] not in ("accounts.google.com", "https://accounts.google.com"):
            raise HTTPException(400, "Invalid issuer")

        if data.get("email_verified") != "true":
            raise HTTPException(400, "Email not verified")

        return {
            "email": data["email"],
            "name": data.get("name")
        }
