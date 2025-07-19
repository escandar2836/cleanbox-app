import os
from cryptography.fernet import Fernet
from dotenv import load_dotenv

# .env 파일 로드 (Docker 환경에서도 작동하도록)
load_dotenv()


def validate_fernet_key(key):
    """Fernet 키가 유효한지 검증"""
    try:
        if isinstance(key, str):
            # 문자열인 경우 bytes로 변환
            key_bytes = key.encode() if isinstance(key, str) else key
        else:
            key_bytes = key

        # Fernet 키 검증
        Fernet(key_bytes)
        return True
    except Exception as e:
        print(f"Invalid Fernet key: {e}")
        return False


def get_encryption_key():
    """환경변수에서 암호화 키를 안전하게 가져옴"""
    key = os.environ.get("CLEANBOX_ENCRYPTION_KEY")

    if key and validate_fernet_key(key):
        return key

    # 키가 없거나 유효하지 않으면 새로 생성
    new_key = Fernet.generate_key()
    print("Warning: Invalid or missing encryption key, generated new key")
    return new_key


class Config:
    SECRET_KEY = os.environ.get("CLEANBOX_SECRET_KEY", "dev")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "CLEANBOX_DATABASE_URI",
        "postgresql://cleanbox_user:cleanbox_password@localhost:5432/cleanbox",
    )
    SQLALCHEMY_ENGINE_OPTIONS = {}
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

    # 보안 설정 - 개선된 키 로딩
    CLEANBOX_ENCRYPTION_KEY = get_encryption_key()
    SESSION_COOKIE_SECURE = (
        os.environ.get("CLEANBOX_SESSION_SECURE", "False").lower() == "true"
    )
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = 3600  # 1시간

    # AI 기능 설정
    ENABLE_AI_FEATURES = os.environ.get("CLEANBOX_ENABLE_AI", "true").lower() == "true"
    USE_OLLAMA = os.environ.get("CLEANBOX_USE_OLLAMA", "true").lower() == "true"
    OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
    OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama2:3b")

    # 스케줄러 설정
    ENABLE_SCHEDULER = (
        os.environ.get("CLEANBOX_ENABLE_SCHEDULER", "true").lower() == "true"
    )
    SYNC_INTERVAL_MINUTES = int(os.environ.get("CLEANBOX_SYNC_INTERVAL", "5"))
    TOKEN_CHECK_INTERVAL_HOURS = int(
        os.environ.get("CLEANBOX_TOKEN_CHECK_INTERVAL", "1")
    )

    # 기타 CleanBox 관련 환경설정 추가 가능


class TestConfig(Config):
    """테스트용 설정"""

    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "CLEANBOX_DATABASE_URI",
        "postgresql://cleanbox_user:cleanbox_password@localhost:5433/cleanbox_test",
    )
    SQLALCHEMY_ENGINE_OPTIONS = {}
    WTF_CSRF_ENABLED = False
    # 테스트 환경에서는 데이터베이스 초기화를 수동으로 제어
    INIT_DB = False
    # 테스트용 Fernet 키 (32바이트 base64 인코딩)
    CLEANBOX_ENCRYPTION_KEY = "bx0fuVNGhldioocf5SO2E1pefdu6m3lr_ccJEo_pqrI="
    # 테스트용 AI 설정
    USE_OLLAMA = True
    OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11435")
    OLLAMA_MODEL = "llama2"
