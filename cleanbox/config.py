# Standard library imports
import os
from datetime import timedelta

# Third-party imports
from cryptography.fernet import Fernet
from dotenv import load_dotenv

# Load .env file
load_dotenv()


def get_encryption_key():
    """Generate or load encryption key"""
    key = os.environ.get("CLEANBOX_ENCRYPTION_KEY")

    if not key:
        # If no key, generate a new one
        key = Fernet.generate_key().decode()
        print(
            f"⚠️  A new encryption key has been generated. Please add the following to your .env file:"
        )
        print(f"CLEANBOX_ENCRYPTION_KEY={key}")

    # Validate key
    try:
        Fernet(key.encode())
        return key.encode()
    except Exception as e:
        raise ValueError(f"Invalid encryption key format: {e}")


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-secret-key"
    # PostgreSQL connection settings
    database_uri = os.environ.get("DATABASE_URI") or os.environ.get("DATABASE_URL")

    if database_uri and database_uri.startswith("postgresql://"):
        # Specify psycopg3 dialect
        database_uri = database_uri.replace("postgresql://", "postgresql+psycopg://")

    SQLALCHEMY_DATABASE_URI = database_uri or "sqlite:///cleanbox.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # PostgreSQL connection settings (psycopg3 compatibility)
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "pool_size": 10,
        "max_overflow": 20,
    }

    # Google OAuth settings
    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")

    # Google Cloud settings
    GOOGLE_CLOUD_PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT")
    GMAIL_WEBHOOK_TOPIC = os.environ.get("GMAIL_WEBHOOK_TOPIC")

    # OpenAI settings
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

    # APScheduler settings
    SCHEDULER_API_ENABLED = True
    SCHEDULER_TIMEZONE = "UTC"

    # Gmail API scopes
    GMAIL_SCOPES = [
        "https://mail.google.com/",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
    ]

    # Security settings - improved key loading
    CLEANBOX_ENCRYPTION_KEY = get_encryption_key()
    SESSION_COOKIE_SECURE = (
        os.environ.get("CLEANBOX_SESSION_SECURE", "False").lower() == "true"
    )
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = 3600  # 1 hour

    # AI feature settings
    ENABLE_AI_FEATURES = os.environ.get("CLEANBOX_ENABLE_AI", "true").lower() == "true"
    OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1-nano")

    # Scheduler settings removed - unnecessary feature per PROJECT_DESCRIPTION
    # ENABLE_SCHEDULER = (
    #     os.environ.get("CLEANBOX_ENABLE_SCHEDULER", "true").lower() == "true"
    # )
    # SYNC_INTERVAL_MINUTES = int(
    #     os.environ.get("CLEANBOX_SYNC_INTERVAL", "5").split("#")[0].strip()
    # )
    # TOKEN_CHECK_INTERVAL_HOURS = int(
    #     os.environ.get("CLEANBOX_TOKEN_CHECK_INTERVAL", "1").split("#")[0].strip()
    # )

    # Additional CleanBox-related environment settings can be added

    # Cache settings (simple in-memory cache)
    CACHE_TYPE = "simple"
    CACHE_DEFAULT_TIMEOUT = 300  # 5 minutes
    CACHE_KEY_PREFIX = "cleanbox_"


class TestConfig(Config):
    """Test configuration"""

    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "CLEANBOX_TEST_DATABASE_URI",
        "sqlite:///:memory:",  # Use in-memory SQLite
    )
    # SQLite settings (remove PostgreSQL options)
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_size": 5,
        "max_overflow": 10,
    }
    WTF_CSRF_ENABLED = False
    # In test environment, control DB initialization manually
    INIT_DB = False
    # Test Fernet key (32-byte base64 encoded)
    CLEANBOX_ENCRYPTION_KEY = "bx0fuVNGhldioocf5SO2E1pefdu6m3lr_ccJEo_pqrI="
    # Test AI settings
    OPENAI_API_KEY = "test-openai-api-key"
    OPENAI_MODEL = "gpt-4.1-nano"
