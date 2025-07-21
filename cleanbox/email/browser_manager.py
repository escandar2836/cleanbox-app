"""
Browser instance reuse manager
Reuse browser instances for memory efficiency.
"""

import asyncio
import logging
from typing import Optional
from playwright.async_api import Browser, BrowserContext, Page


class BrowserManager:
    """Browser instance reuse manager"""

    def __init__(self):
        self.browser = None
        self.context = None
        self.active_pages = 0
        self.max_pages = 5  # Limit for concurrent pages
        self.lock = asyncio.Lock()
        self.logger = logging.getLogger(__name__)

    async def get_browser(self):
        """Return browser instance (reuse)"""
        async with self.lock:
            if self.browser is None:
                # Browser initialization is handled in PlaywrightUnsubscribeService
                pass
            return self.browser

    async def get_context(self):
        """Return context (reuse)"""
        async with self.lock:
            if self.context is None:
                # Context initialization is handled in PlaywrightUnsubscribeService
                pass
            return self.context

    async def create_page(self) -> Optional[Page]:
        """Create a new page (check limit)"""
        async with self.lock:
            if self.active_pages >= self.max_pages:
                print(f"⚠️ Maximum number of pages reached: {self.max_pages}")
                return None

            if self.context:
                self.active_pages += 1
                page = await self.context.new_page()
                print(f"📝 New page created (active pages: {self.active_pages})")
                return page
            return None

    async def close_page(self, page: Page):
        """Cleanup page"""
        async with self.lock:
            if page:
                try:
                    await page.close()
                    self.active_pages = max(0, self.active_pages - 1)
                    print(
                        f"🧹 Page cleanup complete (active pages: {self.active_pages})"
                    )
                except Exception as e:
                    print(f"⚠️ Error during page cleanup: {str(e)}")

    async def cleanup(self):
        """Full cleanup"""
        async with self.lock:
            if self.context:
                await self.context.close()
                self.context = None
            if self.browser:
                await self.browser.close()
                self.browser = None
            self.active_pages = 0
            print("🧹 Browser manager cleanup complete")

    def get_stats(self) -> dict:
        """Return current status"""
        return {
            "active_pages": self.active_pages,
            "max_pages": self.max_pages,
            "browser_active": self.browser is not None,
            "context_active": self.context is not None,
        }


# Global browser manager instance
browser_manager = BrowserManager()
