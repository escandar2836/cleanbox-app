from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import json
from cryptography.fernet import Fernet
import os

db = SQLAlchemy()


class User(UserMixin, db.Model):
    """CleanBox 사용자 모델"""

    __tablename__ = "users"

    id = db.Column(db.String(255), primary_key=True)  # Google OAuth sub
    email = db.Column(db.String(255), unique=True, nullable=False)
    name = db.Column(db.String(255))
    picture = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    last_login = db.Column(db.DateTime, default=datetime.utcnow)
    last_activity = db.Column(db.DateTime, default=datetime.utcnow)
    first_service_access = db.Column(
        db.DateTime, default=datetime.utcnow
    )  # 최초 서비스 접속 시간
    is_online = db.Column(db.Boolean, default=False)
    session_id = db.Column(db.String(255))

    # 관계
    accounts = db.relationship(
        "UserAccount", backref="user", lazy=True, cascade="all, delete-orphan"
    )
    categories = db.relationship(
        "Category", backref="user", lazy=True, cascade="all, delete-orphan"
    )
    emails = db.relationship(
        "Email", backref="user", lazy=True, cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<User {self.email}>"


class UserAccount(db.Model):
    """사용자별 연결된 Gmail 계정 모델"""

    __tablename__ = "user_accounts"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(255), db.ForeignKey("users.id"), nullable=False)
    account_email = db.Column(db.String(255), nullable=False)
    account_name = db.Column(db.String(255))
    is_primary = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # 관계
    tokens = db.relationship(
        "UserToken", backref="account", lazy=True, cascade="all, delete-orphan"
    )
    emails = db.relationship(
        "Email", backref="account", lazy=True, cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<UserAccount {self.account_email}>"


class UserToken(db.Model):
    """사용자 OAuth 토큰 모델 (암호화 저장)"""

    __tablename__ = "user_tokens"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(255), db.ForeignKey("users.id"), nullable=False)
    account_id = db.Column(
        db.Integer, db.ForeignKey("user_accounts.id"), nullable=False
    )
    access_token = db.Column(db.Text, nullable=False)  # 암호화된 토큰
    refresh_token = db.Column(db.Text)  # 암호화된 토큰
    token_uri = db.Column(db.String(255))
    client_id = db.Column(db.String(255))
    client_secret = db.Column(db.String(255))
    scopes = db.Column(db.Text)  # JSON 형태로 저장
    expires_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def set_tokens(self, credentials):
        """토큰을 암호화하여 저장"""
        from flask import current_app

        # 설정에서 키를 가져옴 (config.py에서 이미 검증됨)
        key = current_app.config.get("CLEANBOX_ENCRYPTION_KEY")
        cipher = Fernet(key)

        # None 값 처리
        if credentials.token:
            self.access_token = cipher.encrypt(credentials.token.encode()).decode()
        else:
            self.access_token = None

        if credentials.refresh_token:
            self.refresh_token = cipher.encrypt(
                credentials.refresh_token.encode()
            ).decode()
        else:
            self.refresh_token = None

        self.token_uri = credentials.token_uri
        self.client_id = credentials.client_id
        self.client_secret = credentials.client_secret
        self.scopes = (
            json.dumps(credentials.scopes) if credentials.scopes else json.dumps([])
        )

        if credentials.expiry:
            self.expires_at = credentials.expiry

    def get_tokens(self):
        """암호화된 토큰을 복호화하여 반환"""
        from flask import current_app

        # 설정에서 키를 가져옴 (config.py에서 이미 검증됨)
        key = current_app.config.get("CLEANBOX_ENCRYPTION_KEY")
        cipher = Fernet(key)

        tokens = {
            "token_uri": self.token_uri,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scopes": json.loads(self.scopes) if self.scopes else [],
        }

        # None 값 처리
        if self.access_token:
            tokens["token"] = cipher.decrypt(self.access_token.encode()).decode()
        else:
            tokens["token"] = None

        if self.refresh_token:
            tokens["refresh_token"] = cipher.decrypt(
                self.refresh_token.encode()
            ).decode()

        if self.expires_at:
            tokens["expiry"] = self.expires_at

        return tokens

    def __repr__(self):
        return f"<UserToken {self.user_id}>"


class Category(db.Model):
    """이메일 카테고리 모델"""

    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(255), db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    color = db.Column(db.String(7), default="#007bff")  # HEX 색상
    icon = db.Column(db.String(50), default="fas fa-tag")
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # 관계
    emails = db.relationship("Email", backref="category", lazy=True)

    def __repr__(self):
        return f"<Category {self.name}>"


class Email(db.Model):
    """이메일 모델"""

    __tablename__ = "emails"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(255), db.ForeignKey("users.id"), nullable=False)
    account_id = db.Column(
        db.Integer, db.ForeignKey("user_accounts.id"), nullable=False
    )
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"))
    gmail_id = db.Column(db.String(255), nullable=False)
    thread_id = db.Column(db.String(255))
    subject = db.Column(db.String(500))
    sender = db.Column(db.String(255))
    recipients = db.Column(db.Text)  # JSON 형태로 저장
    content = db.Column(db.Text)
    summary = db.Column(db.Text)
    is_read = db.Column(db.Boolean, default=False)
    is_archived = db.Column(db.Boolean, default=False)
    is_unsubscribed = db.Column(db.Boolean, default=False)
    received_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def __repr__(self):
        return f"<Email {self.subject}>"


class WebhookStatus(db.Model):
    """웹훅 상태 추적 모델"""

    __tablename__ = "webhook_status"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(255), db.ForeignKey("users.id"), nullable=False)
    account_id = db.Column(
        db.Integer, db.ForeignKey("user_accounts.id"), nullable=False
    )
    topic_name = db.Column(db.String(500), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    setup_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)  # Gmail 웹훅은 7일 후 만료
    last_webhook_received = db.Column(db.DateTime)  # 마지막 웹훅 수신 시간
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # 관계
    user = db.relationship("User", backref="webhook_statuses")
    account = db.relationship("UserAccount", backref="webhook_statuses")

    def __repr__(self):
        return f"<WebhookStatus {self.user_id}:{self.account_id}>"

    @property
    def is_expired(self):
        """웹훅이 만료되었는지 확인"""
        return datetime.utcnow() > self.expires_at

    @property
    def is_healthy(self):
        """웹훅이 정상 작동하는지 확인"""
        if not self.is_active:
            return False

        # 7일 이내에 설정되었고, 최근 24시간 내에 웹훅을 받았으면 정상
        if self.is_expired:
            return False

        if self.last_webhook_received:
            # 최근 24시간 내에 웹훅을 받았으면 정상
            return datetime.utcnow() - self.last_webhook_received < timedelta(hours=24)

        # 웹훅을 한 번도 받지 못했으면 설정 후 1시간 이내면 정상
        return datetime.utcnow() - self.setup_at < timedelta(hours=1)
