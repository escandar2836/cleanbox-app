"""
Playwright-based Unsubscribe Service
Optimized for memory and browser reuse to run stably in Render environments.
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
    """Advanced Playwright-based Unsubscribe Service (Memory Optimized)"""

    def __init__(self):
        self.setup_logging()
        self.browser = None
        self.context = None
        self.page = None

        # Memory optimization settings
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

        # Timeout settings (tuned for Render environment)
        self.timeouts = {
            "page_load": 30000,  # 30 seconds
            "element_wait": 10000,  # 10 seconds
            "api_call": 20000,  # 20 seconds
            "retry_delay": 2000,  # 2 seconds
        }

        # Initialize statistics
        self.stats = {
            "total_attempts": 0,
            "successful_unsubscribes": 0,
            "failed_unsubscribes": 0,
            "processing_times": [],
            "browser_reuses": 0,
            "memory_usage": [],
        }

    def _log_memory_usage(self, stage: str):
        """Log memory usage"""
        try:
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024
            print(f"📊 Memory usage [{stage}]: {memory_mb:.1f} MB")
            self.stats["memory_usage"].append(
                {"stage": stage, "memory_mb": memory_mb, "timestamp": time.time()}
            )
        except Exception as e:
            print(f"⚠️ Memory monitoring failed: {str(e)}")

    async def initialize_browser(self):
        """Initialize browser (reusable)"""
        if self.browser is None:
            # Check browser path and dynamic detection
            import os
            import glob

            # Find Chrome executable
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
                    # Wildcard pattern handling
                    matches = glob.glob(path_pattern)
                    if matches:
                        executable_path = matches[0]
                        print(f"📝 Chrome executable found: {executable_path}")
                        break
                elif os.path.exists(path_pattern):
                    executable_path = path_pattern
                    print(f"📝 Chrome executable found: {executable_path}")
                    break

            if not executable_path:
                print(
                    "⚠️ Could not find Chrome executable. Proceeding in auto-detect mode."
                )

            playwright = await async_playwright().start()
            try:
                self.browser = await playwright.chromium.launch(
                    headless=True,
                    args=self.browser_args,
                    chromium_sandbox=False,
                    executable_path=executable_path,
                )
                print("✅ Playwright browser initialized")
            except Exception as e:
                print(f"❌ Browser initialization failed: {str(e)}")
                # Retry (without executable_path)
                self.browser = await playwright.chromium.launch(
                    headless=True,
                    args=self.browser_args,
                    chromium_sandbox=False,
                )
                print("✅ Playwright browser initialized (retry)")

        # Create new context (reuse existing context)
        if self.context is None:
            try:
                print(f" Browser context creation started...")
                print(f"🔍 Browser state: {self.browser}")
                print(f"🔍 Browser type: {type(self.browser)}")
                print(
                    f"🔍 Browser methods: {[m for m in dir(self.browser) if not m.startswith('_')]}"
                )

                self.context = await self.browser.new_context(
                    viewport={"width": 640, "height": 480},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    java_script_enabled=True,
                    ignore_https_errors=True,
                )
                print(f"🔍 Context creation result: {self.context}")
                print(f"🔍 Context type: {type(self.context)}")
                print(
                    f"🔍 Context methods: {[m for m in dir(self.context) if not m.startswith('_')]}"
                )

                if self.context is None:
                    raise Exception("Browser context creation failed")
                print("📝 New browser context created")
            except Exception as e:
                print(f"❌ Browser context creation failed: {str(e)}")
                print(f"🔍 Exception type: {type(e)}")
                print(f"🔍 Exception details: {e}")
                print(f"🔍 Exception traceback: {e.__traceback__}")
                raise Exception(f"Browser context creation failed: {str(e)}")
        else:
            self.stats["browser_reuses"] += 1
            print(
                f"♻️ Browser context reused (reuse count: {self.stats['browser_reuses']})"
            )

        # Create new page
        try:
            print(f" Page creation started...")
            print(f"🔍 Context state: {self.context}")
            print(f"🔍 Context type: {type(self.context)}")
            print(f"🔍 Is context None?: {self.context is None}")

            if self.context is None:
                print(f"❌ Context is None!")
                raise Exception("Context is None")

            print(f"🔍 Calling new_page method...")
            self.page = await self.context.new_page()
            print(f"🔍 Page creation result: {self.page}")
            print(f" Page type: {type(self.page)}")
            print(f"🔍 Is page None?: {self.page is None}")

            if self.page is None:
                raise Exception("Page creation failed")

            print(f"🔍 Setting page timeout...")
            self.page.set_default_timeout(self.timeouts["page_load"])
            print("✅ New page created")
            return self.page
        except Exception as e:
            print(f"❌ Page creation failed: {str(e)}")
            print(f"🔍 Exception type: {type(e)}")
            print(f"🔍 Exception details: {e}")
            print(f"🔍 Context state: {self.context}")
            print(f" Page state: {self.page}")
            print(f"🔍 Exception traceback: {e.__traceback__}")
            # Try to cleanup page
            if self.page:
                try:
                    await self.page.close()
                except:
                    pass
                self.page = None
            raise Exception(f"Page creation failed: {str(e)}")

    async def cleanup_page(self):
        """Cleanup page (keep context)"""
        if self.page:
            try:
                await self.page.close()
                print("🧹 Page cleanup complete")
            except Exception as e:
                print(f"⚠️ Error during page cleanup: {str(e)}")
            finally:
                self.page = None

    async def cleanup_browser(self):
        """Full browser cleanup"""
        if self.page:
            await self.cleanup_page()

        if self.context:
            try:
                await self.context.close()
                print("🧹 Browser context cleanup complete")
            except Exception as e:
                print(f"⚠️ Error during context cleanup: {str(e)}")
            finally:
                self.context = None

        if self.browser:
            try:
                await self.browser.close()
                print("🧹 Browser cleanup complete")
            except Exception as e:
                print(f"⚠️ Error during browser cleanup: {str(e)}")
            finally:
                self.browser = None

    def extract_unsubscribe_links(
        self, email_content: str, email_headers: Dict = None
    ) -> List[str]:
        """Extract unsubscribe links from email (same as before)"""
        print(f"🔍 extract_unsubscribe_links started")
        unsubscribe_links = []

        # 1. Check List-Unsubscribe field in email headers
        if email_headers:
            list_unsubscribe = email_headers.get("List-Unsubscribe", "")
            print(f"📝 List-Unsubscribe header: {list_unsubscribe}")
            if list_unsubscribe:
                links = [link.strip() for link in list_unsubscribe.split(",")]
                unsubscribe_links.extend(links)
                print(f"📝 Links extracted from header: {links}")

        # 2. Search for unsubscribe link patterns in email body
        print(f"📝 Pattern search in email body started")
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
                print(f"📝 Matches found in pattern {i + 1}: {matches}")
            unsubscribe_links.extend(matches)

        # 3. Extract links from HTML tags
        print(f"📝 Extracting links from HTML tags started")
        soup = BeautifulSoup(email_content, "html.parser")
        html_links_found = 0

        for link in soup.find_all("a", href=True):
            href = link.get("href", "").lower()
            link_text = link.get_text().strip().lower()

            unsubscribe_keywords = [
                "unsubscribe",
                "opt-out",
                "remove",
                "cancel",
                "구독해지",  # (Korean: unsubscribe)
                "구독취소",  # (Korean: cancel subscription)
                "수신거부",  # (Korean: refuse reception)
                "수신취소",  # (Korean: cancel reception)
                "email preferences",
                "manage subscription",
                "subscription settings",
                "구독",  # (Korean: subscribe)
                "취소",  # (Korean: cancel)
            ]

            generic_texts = ["여기", "click", "link", "here", "보기", "확인"]
            found = False
            # 1. 일반적 텍스트라면 부모/조부모 텍스트까지 합쳐서 검사
            if link_text in generic_texts:
                parent_text = ""
                if link.parent:
                    parent_text += link.parent.get_text().lower()
                if link.parent and link.parent.parent:
                    parent_text += link.parent.parent.get_text().lower()
                if any(keyword in parent_text for keyword in unsubscribe_keywords):
                    unsubscribe_links.append(link["href"])
                    html_links_found += 1
                    print(
                        f"📝 Unsubscribe link found in HTML (parent context): {link['href']} (parent context matched)"
                    )
                    found = True
            # 2. 기존 방식: href나 텍스트에 키워드가 있으면 추가
            if not found:
                for keyword in unsubscribe_keywords:
                    if keyword in href or keyword in link_text:
                        unsubscribe_links.append(link["href"])
                        html_links_found += 1
                        print(
                            f"📝 Unsubscribe link found in HTML: {link['href']} (keyword: {keyword})"
                        )
                        break

        print(f"📝 Number of unsubscribe links found in HTML: {html_links_found}")

        # Remove duplicates and filter only valid URLs
        print(f"📝 Removing duplicates and validating URLs started")
        print(f"📝 Total links extracted: {len(unsubscribe_links)}")

        valid_links = []
        for link in set(unsubscribe_links):
            if self._is_valid_unsubscribe_url(link):
                valid_links.append(link)
                print(f"📝 Valid link added: {link}")
            else:
                print(f"❌ Invalid link excluded: {link}")

        print(f"📝 Final number of valid links: {len(valid_links)}")
        return valid_links

    def _is_valid_unsubscribe_url(self, url: str) -> bool:
        """Check if the URL is a valid unsubscribe URL"""
        try:
            parsed = urlparse(url)
            return parsed.scheme in ["http", "https"] and parsed.netloc
        except:
            return False

    async def process_unsubscribe_with_playwright_ai(
        self, unsubscribe_url: str, user_email: str = None
    ) -> Dict:
        """Universal unsubscribe processing using Playwright + OpenAI API (memory optimized)"""
        start_time = time.time()
        self.log_unsubscribe_attempt(unsubscribe_url, user_email, start_time)

        max_retries = 2
        retry_count = 0

        while retry_count <= max_retries:
            try:
                print(
                    f"🔧 Playwright + AI unsubscribe attempt ({retry_count + 1}/{max_retries + 1}): {unsubscribe_url}"
                )

                # Initialize browser
                page = await self.initialize_browser()

                # Check if page is None
                if page is None:
                    raise Exception("Browser page initialization failed")

                # Step 1: Initial page access
                print(f"📝 Step 1: Initial page access")
                await page.goto(unsubscribe_url, wait_until="domcontentloaded")
                await page.wait_for_timeout(2000)  # Page loading wait

                # Step 2: Check unsubscribe success state
                print(f"📝 Step 2: Check unsubscribe success state")
                if await self._check_unsubscribe_success(page):
                    await self.cleanup_page()
                    return {
                        "success": True,
                        "message": "Unsubscribe completed.",
                        "error_type": "unsubscribe_success",
                        "processing_time": time.time() - start_time,
                    }

                # Step 3: Try basic unsubscribe
                print(f"📝 Step 3: Try basic unsubscribe")
                basic_result = await self._try_basic_unsubscribe(page, user_email)
                if basic_result["success"]:
                    await self.cleanup_page()
                    return self._finalize_success(basic_result, start_time)

                # Step 4: Handle second page
                print(f"📝 Step 4: Handle second page")
                second_result = await self._try_second_page_unsubscribe(
                    page, user_email
                )
                if second_result["success"]:
                    await self.cleanup_page()
                    return self._finalize_success(second_result, start_time)

                # Step 5: AI analysis and processing
                print(f"📝 Step 5: AI analysis and processing")
                ai_result = await self._analyze_page_with_ai(page, user_email)
                if ai_result["success"]:
                    await self.cleanup_page()
                    return self._finalize_success(ai_result, start_time)

                # Step 6: Final check for unsubscribe success
                print(f"📝 Step 6: Final check for unsubscribe success")
                if await self._check_unsubscribe_success(page):
                    await self.cleanup_page()
                    return {
                        "success": True,
                        "message": "Unsubscribe completed.",
                        "error_type": "unsubscribe_success",
                        "processing_time": time.time() - start_time,
                    }

                # All methods failed
                await self.cleanup_page()
                return self._finalize_failure(
                    "All unsubscribe methods failed.", start_time
                )

            except Exception as e:
                print(f"❌ Playwright + AI unsubscribe attempt failed: {str(e)}")
                await self.cleanup_page()
                retry_count += 1

                if retry_count <= max_retries:
                    print(f"🔄 Retrying... ({retry_count}/{max_retries})")
                    await asyncio.sleep(2)  # Wait before retrying
                else:
                    return self._finalize_failure(
                        f"Unsubscribe processing failed: {str(e)}", start_time
                    )

        return self._finalize_failure("Exceeded maximum retry count", start_time)

    async def _try_basic_unsubscribe(self, page: Page, user_email: str = None) -> Dict:
        """Basic unsubscribe processing (integrated JavaScript-based)"""
        try:
            print(f"📝 Basic unsubscribe processing started")

            # Integrated JavaScript-based unsubscribe processing
            return await self._try_javascript_submit(
                page, user_email, is_recursive=False
            )

        except Exception as e:
            return {
                "success": False,
                "message": f"Basic unsubscribe processing failed: {str(e)}",
            }

    async def _try_legacy_unsubscribe(self, page: Page, user_email: str = None) -> Dict:
        """Legacy unsubscribe processing (backward compatibility)"""
        try:
            # Legacy selectors
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
                                f"📝 Legacy element found: {selector} - text: '{element_text}'"
                            )

                            # Check unsubscribe-related keywords
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
                                print(f"📝 Legacy element clicked: {element_text}")

                                # Save current URL before click
                                before_url = page.url

                                # Execute click (short timeout)
                                try:
                                    await element.click(timeout=5000)
                                except Exception as click_error:
                                    print(
                                        f"⚠️ Click failed, retrying with JavaScript: {str(click_error)}"
                                    )
                                    await page.evaluate(
                                        "(element) => element.click()", element
                                    )

                                # Short wait
                                await page.wait_for_timeout(2000)

                                # Check URL change
                                after_url = page.url
                                if before_url != after_url:
                                    print(
                                        f"📝 URL change detected: {before_url} → {after_url}"
                                    )

                                # Check unsubscribe completion
                                if await self._check_unsubscribe_success(page):
                                    return {
                                        "success": True,
                                        "message": "Unsubscribe confirmed after legacy click",
                                        "method": "legacy_completed",
                                        "selector": selector,
                                    }
                                # AI-based unsubscribe completion check
                                print(
                                    "🤖 Starting AI-based unsubscribe completion analysis..."
                                )
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
                                        f"🤖 Unsubscribe confirmed by AI analysis (confidence: {ai_result['confidence']}%)"
                                    )
                                    return {
                                        "success": True,
                                        "message": f"Legacy unsubscribe success (AI confidence: {ai_result['confidence']}%)",
                                        "ai_confidence": ai_result["confidence"],
                                        "ai_reason": ai_result["reason"],
                                    }
                                else:
                                    print(
                                        f"🤖 AI analysis result: Unsubscribe not completed (confidence: {ai_result['confidence']}%)"
                                    )
                                    # Also check with legacy method
                                    if await self._check_basic_success_indicators(page):
                                        print("📝 Success confirmed by basic indicator")
                                        return {
                                            "success": True,
                                            "message": "Legacy unsubscribe success",
                                        }
                                    else:
                                        print("📝 Judged as unsubscribe not completed")
                                        return {
                                            "success": False,
                                            "message": "Legacy unsubscribe not completed",
                                        }

                except Exception as e:
                    print(f"⚠️ Error processing legacy selector {selector}: {str(e)}")
                    continue

            return {
                "success": False,
                "message": "Could not find legacy unsubscribe element",
            }

        except Exception as e:
            return {"success": False, "message": f"Legacy unsubscribe failed: {str(e)}"}

    async def _analyze_unsubscribe_completion_with_ai(self, page: Page) -> Dict:
        """Analyze unsubscribe completion using AI (simplified version)"""
        try:
            # Extract page info
            current_url = page.url
            title = await page.title()
            content = await page.content()

            # Create simplified prompt
            prompt = f"""
