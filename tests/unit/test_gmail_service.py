import pytest
from unittest.mock import patch, MagicMock
from cleanbox.email.gmail_service import GmailService
from datetime import datetime


class TestGmailService:
    @patch("cleanbox.email.gmail_service.UserAccount")
    @patch("cleanbox.email.gmail_service.get_user_credentials")
    @patch("cleanbox.email.gmail_service.build")
    def test_get_new_emails(self, mock_build, mock_get_creds, mock_account):
        mock_account.query.filter_by.return_value.first.return_value = MagicMock(
            created_at="2023-01-01"
        )
        mock_get_creds.return_value = {
            "token": "t",
            "refresh_token": "r",
            "token_uri": "u",
            "client_id": "c",
            "client_secret": "s",
            "scopes": [],
            "expiry": None,
        }
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        gs = GmailService("user1", 1)
        with patch.object(
            gs, "fetch_recent_emails", return_value=[{"gmail_id": "g1"}]
        ) as mock_fetch:
            emails = gs.get_new_emails()
            assert emails == [{"gmail_id": "g1"}]

    @patch("cleanbox.email.gmail_service.Email")
    @patch("cleanbox.email.gmail_service.db")
    def test_save_email_to_db(self, mock_db, mock_email):
        gs = GmailService.__new__(GmailService)
        gs.user_id = "user1"
        gs.account_id = 1
        mock_email.query.filter_by.return_value.first.return_value = None
        email_data = {
            "gmail_id": "g1",
            "subject": "Subject",
            "sender": "a@b.com",
            "body": "Body text",
        }
        email_obj = MagicMock()
        mock_email.return_value = email_obj
        result = GmailService.save_email_to_db(gs, email_data)
        assert result == email_obj

    @patch("cleanbox.email.gmail_service.Email")
    @patch("cleanbox.email.gmail_service.db")
    def test_update_email_category(self, mock_db, mock_email):
        gs = GmailService.__new__(GmailService)
        gs.user_id = "user1"
        gs.account_id = 1
        email_obj = MagicMock()
        mock_email.query.filter_by.return_value.first.return_value = email_obj
        result = GmailService.update_email_category(gs, "g1", 2)
        assert result is True
        assert email_obj.category_id == 2

    @patch("cleanbox.email.gmail_service.Email")
    @patch("cleanbox.email.gmail_service.db")
    def test_archive_email(self, mock_db, mock_email):
        gs = GmailService.__new__(GmailService)
        gs.user_id = "user1"
        gs.account_id = 1
        email_obj = MagicMock()
        mock_email.query.filter_by.return_value.first.return_value = email_obj
        gs.service = MagicMock()
        result = GmailService.archive_email(gs, "g1")
        assert result is True
        assert email_obj.is_archived is True

    @patch("cleanbox.email.gmail_service.Email")
    def test_delete_email(self, mock_email):
        gs = GmailService.__new__(GmailService)
        gs.user_id = "user1"
        gs.account_id = 1
        gs.service = MagicMock()
        result = GmailService.delete_email(gs, "g1")
        assert result is True

    @patch("cleanbox.email.gmail_service.Email")
    @patch("cleanbox.email.gmail_service.db")
    @patch("cleanbox.email.gmail_service.AdvancedUnsubscribeService")
    def test_process_unsubscribe(self, mock_unsub, mock_db, mock_email):
        from cleanbox import create_app

        app = create_app(testing=True)
        gs = GmailService.__new__(GmailService)
        gs.user_id = "user1"
        gs.account_id = 1
        gs.advanced_unsubscribe = mock_unsub.return_value
        email_obj = MagicMock(id=1, sender="a@b.com", content="Body text", headers={})
        mock_unsub.return_value.process_unsubscribe_advanced.return_value = {
            "success": True
        }
        with app.app_context():
            result = GmailService.process_unsubscribe(gs, email_obj)
            assert result["success"] is True

    @patch("cleanbox.email.gmail_service.Email")
    @patch("cleanbox.email.gmail_service.UserAccount")
    def test_get_email_statistics(self, mock_account, mock_email):
        gs = GmailService.__new__(GmailService)
        gs.user_id = "user1"
        gs.account_id = 1
        mock_email.query.filter_by.return_value.count.return_value = 5
        mock_account.query.get.return_value = MagicMock(
            account_email="a@b.com", account_name="A", is_primary=True
        )
        gs.get_user_categories = MagicMock(return_value=[])
        stats = GmailService.get_email_statistics(gs)
        assert stats["total"] == 5
        assert stats["account"]["email"] == "a@b.com"

    @patch("cleanbox.email.gmail_service.UserAccount")
    @patch("cleanbox.email.gmail_service.get_user_credentials")
    @patch("cleanbox.email.gmail_service.build")
    def test_setup_gmail_watch(self, mock_build, mock_get_creds, mock_account):
        from cleanbox import create_app

        app = create_app(testing=True)
        mock_account.query.get.return_value = MagicMock(account_email="a@b.com")
        mock_get_creds.return_value = {
            "token": "t",
            "refresh_token": "r",
            "token_uri": "u",
            "client_id": "c",
            "client_secret": "s",
            "scopes": [],
            "expiry": None,
        }
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        gs = GmailService("user1", 1)
        mock_service.users().watch.return_value.execute.return_value = {
            "historyId": "h",
            "expiration": "e",
        }
        with app.app_context():
            result = gs.setup_gmail_watch("topic")
            assert result is True

    @patch("cleanbox.email.gmail_service.UserAccount")
    @patch("cleanbox.email.gmail_service.get_user_credentials")
    @patch("cleanbox.email.gmail_service.build")
    def test_get_webhook_status(self, mock_build, mock_get_creds, mock_account):
        from cleanbox import create_app

        app = create_app(testing=True)
        mock_account.query.get.return_value = MagicMock(account_email="a@b.com")
        mock_get_creds.return_value = {
            "token": "t",
            "refresh_token": "r",
            "token_uri": "u",
            "client_id": "c",
            "client_secret": "s",
            "scopes": [],
            "expiry": None,
        }
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        gs = GmailService("user1", 1)
        import cleanbox.models as models_mod

        with patch.object(models_mod, "WebhookStatus") as mock_ws:
            mock_ws.query.filter_by.return_value.first.return_value = MagicMock(
                is_active=True,
                is_expired=False,
                is_healthy=True,
                last_webhook_received=None,
                setup_at=datetime.utcnow(),
                expires_at=datetime.utcnow(),
            )
            with app.app_context():
                status = gs.get_webhook_status()
                assert status["status"] in (
                    "healthy",
                    "expired",
                    "unhealthy",
                    "not_setup",
                    "error",
                )
