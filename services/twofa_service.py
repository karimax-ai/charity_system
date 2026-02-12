# app/services/twofa_service.py
import pyotp
import qrcode
import io
import base64

class TwoFAService:
    @staticmethod
    def generate_secret() -> str:
        return pyotp.random_base32()  # 16 chars base32

    @staticmethod
    def get_qr_code_uri(user_email: str, secret: str, issuer_name: str = "CharityPlatform"):
        totp = pyotp.TOTP(secret)
        uri = totp.provisioning_uri(name=user_email, issuer_name=issuer_name)
        # تولید QR code به صورت base64 برای فرانت
        qr = qrcode.make(uri)
        buf = io.BytesIO()
        qr.save(buf, format="PNG")
        qr_b64 = base64.b64encode(buf.getvalue()).decode()
        return f"data:image/png;base64,{qr_b64}"

    @staticmethod
    def verify_token(secret: str, token: str) -> bool:
        totp = pyotp.TOTP(secret)
        return totp.verify(token)
