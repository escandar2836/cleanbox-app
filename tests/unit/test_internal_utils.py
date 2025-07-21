import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
from cleanbox.email.routes import (
    process_missed_emails_for_account,
    check_and_repair_webhooks_for_user,
    setup_gmail_webhook,
)
from cleanbox.email.gmail_service import GmailService


class TestInternalUtils:
    @patch.object(
        GmailService,
        "fetch_recent_emails",
        return_value=[
            {
                "gmail_id": "g1",
                "subject": "제목",
                "snippet": "요약",
                "sender": "a@b.com",
            }
        ],
    )
    @patch("cleanbox.email.gmail_service.build")
    @patch("cleanbox.email.gmail_service.get_user_credentials")
    @patch("cleanbox.email.routes.GmailService")
    @patch("cleanbox.email.ai_classifier.AIClassifier")
    @patch("cleanbox.email.routes.Email")
    @patch("cleanbox.email.routes.db")
    def test_process_missed_emails_for_account_success(
        self,
        mock_db,
        mock_email,
        mock_ai,
        mock_gmail,
        mock_get_creds,
        mock_build,
        mock_fetch,
    ):
        from cleanbox import create_app

        app = create_app(testing=True)
        mock_build.return_value = MagicMock()
        mock_get_creds.return_value = {
            "token": "t",
            "refresh_token": "r",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "c",
            "client_secret": "s",
            "scopes": [],
            "expiry": None,
        }
        mock_gmail.return_value.get_user_categories.return_value = [
            MagicMock(id=1, name="Work", description="업무")
        ]
        mock_ai.return_value.classify_email.return_value = {
            "category_id": 1,
            "category_name": "Work",
            "confidence_score": 90,
        }
        mock_email.query.filter_by.return_value.first.return_value = None
        with app.app_context():
            result = process_missed_emails_for_account(
                "user1", 1, datetime.utcnow() - timedelta(days=1)
            )
            assert result["success"] is True
            assert result["processed_count"] == 1
            assert result["classified_count"] == 1

    @patch("cleanbox.email.routes.UserAccount")
    @patch("cleanbox.email.routes.WebhookStatus")
    @patch("cleanbox.email.routes.setup_webhook_for_account")
    def test_check_and_repair_webhooks_for_user(
        self, mock_setup, mock_ws, mock_account
    ):
        mock_account.query.filter_by.return_value.all.return_value = [
            MagicMock(id=1, account_email="a@b.com")
        ]
        mock_ws.query.filter_by.return_value.first.return_value = MagicMock(
            is_expired=True, expires_at=datetime.utcnow() - timedelta(days=1)
        )
        mock_setup.return_value = True
        result = check_and_repair_webhooks_for_user("user1")
        assert result["success"] is True
        assert result["repaired_count"] >= 0

    @patch("cleanbox.email.routes.UserAccount")
    @patch("cleanbox.email.routes.GmailService")
    def test_setup_gmail_webhook(self, mock_gmail, mock_account):
        mock_account.query.get.return_value = MagicMock(
            user_id="user1", account_email="a@b.com"
        )
        mock_gmail.return_value.setup_gmail_watch.return_value = True
        result = setup_gmail_webhook(1, "topic")
        assert result["success"] is True
