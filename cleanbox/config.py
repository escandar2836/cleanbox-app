import os
from cryptography.fernet import Fernet


class Config:
    SECRET_KEY = os.environ.get("CLEANBOX_SECRET_KEY", "dev")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "CLEANBOX_DATABASE_URI", "sqlite:///cleanbox.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Google OAuth 설정
    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
    GOOGLE_REDIRECT_URI = os.environ.get(
        "GOOGLE_REDIRECT_URI", "http://localhost:5000/auth/callback"
    )

    # Gmail API 범위
    GMAIL_SCOPES = [
        "https://mail.google.com/",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
    ]

    # 보안 설정
    CLEANBOX_ENCRYPTION_KEY = os.environ.get(
        "CLEANBOX_ENCRYPTION_KEY", Fernet.generate_key()
    )
    SESSION_COOKIE_SECURE = (
        os.environ.get("CLEANBOX_SESSION_SECURE", "False").lower() == "true"
    )
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = 3600  # 1시간

    # 기타 CleanBox 관련 환경설정 추가 가능
