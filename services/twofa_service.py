import pyotp
import qrcode
import io
import base64
import secrets
import string
import hashlib
from datetime import datetime
from typing import List, Dict


class TwoFAService:

    @staticmethod
    def generate_secret() -> str:
        return pyotp.random_base32()

    # -----------------------------------
    # BACKUP CODES
    # -----------------------------------
    @staticmethod
    def _hash(code: str) -> str:
        return hashlib.sha256(code.encode()).hexdigest()

    @classmethod
    def generate_backup_codes(cls, count=8) -> List[Dict]:
        alphabet = string.ascii_uppercase + string.digits
        codes = []

        for _ in range(count):
            raw = ''.join(secrets.choice(alphabet) for _ in range(8))
            formatted = f"{raw[:4]}-{raw[4:]}"
            codes.append({
                "code": formatted,
                "hash": cls._hash(raw),
                "used": False
            })

        return codes

    @classmethod
    def verify_backup_code(cls, stored: List[Dict], input_code: str) -> bool:
        raw = input_code.replace("-", "")
        hashed = cls._hash(raw)

        for c in stored:
            if not c["used"] and c["hash"] == hashed:
                c["used"] = True
                c["used_at"] = datetime.utcnow().isoformat()
                return True
        return False

    # -----------------------------------
    # QR
    # -----------------------------------
    @staticmethod
    def get_qr_code_uri(email: str, secret: str, issuer="CharityPlatform"):
        totp = pyotp.TOTP(secret)
        uri = totp.provisioning_uri(email, issuer_name=issuer)

        img = qrcode.make(uri)
        buf = io.BytesIO()
        img.save(buf, format="PNG")

        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

    # -----------------------------------
    # VERIFY TOTP
    # -----------------------------------
    @staticmethod
    def verify_token(secret: str, token: str) -> bool:
        return pyotp.TOTP(secret).verify(token, valid_window=1)
