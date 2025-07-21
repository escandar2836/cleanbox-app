"""
Playwright 기반 구독해지 서비스
메모리 최적화와 브라우저 재사용을 통해 Render 환경에서 안정적으로 동작합니다.
"""

import asyncio
import logging
import re
import time
import os
import json
import psutil
from typing import List, Dict, Optional
from urllib.parse import urlparse

from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from bs4 import BeautifulSoup
import openai


class PlaywrightUnsubscribeService:
    """Playwright 기반 고급 구독해지 서비스 (메모리 최적화)"""

    def __init__(self):
        self.setup_logging()
        self.browser = None
        self.context = None
        self.page = None

        # 메모리 최적화 설정
        self.browser_args = [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-extensions",
            "--disable-plugins",
            "--disable-images",
            "--headless",
            "--window-size=640,480",
            "--max_old_space_size=64",
            "--single-process",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--memory-pressure-off",
            "--disable-web-security",
            "--disable-features=VizDisplayCompositor",
            "--disable-software-rasterizer",
            "--disable-threaded-animation",
            "--disable-threaded-scrolling",
            "--disable-logging",
            "--disable-dev-tools",
            "--disable-default-apps",
            "--disable-popup-blocking",
            "--disable-notifications",
            "--disable-remote-fonts",
            "--disable-smooth-scrolling",
            "--disable-webgl",
            "--disable-3d-apis",
            "--disable-accelerated-2d-canvas",
            "--disable-accelerated-jpeg-decoding",
            "--disable-accelerated-mjpeg-decode",
            "--disable-accelerated-video-decode",
            "--disable-accelerated-video-encode",
            "--disable-gpu-sandbox",
            "--disable-threaded-compositing",
            "--disable-touch-drag-drop",
            "--disable-touch-feedback",
            "--disable-xss-auditor",
            "--no-zygote",
            "--disable-ipc-flooding-protection",
            "--disable-renderer-backgrounding",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-features=TranslateUI",
            "--disable-ipc-flooding-protection",
            "--memory-pressure-off",
            "--max_old_space_size=64",
            "--disable-web-security",
            "--disable-features=VizDisplayCompositor",
            "--disable-software-rasterizer",
            "--disable-threaded-animation",
            "--disable-threaded-scrolling",
            "--disable-checker-imaging",
            "--disable-new-content-rendering-timeout",
            "--disable-hang-monitor",
            "--disable-prompt-on-repost",
            "--disable-client-side-phishing-detection",
            "--disable-component-update",
            "--disable-default-apps",
            "--disable-sync",
            "--disable-translate",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-networking",
            "--disable-sync-preferences",
            "--disable-background-mode",
            "--disable-background-downloads",
        ]

        # 타임아웃 설정 (Render 환경에 맞게 조정)
        self.timeouts = {
            "page_load": 30000,  # 30초
            "element_wait": 10000,  # 10초
            "api_call": 20000,  # 20초
            "retry_delay": 2000,  # 2초
        }

        # 통계 초기화
        self.stats = {
            "total_attempts": 0,
            "successful_unsubscribes": 0,
            "failed_unsubscribes": 0,
            "processing_times": [],
            "browser_reuses": 0,
            "memory_usage": [],
        }

    def _log_memory_usage(self, stage: str):
        """메모리 사용량 로깅"""
        try:
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024
            print(f"📊 메모리 사용량 [{stage}]: {memory_mb:.1f} MB")
            self.stats["memory_usage"].append(
                {"stage": stage, "memory_mb": memory_mb, "timestamp": time.time()}
            )
        except Exception as e:
            print(f"⚠️ 메모리 모니터링 실패: {str(e)}")

    async def initialize_browser(self):
        """브라우저 초기화 (재사용 가능)"""
        if self.browser is None:
            # 브라우저 경로 확인 및 동적 탐지
            import os
            import glob

            # Chrome 실행 파일 찾기
            chrome_paths = [
                os.path.expanduser(
                    "~/.cache/ms-playwright/chromium-*/chrome-linux/chrome"
                ),
                os.path.expanduser(
                    "~/.cache/ms-playwright/chromium-*/chrome-linux/chromium"
                ),
                "/root/.cache/ms-playwright/chromium-*/chrome-linux/chrome",
                "/root/.cache/ms-playwright/chromium-*/chrome-linux/chromium",
                "/ms-playwright/chromium-*/chrome-linux/chrome",
                "/ms-playwright/chromium-*/chrome-linux/chromium",
                "/usr/bin/chromium",
                "/usr/bin/chromium-browser",
                "/usr/bin/google-chrome",
            ]

            executable_path = None
            for path_pattern in chrome_paths:
                if "*" in path_pattern:
                    # 와일드카드 패턴 처리
                    matches = glob.glob(path_pattern)
                    if matches:
                        executable_path = matches[0]
                        print(f"📝 Chrome 실행 파일 발견: {executable_path}")
                        break
                elif os.path.exists(path_pattern):
                    executable_path = path_pattern
                    print(f"📝 Chrome 실행 파일 발견: {executable_path}")
                    break

            if not executable_path:
                print(
                    "⚠️ Chrome 실행 파일을 찾을 수 없습니다. 자동 감지 모드로 진행합니다."
                )

            playwright = await async_playwright().start()
            try:
                self.browser = await playwright.chromium.launch(
                    headless=True,
                    args=self.browser_args,
                    chromium_sandbox=False,
                    executable_path=executable_path,
                )
                print("✅ Playwright 브라우저 초기화 완료")
            except Exception as e:
                print(f"❌ 브라우저 초기화 실패: {str(e)}")
                # 재시도 (executable_path 없이)
                self.browser = await playwright.chromium.launch(
                    headless=True,
                    args=self.browser_args,
                    chromium_sandbox=False,
                )
                print("✅ Playwright 브라우저 초기화 완료 (재시도)")

        # 새 컨텍스트 생성 (기존 컨텍스트 재사용)
        if self.context is None:
            try:
                print(f" 브라우저 컨텍스트 생성 시작...")
                print(f"🔍 브라우저 상태: {self.browser}")
                print(f"🔍 브라우저 타입: {type(self.browser)}")
                print(
                    f"🔍 브라우저 메서드: {[m for m in dir(self.browser) if not m.startswith('_')]}"
                )

                self.context = await self.browser.new_context(
                    viewport={"width": 640, "height": 480},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    java_script_enabled=True,
                    ignore_https_errors=True,
                )
                print(f"🔍 컨텍스트 생성 결과: {self.context}")
                print(f"🔍 컨텍스트 타입: {type(self.context)}")
                print(
                    f"🔍 컨텍스트 메서드: {[m for m in dir(self.context) if not m.startswith('_')]}"
                )

                if self.context is None:
                    raise Exception("브라우저 컨텍스트 생성 실패")
                print("📝 새 브라우저 컨텍스트 생성")
            except Exception as e:
                print(f"❌ 브라우저 컨텍스트 생성 실패: {str(e)}")
                print(f"🔍 예외 타입: {type(e)}")
                print(f"🔍 예외 상세: {e}")
                print(f"🔍 예외 traceback: {e.__traceback__}")
                raise Exception(f"브라우저 컨텍스트 생성 실패: {str(e)}")
        else:
            self.stats["browser_reuses"] += 1
            print(
                f"♻️ 브라우저 컨텍스트 재사용 (재사용 횟수: {self.stats['browser_reuses']})"
            )

        # 새 페이지 생성
        try:
            print(f" 페이지 생성 시작...")
            print(f"🔍 컨텍스트 상태: {self.context}")
            print(f"🔍 컨텍스트 타입: {type(self.context)}")
            print(f"🔍 컨텍스트가 None인가?: {self.context is None}")

            if self.context is None:
                print(f"❌ 컨텍스트가 None입니다!")
                raise Exception("컨텍스트가 None입니다")

            print(f"🔍 new_page 메서드 호출 전...")
            self.page = await self.context.new_page()
            print(f"🔍 페이지 생성 결과: {self.page}")
            print(f" 페이지 타입: {type(self.page)}")
            print(f"🔍 페이지가 None인가?: {self.page is None}")

            if self.page is None:
                raise Exception("페이지 생성 실패")

            print(f"🔍 페이지 타임아웃 설정 시작...")
            self.page.set_default_timeout(self.timeouts["page_load"])
            print("✅ 새 페이지 생성 완료")
            return self.page
        except Exception as e:
            print(f"❌ 페이지 생성 실패: {str(e)}")
            print(f"🔍 예외 타입: {type(e)}")
            print(f"🔍 예외 상세: {e}")
            print(f"🔍 컨텍스트 상태: {self.context}")
            print(f" 페이지 상태: {self.page}")
            print(f"🔍 예외 traceback: {e.__traceback__}")
            # 페이지 정리 시도
            if self.page:
                try:
                    await self.page.close()
                except:
                    pass
                self.page = None
            raise Exception(f"페이지 생성 실패: {str(e)}")

    async def cleanup_page(self):
        """페이지 정리 (컨텍스트는 유지)"""
        if self.page:
            try:
                await self.page.close()
                print("🧹 페이지 정리 완료")
            except Exception as e:
                print(f"⚠️ 페이지 정리 중 오류: {str(e)}")
            finally:
                self.page = None

    async def cleanup_browser(self):
        """브라우저 완전 정리"""
        if self.page:
            await self.cleanup_page()

        if self.context:
            try:
                await self.context.close()
                print("🧹 브라우저 컨텍스트 정리 완료")
            except Exception as e:
                print(f"⚠️ 컨텍스트 정리 중 오류: {str(e)}")
            finally:
                self.context = None

        if self.browser:
            try:
                await self.browser.close()
                print("🧹 브라우저 정리 완료")
            except Exception as e:
                print(f"⚠️ 브라우저 정리 중 오류: {str(e)}")
            finally:
                self.browser = None

    def extract_unsubscribe_links(
        self, email_content: str, email_headers: Dict = None
    ) -> List[str]:
        """이메일에서 구독해지 링크 추출 (기존과 동일)"""
        print(f"🔍 extract_unsubscribe_links 시작")
        unsubscribe_links = []

        # 1. 이메일 헤더에서 List-Unsubscribe 필드 확인
        if email_headers:
            list_unsubscribe = email_headers.get("List-Unsubscribe", "")
            print(f"📝 List-Unsubscribe 헤더: {list_unsubscribe}")
            if list_unsubscribe:
                links = [link.strip() for link in list_unsubscribe.split(",")]
                unsubscribe_links.extend(links)
                print(f"📝 헤더에서 추출된 링크: {links}")

        # 2. 이메일 본문에서 구독해지 링크 패턴 검색
        print(f"📝 이메일 본문에서 패턴 검색 시작")
        patterns = [
            r'https?://[^\s<>"]*unsubscribe[^\s<>"]*',
            r'https?://[^\s<>"]*opt-out[^\s<>"]*',
            r'https?://[^\s<>"]*remove[^\s<>"]*',
            r'https?://[^\s<>"]*cancel[^\s<>"]*',
            r'https?://[^\s<>"]*subscription[^\s<>"]*',
            r'https?://[^\s<>"]*email[^\s<>"]*preferences[^\s<>"]*',
            r'https?://[^\s<>"]*manage[^\s<>"]*subscription[^\s<>"]*',
            r'https?://[^\s<>"]*preferences[^\s<>"]*',
            r'https?://[^\s<>"]*settings[^\s<>"]*',
            r'https?://[^\s<>"]*account[^\s<>"]*',
        ]

        for i, pattern in enumerate(patterns):
            matches = re.findall(pattern, email_content, re.IGNORECASE)
            if matches:
                print(f"📝 패턴 {i + 1}에서 매치 발견: {matches}")
            unsubscribe_links.extend(matches)

        # 3. HTML 태그에서 링크 추출
        print(f"📝 HTML 태그에서 링크 추출 시작")
        soup = BeautifulSoup(email_content, "html.parser")
        html_links_found = 0

        for link in soup.find_all("a", href=True):
            href = link.get("href", "").lower()
            link_text = link.get_text().lower()

            unsubscribe_keywords = [
                "unsubscribe",
                "opt-out",
                "remove",
                "cancel",
                "구독해지",
                "구독취소",
                "수신거부",
                "수신취소",
                "email preferences",
                "manage subscription",
                "subscription settings",
            ]

            for keyword in unsubscribe_keywords:
                if keyword in href or keyword in link_text:
                    unsubscribe_links.append(link["href"])
                    html_links_found += 1
                    print(
                        f"📝 HTML에서 구독해지 링크 발견: {link['href']} (키워드: {keyword})"
                    )
                    break

        print(f"📝 HTML에서 발견된 구독해지 링크 수: {html_links_found}")

        # 중복 제거 및 유효한 URL만 필터링
        print(f"📝 중복 제거 및 유효성 검사 시작")
        print(f"📝 추출된 총 링크 수: {len(unsubscribe_links)}")

        valid_links = []
        for link in set(unsubscribe_links):
            if self._is_valid_unsubscribe_url(link):
                valid_links.append(link)
                print(f"📝 유효한 링크 추가: {link}")
            else:
                print(f"❌ 유효하지 않은 링크 제외: {link}")

        print(f"📝 최종 유효한 링크 수: {len(valid_links)}")
        return valid_links

    def _is_valid_unsubscribe_url(self, url: str) -> bool:
        """유효한 구독해지 URL인지 확인"""
        try:
            parsed = urlparse(url)
            return parsed.scheme in ["http", "https"] and parsed.netloc
        except:
            return False

    async def process_unsubscribe_with_playwright_ai(
        self, unsubscribe_url: str, user_email: str = None
    ) -> Dict:
        """Playwright + OpenAI API를 활용한 범용 구독해지 처리 (메모리 최적화)"""
        start_time = time.time()
        self.log_unsubscribe_attempt(unsubscribe_url, user_email, start_time)

        max_retries = 2
        retry_count = 0

        while retry_count <= max_retries:
            try:
                print(
                    f"🔧 Playwright + AI 구독해지 시도 (시도 {retry_count + 1}/{max_retries + 1}): {unsubscribe_url}"
                )

                # 브라우저 초기화
                page = await self.initialize_browser()

                # 페이지가 None인지 확인
                if page is None:
                    raise Exception("브라우저 페이지 초기화 실패")

                # 1단계: 초기 페이지 접속
                print(f"📝 1단계: 초기 페이지 접속")
                await page.goto(unsubscribe_url, wait_until="domcontentloaded")
                await page.wait_for_timeout(2000)  # 페이지 로딩 대기

                # 2단계: 구독해지 성공 상태 확인
                print(f"📝 2단계: 구독해지 성공 상태 확인")
                if await self._check_unsubscribe_success(page):
                    await self.cleanup_page()
                    return {
                        "success": True,
                        "message": "구독해지가 완료되었습니다.",
                        "error_type": "unsubscribe_success",
                        "processing_time": time.time() - start_time,
                    }

                # 3단계: 기본 구독해지 시도
                print(f"📝 3단계: 기본 구독해지 시도")
                basic_result = await self._try_basic_unsubscribe(page, user_email)
                if basic_result["success"]:
                    await self.cleanup_page()
                    return self._finalize_success(basic_result, start_time)

                # 4단계: 두 번째 페이지 처리
                print(f"📝 4단계: 두 번째 페이지 처리")
                second_result = await self._try_second_page_unsubscribe(
                    page, user_email
                )
                if second_result["success"]:
                    await self.cleanup_page()
                    return self._finalize_success(second_result, start_time)

                # 5단계: AI 분석 및 처리
                print(f"📝 5단계: AI 분석 및 처리")
                ai_result = await self._analyze_page_with_ai(page, user_email)
                if ai_result["success"]:
                    await self.cleanup_page()
                    return self._finalize_success(ai_result, start_time)

                # 6단계: 최종 구독해지 성공 상태 확인
                print(f"📝 6단계: 최종 구독해지 성공 상태 확인")
                if await self._check_unsubscribe_success(page):
                    await self.cleanup_page()
                    return {
                        "success": True,
                        "message": "구독해지가 완료되었습니다.",
                        "error_type": "unsubscribe_success",
                        "processing_time": time.time() - start_time,
                    }

                # 모든 방법 실패
                await self.cleanup_page()
                return self._finalize_failure(
                    "모든 구독해지 방법에서 실패했습니다.", start_time
                )

            except Exception as e:
                print(f"❌ Playwright + AI 구독해지 시도 실패: {str(e)}")
                await self.cleanup_page()
                retry_count += 1

                if retry_count <= max_retries:
                    print(f"🔄 재시도 중... ({retry_count}/{max_retries})")
                    await asyncio.sleep(2)  # 재시도 전 대기
                else:
                    return self._finalize_failure(
                        f"구독해지 처리 실패: {str(e)}", start_time
                    )

        return self._finalize_failure("최대 재시도 횟수 초과", start_time)

    async def _try_basic_unsubscribe(self, page: Page, user_email: str = None) -> Dict:
        """기본 구독해지 처리 (통합 JavaScript 기반)"""
        try:
            print(f"📝 기본 구독해지 처리 시작")

            # 통합 JavaScript 기반 구독해지 처리
            return await self._try_javascript_submit(
                page, user_email, is_recursive=False
            )

        except Exception as e:
            return {
                "success": False,
                "message": f"기본 구독해지 처리 실패: {str(e)}",
            }

    async def _try_legacy_unsubscribe(self, page: Page, user_email: str = None) -> Dict:
        """기존 방식의 구독해지 처리 (하위 호환성)"""
        try:
            # 기존 선택자들
            legacy_selectors = [
                "button[type='submit']",
                "input[type='submit']",
                "button",
                "input[type='button']",
                "a[href*='unsubscribe']",
                "a[href*='opt-out']",
                ".confirm-button",
                ".submit-button",
                ".unsubscribe-button",
                "#confirm",
                "#submit",
                "#unsubscribe",
                "[class*='confirm']",
                "[class*='submit']",
                "[class*='unsubscribe']",
            ]

            for selector in legacy_selectors:
                try:
                    elements = await page.query_selector_all(selector)
                    for element in elements:
                        is_visible = await element.is_visible()
                        is_enabled = await element.is_enabled()

                        if is_visible and is_enabled:
                            element_text = await element.text_content()
                            print(
                                f"📝 기존 방식 요소 발견: {selector} - 텍스트: '{element_text}'"
                            )

                            # 구독해지 관련 키워드 확인
                            unsubscribe_keywords = [
                                "unsubscribe",
                                "구독해지",
                                "opt-out",
                                "수신거부",
                                "remove",
                                "제거",
                                "cancel",
                                "취소",
                                "confirm",
                                "확인",
                                "submit",
                                "제출",
                            ]

                            is_unsubscribe_element = any(
                                keyword in element_text.lower()
                                for keyword in unsubscribe_keywords
                            )

                            if (
                                is_unsubscribe_element
                                or "unsubscribe" in selector.lower()
                            ):
                                print(f"📝 기존 방식 요소 클릭: {element_text}")

                                # 클릭 전 현재 URL 저장
                                before_url = page.url

                                # 클릭 실행 (짧은 타임아웃)
                                try:
                                    await element.click(timeout=5000)
                                except Exception as click_error:
                                    print(
                                        f"⚠️ 클릭 실패, JavaScript로 재시도: {str(click_error)}"
                                    )
                                    await page.evaluate(
                                        "(element) => element.click()", element
                                    )

                                # 짧은 대기
                                await page.wait_for_timeout(2000)

                                # URL 변경 확인
                                after_url = page.url
                                if before_url != after_url:
                                    print(
                                        f"📝 URL 변경 감지: {before_url} → {after_url}"
                                    )

                                # 구독해지 완료 확인
                                if await self._check_unsubscribe_success(page):
                                    return {
                                        "success": True,
                                        "message": "기존 방식 클릭 후 구독해지 완료 확인",
                                        "method": "legacy_completed",
                                        "selector": selector,
                                    }
                                # AI 기반 구독해지 완료 판단
                                print("🤖 AI 기반 구독해지 완료 분석 시작...")
                                ai_result = (
                                    await self._analyze_unsubscribe_completion_with_ai(
                                        page
                                    )
                                )

                                if (
                                    ai_result["success"]
                                    and ai_result["confidence"] >= 70
                                ):
                                    print(
                                        f"🤖 AI 분석으로 구독해지 완료 확인 (신뢰도: {ai_result['confidence']}%)"
                                    )
                                    return {
                                        "success": True,
                                        "message": f"기존 방식 구독해지 성공 (AI 신뢰도: {ai_result['confidence']}%)",
                                        "ai_confidence": ai_result["confidence"],
                                        "ai_reason": ai_result["reason"],
                                    }
                                else:
                                    print(
                                        f"🤖 AI 분석 결과: 구독해지 미완료 (신뢰도: {ai_result['confidence']}%)"
                                    )
                                    # 기존 방식으로도 확인
                                    if await self._check_basic_success_indicators(page):
                                        print("📝 기본 지표로 성공 확인")
                                        return {
                                            "success": True,
                                            "message": "기존 방식 구독해지 성공",
                                        }
                                    else:
                                        print("📝 구독해지 미완료로 판단")
                                        return {
                                            "success": False,
                                            "message": "기존 방식 구독해지 미완료",
                                        }

                except Exception as e:
                    print(f"⚠️ 기존 방식 선택자 {selector} 처리 중 오류: {str(e)}")
                    continue

            return {
                "success": False,
                "message": "기존 방식 구독해지 요소를 찾을 수 없습니다",
            }

        except Exception as e:
            return {"success": False, "message": f"기존 방식 구독해지 실패: {str(e)}"}

    async def _analyze_unsubscribe_completion_with_ai(self, page: Page) -> Dict:
        """AI를 사용한 구독해지 완료 분석 (단순화된 버전)"""
        try:
            # 페이지 정보 추출
            current_url = page.url
            title = await page.title()
            content = await page.content()

            # 단순화된 프롬프트 생성
            prompt = f"""
다음 웹 페이지에서 구독해지 상태를 분석해주세요.

URL: {current_url}
제목: {title}
페이지 내용: {content[:2000]}

중요한 판단 기준:
1. 재구독 버튼("다시 구독하기", "Resubscribe", "재구독")이 나타나면 구독해지가 성공한 것입니다.
2. "이미 구독해지됨", "already unsubscribed" 등의 메시지도 성공입니다.
3. "오류", "실패", "error", "failed" 등의 메시지는 실패입니다.

JSON 형식으로 답변해주세요:
{{
    "success": true/false,
    "confidence": 0-100,
    "reason": "판단 근거"
}}
"""

            # OpenAI API 호출
            ai_response = await self._call_simple_ai_api(prompt)

            return self._parse_simple_ai_result(ai_response, current_url, title)

        except Exception as e:
            print(f"⚠️ AI 구독해지 완료 분석 실패: {str(e)}")
            return {"success": False, "confidence": 0, "reason": str(e)}

    def _parse_simple_ai_result(self, ai_response: str, url: str, title: str) -> Dict:
        """AI 응답을 직접 파싱 (단순화된 버전)"""
        try:
            import json

            # JSON 파싱 시도
            try:
                # JSON 블록 찾기
                start_idx = ai_response.find("{")
                end_idx = ai_response.rfind("}") + 1
                if start_idx != -1 and end_idx != 0:
                    json_str = ai_response[start_idx:end_idx]
                    data = json.loads(json_str)

                    result = {
                        "success": data.get("success", False),
                        "confidence": data.get("confidence", 50),
                        "reason": data.get("reason", ai_response),
                        "url": url,
                        "title": title,
                    }

                    print(f"🤖 AI 구독해지 완료 분석 (단순화):")
                    print(f"   - 성공 여부: {result['success']}")
                    print(f"   - 신뢰도: {result['confidence']}%")
                    print(f"   - 이유: {result['reason']}")

                    return result

            except json.JSONDecodeError:
                pass

            # JSON 파싱 실패 시 텍스트 기반 판단
            response_lower = ai_response.lower()

            # 성공 지표들
            success_indicators = [
                "success",
                "true",
                "성공",
                "완료",
                "완료됨",
                "구독해지됨",
                "unsubscribed",
                "cancelled",
                "resubscribe",
                "다시 구독하기",
                "재구독",
                "already unsubscribed",
                "이미 구독해지",
            ]

            # 실패 지표들
            failure_indicators = [
                "false",
                "실패",
                "오류",
                "error",
                "failed",
                "완료되지 않음",
                "invalid",
                "not found",
                "expired",
            ]

            # 판단
            is_success = any(
                indicator in response_lower for indicator in success_indicators
            )
            is_failure = any(
                indicator in response_lower for indicator in failure_indicators
            )

            # 최종 판단 (성공 지표가 있으면 성공, 실패 지표만 있으면 실패)
            success = is_success or (not is_failure and "success" in response_lower)
            confidence = 80 if success else 20

            result = {
                "success": success,
                "confidence": confidence,
                "reason": ai_response,
                "url": url,
                "title": title,
            }

            print(f"🤖 AI 구독해지 완료 분석 (텍스트 기반):")
            print(f"   - 성공 여부: {success}")
            print(f"   - 신뢰도: {confidence}%")
            print(f"   - 이유: {ai_response}")

            return result

        except Exception as e:
            print(f"⚠️ AI 응답 파싱 실패: {str(e)}")
            return {
                "success": False,
                "confidence": 0,
                "reason": f"파싱 오류: {str(e)}",
                "url": url,
                "title": title,
            }

    async def _check_post_request_success(self, page: Page) -> bool:
        """POST 요청 성공 여부 확인 (AI 기반 개선)"""
        try:
            # 기존 방식으로 먼저 확인
            basic_result = await self._check_basic_success_indicators(page)
            if basic_result:
                print("📝 기본 지표로 성공 확인")
                return True

            # AI 기반 분석으로 추가 확인
            print("🤖 AI 기반 구독해지 완료 분석 시작...")
            ai_result = await self._analyze_unsubscribe_completion_with_ai(page)

            if ai_result["success"] and ai_result["confidence"] >= 70:
                print(f"🤖 AI 분석으로 성공 확인 (신뢰도: {ai_result['confidence']}%)")
                return True

            return False

        except Exception as e:
            print(f"⚠️ POST 요청 확인 중 오류: {str(e)}")
            return False

    async def _analyze_page_for_next_action(self, page: Page) -> Dict:
        """페이지 분석하여 다음 액션 결정"""
        try:
            ai_result = await self._analyze_unsubscribe_completion_with_ai(page)

            if ai_result["success"]:
                # 구독해지가 완료된 경우 성공
                return {
                    "action": "success",
                    "message": "구독해지가 완료되었습니다",
                    "confidence": ai_result["confidence"],
                }
            else:
                # 구독해지가 완료되지 않은 경우 실패
                return {
                    "action": "error",
                    "message": "구독해지 중 오류가 발생했습니다",
                    "confidence": ai_result["confidence"],
                }

        except Exception as e:
            return {
                "action": "error",
                "message": f"페이지 분석 실패: {str(e)}",
                "confidence": 0,
            }

    async def _call_simple_ai_api(self, prompt: str) -> str:
        """단순화된 OpenAI API 호출"""
        try:
            client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

            response = client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {
                        "role": "system",
                        "content": "웹 페이지의 구독해지 완료 여부를 판단하는 AI입니다. JSON 형식으로 답변하세요.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=200,
                temperature=0.1,
            )

            content = response.choices[0].message.content
            print(f"🤖 AI 응답: {content}")
            return content

        except Exception as e:
            print(f"⚠️ OpenAI API 호출 실패: {str(e)}")
            return '{"success": false, "confidence": 0, "reason": "API 호출 실패"}'

    def _parse_simple_completion_result(self, ai_response: str) -> Dict:
        """단순화된 AI 응답 파싱 (하위 호환성)"""
        try:
            import json

            # JSON 파싱 시도
            try:
                start_idx = ai_response.find("{")
                end_idx = ai_response.rfind("}") + 1
                if start_idx != -1 and end_idx != 0:
                    json_str = ai_response[start_idx:end_idx]
                    data = json.loads(json_str)

                    return {
                        "success": data.get("success", False),
                        "confidence": data.get("confidence", 50),
                        "reason": data.get("reason", ai_response),
                    }
            except json.JSONDecodeError:
                pass

            # 텍스트 기반 판단 (하위 호환성)
            response_lower = ai_response.lower()

            success_indicators = [
                "success",
                "true",
                "성공",
                "완료",
                "완료됨",
                "구독해지됨",
                "unsubscribed",
                "cancelled",
                "resubscribe",
                "다시 구독하기",
                "재구독",
                "already unsubscribed",
                "이미 구독해지",
            ]

            failure_indicators = [
                "false",
                "실패",
                "오류",
                "error",
                "failed",
                "완료되지 않음",
                "invalid",
                "not found",
                "expired",
            ]

            is_success = any(
                indicator in response_lower for indicator in success_indicators
            )
            is_failure = any(
                indicator in response_lower for indicator in failure_indicators
            )

            success = is_success or (not is_failure and "success" in response_lower)
            confidence = 80 if success else 20

            return {
                "success": success,
                "confidence": confidence,
                "reason": ai_response,
            }

        except Exception as e:
            print(f"⚠️ 단순화된 AI 응답 파싱 실패: {str(e)}")
            return {"success": False, "confidence": 0, "reason": f"파싱 오류: {str(e)}"}

    async def _check_basic_success_indicators(self, page: Page) -> bool:
        """기본 성공 지표 확인 (개선된 버전)"""
        try:
            # 1. URL 기반 확인
            current_url = page.url
            success_url_indicators = [
                "success",
                "confirmed",
                "unsubscribed",
                "cancelled",
                "removed",
                "thank",
                "complete",
                "완료",
                "성공",
                "확인",
                "해지",
                "취소",
            ]

            if any(
                indicator in current_url.lower() for indicator in success_url_indicators
            ):
                print(f"📝 URL 기반 성공 확인: {current_url}")
                return True

            # 2. 페이지 제목 기반 확인
            title = await page.title()
            success_title_indicators = [
                "unsubscribed",
                "cancelled",
                "removed",
                "confirmed",
                "success",
                "complete",
                "thank you",
                "구독해지",
                "취소",
                "확인",
                "완료",
                "성공",
            ]

            if any(
                indicator in title.lower() for indicator in success_title_indicators
            ):
                print(f"📝 제목 기반 성공 확인: {title}")
                return True

            # 3. 페이지 내용 기반 확인
            content = await page.content()
            content_lower = content.lower()

            success_content_indicators = [
                "successfully unsubscribed",
                "unsubscribed successfully",
                "subscription cancelled",
                "cancelled successfully",
                "removed from mailing list",
                "no longer receive",
                "thank you for",
                "구독해지 완료",
                "구독이 취소되었습니다",
                "수신거부 완료",
                "더 이상 수신하지 않습니다",
                "감사합니다",
                "성공적으로",
                "완료되었습니다",
            ]

            if any(
                indicator in content_lower for indicator in success_content_indicators
            ):
                print(f"📝 내용 기반 성공 확인")
                return True

            # 4. 특정 요소 기반 확인
            success_elements = [
                ".success-message",
                ".confirmation-message",
                ".thank-you-message",
                "#success",
                "#confirmation",
                "#thank-you",
                "[class*='success']",
                "[class*='confirm']",
                "[class*='thank']",
                "[id*='success']",
                "[id*='confirm']",
                "[id*='thank']",
            ]

            for selector in success_elements:
                try:
                    element = await page.query_selector(selector)
                    if element and await element.is_visible():
                        element_text = await element.text_content()
                        if element_text:
                            print(
                                f"📝 요소 기반 성공 확인: {selector} - {element_text}"
                            )
                            return True
                except Exception:
                    continue

            # 5. 재구독 버튼 확인 (성공 지표)
            resubscribe_indicators = [
                "resubscribe",
                "다시 구독하기",
                "재구독",
                "subscribe again",
                "re-subscribe",
                "다시 구독",
                "재구독하기",
            ]

            if any(indicator in content_lower for indicator in resubscribe_indicators):
                print(f"📝 재구독 버튼 발견 - 구독해지 성공으로 인식")
                return True

            # 6. 오류 메시지 확인 (실패 지표)
            error_indicators = [
                "error",
                "failed",
                "invalid",
                "not found",
                "expired",
                "오류",
                "실패",
                "잘못된",
                "찾을 수 없음",
                "만료됨",
            ]

            if any(indicator in content_lower for indicator in error_indicators):
                print(f"📝 오류 지표 발견")
                return False

            # 7. AI 기반 분석 (보조 지표)
            try:
                ai_result = await self._analyze_unsubscribe_completion_with_ai(page)
                if ai_result["success"] and ai_result["confidence"] >= 60:
                    print(f"📝 AI 기반 성공 확인 (신뢰도: {ai_result['confidence']}%)")
                    return True
            except Exception as e:
                print(f"⚠️ AI 분석 실패: {str(e)}")

            return False

        except Exception as e:
            print(f"⚠️ 성공 지표 확인 실패: {str(e)}")
            return False

    async def _check_unsubscribe_success(self, page: Page) -> bool:
        """구독해지 성공 상태인지 확인 (이미 구독해지됨 + 구독해지 성공)"""
        try:
            content = await page.content()
            content_lower = content.lower()
            current_url = page.url
            title = await page.title()

            # 기본 키워드 체크 (빠른 필터링)
            basic_indicators = [
                # 이미 구독해지됨 지표
                "already unsubscribed",
                "already cancelled",
                "already removed",
                "previously unsubscribed",
                "previously cancelled",
                "previously removed",
                "이미 구독해지",
                "이미 취소",
                "이미 해지",
                "이미 수신거부",
                "이미 수신취소",
                "이미 구독해지됨",
                "이미 취소됨",
                "이미 해지됨",
                "이미 수신거부됨",
                "이미 수신취소됨",
                "이미 구독해지되었습니다",
                "이미 취소되었습니다",
                "이미 해지되었습니다",
                "이미 수신거부되었습니다",
                "이미 수신취소되었습니다",
                # 구독해지 성공 지표
                "unsubscribe successful",
                "successfully unsubscribed",
                "unsubscribe completed",
                "you have been unsubscribed",
                "구독해지가 완료되었습니다",
                "구독해지 성공",
                "구독해지 완료",
                "구독이 해지되었습니다",
                "구독해지 처리 완료",
                "unsubscribe processed",
            ]

            # URL, 제목, 내용에서 기본 지표 확인
            all_text = f"{current_url} {title} {content_lower}"

            for indicator in basic_indicators:
                if indicator in all_text:
                    print(f"📝 구독해지 성공 지표 발견: {indicator}")
                    return True

            # AI 기반 분석 (기본 키워드가 없는 경우)
            print(f"📝 AI 기반 구독해지 상태 분석 시작")

            # 페이지 텍스트 추출 (HTML 태그 제거)
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(content, "html.parser")
            page_text = soup.get_text(separator=" ", strip=True)

            # AI 프롬프트 생성
            ai_prompt = f"""
다음 웹페이지의 내용을 분석하여 사용자의 구독해지 상태를 판단해주세요.

페이지 제목: {title}
페이지 URL: {current_url}
페이지 내용: {page_text[:2000]}  # 처음 2000자만 사용

다음과 같은 메시지들이 있으면 "이미 구독해지됨"으로 판단합니다:
- "현재 이메일은 구독중인 이메일이 아닙니다"
- "이미 구독해지된 상태입니다"
- "You are not subscribed to this newsletter"
- "Already unsubscribed"
- "구독 중인 이메일이 아닙니다"
- "이미 구독해지되었습니다"
- "구독 상태가 아닙니다"
- "not subscribed"
- "no longer subscribed"
- "subscription not found"
- "이메일이 구독 목록에 없습니다"
- "구독 정보를 찾을 수 없습니다"

다음과 같은 메시지들이 있으면 "구독해지 성공"으로 판단합니다:
- "구독해지가 완료되었습니다"
- "Unsubscribe successful"
- "Successfully unsubscribed"
- "구독해지 성공"
- "구독해지 완료"
- "Unsubscribe completed"
- "You have been unsubscribed"
- "구독이 해지되었습니다"
- "구독해지 처리 완료"
- "Unsubscribe processed"

답변은 다음 형식으로만 해주세요:
- 이미 구독해지됨: "ALREADY_UNSUBSCRIBED"
- 구독해지 성공: "SUCCESS"
- 구독해지 실패: "FAILED"
- 판단 불가: "UNKNOWN"

답변:
"""

            # AI API 호출
            try:
                ai_response = await self._call_simple_ai_api(ai_prompt)
                print(f"📝 AI 응답: {ai_response}")

                if "ALREADY_UNSUBSCRIBED" in ai_response.upper():
                    print(f"📝 AI가 이미 구독해지됨으로 판단")
                    return True
                elif "SUCCESS" in ai_response.upper():
                    print(f"📝 AI가 구독해지 성공으로 판단")
                    return True
                elif "FAILED" in ai_response.upper():
                    print(f"📝 AI가 구독해지 실패로 판단")
                    return False
                else:
                    print(f"📝 AI가 판단 불가로 응답")
                    return False

            except Exception as ai_error:
                print(f"⚠️ AI 분석 실패: {str(ai_error)}")
            return False

        except Exception as e:
            print(f"⚠️ 구독해지 상태 확인 실패: {str(e)}")
            return False

    async def _create_temp_page_from_response(
        self, response_text: str
    ) -> Optional[Page]:
        """응답 내용을 임시 페이지로 생성"""
        try:
            # 임시 HTML 페이지 생성
            temp_html = f"""
            <!DOCTYPE html>
            <html>
            <head><title>Response</title></head>
            <body>{response_text}</body>
            </html>
            """

            # 새 페이지 생성
            temp_page = await self.browser.new_page()
            await temp_page.set_content(temp_html)

            return temp_page

        except Exception as e:
            print(f"⚠️ 임시 페이지 생성 실패: {str(e)}")
            return None

    async def _parse_post_response(self, response) -> Optional[Page]:
        """POST 응답을 임시 페이지로 파싱"""
        try:
            content_type = response.headers.get("content-type", "")

            if "text/html" in content_type:
                # HTML 응답
                response_text = await response.text()
                return await self._create_temp_page_from_response(response_text)

            elif "application/json" in content_type:
                # JSON 응답
                import json

                json_data = await response.json()
                response_text = json.dumps(json_data, indent=2)
                return await self._create_temp_page_from_response(response_text)

            else:
                # 일반 텍스트 응답
                response_text = await response.text()
                return await self._create_temp_page_from_response(response_text)

        except Exception as e:
            print(f"⚠️ POST 응답 파싱 실패: {str(e)}")
            return None

    async def _check_response_with_temp_page(self, response) -> bool:
        """임시 페이지로 응답 확인 (메모리 최적화)"""
        temp_page = None
        try:
            temp_page = await self._parse_post_response(response)
            if temp_page:
                return await self._check_unsubscribe_success(temp_page)
            return False
        finally:
            if temp_page:
                await temp_page.close()

    async def _detect_page_navigation(
        self, page: Page, before_url: str, before_title: str = None
    ) -> Dict:
        """페이지 이동 감지 및 처리"""
        try:
            await page.wait_for_timeout(2000)  # 페이지 로딩 대기

            after_url = page.url
            after_title = await page.title()

            # URL 변경 감지
            url_changed = before_url != after_url
            title_changed = before_title and before_title != after_title

            if url_changed:
                print(f"📝 URL 변경 감지: {before_url} → {after_url}")

                # 새 페이지에서 구독해지 완료 확인
                if await self._check_unsubscribe_success(page):
                    return {
                        "success": True,
                        "message": "페이지 이동 후 구독해지 완료 확인",
                        "method": "navigation_completed",
                        "url_change": f"{before_url} → {after_url}",
                    }

                # 기본 성공 지표 확인
                elif await self._check_basic_success_indicators(page):
                    return {
                        "success": True,
                        "message": "페이지 이동 후 구독해지 성공",
                        "method": "navigation_success",
                        "url_change": f"{before_url} → {after_url}",
                    }

            elif title_changed:
                print(f"📝 제목 변경 감지: {before_title} → {after_title}")

                # 제목 변경 후 구독해지 완료 확인
                if await self._check_unsubscribe_success(page):
                    return {
                        "success": True,
                        "message": "제목 변경 후 구독해지 완료 확인",
                        "method": "title_change_completed",
                        "title_change": f"{before_title} → {after_title}",
                    }

            # 페이지 이동이 없었지만 구독해지 완료 확인
            if await self._check_unsubscribe_success(page):
                return {
                    "success": True,
                    "message": "페이지 이동 없이 구독해지 완료 확인",
                    "method": "no_navigation_completed",
                }

            return {
                "success": False,
                "message": "페이지 이동 감지됨 but 구독해지 미완료",
                "method": "navigation_detected_but_incomplete",
                "url_changed": url_changed,
                "title_changed": title_changed,
            }

        except Exception as e:
            print(f"⚠️ 페이지 이동 감지 실패: {str(e)}")
            return {
                "success": False,
                "message": f"페이지 이동 감지 실패: {str(e)}",
                "method": "navigation_detection_failed",
            }

    async def _wait_for_network_idle_and_check(
        self, page: Page, timeout: int = 10000
    ) -> Dict:
        """네트워크 요청 완료 대기 후 구독해지 확인"""
        try:
            # 네트워크 요청 완료 대기
            await page.wait_for_load_state("networkidle", timeout=timeout)
            print("📝 네트워크 요청 완료 대기 성공")

            # 구독해지 완료 확인
            if await self._check_unsubscribe_success(page):
                return {
                    "success": True,
                    "message": "네트워크 요청 완료 후 구독해지 완료 확인",
                    "method": "network_idle_completed",
                }

            return {
                "success": False,
                "message": "네트워크 요청 완료 but 구독해지 미완료",
                "method": "network_idle_incomplete",
            }

        except Exception as e:
            print(f"⚠️ 네트워크 대기 실패: {str(e)}")
            # 네트워크 대기 실패 시 기본 대기로 전환
            await page.wait_for_timeout(3000)

            if await self._check_unsubscribe_success(page):
                return {
                    "success": True,
                    "message": "기본 대기 후 구독해지 완료 확인",
                    "method": "timeout_fallback_completed",
                }

            return {
                "success": False,
                "message": f"네트워크 대기 실패: {str(e)}",
                "method": "network_wait_failed",
            }

    async def _detect_captcha(self, page: Page) -> bool:
        """CAPTCHA 감지"""
        try:
            captcha_selectors = [
                ".captcha",
                ".recaptcha",
                "[class*='captcha']",
                "#captcha",
                "[id*='captcha']",
                ".g-recaptcha",
                "[class*='recaptcha']",
                "[id*='recaptcha']",
                ".h-captcha",
                "[class*='h-captcha']",
                ".turnstile",
                "[class*='turnstile']",
                "iframe[src*='recaptcha']",
                "iframe[src*='captcha']",
                "iframe[src*='turnstile']",
                "iframe[src*='hcaptcha']",
            ]

            for selector in captcha_selectors:
                elements = await page.query_selector_all(selector)
                if elements:
                    print(f"📝 CAPTCHA 감지: {selector}")
                    return True

            # CAPTCHA 관련 텍스트 확인
            content = await page.content()
            content_lower = content.lower()

            captcha_keywords = [
                "captcha",
                "recaptcha",
                "turnstile",
                "hcaptcha",
                "로봇이 아닙니다",
                "인간임을 확인",
                "보안 확인",
                "verify you are human",
                "i am not a robot",
            ]

            for keyword in captcha_keywords:
                if keyword in content_lower:
                    print(f"📝 CAPTCHA 키워드 감지: {keyword}")
                    return True

            return False

        except Exception as e:
            print(f"⚠️ CAPTCHA 감지 실패: {str(e)}")
            return False

    async def _handle_captcha_required(self, page: Page) -> Dict:
        """CAPTCHA 요구 시 처리"""
        return {
            "success": False,
            "message": "CAPTCHA가 요구되어 자동 처리할 수 없습니다. 수동으로 처리해주세요.",
            "error_type": "captcha_required",
            "method": "captcha_detected",
        }

    async def _handle_email_confirmation(
        self, page: Page, user_email: str = None
    ) -> bool:
        """이메일 확인 요구 처리"""
        try:
            if not user_email:
                print("⚠️ 사용자 이메일이 없어 이메일 확인 처리 불가")
                return False

            # 이메일 입력 필드 감지
            email_inputs = await page.query_selector_all(
                "input[type='email'], input[name*='email'], input[placeholder*='email'], input[placeholder*='이메일']"
            )

            if email_inputs:
                print(f"📝 이메일 입력 필드 발견: {len(email_inputs)}개")

                for email_input in email_inputs:
                    try:
                        # 이메일 입력
                        await email_input.fill(user_email)
                        print(f"📝 이메일 입력: {user_email}")

                        # 이메일 입력 후 제출 버튼 찾기
                        submit_selectors = [
                            "input[type='submit']",
                            "button[type='submit']",
                            "button",
                            "[class*='submit']",
                            "[class*='confirm']",
                        ]

                        for submit_selector in submit_selectors:
                            submit_elements = await page.query_selector_all(
                                submit_selector
                            )
                            for submit_element in submit_elements:
                                if await submit_element.is_visible():
                                    element_text = await submit_element.text_content()
                                    print(f"📝 제출 버튼 클릭: {element_text}")

                                    # 제출 버튼 클릭
                                    await submit_element.click()

                                    # 페이지 이동 또는 응답 대기
                                    await page.wait_for_timeout(3000)

                                    # 구독해지 완료 확인
                                    if await self._check_unsubscribe_success(page):
                                        print("✅ 이메일 확인 후 구독해지 완료")
                                        return True

                                    break

                    except Exception as e:
                        print(f"⚠️ 이메일 입력 처리 실패: {str(e)}")
                        continue

                return False

            return False

        except Exception as e:
            print(f"⚠️ 이메일 확인 처리 실패: {str(e)}")
            return False

    async def _execute_complex_javascript(self, page: Page) -> bool:
        """복잡한 JavaScript 로직 실행"""
        try:
            print("📝 복잡한 JavaScript 로직 실행 시도")

            # JavaScript 함수 감지 및 실행
            js_result = await page.evaluate(
                """
                () => {
                    const functions = ['unsubscribe', 'confirmUnsubscribe', 'processUnsubscribe', 'handleUnsubscribe'];
                    
                    for (const funcName of functions) {
                        if (typeof window[funcName] === 'function') {
                            console.log('Found function:', funcName);
                            try {
                                window[funcName]();
                                return { success: true, function: funcName };
                            } catch (e) {
                                console.error('Function execution failed:', e);
                            }
                        }
                    }
                    
                    // Form submit 시도
                    const forms = document.querySelectorAll('form');
                    for (const form of forms) {
                        if (form.action && form.action.toLowerCase().includes('unsubscribe')) {
                            console.log('Found unsubscribe form');
                            form.submit();
                            return { success: true, method: 'form_submit' };
                        }
                    }
                    
                    // 버튼 클릭 시도
                    const buttons = document.querySelectorAll('button, input[type="submit"], a');
                    for (const button of buttons) {
                        const text = button.textContent || button.value || '';
                        if (text.toLowerCase().includes('unsubscribe') || 
                            text.toLowerCase().includes('구독해지') ||
                            text.toLowerCase().includes('취소') ||
                            text.toLowerCase().includes('해지')) {
                            console.log('Found unsubscribe button:', text);
                            button.click();
                            return { success: true, method: 'button_click', button: text };
                        }
                    }
                    
                    return { success: false, reason: 'no_method_found' };
                }
            """
            )

            if js_result.get("success"):
                print(f"📝 JavaScript 실행 성공: {js_result}")

                # 비동기 처리 대기
                await page.wait_for_timeout(5000)

                # 동적 콘텐츠 로딩 대기
                try:
                    await page.wait_for_function(
                        """
                        () => {
                            return document.querySelector('.success-message') !== null ||
                                   document.querySelector('.error-message') !== null ||
                                   document.querySelector('[class*="success"]') !== null ||
                                   document.querySelector('[class*="error"]') !== null ||
                                   document.querySelector('[id*="success"]') !== null ||
                                   document.querySelector('[id*="error"]') !== null;
                        }
                    """,
                        timeout=10000,
                    )
                    print("📝 동적 콘텐츠 로딩 완료")
                except Exception as e:
                    print(f"⚠️ 동적 콘텐츠 대기 실패: {str(e)}")

                return True
            else:
                print(f"⚠️ JavaScript 실행 실패: {js_result}")
                return False

        except Exception as e:
            print(f"⚠️ 복잡한 JavaScript 실행 실패: {str(e)}")
            return False

    async def _wait_for_service_worker(self, page: Page) -> bool:
        """Service Worker 등록 대기 (타임아웃 포함)"""
        try:
            print("📝 Service Worker 등록 대기")

            # Service Worker 등록 확인 (5초 타임아웃)
            sw_result = await page.evaluate(
                """
                () => {
                    return new Promise((resolve) => {
                        if ('serviceWorker' in navigator) {
                            // 5초 타임아웃 설정
                            const timeout = setTimeout(() => {
                                resolve({ success: false, message: 'Service Worker timeout' });
                            }, 5000);
                            
                            navigator.serviceWorker.ready.then(() => {
                                clearTimeout(timeout);
                                resolve({ success: true, message: 'Service Worker ready' });
                            }).catch(e => {
                                clearTimeout(timeout);
                                resolve({ success: false, error: e.message });
                            });
                        } else {
                            resolve({ success: false, message: 'Service Worker not supported' });
                        }
                    });
                }
                """
            )

            if sw_result.get("success"):
                print("📝 Service Worker 등록 완료")
                return True
            else:
                print(f"⚠️ Service Worker 등록 실패: {sw_result}")
                return False

        except Exception as e:
            print(f"⚠️ Service Worker 대기 실패: {str(e)}")
            return False

    async def _detect_spa_navigation(self, page: Page, before_url: str) -> bool:
        """SPA 네비게이션 감지"""
        try:
            print("📝 SPA 네비게이션 감지")

            # History API 변경 감지
            navigation_result = await page.wait_for_function(
                """
                (beforeUrl) => {
                    return window.location.pathname !== beforeUrl ||
                           window.location.search !== '' ||
                           window.location.hash !== '';
                }
            """,
                arg=before_url,
                timeout=5000,
            )

            if navigation_result:
                current_url = page.url
                print(f"📝 SPA 네비게이션 감지: {before_url} → {current_url}")
                return True

            return False

        except Exception as e:
            print(f"⚠️ SPA 네비게이션 감지 실패: {str(e)}")
            return False

    async def _handle_multi_step_unsubscribe(
        self, page: Page, user_email: str = None
    ) -> Dict:
        """다단계 구독해지 처리 (무한 루프 방지)"""
        try:
            print("📝 다단계 구독해지 처리 시작")
            steps = []

            # 1단계: 직접적인 구독해지 시도 (무한 루프 방지)
            print("📝 1단계: 직접 구독해지 시도")

            # Form submit 시도
            forms = await page.query_selector_all("form")
            for form in forms:
                try:
                    action = await form.get_attribute("action")
                    if action and "unsubscribe" in action.lower():
                        print(f"📝 다단계 Form submit 실행: {action}")

                        # 클릭 전 상태 저장
                        before_url = page.url
                        before_title = await page.title()

                        # JavaScript로 form submit 실행
                        await page.evaluate("(form) => form.submit()", form)

                        # 페이지 이동 감지
                        navigation_result = await self._detect_page_navigation(
                            page, before_url, before_title
                        )
                        if navigation_result["success"]:
                            steps.append("1단계 완료 (Form submit)")
                            print("✅ 1단계 완료 (Form submit)")
                            break

                except Exception as e:
                    print(f"⚠️ 다단계 Form submit 실패: {str(e)}")
                    continue

            # Form submit이 성공하지 않았으면 버튼 클릭 시도
            if not steps:
                enhanced_selectors = [
                    "input[type='submit']",
                    "button[type='submit']",
                    "button",
                    ".unsubscribe-button",
                    "#unsubscribe",
                    "[class*='unsubscribe']",
                    ".confirm-button",
                    ".submit-button",
                    "[class*='confirm']",
                ]

                for selector in enhanced_selectors:
                    try:
                        elements = await page.query_selector_all(selector)
                        for element in elements:
                            if (
                                await element.is_visible()
                                and await element.is_enabled()
                            ):
                                element_text = await element.text_content()
                                print(
                                    f"📝 다단계 버튼 클릭: {selector} - '{element_text}'"
                                )

                                # 클릭 전 상태 저장
                                before_url = page.url
                                before_title = await page.title()

                                # JavaScript로 클릭
                                await page.evaluate(
                                    "(element) => element.click()", element
                                )

                                # 페이지 이동 감지
                                navigation_result = await self._detect_page_navigation(
                                    page, before_url, before_title
                                )
                                if navigation_result["success"]:
                                    steps.append("1단계 완료 (버튼 클릭)")
                                    print("✅ 1단계 완료 (버튼 클릭)")
                                    break

                    except Exception as e:
                        print(f"⚠️ 다단계 버튼 클릭 실패: {str(e)}")
                        continue

                    if steps:  # 성공했으면 중단
                        break

            # 2단계: 완료 페이지 확인
            if steps:
                print("📝 2단계: 완료 페이지 확인")
                await page.wait_for_timeout(3000)  # 페이지 로딩 대기

                final_result = await self._check_unsubscribe_success(page)
                if final_result:
                    steps.append("2단계 완료")
                    print("✅ 2단계 완료")
                    return {
                        "success": True,
                        "message": "다단계 구독해지 완료",
                        "method": "multi_step_completed",
                        "steps": steps,
                    }
                else:
                    # 기본 성공 지표 확인
                    if await self._check_basic_success_indicators(page):
                        steps.append("2단계 완료 (기본 지표)")
                        print("✅ 2단계 완료 (기본 지표)")
                        return {
                            "success": True,
                            "message": "다단계 구독해지 완료 (기본 지표)",
                            "method": "multi_step_basic_completed",
                            "steps": steps,
                        }

            return {
                "success": False,
                "message": "다단계 구독해지 실패",
                "method": "multi_step_failed",
                "steps": steps,
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"다단계 구독해지 처리 실패: {str(e)}",
                "method": "multi_step_error",
            }

    async def _try_second_page_unsubscribe(
        self, page: Page, user_email: str = None
    ) -> Dict:
        """두 번째 페이지 구독해지 처리 (통합 JavaScript 기반)"""
        try:
            print(f"📝 두 번째 페이지 구독해지 처리 시작")

            # 통합 JavaScript 기반 구독해지 처리
            return await self._try_javascript_submit(
                page, user_email, is_recursive=False
            )

        except Exception as e:
            return {
                "success": False,
                "message": f"두 번째 페이지 구독해지 실패: {str(e)}",
            }

    async def _try_form_action_submit(self, page: Page, user_email: str = None) -> Dict:
        """Form Action URL을 통한 구독해지 처리"""
        try:
            print(f"📝 Form Action URL 처리 시도")

            # Form 요소 찾기
            forms = await page.query_selector_all("form")

            for form in forms:
                try:
                    action = await form.get_attribute("action")
                    method = await form.get_attribute("method") or "GET"

                    if action and "unsubscribe" in action.lower():
                        print(f"📝 구독해지 Form 발견: {action}")

                        # Form 데이터 수집
                        form_data = {}
                        inputs = await form.query_selector_all("input")

                        for input_elem in inputs:
                            name = await input_elem.get_attribute("name")
                            value = await input_elem.get_attribute("value")
                            input_type = await input_elem.get_attribute("type")

                            if name and input_type != "submit":
                                form_data[name] = value or ""

                        print(f"📝 Form 데이터: {form_data}")

                        # POST 요청 실행 (개선된 버전)
                        if method.upper() == "POST":
                            response = await page.request.post(action, data=form_data)
                            print(f"📝 POST 요청 완료: {response.status}")

                            if response.status in [200, 201, 302]:
                                # 응답 내용을 임시 페이지로 파싱하여 _check_unsubscribe_success 사용
                                if await self._check_response_with_temp_page(response):
                                    return {
                                        "success": True,
                                        "message": "POST 응답에서 구독해지 완료 확인",
                                        "method": "form_action_post_completed",
                                    }
                                # 기본 성공 지표 확인 (페이지가 변경된 경우)
                                elif await self._check_basic_success_indicators(page):
                                    return {
                                        "success": True,
                                        "message": "Form Action URL을 통한 구독해지 성공",
                                        "method": "form_action_post",
                                    }

                        # GET 요청 실행
                        elif method.upper() == "GET":
                            query_string = "&".join(
                                [f"{k}={v}" for k, v in form_data.items()]
                            )
                            full_url = (
                                f"{action}?{query_string}" if query_string else action
                            )

                            await page.goto(full_url, wait_until="domcontentloaded")
                            await page.wait_for_timeout(2000)

                            # 구독해지 완료 확인
                            if await self._check_unsubscribe_success(page):
                                return {
                                    "success": True,
                                    "message": "Form Action GET 후 구독해지 완료 확인",
                                    "method": "form_action_get_completed",
                                }
                            # 기본 성공 지표 확인
                            elif await self._check_basic_success_indicators(page):
                                return {
                                    "success": True,
                                    "message": "Form Action URL을 통한 구독해지 성공",
                                    "method": "form_action_get",
                                }

                except Exception as e:
                    print(f"⚠️ Form 처리 중 오류: {str(e)}")
                    continue

            return {"success": False, "message": "Form Action URL 처리 실패"}

        except Exception as e:
            return {"success": False, "message": f"Form Action URL 처리 실패: {str(e)}"}

    async def _try_javascript_submit(
        self, page: Page, user_email: str = None, is_recursive: bool = False
    ) -> Dict:
        """통합 JavaScript 기반 구독해지 처리 (모든 방법 통합 + 개선된 기능)"""
        try:
            print(f"📝 통합 JavaScript 구독해지 처리 시작")
            self._log_memory_usage("javascript_submit_start")

            # 0단계: CAPTCHA 감지 및 처리
            if await self._detect_captcha(page):
                return await self._handle_captcha_required(page)

            # 1단계: 이메일 확인 요구 처리
            if await self._handle_email_confirmation(page, user_email):
                # 이메일 입력 후 구독해지 완료 확인
                if await self._check_unsubscribe_success(page):
                    return {
                        "success": True,
                        "message": "이메일 확인 후 구독해지 완료",
                        "method": "email_confirmation_completed",
                    }

            # 2단계: Form Action URL 처리 (POST 응답 파싱 포함)
            form_result = await self._try_form_action_submit(page, user_email)
            if form_result["success"]:
                return form_result

            # 3단계: Form submit JavaScript 실행
            self._log_memory_usage("form_submit_start")
            forms = await page.query_selector_all("form")
            print(f"📝 발견된 form 개수: {len(forms)}")

            for form in forms:
                try:
                    action = await form.get_attribute("action")
                    print(f"📝 Form action: {action}")

                    # React 앱의 경우 action이 없을 수 있음
                    if action and "unsubscribe" in action.lower():
                        print(f"📝 JavaScript Form submit 실행: {action}")

                        # 클릭 전 상태 저장
                        before_url = page.url
                        before_title = await page.title()

                        # JavaScript로 form submit 실행
                        await page.evaluate("(form) => form.submit()", form)

                        # SPA 네비게이션 감지
                        if await self._detect_spa_navigation(page, before_url):
                            if await self._check_unsubscribe_success(page):
                                return {
                                    "success": True,
                                    "message": "SPA 네비게이션 후 구독해지 완료",
                                    "method": "spa_navigation_completed",
                                }

                        # 페이지 이동 감지 및 처리
                        navigation_result = await self._detect_page_navigation(
                            page, before_url, before_title
                        )
                        if navigation_result["success"]:
                            return navigation_result

                        # 네트워크 요청 완료 대기 후 확인
                        network_result = await self._wait_for_network_idle_and_check(
                            page
                        )
                        if network_result["success"]:
                            return network_result
                    else:
                        # React 앱의 경우 form 내부 버튼 클릭으로 처리
                        print(f"📝 React 앱 Form 처리 시도")
                        buttons = await form.query_selector_all("button[type='submit']")
                        if buttons:
                            for button in buttons:
                                if (
                                    await button.is_visible()
                                    and await button.is_enabled()
                                ):
                                    button_text = await button.text_content()
                                    print(f"📝 React Form 버튼 발견: '{button_text}'")

                                    # 클릭 전 상태 저장
                                    before_url = page.url
                                    before_title = await page.title()

                                    # JavaScript로 클릭
                                    await page.evaluate(
                                        "(button) => button.click()", button
                                    )

                                    # 페이지 이동 감지 및 처리
                                    navigation_result = (
                                        await self._detect_page_navigation(
                                            page, before_url, before_title
                                        )
                                    )
                                    if navigation_result["success"]:
                                        return navigation_result

                                    # 네트워크 요청 완료 대기 후 확인
                                    network_result = (
                                        await self._wait_for_network_idle_and_check(
                                            page
                                        )
                                    )
                                    if network_result["success"]:
                                        return network_result

                except Exception as e:
                    print(f"⚠️ JavaScript Form submit 실패: {str(e)}")
                    continue

            # 4단계: 복잡한 JavaScript 로직 실행
            if await self._execute_complex_javascript(page):
                # 복잡한 JavaScript 실행 후 구독해지 완료 확인
                if await self._check_unsubscribe_success(page):
                    return {
                        "success": True,
                        "message": "복잡한 JavaScript 실행 후 구독해지 완료",
                        "method": "complex_js_completed",
                    }

            # 5단계: 개선된 선택자로 클릭 처리
            enhanced_selectors = [
                # 기본 버튼/입력
                "input[type='submit']",
                "button[type='submit']",
                "button",
                # React 앱 특화 선택자
                "form button[type='submit']",
                "form .btn",
                "form button.btn",
                "footer button",
                "section button",
                # 텍스트 기반 선택자 (React 앱용)
                "button:has-text('수신거부하기')",
                "button:has-text('Unsubscribe')",
                "button:has-text('구독해지')",
                "button:has-text('취소')",
                # 구독해지 관련
                ".unsubscribe-button",
                "#unsubscribe",
                "[class*='unsubscribe']",
                "a[href*='unsubscribe']",
                "a[href*='opt-out']",
                # 확인/제출 관련
                ".confirm-button",
                ".submit-button",
                "#confirm",
                "#submit",
                "[class*='confirm']",
                "[class*='submit']",
                # React 앱 클래스명 패턴
                "[class*='btn']",
                "[class*='button']",
                "[class*='submit']",
                "[class*='unsubscribe']",
            ]

            # React 앱 로딩 대기
            try:
                await page.wait_for_function(
                    """
                    () => {
                        // React 앱이 로드되었는지 확인
                        const root = document.getElementById('root');
                        if (!root) return false;
                        
                        // 버튼이 있는지 확인
                        const buttons = root.querySelectorAll('button');
                        return buttons.length > 0;
                    }
                """,
                    timeout=10000,
                )
                print("📝 React 앱 로딩 완료")
            except Exception as e:
                print(f"⚠️ React 앱 대기 실패: {str(e)}")

            for selector in enhanced_selectors:
                try:
                    elements = await page.query_selector_all(selector)
                    print(f"📝 선택자 '{selector}'에서 {len(elements)}개 요소 발견")

                    for element in elements:
                        is_visible = await element.is_visible()
                        is_enabled = await element.is_enabled()

                        if is_visible and is_enabled:
                            element_text = await element.text_content()
                            print(
                                f"📝 발견된 요소: {selector} - 텍스트: '{element_text}'"
                            )

                            # 재구독 버튼 확인 (클릭하면 안 됨!)
                            resubscribe_keywords = [
                                "resubscribe",
                                "다시 구독하기",
                                "재구독",
                                "subscribe again",
                                "re-subscribe",
                                "다시 구독",
                                "재구독하기",
                            ]

                            is_resubscribe_button = any(
                                keyword in element_text.lower()
                                for keyword in resubscribe_keywords
                            )

                            if is_resubscribe_button:
                                print(
                                    f"🎉 재구독 버튼 발견 - 구독해지 성공으로 인식 (클릭하지 않음)"
                                )
                                return {
                                    "success": True,
                                    "message": "재구독 버튼 발견으로 구독해지 성공 확인",
                                    "method": "resubscribe_button_detected",
                                    "button_text": element_text,
                                }

                            # 구독해지 관련 키워드 확인
                            unsubscribe_keywords = [
                                "수신거부하기",
                                "unsubscribe",
                                "구독해지",
                                "취소",
                                "opt-out",
                                "remove",
                                "cancel",
                                "해지",
                            ]

                            is_unsubscribe_button = any(
                                keyword in element_text.lower()
                                for keyword in unsubscribe_keywords
                            )

                            if is_unsubscribe_button:
                                print(
                                    f"📝 구독해지 버튼 발견: {selector} - 텍스트: '{element_text}'"
                                )

                                # 클릭 전 상태 저장
                                before_url = page.url
                                before_title = await page.title()

                                # JavaScript로 클릭 이벤트 실행
                                await page.evaluate(
                                    "(element) => element.click()", element
                                )

                                # SPA 네비게이션 감지
                                if await self._detect_spa_navigation(page, before_url):
                                    if await self._check_unsubscribe_success(page):
                                        return {
                                            "success": True,
                                            "message": "SPA 네비게이션 후 구독해지 완료",
                                            "method": "spa_navigation_completed",
                                        }

                                # 페이지 이동 감지 및 처리
                                navigation_result = await self._detect_page_navigation(
                                    page, before_url, before_title
                                )
                                if navigation_result["success"]:
                                    return navigation_result

                                # 네트워크 요청 완료 대기 후 확인
                                network_result = (
                                    await self._wait_for_network_idle_and_check(page)
                                )
                                if network_result["success"]:
                                    return network_result

                except Exception as e:
                    print(f"⚠️ JavaScript 클릭 실패: {str(e)}")
                    continue

            # 6단계: 다단계 구독해지 처리 (재귀 호출 방지)
            if not is_recursive:
                multi_step_result = await self._handle_multi_step_unsubscribe(
                    page, user_email
                )
                if multi_step_result["success"]:
                    return multi_step_result

            # 7단계: 링크 기반 처리
            link_result = await self._try_link_based_unsubscribe(page, user_email)
            if link_result["success"]:
                return link_result

            return {"success": False, "message": "통합 JavaScript 구독해지 처리 실패"}

        except Exception as e:
            return {
                "success": False,
                "message": f"통합 JavaScript 구독해지 처리 실패: {str(e)}",
            }

    async def _try_enhanced_selectors(self, page: Page, user_email: str = None) -> Dict:
        """개선된 선택자로 구독해지 처리"""
        try:
            print(f"📝 개선된 선택자 처리 시도")

            # 확장된 선택자 목록
            enhanced_selectors = [
                # 기본 버튼/입력
                "input[type='submit']",
                "button[type='submit']",
                "input[type='button']",
                "button",
                # 구독해지 관련
                "a[href*='unsubscribe']",
                "a[href*='opt-out']",
                "a[href*='remove']",
                "a[href*='cancel']",
                ".unsubscribe",
                "#unsubscribe",
                "[class*='unsubscribe']",
                "[id*='unsubscribe']",
                ".unsubscribe-button",
                "#unsubscribe-button",
                # 확인/제출 관련
                ".confirm-button",
                ".submit-button",
                "#confirm",
                "#submit",
                "[class*='confirm']",
                "[class*='submit']",
                "[id*='confirm']",
                "[id*='submit']",
                # 일반적인 버튼
                ".btn",
                ".button",
                "[class*='btn']",
                "[class*='button']",
                # 텍스트 기반 선택자
                "button:has-text('Unsubscribe')",
                "button:has-text('구독해지')",
                "button:has-text('Confirm')",
                "button:has-text('확인')",
                "input:has-text('Unsubscribe')",
                "input:has-text('구독해지')",
                # 폼 관련
                "form[action*='unsubscribe']",
                "form[action*='opt-out']",
                "form[action*='remove']",
                "form[action*='cancel']",
            ]

            for selector in enhanced_selectors:
                try:
                    elements = await page.query_selector_all(selector)

                    for element in elements:
                        is_visible = await element.is_visible()
                        is_enabled = await element.is_enabled()

                        if is_visible and is_enabled:
                            element_text = await element.text_content()
                            print(
                                f"📝 개선된 선택자 요소 발견: {selector} - 텍스트: '{element_text}'"
                            )

                            # 재구독 버튼 확인 (클릭하면 안 됨!)
                            resubscribe_keywords = [
                                "resubscribe",
                                "다시 구독하기",
                                "재구독",
                                "subscribe again",
                                "re-subscribe",
                                "다시 구독",
                                "재구독하기",
                            ]

                            is_resubscribe_button = any(
                                keyword in element_text.lower()
                                for keyword in resubscribe_keywords
                            )

                            if is_resubscribe_button:
                                print(
                                    f"🎉 재구독 버튼 발견 - 구독해지 성공으로 인식 (클릭하지 않음)"
                                )
                                return {
                                    "success": True,
                                    "message": "재구독 버튼 발견으로 구독해지 성공 확인",
                                    "method": "resubscribe_button_detected",
                                    "button_text": element_text,
                                }

                            # 구독해지 관련 키워드 확인
                            action_keywords = [
                                "confirm",
                                "확인",
                                "submit",
                                "제출",
                                "unsubscribe",
                                "구독해지",
                                "cancel",
                                "취소",
                                "remove",
                                "제거",
                                "opt-out",
                                "수신거부",
                                "수신취소",
                            ]

                            is_action_element = any(
                                (
                                    keyword in element_text.lower()
                                    if element_text
                                    else False
                                )
                                for keyword in action_keywords
                            )

                            if is_action_element or any(
                                keyword in selector.lower()
                                for keyword in ["unsubscribe", "confirm", "submit"]
                            ):
                                print(f"📝 개선된 선택자 요소 클릭: {element_text}")

                                # 클릭 전 현재 URL 저장
                                before_url = page.url

                                # 클릭 실행 (타임아웃 증가)
                                try:
                                    await element.click(timeout=15000)
                                except Exception as click_error:
                                    print(
                                        f"⚠️ 클릭 실패, JavaScript로 재시도: {str(click_error)}"
                                    )
                                    await page.evaluate(
                                        "(element) => element.click()", element
                                    )

                                # 네트워크 요청 완료 대기
                                try:
                                    await page.wait_for_load_state(
                                        "networkidle", timeout=10000
                                    )
                                    print("📝 네트워크 요청 완료 대기 성공")
                                except Exception as e:
                                    print(
                                        f"⚠️ 네트워크 대기 실패, 기본 대기로 전환: {str(e)}"
                                    )
                                    await page.wait_for_timeout(5000)

                                # URL 변경 확인
                                after_url = page.url
                                if before_url != after_url:
                                    print(
                                        f"📝 URL 변경 감지: {before_url} → {after_url}"
                                    )

                                # 구독해지 완료 확인
                                if await self._check_unsubscribe_success(page):
                                    return {
                                        "success": True,
                                        "message": "개선된 선택자 클릭 후 구독해지 완료 확인",
                                        "method": "enhanced_selectors_completed",
                                        "selector": selector,
                                    }
                                # 기본 성공 지표 확인
                                elif await self._check_basic_success_indicators(page):
                                    return {
                                        "success": True,
                                        "message": f"개선된 선택자로 구독해지 성공: {selector}",
                                        "method": "enhanced_selector",
                                        "selector": selector,
                                    }

                except Exception as e:
                    print(f"⚠️ 개선된 선택자 {selector} 처리 중 오류: {str(e)}")
                    continue

            return {"success": False, "message": "개선된 선택자 처리 실패"}

        except Exception as e:
            return {"success": False, "message": f"개선된 선택자 처리 실패: {str(e)}"}

    async def _try_link_based_unsubscribe(
        self, page: Page, user_email: str = None
    ) -> Dict:
        """링크 기반 구독해지 처리"""
        try:
            print(f"📝 링크 기반 구독해지 처리 시도")

            # 모든 링크 찾기
            links = await page.query_selector_all("a[href]")

            for link in links:
                try:
                    href = await link.get_attribute("href")
                    link_text = await link.text_content()

                    # 재구독 링크 확인 (클릭하면 안 됨!)
                    resubscribe_keywords = [
                        "resubscribe",
                        "다시 구독하기",
                        "재구독",
                        "subscribe again",
                        "re-subscribe",
                        "다시 구독",
                        "재구독하기",
                    ]

                    is_resubscribe_link = any(
                        keyword in link_text.lower() for keyword in resubscribe_keywords
                    )

                    if is_resubscribe_link:
                        print(
                            f"🎉 재구독 링크 발견 - 구독해지 성공으로 인식 (클릭하지 않음)"
                        )
                        return {
                            "success": True,
                            "message": "재구독 링크 발견으로 구독해지 성공 확인",
                            "method": "resubscribe_link_detected",
                            "link_text": link_text,
                        }

                    if href and any(
                        keyword in href.lower()
                        for keyword in ["unsubscribe", "opt-out", "remove", "cancel"]
                    ):
                        print(f"📝 구독해지 링크 발견: {href} - 텍스트: '{link_text}'")

                        # 링크 클릭
                        await link.click(timeout=15000)

                        # 네트워크 요청 완료 대기
                        try:
                            await page.wait_for_load_state("networkidle", timeout=10000)
                            print("📝 링크 클릭 후 네트워크 요청 완료 대기 성공")
                        except Exception as e:
                            print(f"⚠️ 네트워크 대기 실패, 기본 대기로 전환: {str(e)}")
                            await page.wait_for_timeout(5000)

                        # 구독해지 완료 확인
                        if await self._check_unsubscribe_success(page):
                            return {
                                "success": True,
                                "message": "링크 클릭 후 구독해지 완료 확인",
                                "method": "link_based_completed",
                                "link": href,
                            }
                        # 기본 성공 지표 확인
                        elif await self._check_basic_success_indicators(page):
                            return {
                                "success": True,
                                "message": f"링크 기반 구독해지 성공: {href}",
                                "method": "link_based",
                                "link": href,
                            }

                except Exception as e:
                    print(f"⚠️ 링크 처리 중 오류: {str(e)}")
                    continue

            return {"success": False, "message": "링크 기반 구독해지 처리 실패"}

        except Exception as e:
            return {
                "success": False,
                "message": f"링크 기반 구독해지 처리 실패: {str(e)}",
            }

    async def _analyze_page_with_ai(self, page: Page, user_email: str = None) -> Dict:
        """AI를 사용한 페이지 분석 및 처리"""
        try:
            # 페이지 정보 추출
            page_info = await self._extract_page_info(page)

            # AI 프롬프트 생성
            prompt = self._create_ai_prompt(page_info, user_email)

            # OpenAI API 호출
            ai_response = await self._call_openai_api(prompt)

            # AI 지시 실행
            return await self._execute_ai_instructions(page, ai_response, user_email)

        except Exception as e:
            return {"success": False, "message": f"AI 분석 실패: {str(e)}"}

    async def _extract_page_info(self, page: Page) -> Dict:
        """페이지 정보 추출"""
        try:
            # 페이지 제목
            title = await page.title()

            # 모든 링크
            links = await page.eval_on_selector_all(
                "a[href]",
                """
                (elements) => {
                    return elements.map(el => ({
                        text: el.textContent?.trim() || '',
                        href: el.href || '',
                        class: Array.from(el.classList || []),
                        id: el.id || ''
                    }));
                }
            """,
            )

            # 모든 버튼
            buttons = await page.eval_on_selector_all(
                "button",
                """
                (elements) => {
                    return elements.map(el => ({
                        text: el.textContent?.trim() || '',
                        type: el.type || '',
                        class: Array.from(el.classList || []),
                        id: el.id || ''
                    }));
                }
            """,
            )

            # 모든 폼
            forms = await page.eval_on_selector_all(
                "form",
                """
                (elements) => {
                    return elements.map(el => ({
                        action: el.action || '',
                        method: el.method || '',
                        class: Array.from(el.classList || []),
                        id: el.id || ''
                    }));
                }
            """,
            )

            return {
                "title": title,
                "url": page.url,
                "links": links,
                "buttons": buttons,
                "forms": forms,
            }

        except Exception as e:
            print(f"⚠️ 페이지 정보 추출 실패: {str(e)}")
            return {"error": str(e)}

    def _create_ai_prompt(self, page_info: Dict, user_email: str = None) -> str:
        """AI 프롬프트 생성"""
        prompt = f"""
웹 페이지에서 구독해지 기능을 찾아 실행해주세요.

페이지 정보:
- 제목: {page_info.get('title', 'N/A')}
- URL: {page_info.get('url', 'N/A')}

사용자 이메일: {user_email or 'N/A'}

사용 가능한 요소들:
"""

        # 링크 정보 추가
        if page_info.get("links"):
            prompt += "\n링크들:\n"
            for link in page_info["links"][:10]:  # 처음 10개만
                prompt += f"- 텍스트: '{link['text']}', href: '{link['href']}'\n"

        # 버튼 정보 추가
        if page_info.get("buttons"):
            prompt += "\n버튼들:\n"
            for button in page_info["buttons"][:10]:  # 처음 10개만
                prompt += f"- 텍스트: '{button['text']}', 타입: '{button['type']}'\n"

        prompt += """
다음 중 하나의 액션을 선택하고 실행하세요:
1. 구독해지 링크 클릭
2. 구독해지 버튼 클릭
3. 폼 제출
4. 확인 버튼 클릭

응답 형식:
{
    "action": "link_click|button_click|form_submit|confirm",
    "target": "클릭할 텍스트나 선택자",
    "reason": "선택한 이유"
}
"""

        return prompt

    async def _call_openai_api(self, prompt: str) -> Dict:
        """OpenAI API 호출"""
        try:
            client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

            response = client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {
                        "role": "system",
                        "content": "웹 페이지에서 구독해지 기능을 찾아 실행하는 AI 어시스턴트입니다.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=500,
                temperature=0.1,
            )

            content = response.choices[0].message.content
            print(f"🤖 AI 응답: {content}")

            # JSON 파싱 시도
            try:
                return json.loads(content)
            except:
                # JSON이 아닌 경우 기본 응답
                return {"action": "none", "reason": "AI 응답을 파싱할 수 없습니다"}

        except Exception as e:
            print(f"⚠️ OpenAI API 호출 실패: {str(e)}")
            return {"action": "none", "reason": f"OpenAI API 오류: {str(e)}"}

    async def _execute_ai_instructions(
        self, page: Page, ai_response: Dict, user_email: str = None
    ) -> Dict:
        """AI 지시 실행 (AI 기반 완료 판단 적용)"""
        try:
            action = ai_response.get("action", "none")
            target = ai_response.get("target", "")

            if action == "none":
                return {
                    "success": False,
                    "message": ai_response.get(
                        "reason", "구독해지 요소를 찾을 수 없습니다"
                    ),
                }

            elif action == "link_click":
                # 링크 클릭 처리
                elements = await page.query_selector_all("a")
                for element in elements:
                    element_text = await element.text_content()
                    if target.lower() in element_text.lower():
                        print(f"📝 AI 지시에 따른 링크 클릭: {element_text}")

                        # 클릭 전 현재 URL 저장
                        before_url = page.url

                        # 클릭 실행
                        await element.click()

                        # 네트워크 요청 완료 대기
                        try:
                            await page.wait_for_load_state("networkidle", timeout=15000)
                            print("📝 네트워크 요청 완료 대기 성공")
                        except Exception as e:
                            print(f"⚠️ 네트워크 대기 실패, 기본 대기로 전환: {str(e)}")
                            await page.wait_for_timeout(5000)

                        # AI 기반 구독해지 완료 판단
                        print("🤖 AI 기반 구독해지 완료 분석 시작...")
                        ai_result = await self._analyze_unsubscribe_completion_with_ai(
                            page
                        )

                        if ai_result["success"] and ai_result["confidence"] >= 70:
                            print(
                                f"🤖 AI 분석으로 구독해지 완료 확인 (신뢰도: {ai_result['confidence']}%)"
                            )
                            return {
                                "success": True,
                                "message": f"AI 지시에 따른 링크 클릭 완료 (AI 신뢰도: {ai_result['confidence']}%)",
                                "ai_confidence": ai_result["confidence"],
                                "ai_reason": ai_result["reason"],
                            }
                        else:
                            print(
                                f"🤖 AI 분석 결과: 구독해지 미완료 (신뢰도: {ai_result['confidence']}%)"
                            )
                            return {
                                "success": True,
                                "message": "AI 지시에 따른 링크 클릭 완료",
                            }

            elif action == "button_click":
                # 버튼 클릭 처리
                elements = await page.query_selector_all("button")
                for element in elements:
                    element_text = await element.text_content()
                    if target.lower() in element_text.lower():
                        print(f"📝 AI 지시에 따른 버튼 클릭: {element_text}")

                        # 클릭 전 현재 URL 저장
                        before_url = page.url

                        # 클릭 실행
                        await element.click()

                        # 네트워크 요청 완료 대기
                        try:
                            await page.wait_for_load_state("networkidle", timeout=10000)
                            print("📝 네트워크 요청 완료 대기 성공")
                        except Exception as e:
                            print(f"⚠️ 네트워크 대기 실패, 기본 대기로 전환: {str(e)}")
                            await page.wait_for_timeout(2000)

                        # AI 기반 구독해지 완료 판단
                        print("🤖 AI 기반 구독해지 완료 분석 시작...")
                        ai_result = await self._analyze_unsubscribe_completion_with_ai(
                            page
                        )

                        if ai_result["success"] and ai_result["confidence"] >= 70:
                            print(
                                f"🤖 AI 분석으로 구독해지 완료 확인 (신뢰도: {ai_result['confidence']}%)"
                            )
                            return {
                                "success": True,
                                "message": f"AI 지시에 따른 버튼 클릭 완료 (AI 신뢰도: {ai_result['confidence']}%)",
                                "ai_confidence": ai_result["confidence"],
                                "ai_reason": ai_result["reason"],
                            }
                        else:
                            print(
                                f"🤖 AI 분석 결과: 구독해지 미완료 (신뢰도: {ai_result['confidence']}%)"
                            )
                            return {
                                "success": True,
                                "message": "AI 지시에 따른 버튼 클릭 완료",
                            }

            elif action == "form_submit":
                # 폼 제출 처리
                forms = await page.query_selector_all("form")
                for form in forms:
                    if user_email:
                        # 이메일 필드 찾아서 입력
                        email_inputs = await form.query_selector_all(
                            "input[type='email'], input[name*='email']"
                        )
                        for email_input in email_inputs:
                            await email_input.fill(user_email)

                    submit_buttons = await form.query_selector_all(
                        "input[type='submit'], button[type='submit']"
                    )
                    for button in submit_buttons:
                        button_text = await button.text_content()
                        print(f"📝 AI 지시에 따른 폼 제출: {button_text}")

                        # 제출 전 현재 URL 저장
                        before_url = page.url

                        # 폼 제출
                        await button.click()

                        # 네트워크 요청 완료 대기
                        try:
                            await page.wait_for_load_state("networkidle", timeout=10000)
                            print("📝 네트워크 요청 완료 대기 성공")
                        except Exception as e:
                            print(f"⚠️ 네트워크 대기 실패, 기본 대기로 전환: {str(e)}")
                            await page.wait_for_timeout(2000)

                        # AI 기반 구독해지 완료 판단
                        print("🤖 AI 기반 구독해지 완료 분석 시작...")
                        ai_result = await self._analyze_unsubscribe_completion_with_ai(
                            page
                        )

                        if ai_result["success"] and ai_result["confidence"] >= 70:
                            print(
                                f"🤖 AI 분석으로 구독해지 완료 확인 (신뢰도: {ai_result['confidence']}%)"
                            )
                            return {
                                "success": True,
                                "message": f"AI 지시에 따른 폼 제출 완료 (AI 신뢰도: {ai_result['confidence']}%)",
                                "ai_confidence": ai_result["confidence"],
                                "ai_reason": ai_result["reason"],
                            }
                        else:
                            print(
                                f"🤖 AI 분석 결과: 구독해지 미완료 (신뢰도: {ai_result['confidence']}%)"
                            )
                            return {
                                "success": True,
                                "message": "AI 지시에 따른 폼 제출 완료",
                            }

            elif action == "confirm":
                # 확인 버튼 클릭 처리
                elements = await page.query_selector_all(
                    "button:has-text('확인'), button:has-text('Confirm')"
                )
                for element in elements:
                    element_text = await element.text_content()
                    if target.lower() in element_text.lower():
                        print(f"📝 AI 지시에 따른 확인 버튼 클릭: {element_text}")

                        # 클릭 전 현재 URL 저장
                        before_url = page.url

                        # 클릭 실행
                        await element.click()

                        # 네트워크 요청 완료 대기
                        try:
                            await page.wait_for_load_state("networkidle", timeout=10000)
                            print("📝 네트워크 요청 완료 대기 성공")
                        except Exception as e:
                            print(f"⚠️ 네트워크 대기 실패, 기본 대기로 전환: {str(e)}")
                            await page.wait_for_timeout(2000)

                        # AI 기반 구독해지 완료 판단
                        print("🤖 AI 기반 구독해지 완료 분석 시작...")
                        ai_result = await self._analyze_unsubscribe_completion_with_ai(
                            page
                        )

                        if ai_result["success"] and ai_result["confidence"] >= 70:
                            print(
                                f"🤖 AI 분석으로 구독해지 완료 확인 (신뢰도: {ai_result['confidence']}%)"
                            )
                            return {
                                "success": True,
                                "message": f"AI 지시에 따른 확인 버튼 클릭 완료 (AI 신뢰도: {ai_result['confidence']}%)",
                                "ai_confidence": ai_result["confidence"],
                                "ai_reason": ai_result["reason"],
                            }
                        else:
                            print(
                                f"🤖 AI 분석 결과: 구독해지 미완료 (신뢰도: {ai_result['confidence']}%)"
                            )
                            return {
                                "success": True,
                                "message": "AI 지시에 따른 확인 버튼 클릭 완료",
                            }

            return {"success": False, "message": "AI 지시를 실행할 수 없습니다"}

        except Exception as e:
            return {"success": False, "message": f"AI 지시 실행 실패: {str(e)}"}

    async def _try_form_submit(self, page: Page, user_email: str = None) -> Dict:
        """폼 제출 전용 처리"""
        try:
            # 폼 찾기
            forms = await page.query_selector_all("form")
            for form in forms:
                # 이메일 필드가 있다면 입력
                if user_email:
                    email_inputs = await form.query_selector_all(
                        "input[type='email'], input[name*='email']"
                    )
                    for email_input in email_inputs:
                        await email_input.fill(user_email)
                        print(f"📝 이메일 입력: {user_email}")

                # 제출 버튼 찾기
                submit_buttons = await form.query_selector_all(
                    "input[type='submit'], button[type='submit']"
                )
                for button in submit_buttons:
                    button_text = await button.text_content()
                    print(f"📝 폼 제출 버튼 발견: {button_text}")

                    # 제출 전 URL 저장
                    before_url = page.url

                    # 폼 제출
                    await button.click()

                    # 네트워크 요청 완료 대기
                    try:
                        await page.wait_for_load_state("networkidle", timeout=10000)
                        print("📝 폼 제출 후 네트워크 요청 완료")
                    except:
                        await page.wait_for_timeout(3000)

                    # 결과 확인
                    if await self._check_post_request_success(page):
                        return {"success": True, "message": "폼 제출 성공"}

            return {"success": False, "message": "폼 제출 실패"}

        except Exception as e:
            return {"success": False, "message": f"폼 제출 오류: {str(e)}"}

    def _finalize_success(self, result: Dict, start_time: float) -> Dict:
        """성공 결과 정리"""
        processing_time = time.time() - start_time
        self.log_unsubscribe_result(result, processing_time, "success")

        return {
            "success": True,
            "message": result.get("message", "구독해지 성공"),
            "processing_time": processing_time,
        }

    def _finalize_failure(self, message: str, start_time: float) -> Dict:
        """실패 결과 정리"""
        processing_time = time.time() - start_time
        self.log_unsubscribe_result(
            {"success": False, "message": message}, processing_time, "failure"
        )

        return {
            "success": False,
            "message": message,
            "processing_time": processing_time,
        }

    def log_unsubscribe_attempt(
        self, url: str, user_email: str = None, start_time: float = None
    ) -> None:
        """구독해지 시도 로깅"""
        self.stats["total_attempts"] += 1
        self.logger.info(f"구독해지 시도: {url}, 사용자: {user_email}")

    def log_unsubscribe_result(
        self, result: Dict, processing_time: float, status: str
    ) -> None:
        """구독해지 결과 로깅"""
        if status == "success":
            self.stats["successful_unsubscribes"] += 1
        else:
            self.stats["failed_unsubscribes"] += 1

        self.stats["processing_times"].append(processing_time)
        self.logger.info(
            f"구독해지 결과: {result.get('message', 'N/A')}, 처리시간: {processing_time:.2f}초"
        )

    def get_statistics(self) -> Dict:
        """통계 정보 반환"""
        return {
            "total_attempts": self.stats["total_attempts"],
            "successful_unsubscribes": self.stats["successful_unsubscribes"],
            "failed_unsubscribes": self.stats["failed_unsubscribes"],
            "success_rate": (
                self.stats["successful_unsubscribes"]
                / self.stats["total_attempts"]
                * 100
                if self.stats["total_attempts"] > 0
                else 0
            ),
            "average_processing_time": (
                sum(self.stats["processing_times"])
                / len(self.stats["processing_times"])
                if self.stats["processing_times"]
                else 0
            ),
            "browser_reuses": self.stats["browser_reuses"],
        }

    def setup_logging(self):
        """로깅 설정"""
        logging.basicConfig(
            level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
        )
        self.logger = logging.getLogger(__name__)

        # 파일 로깅 추가
        if not os.path.exists("logs"):
            os.makedirs("logs")
        file_handler = logging.FileHandler("logs/playwright_unsubscribe_service.log")
        file_handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)


# 동기식 래퍼 함수 (Flask 애플리케이션에서 사용)
def process_unsubscribe_sync(unsubscribe_url: str, user_email: str = None) -> Dict:
    """동기식 구독해지 처리 래퍼"""
    service = PlaywrightUnsubscribeService()
    return asyncio.run(
        service.process_unsubscribe_with_playwright_ai(unsubscribe_url, user_email)
    )
