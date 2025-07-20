"""
브라우저 인스턴스 재사용 관리자
메모리 효율성을 위해 브라우저 인스턴스를 재사용합니다.
"""

import asyncio
import logging
from typing import Optional
from playwright.async_api import Browser, BrowserContext, Page


class BrowserManager:
    """브라우저 인스턴스 재사용 관리자"""

    def __init__(self):
        self.browser = None
        self.context = None
        self.active_pages = 0
        self.max_pages = 5  # 동시 페이지 수 제한
        self.lock = asyncio.Lock()
        self.logger = logging.getLogger(__name__)

    async def get_browser(self):
        """브라우저 인스턴스 반환 (재사용)"""
        async with self.lock:
            if self.browser is None:
                # 브라우저 초기화는 PlaywrightUnsubscribeService에서 처리
                pass
            return self.browser

    async def get_context(self):
        """컨텍스트 반환 (재사용)"""
        async with self.lock:
            if self.context is None:
                # 컨텍스트 초기화는 PlaywrightUnsubscribeService에서 처리
                pass
            return self.context

    async def create_page(self) -> Optional[Page]:
        """새 페이지 생성 (제한 확인)"""
        async with self.lock:
            if self.active_pages >= self.max_pages:
                print(f"⚠️ 최대 페이지 수 도달: {self.max_pages}")
                return None

            if self.context:
                self.active_pages += 1
                page = await self.context.new_page()
                print(f"📝 새 페이지 생성 (활성 페이지: {self.active_pages})")
                return page
            return None

    async def close_page(self, page: Page):
        """페이지 정리"""
        async with self.lock:
            if page:
                try:
                    await page.close()
                    self.active_pages = max(0, self.active_pages - 1)
                    print(f"🧹 페이지 정리 완료 (활성 페이지: {self.active_pages})")
                except Exception as e:
                    print(f"⚠️ 페이지 정리 중 오류: {str(e)}")

    async def cleanup(self):
        """전체 정리"""
        async with self.lock:
            if self.context:
                await self.context.close()
                self.context = None
            if self.browser:
                await self.browser.close()
                self.browser = None
            self.active_pages = 0
            print("🧹 브라우저 매니저 정리 완료")

    def get_stats(self) -> dict:
        """현재 상태 반환"""
        return {
            "active_pages": self.active_pages,
            "max_pages": self.max_pages,
            "browser_active": self.browser is not None,
            "context_active": self.context is not None,
        }


# 전역 브라우저 매니저 인스턴스
browser_manager = BrowserManager()