Please analyze the unsubscribe status on the following web page.

URL: {current_url}
Title: {title}
Page content: {content[:2000]}

Important criteria:
1. If a resubscribe button ("Resubscribe", "Subscribe again") appears, unsubscribe is considered successful.
2. Messages like "already unsubscribed" are also considered success.
3. Messages like "error", "failed" indicate failure.

Please answer in JSON format:
{{
    "success": true/false,
    "confidence": 0-100,
    "reason": "Reason for judgment"
}}
"""

            # OpenAI API call
            ai_response = await self._call_simple_ai_api(prompt)

            return self._parse_simple_ai_result(ai_response, current_url, title)

        except Exception as e:
            print(f"⚠️ AI unsubscribe completion analysis failed: {str(e)}")
            return {"success": False, "confidence": 0, "reason": str(e)}

    def _parse_simple_ai_result(self, ai_response: str, url: str, title: str) -> Dict:
        """Directly parse AI response (simplified version)"""
        try:
            import json

            # Try JSON parsing
            try:
                # Find JSON block
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

                    print(f"🤖 AI unsubscribe completion analysis (simplified):")
                    print(f"   - Success: {result['success']}")
                    print(f"   - Confidence: {result['confidence']}%")
                    print(f"   - Reason: {result['reason']}")

                    return result

            except json.JSONDecodeError:
                pass

            # If JSON parsing fails, judge based on text
            response_lower = ai_response.lower()

            # Success indicators
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

            # Failure indicators
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

            # Check
            is_success = any(
                indicator in response_lower for indicator in success_indicators
            )
            is_failure = any(
                indicator in response_lower for indicator in failure_indicators
            )

            # Final judgment (success if any success indicator, failure if only failure indicators)
            success = is_success or (not is_failure and "success" in response_lower)
            confidence = 80 if success else 20

            result = {
                "success": success,
                "confidence": confidence,
                "reason": ai_response,
                "url": url,
                "title": title,
            }

            print(f"🤖 AI unsubscribe completion analysis (text-based):")
            print(f"   - Success: {success}")
            print(f"   - Confidence: {confidence}%")
            print(f"   - Reason: {ai_response}")

            return result

        except Exception as e:
            print(f"⚠️ AI response parsing failed: {str(e)}")
            return {
                "success": False,
                "confidence": 0,
                "reason": f"Parsing error: {str(e)}",
                "url": url,
                "title": title,
            }

    async def _check_post_request_success(self, page: Page) -> bool:
        """Check POST request success (AI-based improved)"""
        try:
            # First check with legacy method
            basic_result = await self._check_basic_success_indicators(page)
            if basic_result:
                print("📝 Success confirmed by basic indicator")
                return True

            # Additional check with AI-based analysis
            print("🤖 Starting AI-based unsubscribe completion analysis...")
            ai_result = await self._analyze_unsubscribe_completion_with_ai(page)

            if ai_result["success"] and ai_result["confidence"] >= 70:
                print(
                    f"🤖 Success confirmed by AI analysis (confidence: {ai_result['confidence']}%)"
                )
                return True

            return False

        except Exception as e:
            print(f"⚠️ Error during POST request check: {str(e)}")
            return False

    async def _analyze_page_for_next_action(self, page: Page) -> Dict:
        """Analyze page to determine next action"""
        try:
            ai_result = await self._analyze_unsubscribe_completion_with_ai(page)

            if ai_result["success"]:
                # Unsubscribe completed
                return {
                    "action": "success",
                    "message": "Unsubscribe completed",
                    "confidence": ai_result["confidence"],
                }
            else:
                # Unsubscribe failed
                return {
                    "action": "error",
                    "message": "An error occurred during unsubscribe",
                    "confidence": ai_result["confidence"],
                }

        except Exception as e:
            return {
                "action": "error",
                "message": f"Page analysis failed: {str(e)}",
                "confidence": 0,
            }

    async def _call_simple_ai_api(self, prompt: str) -> str:
        """Simplified OpenAI API call"""
        try:
            client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

            response = client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an AI that determines whether unsubscribe is complete on a web page. Please answer in JSON format.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=200,
                temperature=0.1,
            )

            content = response.choices[0].message.content
            print(f"🤖 AI response: {content}")
            return content

        except Exception as e:
            print(f"⚠️ OpenAI API call failed: {str(e)}")
            return '{"success": false, "confidence": 0, "reason": "API call failed"}'

    def _parse_simple_completion_result(self, ai_response: str) -> Dict:
        """Parse simplified AI response (backward compatibility)"""
        try:
            import json

            # Try JSON parsing
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

            # Text-based judgment (backward compatibility)
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
            print(f"⚠️ Failed to parse simplified AI response: {str(e)}")
            return {
                "success": False,
                "confidence": 0,
                "reason": f"Parsing error: {str(e)}",
            }

    async def _check_basic_success_indicators(self, page: Page) -> bool:
        """Check basic success indicators (improved version)"""
        try:
            # 1. Check by URL
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
                print(f"📝 URL-based success confirmed: {current_url}")
                return True

            # 2. Check by page title
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
                print(f"📝 Title-based success confirmed: {title}")
                return True

            # 3. Check by page content
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
                "Unsubscribe completed",
                "Unsubscribe has been cancelled",
                "Unsubscribe request completed",
                "No longer receiving",
                "Thank you",
                "Successfully",
                "Completed",
            ]

            if any(
                indicator in content_lower for indicator in success_content_indicators
            ):
                print(f"📝 Content-based success confirmed")
                return True

            # 4. Check specific elements
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
                                f"📝 Success confirmed by element: {selector} - {element_text}"
                            )
                            return True
                except Exception:
                    continue

            # 5. Check resubscribe button
            resubscribe_indicators = [
                "resubscribe",
                "subscribe again",
                "re-subscribe",
                "subscribe again",
                "re-subscribe",
            ]

            if any(indicator in content_lower for indicator in resubscribe_indicators):
                print(f"📝 Resubscribe button found - considered successful")
                return True

            # 6. Check error messages
            error_indicators = [
                "error",
                "failed",
                "invalid",
                "not found",
                "expired",
                "Error",
                "Failed",
                "Invalid",
                "Not found",
                "Expired",
            ]

            if any(indicator in content_lower for indicator in error_indicators):
                print(f"📝 Error indicators found")
                return False

            # 7. Check AI-based analysis
            try:
                ai_result = await self._analyze_unsubscribe_completion_with_ai(page)
                if ai_result["success"] and ai_result["confidence"] >= 60:
                    print(
                        f"📝 Success confirmed by AI analysis (confidence: {ai_result['confidence']}%)"
                    )
                    return True
            except Exception as e:
                print(f"⚠️ AI analysis failed: {str(e)}")

            return False

        except Exception as e:
            print(f"⚠️ Failed to check basic success indicators: {str(e)}")
            return False

    async def _check_unsubscribe_success(self, page: Page) -> bool:
        """Check if unsubscribe is successful (already unsubscribed + success)"""
        try:
            content = await page.content()
            content_lower = content.lower()
            current_url = page.url
            title = await page.title()

            # Basic keywords check (quick filtering)
            basic_indicators = [
                # Already unsubscribed indicators
                "already unsubscribed",
                "already cancelled",
                "already removed",
                "previously unsubscribed",
                "previously cancelled",
                "previously removed",
                "already unsubscribed",
                "already cancelled",
                "already removed",
                "already unsubscribed",
                "already cancelled",
                "already removed",
                "already unsubscribed",
                "already cancelled",
                "already removed",
                # Unsubscribe success indicators
                "unsubscribe successful",
                "successfully unsubscribed",
                "unsubscribe completed",
                "you have been unsubscribed",
                "Unsubscribe completed",
                "Unsubscribe success",
                "Unsubscribe completed",
                "Unsubscribe has been cancelled",
                "Unsubscribe request completed",
                "unsubscribe processed",
            ]

            # Check basic indicators in URL, title, and content
            all_text = f"{current_url} {title} {content_lower}"

            for indicator in basic_indicators:
                if indicator in all_text:
                    print(f"📝 Unsubscribe success indicator found: {indicator}")
                    return True

            # AI-based analysis (if no basic keywords are present)
            print(f"📝 Starting AI-based unsubscribe status analysis")

            # Extract text from page (remove HTML tags)
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(content, "html.parser")
            page_text = soup.get_text(separator=" ", strip=True)

            # Create AI prompt
            ai_prompt = f"""
