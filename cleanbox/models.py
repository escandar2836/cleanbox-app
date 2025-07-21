# Standard library imports
import json
import os
from datetime import datetime, timedelta

# Third-party imports
from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from cryptography.fernet import Fernet

db = SQLAlchemy()


class User(UserMixin, db.Model):
    """CleanBox user model"""

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
    )  # First service access time
    is_online = db.Column(db.Boolean, default=False)
    session_id = db.Column(db.String(255))

    # Relationships
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
    """Gmail account model linked per user"""

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

    # Relationships
    tokens = db.relationship(
        "UserToken", backref="account", lazy=True, cascade="all, delete-orphan"
    )
    emails = db.relationship(
        "Email", backref="account", lazy=True, cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<UserAccount {self.account_email}>"


class UserToken(db.Model):
    """User OAuth token model (encrypted storage)"""

    __tablename__ = "user_tokens"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(255), db.ForeignKey("users.id"), nullable=False)
    account_id = db.Column(
        db.Integer, db.ForeignKey("user_accounts.id"), nullable=False
    )
    access_token = db.Column(db.Text, nullable=False)  # Encrypted token
    refresh_token = db.Column(db.Text)  # Encrypted token
    token_uri = db.Column(db.String(255))
    client_id = db.Column(db.String(255))
    client_secret = db.Column(db.String(255))
    scopes = db.Column(db.Text)  # Stored as JSON
    expires_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def set_tokens(self, credentials):
        """Encrypt and store tokens"""
        from flask import current_app

        # Get key from config (already validated in config.py)
        key = current_app.config.get("CLEANBOX_ENCRYPTION_KEY")
        cipher = Fernet(key)

        # Handle None values
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
        """Decrypt and return tokens"""
        from flask import current_app

        # Get key from config (already validated in config.py)
        key = current_app.config.get("CLEANBOX_ENCRYPTION_KEY")
        cipher = Fernet(key)

        tokens = {
            "token_uri": self.token_uri,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scopes": json.loads(self.scopes) if self.scopes else [],
        }

        # Handle None values
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
    """Email category model"""

    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(255), db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    color = db.Column(db.String(7), default="#007bff")  # HEX color
    icon = db.Column(db.String(50), default="fas fa-tag")
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    emails = db.relationship("Email", backref="category", lazy=True)

    def __repr__(self):
        return f"<Category {self.name}>"


class Email(db.Model):
    """Email model"""

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
    recipients = db.Column(db.Text)  # Stored as JSON
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
    """Webhook status tracking model"""

    __tablename__ = "webhook_status"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(255), db.ForeignKey("users.id"), nullable=False)
    account_id = db.Column(
        db.Integer, db.ForeignKey("user_accounts.id"), nullable=False
    )
    topic_name = db.Column(db.String(500), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    setup_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(
        db.DateTime, nullable=False
    )  # Gmail webhook expires after 7 days
    last_webhook_received = db.Column(db.DateTime)  # Last webhook received time
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    user = db.relationship("User", backref="webhook_statuses")
    account = db.relationship("UserAccount", backref="webhook_statuses")

    def __repr__(self):
        return f"<WebhookStatus {self.user_id}:{self.account_id}>"

    @property
    def is_expired(self):
        """Check if webhook is expired"""
        return datetime.utcnow() > self.expires_at

    @property
    def is_healthy(self):
        """Check if webhook is healthy"""
        if not self.is_active:
            return False

        # If set within 7 days and received webhook in last 24 hours, it's healthy
        if self.is_expired:
            return False

        if self.last_webhook_received:
            # If received webhook in last 24 hours, it's healthy
            return datetime.utcnow() - self.last_webhook_received < timedelta(hours=24)

        # If never received a webhook, it's healthy within 1 hour after setup
        return datetime.utcnow() - self.setup_at < timedelta(hours=1)
