import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from cleanbox.email.advanced_unsubscribe import AdvancedUnsubscribeService


class TestAdvancedUnsubscribeService:
    @patch("cleanbox.email.advanced_unsubscribe.PlaywrightUnsubscribeService")
    def test_extract_unsubscribe_links(self, mock_playwright):
        mock_playwright.return_value.extract_unsubscribe_links.return_value = [
            "http://unsubscribe.com"
        ]
        service = AdvancedUnsubscribeService()
        links = service.extract_unsubscribe_links("body text", {})
        assert links == ["http://unsubscribe.com"]

    @pytest.mark.asyncio
    @patch("cleanbox.email.advanced_unsubscribe.PlaywrightUnsubscribeService")
    @patch("cleanbox.email.advanced_unsubscribe.process_unsubscribe_sync")
    async def test_process_unsubscribe_advanced_success(
        self, mock_sync, mock_playwright
    ):
        mock_playwright.return_value.extract_unsubscribe_links_with_ai_fallback = (
            AsyncMock(return_value=["http://unsubscribe.com"])
        )
        mock_playwright.return_value.process_unsubscribe_with_playwright_ai = AsyncMock(
            return_value={"success": True, "message": "ok"}
        )
        mock_sync.return_value = {"success": True, "message": "ok"}
        service = AdvancedUnsubscribeService()
        result = await service.process_unsubscribe_advanced(
            "body text", {}, "user@example.com"
        )
        assert result["success"] is True

    @pytest.mark.asyncio
    @patch.object(AdvancedUnsubscribeService, "playwright_service", create=True)
    async def test_process_unsubscribe_advanced_no_links(self, mock_playwright):
        mock_playwright.extract_unsubscribe_links_with_ai_fallback = AsyncMock(
            return_value=[]
        )
        service = AdvancedUnsubscribeService()
        result = await service.process_unsubscribe_advanced(
            "body text", {}, "user@example.com"
        )
        assert result["success"] is False
        assert result["error_type"] == "no_unsubscribe_link"

    @patch("cleanbox.email.advanced_unsubscribe.process_unsubscribe_sync")
    def test_process_unsubscribe_simple(self, mock_sync):
        mock_sync.return_value = {"success": True, "message": "ok"}
        service = AdvancedUnsubscribeService()
        result = service.process_unsubscribe_simple("http://unsubscribe.com")
        assert result["success"] is True

    def test_is_valid_unsubscribe_url(self):
        service = AdvancedUnsubscribeService()
        assert service._is_valid_unsubscribe_url("http://test.com") == True
        assert service._is_valid_unsubscribe_url("ftp://test.com") == False
        assert service._is_valid_unsubscribe_url("") == False

    def test_detect_personal_email(self):
        service = AdvancedUnsubscribeService()
        # Personal domain
        headers = {"From": "user@gmail.com"}
        assert service._detect_personal_email("content", headers) is True
        # No marketing keyword
        assert service._detect_personal_email("hello", {}) is True
        # Marketing keyword exists
        assert service._detect_personal_email("unsubscribe notice", {}) is False
