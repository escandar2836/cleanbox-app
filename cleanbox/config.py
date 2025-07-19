import os
from cryptography.fernet import Fernet
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()


def get_encryption_key():
    """암호화 키 생성 또는 로드"""
    key = os.environ.get("CLEANBOX_ENCRYPTION_KEY")

    if not key:
        # 키가 없으면 새로 생성
        key = Fernet.generate_key().decode()
        print(f"⚠️  새로운 암호화 키가 생성되었습니다. .env 파일에 다음을 추가하세요:")
        print(f"CLEANBOX_ENCRYPTION_KEY={key}")

    # 키 유효성 검증
    try:
        Fernet(key.encode())
        return key.encode()
    except Exception as e:
        raise ValueError(f"잘못된 암호화 키 형식: {e}")


class Config:
    SECRET_KEY = os.environ.get("CLEANBOX_SECRET_KEY", "dev")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "CLEANBOX_DATABASE_URI",
        "postgresql://cleanbox_user:cleanbox_password@localhost:5432/cleanbox",
    )
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "pool_timeout": 20,
        "max_overflow": 10,
        "pool_size": 5,
        "connect_args": {
            "sslmode": "require",
            "connect_timeout": 10,
            "application_name": "cleanbox_app",
            "keepalives_idle": 600,
            "keepalives_interval": 30,
            "keepalives_count": 5,
        },
    }
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
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
    OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1-nano")

    # 스케줄러 설정 제거 - PROJECT_DESCRIPTION 기준으로 불필요한 기능
    # ENABLE_SCHEDULER = (
    #     os.environ.get("CLEANBOX_ENABLE_SCHEDULER", "true").lower() == "true"
    # )
    # SYNC_INTERVAL_MINUTES = int(
    #     os.environ.get("CLEANBOX_SYNC_INTERVAL", "5").split("#")[0].strip()
    # )
    # TOKEN_CHECK_INTERVAL_HOURS = int(
    #     os.environ.get("CLEANBOX_TOKEN_CHECK_INTERVAL", "1").split("#")[0].strip()
    # )

    # 기타 CleanBox 관련 환경설정 추가 가능


class TestConfig(Config):
    """테스트용 설정"""

    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "CLEANBOX_TEST_DATABASE_URI",
        "sqlite:///:memory:",  # 메모리 기반 SQLite 사용
    )
    # SQLite용 설정 (PostgreSQL 옵션 제거)
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "connect_args": {
            "timeout": 10,
        },
    }
    WTF_CSRF_ENABLED = False
    # 테스트 환경에서는 데이터베이스 초기화를 수동으로 제어
    INIT_DB = False
    # 테스트용 Fernet 키 (32바이트 base64 인코딩)
    CLEANBOX_ENCRYPTION_KEY = "bx0fuVNGhldioocf5SO2E1pefdu6m3lr_ccJEo_pqrI="
    # 테스트용 AI 설정
    OPENAI_API_KEY = "test-openai-api-key"
    OPENAI_MODEL = "gpt-4.1-nano"
