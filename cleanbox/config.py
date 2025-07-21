"""CleanBox 애플리케이션 설정 모듈."""

import os
from datetime import timedelta
from typing import Optional

from cryptography.fernet import Fernet
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()


def get_encryption_key() -> bytes:
    """암호화 키를 생성하거나 로드합니다."""
    key = os.environ.get("CLEANBOX_ENCRYPTION_KEY")

    if not key:
        # 키가 없으면 새로 생성
        key = Fernet.generate_key().decode()
        # 운영 환경에서는 로그로 대체
        print(f"⚠️ 새로운 암호화 키가 생성되었습니다. .env 파일에 다음을 추가하세요:")
        print(f"CLEANBOX_ENCRYPTION_KEY={key}")

    # 키 유효성 검증
    try:
        Fernet(key.encode())
        return key.encode()
    except Exception as e:
        raise ValueError(f"잘못된 암호화 키 형식: {e}")


class Config:
    """CleanBox 애플리케이션 기본 설정 클래스."""

    SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-secret-key"

    # PostgreSQL 연결 설정
    database_uri = os.environ.get("DATABASE_URI") or os.environ.get("DATABASE_URL")

    if database_uri and database_uri.startswith("postgresql://"):
        # psycopg3 dialect 명시
        database_uri = database_uri.replace("postgresql://", "postgresql+psycopg://")

    SQLALCHEMY_DATABASE_URI = database_uri or "sqlite:///cleanbox.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # PostgreSQL 연결 설정 (psycopg3 호환성)
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "pool_size": 10,
        "max_overflow": 20,
    }

    # Google OAuth 설정
    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")

    # Google Cloud 설정
    GOOGLE_CLOUD_PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT")
    GMAIL_WEBHOOK_TOPIC = os.environ.get("GMAIL_WEBHOOK_TOPIC")

    # OpenAI 설정
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

    # APScheduler 설정
    SCHEDULER_API_ENABLED = True
    SCHEDULER_TIMEZONE = "UTC"

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
    OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1-nano")

    # 캐시 설정 (메모리 기반 간단한 캐시)
    CACHE_TYPE = "simple"
    CACHE_DEFAULT_TIMEOUT = 300  # 5분
    CACHE_KEY_PREFIX = "cleanbox_"


class TestConfig(Config):
    """테스트용 설정 클래스."""

    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "CLEANBOX_TEST_DATABASE_URI",
        "sqlite:///:memory:",  # 메모리 기반 SQLite 사용
    )
    # SQLite용 설정 (PostgreSQL 옵션 제거)
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_size": 5,
        "max_overflow": 10,
    }
    WTF_CSRF_ENABLED = False
    # 테스트 환경에서는 데이터베이스 초기화를 수동으로 제어
    INIT_DB = False
    # 테스트용 Fernet 키 (32바이트 base64 인코딩)
    CLEANBOX_ENCRYPTION_KEY = "bx0fuVNGhldioocf5SO2E1pefdu6m3lr_ccJEo_pqrI="
    # 테스트용 AI 설정
    OPENAI_API_KEY = "test-openai-api-key"
    OPENAI_MODEL = "gpt-4.1-nano"