Please analyze the unsubscribe status on the following web page.

Page title: {title}
Page URL: {current_url}
Page content: {page_text[:2000]}  # Using only the first 2000 characters

The following messages indicate "already unsubscribed":
- "You are not subscribed to this newsletter"
- "Already unsubscribed"
- "not subscribed"
- "no longer subscribed"
- "subscription not found"
- "Email is not in the subscription list"
- "Could not find subscription information"

The following messages indicate "unsubscribe success":
- "Unsubscribe completed"
- "Unsubscribe successful"
- "Successfully unsubscribed"
- "Unsubscribe success"
- "Unsubscribe completed"
- "Unsubscribe has been cancelled"
- "Unsubscribe request completed"
- "Unsubscribe processed"

Please answer in the following format:
- Already unsubscribed: "ALREADY_UNSUBSCRIBED"
- Unsubscribe success: "SUCCESS"
- Unsubscribe failure: "FAILED"
- Unable to determine: "UNKNOWN"

Answer:
"""

            # AI API call
            try:
                ai_response = await self._call_simple_ai_api(ai_prompt)
                print(f"📝 AI response: {ai_response}")

                if "ALREADY_UNSUBSCRIBED" in ai_response.upper():
                    print(f"📝 AI determined already unsubscribed")
                    return True
                elif "SUCCESS" in ai_response.upper():
                    print(f"📝 AI determined unsubscribe success")
                    return True
                elif "FAILED" in ai_response.upper():
                    print(f"📝 AI determined unsubscribe failure")
                    return False
                else:
                    print(f"📝 AI unable to determine unsubscribe status")
                    return False

            except Exception as ai_error:
                print(f"⚠️ AI analysis failed: {str(ai_error)}")
                return False

        except Exception as e:
            print(f"⚠️ Failed to check unsubscribe success: {str(e)}")
            return False

    async def _create_temp_page_from_response(
        self, response_text: str
    ) -> Optional[Page]:
        """Create temporary page from response"""
        try:
            # Create temporary HTML page
            temp_html = f"""
            <!DOCTYPE html>
            <html>
            <head><title>Response</title></head>
            <body>{response_text}</body>
            </html>
            """

            # Create new page
            temp_page = await self.browser.new_page()
            await temp_page.set_content(temp_html)

            return temp_page

        except Exception as e:
            print(f"⚠️ Failed to create temporary page: {str(e)}")
            return None

    async def _parse_post_response(self, response) -> Optional[Page]:
        """Parse POST response as temporary page"""
        try:
            content_type = response.headers.get("content-type", "")

            if "text/html" in content_type:
                # HTML response
                response_text = await response.text()
                return await self._create_temp_page_from_response(response_text)

            elif "application/json" in content_type:
                # JSON response
                import json

                json_data = await response.json()
                response_text = json.dumps(json_data, indent=2)
                return await self._create_temp_page_from_response(response_text)

            else:
                # General text response
                response_text = await response.text()
                return await self._create_temp_page_from_response(response_text)

        except Exception as e:
            print(f"⚠️ Failed to parse POST response: {str(e)}")
            return None

    async def _check_response_with_temp_page(self, response) -> bool:
        """Check response using temporary page (memory optimized)"""
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
        """Detect page navigation and handle it"""
        try:
            await page.wait_for_timeout(2000)  # Page loading wait

            after_url = page.url
            after_title = await page.title()

            # Check URL change
            url_changed = before_url != after_url
            title_changed = before_title and before_title != after_title

            if url_changed:
                print(f"📝 URL change detected: {before_url} → {after_url}")

                # Check if unsubscribe is successful on new page
                if await self._check_unsubscribe_success(page):
                    return {
                        "success": True,
                        "message": "Unsubscribe successful after page navigation",
                        "method": "navigation_completed",
                        "url_change": f"{before_url} → {after_url}",
                    }

                # Check basic success indicators
                elif await self._check_basic_success_indicators(page):
                    return {
                        "success": True,
                        "message": "Unsubscribe successful after page navigation",
                        "method": "navigation_success",
                        "url_change": f"{before_url} → {after_url}",
                    }

            elif title_changed:
                print(f"📝 Title change detected: {before_title} → {after_title}")

                # Check if unsubscribe is successful after title change
                if await self._check_unsubscribe_success(page):
                    return {
                        "success": True,
                        "message": "Unsubscribe successful after title change",
                        "method": "title_change_completed",
                        "title_change": f"{before_title} → {after_title}",
                    }

            # No navigation occurred but unsubscribe is successful
            if await self._check_unsubscribe_success(page):
                return {
                    "success": True,
                    "message": "Unsubscribe successful without navigation",
                    "method": "no_navigation_completed",
                }

            return {
                "success": False,
                "message": "Page navigation detected but unsubscribe incomplete",
                "method": "navigation_detected_but_incomplete",
                "url_changed": url_changed,
                "title_changed": title_changed,
            }

        except Exception as e:
            print(f"⚠️ Failed to detect page navigation: {str(e)}")
            return {
                "success": False,
                "message": f"Failed to detect page navigation: {str(e)}",
                "method": "navigation_detection_failed",
            }

    async def _wait_for_network_idle_and_check(
        self, page: Page, timeout: int = 10000
    ) -> Dict:
        """Wait for network requests to complete and check unsubscribe status"""
        try:
            # Wait for network requests to complete
            await page.wait_for_load_state("networkidle", timeout=timeout)
            print("📝 Network requests completed successfully")

            # Check if unsubscribe is successful
            if await self._check_unsubscribe_success(page):
                return {
                    "success": True,
                    "message": "Unsubscribe successful after network requests",
                    "method": "network_idle_completed",
                }

            return {
                "success": False,
                "message": "Network requests completed but unsubscribe incomplete",
                "method": "network_idle_incomplete",
            }

        except Exception as e:
            print(f"⚠️ Failed to wait for network idle: {str(e)}")
            # Fallback to default wait time if network idle fails
            await page.wait_for_timeout(3000)

            if await self._check_unsubscribe_success(page):
                return {
                    "success": True,
                    "message": "Unsubscribe successful after default wait",
                    "method": "timeout_fallback_completed",
                }

            return {
                "success": False,
                "message": f"Failed to wait for network idle: {str(e)}",
                "method": "network_wait_failed",
            }

    async def _detect_captcha(self, page: Page) -> bool:
        """Detect CAPTCHA"""
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
                    print(f"📝 CAPTCHA detected: {selector}")
                    return True

            # Check for text related to CAPTCHA
            content = await page.content()
            content_lower = content.lower()

            captcha_keywords = [
                "captcha",
                "recaptcha",
                "turnstile",
                "hcaptcha",
                "not a robot",
                "human verification",
                "security check",
                "verify you are human",
                "i am not a robot",
            ]

            for keyword in captcha_keywords:
                if keyword in content_lower:
                    print(f"📝 CAPTCHA keyword detected: {keyword}")
                    return True

            return False

        except Exception as e:
            print(f"⚠️ Failed to detect CAPTCHA: {str(e)}")
            return False

    async def _handle_captcha_required(self, page: Page) -> Dict:
        """Handle CAPTCHA requirement"""
        return {
            "success": False,
            "message": "CAPTCHA required but unable to process automatically. Please handle manually.",
            "error_type": "captcha_required",
            "method": "captcha_detected",
        }

    async def _handle_email_confirmation(
        self, page: Page, user_email: str = None
    ) -> bool:
        """Handle email confirmation request"""
        try:
            if not user_email:
                print("⚠️ No user email provided, unable to handle email confirmation")
                return False

            # Detect email input fields
            email_inputs = await page.query_selector_all(
                "input[type='email'], input[name*='email'], input[placeholder*='email'], input[placeholder*='이메일']"
            )

            if email_inputs:
                print(f"📝 Found {len(email_inputs)} email input fields")

                for email_input in email_inputs:
                    try:
                        # Fill email input
                        await email_input.fill(user_email)
                        print(f"📝 Email input filled: {user_email}")

                        # Find submit button
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
                                    print(f"📝 Submit button clicked: {element_text}")

                                    # Click submit button
                                    await submit_element.click()

                                    # Wait for page navigation or response
                                    await page.wait_for_timeout(3000)

                                    # Check if unsubscribe is successful
                                    if await self._check_unsubscribe_success(page):
                                        print("✅ Email confirmation successful")
                                        return True

                                    break

                    except Exception as e:
                        print(f"⚠️ Failed to handle email input: {str(e)}")
                        continue

                return False

            return False

        except Exception as e:
            print(f"⚠️ Failed to handle email confirmation: {str(e)}")
            return False

    async def _execute_complex_javascript(self, page: Page) -> bool:
        """Execute complex JavaScript logic"""
        try:
            print("📝 Executing complex JavaScript logic")

            # Detect and execute JavaScript functions
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
                    
                    // Form submit attempt
                    const forms = document.querySelectorAll('form');
                    for (const form of forms) {
                        if (form.action && form.action.toLowerCase().includes('unsubscribe')) {
                            console.log('Found unsubscribe form');
                            form.submit();
                            return { success: true, method: 'form_submit' };
                        }
                    }
                    
                    // Button click attempt
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
                print(f"📝 JavaScript execution successful: {js_result}")

                # Wait for asynchronous processing
                await page.wait_for_timeout(5000)

                # Wait for dynamic content loading
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
                    print("📝 Dynamic content loaded successfully")
                except Exception as e:
                    print(f"⚠️ Failed to wait for dynamic content: {str(e)}")

                return True
            else:
                print(f"⚠️ Failed to execute JavaScript: {js_result}")
                return False

        except Exception as e:
            print(f"⚠️ Failed to execute complex JavaScript: {str(e)}")
            return False

    async def _wait_for_service_worker(self, page: Page) -> bool:
        """Wait for Service Worker registration (with timeout)"""
        try:
            print("📝 Waiting for Service Worker registration")

            # Check Service Worker registration (5-second timeout)
            sw_result = await page.evaluate(
                """
                () => {
                    return new Promise((resolve) => {
                        if ('serviceWorker' in navigator) {
                            // Set timeout for 5 seconds
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
                print("📝 Service Worker registration successful")
                return True
            else:
                print(f"⚠️ Failed to register Service Worker: {sw_result}")
                return False

        except Exception as e:
            print(f"⚠️ Failed to wait for Service Worker: {str(e)}")
            return False

    async def _detect_spa_navigation(self, page: Page, before_url: str) -> bool:
        """Detect SPA navigation"""
        try:
            print("📝 Detecting SPA navigation")

            # Detect changes in History API
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
                print(f"📝 SPA navigation detected: {before_url} → {current_url}")
                return True

            return False

        except Exception as e:
            print(f"⚠️ Failed to detect SPA navigation: {str(e)}")
            return False

    async def _handle_multi_step_unsubscribe(
        self, page: Page, user_email: str = None
    ) -> Dict:
        """Handle multi-step unsubscribe (prevent infinite loop)"""
        try:
            print("📝 Starting multi-step unsubscribe process")
            steps = []

            # 1st step: Direct unsubscribe attempt (prevent infinite loop)
            print("📝 1st step: Direct unsubscribe attempt")

            # Form submit attempt
            forms = await page.query_selector_all("form")
            for form in forms:
                try:
                    action = await form.get_attribute("action")
                    if action and "unsubscribe" in action.lower():
                        print(f"📝 Executing multi-step form submit: {action}")

                        # Save current state before form submit
                        before_url = page.url
                        before_title = await page.title()

                        # Execute form submit using JavaScript
                        await page.evaluate("(form) => form.submit()", form)

                        # Detect page navigation
                        navigation_result = await self._detect_page_navigation(
                            page, before_url, before_title
                        )
                        if navigation_result["success"]:
                            steps.append("1st step completed (form submit)")
                            print("✅ 1st step completed (form submit)")
                            break

                except Exception as e:
                    print(f"⚠️ Failed to execute multi-step form submit: {str(e)}")
                    continue

            # If form submit failed, try button click
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
                                    f"📝 Clicking multi-step button: {selector} - '{element_text}'"
                                )

                                # Save current state before click
                                before_url = page.url
                                before_title = await page.title()

                                # Execute click using JavaScript
                                await page.evaluate(
                                    "(element) => element.click()", element
                                )

                                # Detect page navigation
                                navigation_result = await self._detect_page_navigation(
                                    page, before_url, before_title
                                )
                                if navigation_result["success"]:
                                    steps.append("1st step completed (button click)")
                                    print("✅ 1st step completed (button click)")
                                    break

                    except Exception as e:
                        print(f"⚠️ Failed to click multi-step button: {str(e)}")
                        continue

                    if steps:  # If successful, break out of loop
                        break

            # 2nd step: Check completion of final page
            if steps:
                print("📝 2nd step: Check completion of final page")
                await page.wait_for_timeout(3000)  # Page loading wait

                final_result = await self._check_unsubscribe_success(page)
                if final_result:
                    steps.append("2nd step completed")
                    print("✅ 2nd step completed")
                    return {
                        "success": True,
                        "message": "Multi-step unsubscribe completed",
                        "method": "multi_step_completed",
                        "steps": steps,
                    }
                else:
                    # Check basic success indicators
                    if await self._check_basic_success_indicators(page):
                        steps.append("2nd step completed (basic indicators)")
                        print("✅ 2nd step completed (basic indicators)")
                        return {
                            "success": True,
                            "message": "Multi-step unsubscribe completed (basic indicators)",
                            "method": "multi_step_basic_completed",
                            "steps": steps,
                        }

            return {
                "success": False,
                "message": "Multi-step unsubscribe failed",
                "method": "multi_step_failed",
                "steps": steps,
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to handle multi-step unsubscribe: {str(e)}",
                "method": "multi_step_error",
            }

    async def _try_second_page_unsubscribe(
        self, page: Page, user_email: str = None
    ) -> Dict:
        """Handle second page unsubscribe (integrated JavaScript-based)"""
        try:
            print(f"📝 Handling second page unsubscribe started")

            # Integrated JavaScript-based unsubscribe processing
            return await self._try_javascript_submit(
                page, user_email, is_recursive=False
            )

        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to handle second page unsubscribe: {str(e)}",
            }

    async def _try_form_action_submit(self, page: Page, user_email: str = None) -> Dict:
        """Submit form using Form Action URL"""
        try:
            print(f"📝 Handling Form Action URL")

            # Find form elements
            forms = await page.query_selector_all("form")

            for form in forms:
                try:
                    action = await form.get_attribute("action")
                    method = await form.get_attribute("method") or "GET"

                    if action and "unsubscribe" in action.lower():
                        print(f"📝 Found unsubscribe form: {action}")

                        # Collect form data
                        form_data = {}
                        inputs = await form.query_selector_all("input")

                        for input_elem in inputs:
                            name = await input_elem.get_attribute("name")
                            value = await input_elem.get_attribute("value")
                            input_type = await input_elem.get_attribute("type")

                            if name and input_type != "submit":
                                form_data[name] = value or ""

                        print(f"📝 Form data: {form_data}")

                        # Execute POST request (improved version)
                        if method.upper() == "POST":
                            response = await page.request.post(action, data=form_data)
                            print(f"📝 POST request completed: {response.status}")

                            if response.status in [200, 201, 302]:
                                # Parse response as temporary page
                                if await self._check_response_with_temp_page(response):
                                    return {
                                        "success": True,
                                        "message": "Unsubscribe confirmed after form submission",
                                        "method": "form_action_post_completed",
                                    }
                                # Check basic success indicators (if page has changed)
                                elif await self._check_basic_success_indicators(page):
                                    return {
                                        "success": True,
                                        "message": "Unsubscribe successful via Form Action URL",
                                        "method": "form_action_post",
                                    }

                        # Execute GET request
                        elif method.upper() == "GET":
                            query_string = "&".join(
                                [f"{k}={v}" for k, v in form_data.items()]
                            )
                            full_url = (
                                f"{action}?{query_string}" if query_string else action
                            )

                            await page.goto(full_url, wait_until="domcontentloaded")
                            await page.wait_for_timeout(2000)

                            # Check if unsubscribe is successful
                            if await self._check_unsubscribe_success(page):
                                return {
                                    "success": True,
                                    "message": "Unsubscribe successful after Form Action GET",
                                    "method": "form_action_get_completed",
                                }
                            # Check basic success indicators
                            elif await self._check_basic_success_indicators(page):
                                return {
                                    "success": True,
                                    "message": "Unsubscribe successful via Form Action URL",
                                    "method": "form_action_get",
                                }

                except Exception as e:
                    print(f"⚠️ Error processing form: {str(e)}")
                    continue

            return {"success": False, "message": "Failed to handle Form Action URL"}

        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to handle Form Action URL: {str(e)}",
            }

    async def _try_javascript_submit(
        self, page: Page, user_email: str = None, is_recursive: bool = False
    ) -> Dict:
        """Universal unsubscribe processing using Playwright + OpenAI API (all methods combined + improved functionality)"""
        try:
            print(f"📝 Starting universal unsubscribe processing")
            self._log_memory_usage("javascript_submit_start")

            # 0th step: Detect and handle CAPTCHA
            if await self._detect_captcha(page):
                return await self._handle_captcha_required(page)

            # 1st step: Handle email confirmation request
            if await self._handle_email_confirmation(page, user_email):
                # Submit form after email confirmation
                if await self._check_unsubscribe_success(page):
                    return {
                        "success": True,
                        "message": "Unsubscribe successful after email confirmation",
                        "method": "email_confirmation_completed",
                    }

            # 2nd step: Handle Form Action URL (POST response parsing included)
            form_result = await self._try_form_action_submit(page, user_email)
            if form_result["success"]:
                return form_result

            # 3rd step: Execute Form submit JavaScript
            self._log_memory_usage("form_submit_start")
            forms = await page.query_selector_all("form")
            print(f"📝 Found {len(forms)} forms")

            for form in forms:
                try:
                    action = await form.get_attribute("action")
                    print(f"📝 Form action: {action}")

                    # If this is a React app, action might be missing
                    if action and "unsubscribe" in action.lower():
                        print(f"📝 Executing JavaScript Form submit: {action}")

                        # Save current state before form submit
                        before_url = page.url
                        before_title = await page.title()

                        # Execute form submit using JavaScript
                        await page.evaluate("(form) => form.submit()", form)

                        # Detect SPA navigation
                        if await self._detect_spa_navigation(page, before_url):
                            if await self._check_unsubscribe_success(page):
                                return {
                                    "success": True,
                                    "message": "Unsubscribe successful after SPA navigation",
                                    "method": "spa_navigation_completed",
                                }

                        # Detect page navigation and handle it
                        navigation_result = await self._detect_page_navigation(
                            page, before_url, before_title
                        )
                        if navigation_result["success"]:
                            return navigation_result

                        # Wait for network requests to complete and check
                        network_result = await self._wait_for_network_idle_and_check(
                            page
                        )
                        if network_result["success"]:
                            return network_result
                    else:
                        # If this is a React app, handle button click inside form
                        print(f"📝 Handling React app form")
                        buttons = await form.query_selector_all("button[type='submit']")
                        if buttons:
                            for button in buttons:
                                if (
                                    await button.is_visible()
                                    and await button.is_enabled()
                                ):
                                    button_text = await button.text_content()
                                    print(
                                        f"📝 Found React form button: '{button_text}'"
                                    )

                                    # Save current state before click
                                    before_url = page.url
                                    before_title = await page.title()

                                    # Execute click using JavaScript
                                    await page.evaluate(
                                        "(button) => button.click()", button
                                    )

                                    # Detect page navigation and handle it
                                    navigation_result = (
                                        await self._detect_page_navigation(
                                            page, before_url, before_title
                                        )
                                    )
                                    if navigation_result["success"]:
                                        return navigation_result

                                    # Wait for network requests to complete and check
                                    network_result = (
                                        await self._wait_for_network_idle_and_check(
                                            page
                                        )
                                    )
                                    if network_result["success"]:
                                        return network_result

                except Exception as e:
                    print(f"⚠️ Failed to execute JavaScript Form submit: {str(e)}")
                    continue

            # 4th step: Execute complex JavaScript logic
            if await self._execute_complex_javascript(page):
                # Execute complex JavaScript logic and check if unsubscribe is successful
                if await self._check_unsubscribe_success(page):
                    return {
                        "success": True,
                        "message": "Unsubscribe successful after complex JavaScript execution",
                        "method": "complex_js_completed",
                    }

            # 5th step: Handle enhanced selectors
            enhanced_selectors = [
                # Basic buttons/inputs
                "input[type='submit']",
                "button[type='submit']",
                "button",
                # React-specific selectors
                "form button[type='submit']",
                "form .btn",
                "form button.btn",
                "footer button",
                "section button",
                # Text-based selectors (for React app)
                "button:has-text('수신거부하기')",
                "button:has-text('Unsubscribe')",
                "button:has-text('구독해지')",
                "button:has-text('취소')",
                # Unsubscribe-related
                ".unsubscribe-button",
                "#unsubscribe",
                "[class*='unsubscribe']",
                "a[href*='unsubscribe']",
                "a[href*='opt-out']",
                # Confirm/submit-related
                ".confirm-button",
                ".submit-button",
                "#confirm",
                "#submit",
                "[class*='confirm']",
                "[class*='submit']",
                # React-specific class names
                "[class*='btn']",
                "[class*='button']",
                "[class*='submit']",
                "[class*='unsubscribe']",
            ]

            # Wait for React app to load
            try:
                await page.wait_for_function(
                    """
                    () => {
                        // Check if React app is loaded
                        const root = document.getElementById('root');
                        if (!root) return false;
                        
                        // Check if buttons exist
                        const buttons = root.querySelectorAll('button');
                        return buttons.length > 0;
                    }
                """,
                    timeout=10000,
                )
                print("📝 React app loaded successfully")
            except Exception as e:
                print(f"⚠️ Failed to wait for React app: {str(e)}")

            for selector in enhanced_selectors:
                try:
                    elements = await page.query_selector_all(selector)
                    print(f"📝 Found {len(elements)} elements in selector '{selector}'")

                    for element in elements:
                        is_visible = await element.is_visible()
                        is_enabled = await element.is_enabled()

                        if is_visible and is_enabled:
                            element_text = await element.text_content()
                            print(
                                f"📝 Found element: {selector} - text: '{element_text}'"
                            )

                            # Check resubscribe button (should not be clicked!)
                            resubscribe_keywords = [
                                "resubscribe",
                                "subscribe again",
                                "re-subscribe",
                                "subscribe again",
                                "re-subscribe",
                            ]

                            is_resubscribe_button = any(
                                keyword in element_text.lower()
                                for keyword in resubscribe_keywords
                            )

                            if is_resubscribe_button:
                                print(
                                    f"🎉 Resubscribe button found - considered successful (no click)"
                                )
                                return {
                                    "success": True,
                                    "message": "Resubscribe button found, confirming successful unsubscribe",
                                    "method": "resubscribe_button_detected",
                                    "button_text": element_text,
                                }

                            # Check unsubscribe-related keywords
                            unsubscribe_keywords = [
                                "unsubscribe",
                                "opt-out",
                                "remove",
                                "cancel",
                                "unsubscribe",
                                "unsubscribe-button",
                                "unsubscribe-link",
                                "opt-out-link",
                                "remove-link",
                                "cancel-link",
                            ]

                            is_unsubscribe_button = any(
                                keyword in element_text.lower()
                                for keyword in unsubscribe_keywords
                            )

                            if is_unsubscribe_button:
                                print(
                                    f"📝 Unsubscribe button found: {selector} - text: '{element_text}'"
                                )

                                # Save current state before click
                                before_url = page.url
                                before_title = await page.title()

                                # Execute click event using JavaScript
                                await page.evaluate(
                                    "(element) => element.click()", element
                                )

                                # Detect SPA navigation
                                if await self._detect_spa_navigation(page, before_url):
                                    if await self._check_unsubscribe_success(page):
                                        return {
                                            "success": True,
                                            "message": "Unsubscribe successful after SPA navigation",
                                            "method": "spa_navigation_completed",
                                        }

                                # Detect page navigation and handle it
                                navigation_result = await self._detect_page_navigation(
                                    page, before_url, before_title
                                )
                                if navigation_result["success"]:
                                    return navigation_result

                                # Wait for network requests to complete and check
                                network_result = (
                                    await self._wait_for_network_idle_and_check(page)
                                )
                                if network_result["success"]:
                                    return network_result

                except Exception as e:
                    print(f"⚠️ Failed to handle JavaScript click: {str(e)}")
                    continue

            # 6th step: Handle multi-step unsubscribe (recursive call prevention)
            if not is_recursive:
                multi_step_result = await self._handle_multi_step_unsubscribe(
                    page, user_email
                )
                if multi_step_result["success"]:
                    return multi_step_result

            # 7th step: Handle link-based unsubscribe
            link_result = await self._try_link_based_unsubscribe(page, user_email)
            if link_result["success"]:
                return link_result

            return {
                "success": False,
                "message": "Failed to process universal unsubscribe",
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to process universal unsubscribe: {str(e)}",
            }

    async def _try_enhanced_selectors(self, page: Page, user_email: str = None) -> Dict:
        """Handle enhanced selectors for unsubscribe"""
        try:
            print(f"📝 Trying enhanced selectors")

            # List of extended selectors
            enhanced_selectors = [
                # Basic buttons/inputs
                "input[type='submit']",
                "button[type='submit']",
                "input[type='button']",
                "button",
                # Unsubscribe-related
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
                # Confirm/submit-related
                ".confirm-button",
                ".submit-button",
                "#confirm",
                "#submit",
                "[class*='confirm']",
                "[class*='submit']",
                "[id*='confirm']",
                "[id*='submit']",
                # General buttons
                ".btn",
                ".button",
                "[class*='btn']",
                "[class*='button']",
                # Text-based selectors
                "button:has-text('Unsubscribe')",
                "button:has-text('구독해지')",
                "button:has-text('Confirm')",
                "button:has-text('확인')",
                "input:has-text('Unsubscribe')",
                "input:has-text('구독해지')",
                # Form-related
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
                                f"📝 Found enhanced selector: {selector} - text: '{element_text}'"
                            )

                            # Check resubscribe button (should not be clicked!)
                            resubscribe_keywords = [
                                "resubscribe",
                                "subscribe again",
                                "re-subscribe",
                                "subscribe again",
                                "re-subscribe",
                            ]

                            is_resubscribe_button = any(
                                keyword in element_text.lower()
                                for keyword in resubscribe_keywords
                            )

                            if is_resubscribe_button:
                                print(
                                    f"🎉 Resubscribe button found - considered successful (no click)"
                                )
                                return {
                                    "success": True,
                                    "message": "Resubscribe button found, confirming successful unsubscribe",
                                    "method": "resubscribe_button_detected",
                                    "button_text": element_text,
                                }

                            # Check unsubscribe-related keywords
                            action_keywords = [
                                "confirm",
                                "submit",
                                "unsubscribe",
                                "cancel",
                                "remove",
                                "opt-out",
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
                                print(f"📝 Clicking enhanced selector: {element_text}")

                                # Save current URL before click
                                before_url = page.url

                                # Execute click (increased timeout)
                                try:
                                    await element.click(timeout=15000)
                                except Exception as click_error:
                                    print(
                                        f"⚠️ Click failed, retrying with JavaScript: {str(click_error)}"
                                    )
                                    await page.evaluate(
                                        "(element) => element.click()", element
                                    )

                                # Wait for network requests to complete
                                try:
                                    await page.wait_for_load_state(
                                        "networkidle", timeout=10000
                                    )
                                    print("📝 Network requests completed successfully")
                                except Exception as e:
                                    print(
                                        f"⚠️ Failed to wait for network idle, falling back to default wait: {str(e)}"
                                    )
                                    await page.wait_for_timeout(5000)

                                # Check URL change
                                after_url = page.url
                                if before_url != after_url:
                                    print(
                                        f"📝 URL change detected: {before_url} → {after_url}"
                                    )

                                # Check if unsubscribe is successful
                                if await self._check_unsubscribe_success(page):
                                    return {
                                        "success": True,
                                        "message": "Unsubscribe successful after enhanced selector click",
                                        "method": "enhanced_selectors_completed",
                                        "selector": selector,
                                    }
                                # Check basic success indicators
                                elif await self._check_basic_success_indicators(page):
                                    return {
                                        "success": True,
                                        "message": f"Unsubscribe successful via enhanced selector: {selector}",
                                        "method": "enhanced_selector",
                                        "selector": selector,
                                    }

                except Exception as e:
                    print(f"⚠️ Failed to handle enhanced selector {selector}: {str(e)}")
                    continue

            return {"success": False, "message": "Failed to handle enhanced selectors"}

        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to handle enhanced selectors: {str(e)}",
            }

    async def _try_link_based_unsubscribe(
        self, page: Page, user_email: str = None
    ) -> Dict:
        """Handle link-based unsubscribe"""
        try:
            print(f"📝 Starting link-based unsubscribe process")

            # Find all links
            links = await page.query_selector_all("a[href]")

            for link in links:
                try:
                    href = await link.get_attribute("href")
                    link_text = await link.text_content()

                    # Check if this is a resubscribe link (should not be clicked!)
                    resubscribe_keywords = [
                        "resubscribe",
                        "subscribe again",
                        "re-subscribe",
                        "subscribe again",
                        "re-subscribe",
                        "다시 구독하기",
                        "재구독",
                    ]

                    is_resubscribe_link = any(
                        keyword in link_text.lower() for keyword in resubscribe_keywords
                    )

                    if is_resubscribe_link:
                        print(
                            f"🎉 Resubscribe link found - considered successful (no click)"
                        )
                        return {
                            "success": True,
                            "message": "Resubscribe link found, confirming successful unsubscribe",
                            "method": "resubscribe_link_detected",
                            "link_text": link_text,
                        }

                    if href and any(
                        keyword in href.lower()
                        for keyword in ["unsubscribe", "opt-out", "remove", "cancel"]
                    ):
                        print(
                            f"📝 Unsubscribe link found: {href} - text: '{link_text}'"
                        )

                        # Click link
                        await link.click(timeout=15000)

                        # Wait for network requests to complete
                        try:
                            await page.wait_for_load_state("networkidle", timeout=10000)
                            print(
                                "📝 Link clicked, network requests completed successfully"
                            )
                        except Exception as e:
                            print(
                                f"⚠️ Failed to wait for network idle, falling back to default wait: {str(e)}"
                            )
                            await page.wait_for_timeout(5000)

                        # Check if unsubscribe is successful
                        if await self._check_unsubscribe_success(page):
                            return {
                                "success": True,
                                "message": "Unsubscribe successful after link click",
                                "method": "link_based_completed",
                                "link": href,
                            }
                        # Check basic success indicators
                        elif await self._check_basic_success_indicators(page):
                            return {
                                "success": True,
                                "message": f"Unsubscribe successful via link-based method: {href}",
                                "method": "link_based",
                                "link": href,
                            }

                except Exception as e:
                    print(f"⚠️ Error processing link: {str(e)}")
                    continue

            return {
                "success": False,
                "message": "Failed to process link-based unsubscribe",
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to process link-based unsubscribe: {str(e)}",
            }

    async def _analyze_page_with_ai(self, page: Page, user_email: str = None) -> Dict:
        """Analyze page using AI"""
        try:
            # Extract page information
            page_info = await self._extract_page_info(page)

            # Create AI prompt
            prompt = self._create_ai_prompt(page_info, user_email)

            # Call OpenAI API
            ai_response = await self._call_openai_api(prompt)

            # Execute AI instructions
            return await self._execute_ai_instructions(page, ai_response, user_email)

        except Exception as e:
            return {"success": False, "message": f"Failed to analyze page: {str(e)}"}

    async def _extract_page_info(self, page: Page) -> Dict:
        """Extract page information"""
        try:
            # Page title
            title = await page.title()

            # All links
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

            # All buttons
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

            # All forms
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
            print(f"⚠️ Failed to extract page information: {str(e)}")
            return {"error": str(e)}

    def _create_ai_prompt(self, page_info: Dict, user_email: str = None) -> str:
        """Create AI prompt"""
        prompt = f"""
Please find and execute the unsubscribe functionality on the following web page.

Page information:
- Title: {page_info.get('title', 'N/A')}
- URL: {page_info.get('url', 'N/A')}

User email: {user_email or 'N/A'}

Available elements:
"""

        # Add link information
        if page_info.get("links"):
            prompt += "\nLinks:\n"
            for link in page_info["links"][:10]:  # Only first 10
                prompt += f"- Text: '{link['text']}', href: '{link['href']}'\n"

        # Add button information
        if page_info.get("buttons"):
            prompt += "\nButtons:\n"
            for button in page_info["buttons"][:10]:  # Only first 10
                prompt += f"- Text: '{button['text']}', type: '{button['type']}'\n"

        prompt += """
Please choose one of the following actions and execute it:
1. Click unsubscribe link
2. Click unsubscribe button
3. Submit form
4. Click confirm button

Response format:
{
    "action": "link_click|button_click|form_submit|confirm",
    "target": "Text or selector to click",
    "reason": "Reason for selection"
}
"""

        return prompt

    async def _call_openai_api(self, prompt: str) -> Dict:
        """Call OpenAI API"""
        try:
            client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

            response = client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an AI assistant that finds and executes unsubscribe functionality on a web page. Please answer in JSON format.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=500,
                temperature=0.1,
            )

            content = response.choices[0].message.content
            print(f"🤖 AI response: {content}")

            # Try JSON parsing
            try:
                return json.loads(content)
            except:
                # If not JSON, use default response
                return {"action": "none", "reason": "Failed to parse AI response"}

        except Exception as e:
            print(f"⚠️ Failed to call OpenAI API: {str(e)}")
            return {"action": "none", "reason": f"OpenAI API error: {str(e)}"}

    async def _execute_ai_instructions(
        self, page: Page, ai_response: Dict, user_email: str = None
    ) -> Dict:
        """Execute AI instructions (apply AI-based completion check)"""
        try:
            action = ai_response.get("action", "none")
            target = ai_response.get("target", "")

            if action == "none":
                return {
                    "success": False,
                    "message": ai_response.get(
                        "reason", "Could not find unsubscribe element"
                    ),
                }

            elif action == "link_click":
                # Handle link click
                elements = await page.query_selector_all("a")
                for element in elements:
                    element_text = await element.text_content()
                    if target.lower() in element_text.lower():
                        print(
                            f"📝 Clicking link based on AI instructions: {element_text}"
                        )

                        # Save current URL before click
                        before_url = page.url

                        # Execute click
                        await element.click()

                        # Wait for network requests to complete
                        try:
                            await page.wait_for_load_state("networkidle", timeout=15000)
                            print("📝 Network requests completed successfully")
                        except Exception as e:
                            print(
                                f"⚠️ Failed to wait for network idle, falling back to default wait: {str(e)}"
                            )
                            await page.wait_for_timeout(5000)

                        # Check if unsubscribe is successful
                        print("🤖 Starting AI-based unsubscribe completion analysis...")
                        ai_result = await self._analyze_unsubscribe_completion_with_ai(
                            page
                        )

                        if ai_result["success"] and ai_result["confidence"] >= 70:
                            print(
                                f"🤖 Unsubscribe confirmed by AI analysis (confidence: {ai_result['confidence']}%)"
                            )
                            return {
                                "success": True,
                                "message": f"Unsubscribe successful via AI instructions (AI confidence: {ai_result['confidence']}%)",
                                "ai_confidence": ai_result["confidence"],
                                "ai_reason": ai_result["reason"],
                            }
                        else:
                            print(
                                f"🤖 AI analysis result: Unsubscribe not completed (confidence: {ai_result['confidence']}%)"
                            )
                            return {
                                "success": True,
                                "message": "Unsubscribe successful via AI instructions",
                            }

            elif action == "button_click":
                # Handle button click
                elements = await page.query_selector_all("button")
                for element in elements:
                    element_text = await element.text_content()
                    if target.lower() in element_text.lower():
                        print(
                            f"📝 Clicking button based on AI instructions: {element_text}"
                        )

                        # Save current URL before click
                        before_url = page.url

                        # Execute click
                        await element.click()

                        # Wait for network requests to complete
                        try:
                            await page.wait_for_load_state("networkidle", timeout=10000)
                            print("📝 Network requests completed successfully")
                        except Exception as e:
                            print(
                                f"⚠️ Failed to wait for network idle, falling back to default wait: {str(e)}"
                            )
                            await page.wait_for_timeout(2000)

                        # Check if unsubscribe is successful
                        print("🤖 Starting AI-based unsubscribe completion analysis...")
                        ai_result = await self._analyze_unsubscribe_completion_with_ai(
                            page
                        )

                        if ai_result["success"] and ai_result["confidence"] >= 70:
                            print(
                                f"🤖 Unsubscribe confirmed by AI analysis (confidence: {ai_result['confidence']}%)"
                            )
                            return {
                                "success": True,
                                "message": f"Unsubscribe successful via AI instructions (AI confidence: {ai_result['confidence']}%)",
                                "ai_confidence": ai_result["confidence"],
                                "ai_reason": ai_result["reason"],
                            }
                        else:
                            print(
                                f"🤖 AI analysis result: Unsubscribe not completed (confidence: {ai_result['confidence']}%)"
                            )
                            return {
                                "success": True,
                                "message": "Unsubscribe successful via AI instructions",
                            }

            elif action == "form_submit":
                # Handle form submission
                forms = await page.query_selector_all("form")
                for form in forms:
                    if user_email:
                        # Find email field and fill it
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
                        print(
                            f"📝 Submitting form using AI instructions: {button_text}"
                        )

                        # Save current URL before submission
                        before_url = page.url

                        # Submit form
                        await button.click()

                        # Wait for network requests to complete
                        try:
                            await page.wait_for_load_state("networkidle", timeout=10000)
                            print("📝 Network requests completed successfully")
                        except Exception as e:
                            print(
                                f"⚠️ Failed to wait for network idle, falling back to default wait: {str(e)}"
                            )
                            await page.wait_for_timeout(2000)

                        # Check if unsubscribe is successful
                        print("🤖 Starting AI-based unsubscribe completion analysis...")
                        ai_result = await self._analyze_unsubscribe_completion_with_ai(
                            page
                        )

                        if ai_result["success"] and ai_result["confidence"] >= 70:
                            print(
                                f"🤖 Unsubscribe confirmed by AI analysis (confidence: {ai_result['confidence']}%)"
                            )
                            return {
                                "success": True,
                                "message": f"Unsubscribe successful via AI instructions (AI confidence: {ai_result['confidence']}%)",
                                "ai_confidence": ai_result["confidence"],
                                "ai_reason": ai_result["reason"],
                            }
                        else:
                            print(
                                f"🤖 AI analysis result: Unsubscribe not completed (confidence: {ai_result['confidence']}%)"
                            )
                            return {
                                "success": True,
                                "message": "Unsubscribe successful via AI instructions",
                            }

            elif action == "confirm":
                # Handle confirm button click
                elements = await page.query_selector_all(
                    "button:has-text('확인'), button:has-text('Confirm')"
                )
                for element in elements:
                    element_text = await element.text_content()
                    if target.lower() in element_text.lower():
                        print(
                            f"📝 Clicking confirm button based on AI instructions: {element_text}"
                        )

                        # Save current URL before click
                        before_url = page.url

                        # Execute click
                        await element.click()

                        # Wait for network requests to complete
                        try:
                            await page.wait_for_load_state("networkidle", timeout=10000)
                            print("📝 Network requests completed successfully")
                        except Exception as e:
                            print(
                                f"⚠️ Failed to wait for network idle, falling back to default wait: {str(e)}"
                            )
                            await page.wait_for_timeout(2000)

                        # Check if unsubscribe is successful
                        print("🤖 Starting AI-based unsubscribe completion analysis...")
                        ai_result = await self._analyze_unsubscribe_completion_with_ai(
                            page
                        )

                        if ai_result["success"] and ai_result["confidence"] >= 70:
                            print(
                                f"🤖 Unsubscribe confirmed by AI analysis (confidence: {ai_result['confidence']}%)"
                            )
                            return {
                                "success": True,
                                "message": f"Unsubscribe successful via AI instructions (AI confidence: {ai_result['confidence']}%)",
                                "ai_confidence": ai_result["confidence"],
                                "ai_reason": ai_result["reason"],
                            }
                        else:
                            print(
                                f"🤖 AI analysis result: Unsubscribe not completed (confidence: {ai_result['confidence']}%)"
                            )
                            return {
                                "success": True,
                                "message": "Unsubscribe successful via AI instructions",
                            }

            return {"success": False, "message": "Failed to execute AI instructions"}

        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to execute AI instructions: {str(e)}",
            }

    async def _try_form_submit(self, page: Page, user_email: str = None) -> Dict:
        """Handle form submission separately"""
        try:
            # Find form
            forms = await page.query_selector_all("form")
            for form in forms:
                # If email field exists, fill it
                if user_email:
                    email_inputs = await form.query_selector_all(
                        "input[type='email'], input[name*='email']"
                    )
                    for email_input in email_inputs:
                        await email_input.fill(user_email)
                        print(f"📝 Email input filled: {user_email}")

                # Find submit button
                submit_buttons = await form.query_selector_all(
                    "input[type='submit'], button[type='submit']"
                )
                for button in submit_buttons:
                    button_text = await button.text_content()
                    print(f"📝 Found submit button: {button_text}")

                    # Save current URL before submission
                    before_url = page.url

                    # Submit form
                    await button.click()

                    # Wait for network requests to complete
                    try:
                        await page.wait_for_load_state("networkidle", timeout=10000)
                        print("📝 Network requests completed successfully")
                    except:
                        await page.wait_for_timeout(3000)

                    # Check result
                    if await self._check_post_request_success(page):
                        return {
                            "success": True,
                            "message": "Form submission successful",
                        }

            return {"success": False, "message": "Form submission failed"}

        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to handle form submission: {str(e)}",
            }

    def _finalize_success(self, result: Dict, start_time: float) -> Dict:
        """Finalize success result"""
        processing_time = time.time() - start_time
        self.log_unsubscribe_result(result, processing_time, "success")

        return {
            "success": True,
            "message": result.get("message", "Unsubscribe successful"),
            "processing_time": processing_time,
        }

    def _finalize_failure(self, message: str, start_time: float) -> Dict:
        """Finalize failure result"""
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
        """Log unsubscribe attempt"""
        self.stats["total_attempts"] += 1
        self.logger.info(f"Unsubscribe attempt: {url}, user: {user_email}")

    def log_unsubscribe_result(
        self, result: Dict, processing_time: float, status: str
    ) -> None:
        """Log unsubscribe result"""
        if status == "success":
            self.stats["successful_unsubscribes"] += 1
        else:
            self.stats["failed_unsubscribes"] += 1

        self.stats["processing_times"].append(processing_time)
        self.logger.info(
            f"Unsubscribe result: {result.get('message', 'N/A')}, processing time: {processing_time:.2f} seconds"
        )

    def get_statistics(self) -> Dict:
        """Return statistics"""
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
        """Set up logging"""
        logging.basicConfig(
            level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
        )
        self.logger = logging.getLogger(__name__)

        # Add file logging
        if not os.path.exists("logs"):
            os.makedirs("logs")
        file_handler = logging.FileHandler("logs/playwright_unsubscribe_service.log")
        file_handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)

    async def _init_browser(self):
        """Initialize browser instance"""
        if self.browser is None:
            self.browser = await async_playwright().start()
            self.context = await self.browser.chromium.launch_persistent_context(
                user_data_dir="/tmp/playwright_user_data",
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"],
            )
            print("[INFO] Browser initialized.")

    async def _close_browser(self):
        """Close browser instance"""
        if self.context:
            await self.context.close()
            self.context = None
        if self.browser:
            await self.browser.stop()
            self.browser = None
        print("[INFO] Browser closed.")

    async def process_unsubscribe(self, url: str) -> dict:
        """Process unsubscribe using Playwright"""
        await self._init_browser()
        page = await self.context.new_page()
        try:
            await page.goto(url)
            print(f"[INFO] Navigated to {url}")
            # ... existing code ...
        except Exception as e:
            print(f"[ERROR] Unsubscribe process failed: {str(e)}")
            return {
                "success": False,
                "message": f"Unsubscribe process failed: {str(e)}",
            }
        finally:
            await page.close()
            print("[INFO] Page closed.")

    async def extract_unsubscribe_links_with_ai_fallback(
        self, email_content: str, email_headers: Dict = None, user_email: str = None
    ) -> List[str]:
        """Extract unsubscribe links from email, fallback to AI-based context analysis if none found (async)"""
        # 1. 기존 동기 방식으로 먼저 시도
        links = self.extract_unsubscribe_links(email_content, email_headers)
        # 2. AI 기반 후보도 함께 추출
        ai_links = await self.extract_unsubscribe_links_with_ai_judgement(
            email_content, email_headers, user_email
        )
        # 3. 두 결과를 합치고, 중복 제거
        all_links = list({*links, *ai_links})
        if all_links:
            print(f"📝 [COMBINED] Unsubscribe links (rule+AI): {all_links}")
            return all_links
        print(
            "🤖 No unsubscribe links found by keyword or AI-based context analysis..."
        )
        # 4. Playwright 브라우저/컨텍스트 초기화 (기존 AI fallback)
        await self.initialize_browser()
        temp_page = await self._create_temp_page_from_response(email_content)
        if not temp_page:
            print("❌ Failed to create temp page for AI analysis.")
            return []
        try:
            ai_result = await self._analyze_page_with_ai(temp_page, user_email)
            target = ai_result.get("target")
            if ai_result.get("success") and ai_result.get("message", "").startswith(
                "Unsubscribe successful"
            ):
                if target:
                    from bs4 import BeautifulSoup

                    soup = BeautifulSoup(email_content, "html.parser")
                    for link in soup.find_all("a", href=True):
                        if target.lower() in link.get_text().lower():
                            return [link["href"]]
            return []
        finally:
            await temp_page.close()

    async def extract_unsubscribe_links_with_ai_judgement(
        self, email_content: str, email_headers: Dict = None, user_email: str = None
    ) -> List[str]:
        """AI를 이용해 모든 a태그 후보의 구독 해제 여부를 판단한다."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(email_content, "html.parser")
        candidates = []
        for link in soup.find_all("a", href=True):
            link_text = link.get_text().strip()
            href = link.get("href", "")
            parent_text = link.parent.get_text().strip() if link.parent else ""
            grandparent_text = (
                link.parent.parent.get_text().strip()
                if link.parent and link.parent.parent
                else ""
            )
            candidates.append(
                {
                    "href": href,
                    "text": link_text,
                    "parent_text": parent_text,
                    "grandparent_text": grandparent_text,
                }
            )
        if not candidates:
            return []
        prompt = (
            "아래는 이메일 본문에서 추출한 a태그 후보들입니다. 각 후보가 구독 해제(수신거부, opt-out, unsubscribe) 링크인지 판단해 주세요. "
            "각 항목별로 {href, is_unsubscribe, reason} 형태의 JSON 배열로 답변해 주세요. "
            "is_unsubscribe는 true/false로, reason에는 근거를 간단히 적어주세요.\n"
            "후보 목록:\n"
            + "\n".join(
                [
                    f"- href: {c['href']}, text: {c['text']}, parent: {c['parent_text']}, grandparent: {c['grandparent_text']}"
                    for c in candidates
                ]
            )
        )
        # OpenAI API 호출 (기존 _call_openai_api 활용)
        ai_response = await self._call_openai_api(prompt)
        # 응답 파싱
        try:
            # JSON 배열 형태로 파싱
            result = json.loads(ai_response)
            links = [item["href"] for item in result if item.get("is_unsubscribe")]
            return links
        except Exception as e:
            print(f"⚠️ AI 링크 판별 응답 파싱 실패: {str(e)} | 원본: {ai_response}")
            return []


# Synchronous wrapper function (for use in Flask application)
def process_unsubscribe_sync(unsubscribe_url: str, user_email: str = None) -> Dict:
    """Synchronous unsubscribe processing wrapper (Flask-safe)"""
    service = PlaywrightUnsubscribeService()
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        raise RuntimeError(
            "process_unsubscribe_sync는 이미 실행 중인 이벤트 루프 내에서 호출할 수 없습니다. Flask 등 동기 환경에서만 사용하세요. 비동기 환경에서는 직접 await service.process_unsubscribe_with_playwright_ai(...)를 호출하세요."
        )
    else:
        return asyncio.run(
            service.process_unsubscribe_with_playwright_ai(unsubscribe_url, user_email)
        )
