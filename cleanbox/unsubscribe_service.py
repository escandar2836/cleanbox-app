"""
구독 해지 자동화 서비스
웹 스크래핑을 통해 다양한 서비스의 구독 해지 프로세스를 자동화합니다.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Tuple
from playwright.async_api import async_playwright, Browser, Page
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class UnsubscribeStatus(Enum):
    SUCCESS = "success"
    FAILED = "failed"
    NOT_FOUND = "not_found"
    ALREADY_UNSUBSCRIBED = "already_unsubscribed"


@dataclass
class UnsubscribeResult:
    status: UnsubscribeStatus
    message: str
    screenshot_path: Optional[str] = None
    error_details: Optional[str] = None


class UnsubscribeService:
    """구독 해지 자동화 서비스"""

    def __init__(self):
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None

    async def __aenter__(self):
        """비동기 컨텍스트 매니저 진입"""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-accelerated-2d-canvas",
                "--no-first-run",
                "--no-zygote",
                "--disable-gpu",
            ],
        )
        self.page = await self.browser.new_page()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """비동기 컨텍스트 매니저 종료"""
        if self.page:
            await self.page.close()
        if self.browser:
            await self.browser.close()
        if hasattr(self, "playwright"):
            await self.playwright.stop()

    async def unsubscribe_from_service(
        self, service_name: str, email: str, password: str = None
    ) -> UnsubscribeResult:
        """
        특정 서비스에서 구독 해지 시도

        Args:
            service_name: 서비스 이름 (예: 'netflix', 'spotify')
            email: 계정 이메일
            password: 계정 비밀번호 (필요한 경우)

        Returns:
            UnsubscribeResult: 구독 해지 결과
        """
        try:
            # 서비스별 구독 해지 로직 매핑
            unsubscribe_methods = {
                "netflix": self._unsubscribe_netflix,
                "spotify": self._unsubscribe_spotify,
                "youtube": self._unsubscribe_youtube,
                "amazon": self._unsubscribe_amazon,
                "disney": self._unsubscribe_disney,
                "hulu": self._unsubscribe_hulu,
            }

            if service_name.lower() not in unsubscribe_methods:
                return UnsubscribeResult(
                    status=UnsubscribeStatus.FAILED,
                    message=f"지원하지 않는 서비스: {service_name}",
                )

            method = unsubscribe_methods[service_name.lower()]
            return await method(email, password)

        except Exception as e:
            logger.error(f"구독 해지 중 오류 발생: {str(e)}")
            return UnsubscribeResult(
                status=UnsubscribeStatus.FAILED,
                message=f"구독 해지 중 오류 발생: {str(e)}",
                error_details=str(e),
            )

    async def _unsubscribe_netflix(
        self, email: str, password: str
    ) -> UnsubscribeResult:
        """Netflix 구독 해지"""
        try:
            await self.page.goto("https://www.netflix.com/login")

            # 로그인
            await self.page.fill('input[name="userLoginId"]', email)
            await self.page.fill('input[name="password"]', password)
            await self.page.click('button[type="submit"]')

            # 계정 페이지로 이동
            await self.page.goto("https://www.netflix.com/account")

            # 구독 해지 버튼 찾기 및 클릭
            cancel_button = await self.page.query_selector('a[href*="cancel"]')
            if cancel_button:
                await cancel_button.click()

                # 확인 버튼 클릭
                confirm_button = await self.page.query_selector(
                    'button[data-uia="confirm-cancel"]'
                )
                if confirm_button:
                    await confirm_button.click()
                    return UnsubscribeResult(
                        status=UnsubscribeStatus.SUCCESS,
                        message="Netflix 구독이 성공적으로 해지되었습니다.",
                    )

            return UnsubscribeResult(
                status=UnsubscribeStatus.NOT_FOUND,
                message="Netflix 구독 해지 버튼을 찾을 수 없습니다.",
            )

        except Exception as e:
            return UnsubscribeResult(
                status=UnsubscribeStatus.FAILED,
                message=f"Netflix 구독 해지 실패: {str(e)}",
                error_details=str(e),
            )

    async def _unsubscribe_spotify(
        self, email: str, password: str
    ) -> UnsubscribeResult:
        """Spotify 구독 해지"""
        try:
            await self.page.goto("https://www.spotify.com/account/")

            # 로그인
            await self.page.fill('input[name="username"]', email)
            await self.page.fill('input[name="password"]', password)
            await self.page.click('button[type="submit"]')

            # 구독 관리 페이지로 이동
            await self.page.goto("https://www.spotify.com/account/subscription/")

            # 구독 해지 버튼 찾기 및 클릭
            cancel_button = await self.page.query_selector('a[href*="cancel"]')
            if cancel_button:
                await cancel_button.click()
                return UnsubscribeResult(
                    status=UnsubscribeStatus.SUCCESS,
                    message="Spotify 구독이 성공적으로 해지되었습니다.",
                )

            return UnsubscribeResult(
                status=UnsubscribeStatus.NOT_FOUND,
                message="Spotify 구독 해지 버튼을 찾을 수 없습니다.",
            )

        except Exception as e:
            return UnsubscribeResult(
                status=UnsubscribeStatus.FAILED,
                message=f"Spotify 구독 해지 실패: {str(e)}",
                error_details=str(e),
            )

    async def _unsubscribe_youtube(
        self, email: str, password: str = None
    ) -> UnsubscribeResult:
        """YouTube Premium 구독 해지"""
        try:
            await self.page.goto("https://www.youtube.com/paid_memberships")

            # 구독 해지 버튼 찾기
            cancel_button = await self.page.query_selector(
                'button[aria-label*="cancel"]'
            )
            if cancel_button:
                await cancel_button.click()

                # 확인 버튼 클릭
                confirm_button = await self.page.query_selector(
                    'button[aria-label*="confirm"]'
                )
                if confirm_button:
                    await confirm_button.click()
                    return UnsubscribeResult(
                        status=UnsubscribeStatus.SUCCESS,
                        message="YouTube Premium 구독이 성공적으로 해지되었습니다.",
                    )

            return UnsubscribeResult(
                status=UnsubscribeStatus.NOT_FOUND,
                message="YouTube Premium 구독 해지 버튼을 찾을 수 없습니다.",
            )

        except Exception as e:
            return UnsubscribeResult(
                status=UnsubscribeStatus.FAILED,
                message=f"YouTube Premium 구독 해지 실패: {str(e)}",
                error_details=str(e),
            )

    async def _unsubscribe_amazon(self, email: str, password: str) -> UnsubscribeResult:
        """Amazon Prime 구독 해지"""
        try:
            await self.page.goto("https://www.amazon.com/gp/primecentral")

            # 로그인
            await self.page.fill('input[name="email"]', email)
            await self.page.fill('input[name="password"]', password)
            await self.page.click('input[type="submit"]')

            # 구독 해지 버튼 찾기
            cancel_button = await self.page.query_selector('a[href*="cancel"]')
            if cancel_button:
                await cancel_button.click()
                return UnsubscribeResult(
                    status=UnsubscribeStatus.SUCCESS,
                    message="Amazon Prime 구독이 성공적으로 해지되었습니다.",
                )

            return UnsubscribeResult(
                status=UnsubscribeStatus.NOT_FOUND,
                message="Amazon Prime 구독 해지 버튼을 찾을 수 없습니다.",
            )

        except Exception as e:
            return UnsubscribeResult(
                status=UnsubscribeStatus.FAILED,
                message=f"Amazon Prime 구독 해지 실패: {str(e)}",
                error_details=str(e),
            )

    async def _unsubscribe_disney(self, email: str, password: str) -> UnsubscribeResult:
        """Disney+ 구독 해지"""
        try:
            await self.page.goto("https://www.disneyplus.com/account")

            # 로그인
            await self.page.fill('input[name="email"]', email)
            await self.page.fill('input[name="password"]', password)
            await self.page.click('button[type="submit"]')

            # 구독 해지 버튼 찾기
            cancel_button = await self.page.query_selector(
                'button[data-testid="cancel"]'
            )
            if cancel_button:
                await cancel_button.click()
                return UnsubscribeResult(
                    status=UnsubscribeStatus.SUCCESS,
                    message="Disney+ 구독이 성공적으로 해지되었습니다.",
                )

            return UnsubscribeResult(
                status=UnsubscribeStatus.NOT_FOUND,
                message="Disney+ 구독 해지 버튼을 찾을 수 없습니다.",
            )

        except Exception as e:
            return UnsubscribeResult(
                status=UnsubscribeStatus.FAILED,
                message=f"Disney+ 구독 해지 실패: {str(e)}",
                error_details=str(e),
            )

    async def _unsubscribe_hulu(self, email: str, password: str) -> UnsubscribeResult:
        """Hulu 구독 해지"""
        try:
            await self.page.goto("https://secure.hulu.com/account")

            # 로그인
            await self.page.fill('input[name="email"]', email)
            await self.page.fill('input[name="password"]', password)
            await self.page.click('button[type="submit"]')

            # 구독 해지 버튼 찾기
            cancel_button = await self.page.query_selector('a[href*="cancel"]')
            if cancel_button:
                await cancel_button.click()
                return UnsubscribeResult(
                    status=UnsubscribeStatus.SUCCESS,
                    message="Hulu 구독이 성공적으로 해지되었습니다.",
                )

            return UnsubscribeResult(
                status=UnsubscribeStatus.NOT_FOUND,
                message="Hulu 구독 해지 버튼을 찾을 수 없습니다.",
            )

        except Exception as e:
            return UnsubscribeResult(
                status=UnsubscribeStatus.FAILED,
                message=f"Hulu 구독 해지 실패: {str(e)}",
                error_details=str(e),
            )


# 동기 래퍼 함수
def unsubscribe_from_service_sync(
    service_name: str, email: str, password: str = None
) -> UnsubscribeResult:
    """동기적으로 구독 해지 실행"""
    return asyncio.run(
        UnsubscribeService()
        .__aenter__()
        .unsubscribe_from_service(service_name, email, password)
    )
