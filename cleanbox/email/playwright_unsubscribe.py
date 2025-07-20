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

                # 2단계: 기본 구독해지 시도
                print(f"📝 2단계: 기본 구독해지 시도")
                basic_result = await self._try_basic_unsubscribe(page, user_email)
                if basic_result["success"]:
                    await self.cleanup_page()
                    return self._finalize_success(basic_result, start_time)

                # 3단계: 두 번째 페이지 처리
                print(f"📝 3단계: 두 번째 페이지 처리")
                second_result = await self._try_second_page_unsubscribe(
                    page, user_email
                )
                if second_result["success"]:
                    await self.cleanup_page()
                    return self._finalize_success(second_result, start_time)

                # 4단계: AI 분석 및 처리
                print(f"📝 4단계: AI 분석 및 처리")
                ai_result = await self._analyze_page_with_ai(page, user_email)
                if ai_result["success"]:
                    await self.cleanup_page()
                    return self._finalize_success(ai_result, start_time)

                # 모든 시도 실패
                await self.cleanup_page()
                return self._finalize_failure(
                    "모든 구독해지 방법이 실패했습니다", start_time
                )

            except Exception as e:
                print(f"❌ Playwright 처리 중 오류: {str(e)}")
                await self.cleanup_page()
                retry_count += 1
                if retry_count <= max_retries:
                    print(f"⏳ {self.timeouts['retry_delay']/1000}초 후 재시도...")
                    await asyncio.sleep(self.timeouts["retry_delay"] / 1000)
                else:
                    return self._finalize_failure(
                        f"Playwright 처리 실패: {str(e)}", start_time
                    )

        return self._finalize_failure("최대 재시도 횟수 초과", start_time)

    async def _try_basic_unsubscribe(self, page: Page, user_email: str = None) -> Dict:
        """기본 구독해지 시도 (AI 기반 완료 판단 적용)"""
        try:
            # 구독해지 관련 요소들 찾기
            selectors = [
                "button[type='submit']",
                "input[type='submit']",
                "button",
                "input[type='button']",
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
                "form[action*='unsubscribe']",
                "form[action*='opt-out']",
            ]

            for selector in selectors:
                try:
                    elements = await page.query_selector_all(selector)
                    for element in elements:
                        is_visible = await element.is_visible()
                        is_enabled = await element.is_enabled()

                        if is_visible and is_enabled:
                            element_text = await element.text_content()
                            print(
                                f"📝 구독해지 요소 발견: {selector} - 텍스트: '{element_text}'"
                            )

                            # 구독해지 관련 키워드 확인
                            unsubscribe_keywords = [
                                "unsubscribe",
                                "구독해지",
                                "cancel",
                                "remove",
                                "opt-out",
                                "confirm",
                                "submit",
                                "확인",
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
                                print(f"📝 구독해지 요소 클릭: {element_text}")

                                # 클릭 전 현재 URL 저장
                                before_url = page.url

                                # 클릭 실행
                                await element.click()

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
                                    await page.wait_for_timeout(3000)

                                # URL 변경 확인
                                after_url = page.url
                                if before_url != after_url:
                                    print(
                                        f"📝 URL 변경 감지: {before_url} → {after_url}"
                                    )

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
                                        "message": f"구독해지 성공 (AI 신뢰도: {ai_result['confidence']}%)",
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
                                            "message": "구독해지 성공",
                                        }
                                    else:
                                        print("📝 구독해지 미완료로 판단")
                                        return {
                                            "success": False,
                                            "message": "구독해지 미완료",
                                        }

                except Exception as e:
                    print(f"⚠️ 선택자 {selector} 처리 중 오류: {str(e)}")
                    continue

            return {"success": False, "message": "구독해지 요소를 찾을 수 없습니다"}

        except Exception as e:
            return {"success": False, "message": f"기본 구독해지 실패: {str(e)}"}

    async def _analyze_unsubscribe_completion_with_ai(self, page: Page) -> Dict:
        """AI를 사용한 구독해지 완료 분석 (간단한 방식)"""
        try:
            # 페이지 내용 추출
            content = await page.content()
            current_url = page.url
            current_title = await page.title()

            # 간단한 프롬프트 생성
            prompt = f"""
다음 웹 페이지에서 구독해지가 완료되었는지 판단해주세요.

URL: {current_url}
제목: {current_title}
내용: {content[:1000]}

구독해지가 완료되었으면 "완료됨", 아니면 "완료되지 않음"으로만 답변하세요.
"""

            # OpenAI API 호출
            ai_response = await self._call_simple_ai_api(prompt)

            return self._parse_simple_completion_result(ai_response)

        except Exception as e:
            print(f"⚠️ AI 구독해지 완료 분석 실패: {str(e)}")
            return {"success": False, "confidence": 0, "reason": str(e)}

    def _parse_simple_completion_result(self, ai_response: str) -> Dict:
        """간단한 AI 응답 파싱"""
        try:
            # 응답에서 완료 여부 판단
            response_lower = ai_response.lower()

            # 완료 지표들
            completion_indicators = [
                "완료됨",
                "완료",
                "성공",
                "success",
                "complete",
                "completed",
                "구독해지됨",
                "unsubscribed",
                "cancelled",
                "취소됨",
                "감사합니다",
                "thank you",
                "성공적으로",
                "successfully",
            ]

            # 실패 지표들
            failure_indicators = [
                "완료되지 않음",
                "실패",
                "오류",
                "error",
                "failed",
                "다시 시도",
                "retry",
                "잘못된",
                "invalid",
            ]

            # 완료 여부 판단
            is_completed = any(
                indicator in response_lower for indicator in completion_indicators
            )
            is_failed = any(
                indicator in response_lower for indicator in failure_indicators
            )

            # 신뢰도 계산 (간단한 방식)
            confidence = 80 if is_completed and not is_failed else 20

            result = {
                "success": is_completed,
                "confidence": confidence,
                "reason": ai_response,
                "indicators": [],
                "suggested_action": "",
            }

            print(f"🤖 AI 구독해지 완료 분석:")
            print(f"   - 완료 여부: {is_completed}")
            print(f"   - 신뢰도: {confidence}%")
            print(f"   - 응답: {ai_response}")

            return result

        except Exception as e:
            print(f"⚠️ AI 응답 파싱 실패: {str(e)}")
            return {"success": False, "confidence": 0, "reason": f"파싱 오류: {str(e)}"}

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
        """간단한 OpenAI API 호출"""
        try:
            client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

            response = client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {
                        "role": "system",
                        "content": "웹 페이지가 구독해지 완료 페이지인지 판단하는 AI입니다. '완료됨' 또는 '완료되지 않음'으로만 답변하세요.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=100,
                temperature=0.1,
            )

            content = response.choices[0].message.content
            print(f"🤖 AI 응답: {content}")
            return content

        except Exception as e:
            print(f"⚠️ OpenAI API 호출 실패: {str(e)}")
            return "완료되지 않음"

    def _parse_simple_completion_result(self, ai_response: str) -> Dict:
        """간단한 AI 응답 파싱"""
        try:
            # 응답에서 완료 여부 판단
            response_lower = ai_response.lower()

            # 완료 지표들
            completion_indicators = [
                "완료됨",
                "완료",
                "성공",
                "success",
                "complete",
                "completed",
                "구독해지됨",
                "unsubscribed",
                "cancelled",
                "취소됨",
                "감사합니다",
                "thank you",
                "성공적으로",
                "successfully",
            ]

            # 실패 지표들
            failure_indicators = [
                "완료되지 않음",
                "실패",
                "오류",
                "error",
                "failed",
                "다시 시도",
                "retry",
                "잘못된",
                "invalid",
            ]

            # 완료 여부 판단
            is_completed = any(
                indicator in response_lower for indicator in completion_indicators
            )
            is_failed = any(
                indicator in response_lower for indicator in failure_indicators
            )

            # 신뢰도 계산 (간단한 방식)
            confidence = 80 if is_completed and not is_failed else 20

            result = {
                "success": is_completed,
                "confidence": confidence,
                "reason": ai_response,
                "indicators": [],
                "suggested_action": "",
            }

            print(f"🤖 AI 구독해지 완료 분석:")
            print(f"   - 완료 여부: {is_completed}")
            print(f"   - 신뢰도: {confidence}%")
            print(f"   - 응답: {ai_response}")

            return result

        except Exception as e:
            print(f"⚠️ AI 응답 파싱 실패: {str(e)}")
            return {"success": False, "confidence": 0, "reason": f"파싱 오류: {str(e)}"}

    async def _check_basic_success_indicators(self, page: Page) -> bool:
        """기본 성공 지표 확인 (기존 로직)"""
        try:
            current_url = page.url
            title = await page.title()
            page_content = await page.content()
            page_source = page_content.lower()

            # 기존 성공 지표들
            success_indicators = [
                "unsubscribe complete",
                "구독해지 완료",
                "subscription cancelled",
                "구독이 취소되었습니다",
                "you have been unsubscribed",
                "구독해지되었습니다",
            ]

            for indicator in success_indicators:
                if indicator in page_source:
                    print(f"📝 성공 지표 발견: {indicator}")
                    return True

            # URL/제목 확인
            if any(
                keyword in current_url.lower()
                for keyword in ["complete", "success", "thank"]
            ):
                return True

            if any(
                keyword in title.lower()
                for keyword in ["complete", "success", "unsubscribed"]
            ):
                return True

            return False

        except Exception as e:
            print(f"⚠️ 기본 지표 확인 중 오류: {str(e)}")
            return False

    async def _try_second_page_unsubscribe(
        self, page: Page, user_email: str = None
    ) -> Dict:
        """두 번째 페이지 구독해지 처리 (AI 기반 완료 판단 적용)"""
        try:
            # 두 번째 페이지에서 구독해지 관련 버튼/링크 찾기
            second_page_selectors = [
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

            for selector in second_page_selectors:
                try:
                    elements = await page.query_selector_all(selector)
                    for element in elements:
                        is_visible = await element.is_visible()
                        is_enabled = await element.is_enabled()

                        if is_visible and is_enabled:
                            element_text = await element.text_content()
                            print(
                                f"📝 두 번째 페이지 요소 발견: {selector} - 텍스트: '{element_text}'"
                            )

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
                            ]

                            is_action_element = any(
                                keyword in element_text.lower()
                                for keyword in action_keywords
                            )

                            if (
                                is_action_element
                                or "confirm" in selector.lower()
                                or "submit" in selector.lower()
                            ):
                                print(f"📝 두 번째 페이지 요소 클릭: {element_text}")

                                # 클릭 전 현재 URL 저장
                                before_url = page.url

                                # 클릭 실행
                                await element.click()

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
                                    await page.wait_for_timeout(3000)

                                # URL 변경 확인
                                after_url = page.url
                                if before_url != after_url:
                                    print(
                                        f"📝 URL 변경 감지: {before_url} → {after_url}"
                                    )

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
                                        "message": f"두 번째 페이지 구독해지 성공 (AI 신뢰도: {ai_result['confidence']}%)",
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
                                            "message": "두 번째 페이지 구독해지 성공",
                                        }
                                    else:
                                        print("📝 구독해지 미완료로 판단")
                                        return {
                                            "success": False,
                                            "message": "두 번째 페이지 구독해지 미완료",
                                        }

                except Exception as e:
                    print(f"⚠️ 두 번째 페이지 선택자 {selector} 처리 중 오류: {str(e)}")
                    continue

            return {
                "success": False,
                "message": "두 번째 페이지 구독해지 요소를 찾을 수 없습니다",
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"두 번째 페이지 구독해지 실패: {str(e)}",
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
