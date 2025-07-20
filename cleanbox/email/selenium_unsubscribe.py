"""
Selenium 기반 구독해지 서비스
JavaScript 지원과 더 강력한 웹 자동화 기능을 제공합니다.
"""

import logging
import re
import time
import os
import json
from typing import List, Dict, Optional, Tuple
from urllib.parse import urlparse, urljoin

# Third-party imports
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    WebDriverException,
    ElementClickInterceptedException,
    StaleElementReferenceException,
)
from webdriver_manager.chrome import ChromeDriverManager


class SeleniumUnsubscribeService:
    """Selenium 기반 고급 구독해지 서비스"""

    def __init__(self):
        self.setup_logging()
        self.driver = None

        # 타임아웃 설정 (배포 환경에 맞게 조정)
        self.timeouts = {
            "page_load": 60,  # 30초 → 60초
            "element_wait": 15,  # 10초 → 15초
            "api_call": 30,  # 15초 → 30초
            "retry_delay": 3,  # 2초 → 3초
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
        file_handler = logging.FileHandler("logs/selenium_unsubscribe_service.log")
        file_handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)

        # 통계 초기화
        self.stats = {
            "total_attempts": 0,
            "successful_unsubscribes": 0,
            "failed_unsubscribes": 0,
            "processing_times": [],
            "service_success_rates": {},
            "error_counts": {},
        }

    def _setup_chrome_driver(self) -> webdriver.Chrome:
        """Chrome WebDriver 설정 (메모리 최적화)"""
        chrome_options = Options()

        # 메모리 사용량 최적화
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-plugins")
        chrome_options.add_argument("--disable-images")
        chrome_options.add_argument("--disable-javascript")  # 필요시 제거
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--window-size=1280,720")  # 해상도 줄임
        chrome_options.add_argument("--disable-background-timer-throttling")
        chrome_options.add_argument("--disable-backgrounding-occluded-windows")
        chrome_options.add_argument("--disable-renderer-backgrounding")
        chrome_options.add_argument("--disable-features=TranslateUI")
        chrome_options.add_argument("--disable-ipc-flooding-protection")
        chrome_options.add_argument("--memory-pressure-off")
        chrome_options.add_argument("--max_old_space_size=128")  # 메모리 제한
        chrome_options.add_argument(
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        # ChromeDriver 경로 설정
        if os.environ.get("CHROMEDRIVER_PATH"):
            service = Service(os.environ["CHROMEDRIVER_PATH"])
        else:
            # webdriver-manager 사용
            service = Service(ChromeDriverManager().install())

        try:
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.set_page_load_timeout(self.timeouts["page_load"])
            driver.implicitly_wait(self.timeouts["element_wait"])

            # 메모리 사용량 모니터링
            self._log_memory_usage("Chrome 드라이버 초기화 후")

            return driver
        except Exception as e:
            print(f"❌ Chrome 드라이버 초기화 실패: {str(e)}")
            raise e

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

    def process_unsubscribe_with_selenium_ai(
        self, unsubscribe_url: str, user_email: str = None
    ) -> Dict:
        """Selenium + OpenAI API를 활용한 범용 구독해지 처리 (메모리 최적화)"""
        start_time = time.time()
        self.log_unsubscribe_attempt(unsubscribe_url, user_email, start_time)

        # 초기 메모리 체크
        self._log_memory_usage("처리 시작")
        if not self._check_memory_limit():
            return self._finalize_failure("메모리 부족으로 처리 중단", start_time)

        max_retries = 2
        retry_count = 0

        while retry_count <= max_retries:
            try:
                print(
                    f"🔧 Selenium + AI 구독해지 시도 (시도 {retry_count + 1}/{max_retries + 1}): {unsubscribe_url}"
                )

                # 메모리 체크
                if not self._check_memory_limit():
                    return self._finalize_failure(
                        "메모리 부족으로 처리 중단", start_time
                    )

                # Chrome WebDriver 초기화
                self.driver = self._setup_chrome_driver()

                # 1단계: 초기 페이지 접속
                print(f"📝 1단계: 초기 페이지 접속")
                self.driver.get(unsubscribe_url)
                time.sleep(2)  # 페이지 로딩 대기

                # 메모리 체크
                if not self._check_memory_limit():
                    self._cleanup_driver()
                    return self._finalize_failure(
                        "메모리 부족으로 처리 중단", start_time
                    )

                # 2단계: 기본 구독해지 시도
                print(f"📝 2단계: 기본 구독해지 시도")
                basic_result = self._try_basic_unsubscribe(user_email)
                if basic_result["success"]:
                    self._cleanup_driver()
                    return self._finalize_success(basic_result, start_time)

                # 3단계: 두 번째 페이지 처리
                print(f"📝 3단계: 두 번째 페이지 처리")
                second_result = self._try_second_page_unsubscribe(user_email)
                if second_result["success"]:
                    self._cleanup_driver()
                    return self._finalize_success(second_result, start_time)

                # 4단계: AI 분석 및 처리
                print(f"📝 4단계: AI 분석 및 처리")
                ai_result = self._analyze_page_with_ai(user_email)
                if ai_result["success"]:
                    self._cleanup_driver()
                    return self._finalize_success(ai_result, start_time)

                # 모든 시도 실패
                self._cleanup_driver()
                return self._finalize_failure(
                    "모든 구독해지 방법이 실패했습니다", start_time
                )

            except Exception as e:
                print(f"❌ Selenium 처리 중 오류: {str(e)}")
                self._cleanup_driver()
                retry_count += 1
                if retry_count <= max_retries:
                    print(f"⏳ {self.timeouts['retry_delay']}초 후 재시도...")
                    time.sleep(self.timeouts["retry_delay"])
                else:
                    return self._finalize_failure(
                        f"Selenium 처리 실패: {str(e)}", start_time
                    )

        return self._finalize_failure("최대 재시도 횟수 초과", start_time)

    def _try_basic_unsubscribe(self, user_email: str = None) -> Dict:
        """기본 구독해지 시도"""
        try:
            # 구독해지 관련 요소들 찾기
            selectors = [
                "a[href*='unsubscribe']",
                "a[href*='opt-out']",
                "a[href*='remove']",
                "a[href*='cancel']",
                "button[onclick*='unsubscribe']",
                "input[value*='unsubscribe']",
                ".unsubscribe",
                "#unsubscribe",
                "[class*='unsubscribe']",
                "[id*='unsubscribe']",
            ]

            for selector in selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        if element.is_displayed() and element.is_enabled():
                            print(f"📝 구독해지 요소 발견: {selector}")
                            element.click()
                            time.sleep(2)
                            return {"success": True, "message": "기본 구독해지 성공"}
                except Exception as e:
                    print(f"⚠️ 선택자 {selector} 처리 중 오류: {str(e)}")
                    continue

            return {"success": False, "message": "구독해지 요소를 찾을 수 없습니다"}

        except Exception as e:
            return {"success": False, "message": f"기본 구독해지 실패: {str(e)}"}

    def _try_second_page_unsubscribe(self, user_email: str = None) -> Dict:
        """두 번째 페이지 구독해지 처리"""
        try:
            # 현재 페이지에서 구독해지 관련 버튼/링크 찾기
            second_page_selectors = [
                "button[type='submit']",
                "input[type='submit']",
                "button:contains('Confirm')",
                "button:contains('Unsubscribe')",
                "a:contains('Unsubscribe')",
                ".confirm-button",
                ".submit-button",
                "#confirm",
                "#submit",
            ]

            for selector in second_page_selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        if element.is_displayed() and element.is_enabled():
                            print(f"📝 두 번째 페이지 요소 발견: {selector}")
                            element.click()
                            time.sleep(2)
                            return {
                                "success": True,
                                "message": "두 번째 페이지 구독해지 성공",
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

    def _analyze_page_with_ai(self, user_email: str = None) -> Dict:
        """AI를 사용한 페이지 분석 및 처리"""
        try:
            # 페이지 정보 추출
            page_info = self._extract_page_info()

            # AI 프롬프트 생성
            prompt = self._create_ai_prompt(page_info, user_email)

            # OpenAI API 호출
            ai_response = self._call_openai_api(prompt)

            # AI 지시 실행
            return self._execute_ai_instructions(ai_response, user_email)

        except Exception as e:
            return {"success": False, "message": f"AI 분석 실패: {str(e)}"}

    def _extract_page_info(self) -> Dict:
        """페이지 정보 추출"""
        try:
            page_source = self.driver.page_source
            soup = BeautifulSoup(page_source, "html.parser")

            # 페이지 제목
            title = soup.find("title")
            title_text = title.get_text() if title else ""

            # 모든 링크
            links = []
            for link in soup.find_all("a", href=True):
                links.append(
                    {
                        "text": link.get_text().strip(),
                        "href": link["href"],
                        "class": link.get("class", []),
                        "id": link.get("id", ""),
                    }
                )

            # 모든 버튼
            buttons = []
            for button in soup.find_all("button"):
                buttons.append(
                    {
                        "text": button.get_text().strip(),
                        "type": button.get("type", ""),
                        "class": button.get("class", []),
                        "id": button.get("id", ""),
                    }
                )

            # 모든 폼
            forms = []
            for form in soup.find_all("form"):
                forms.append(
                    {
                        "action": form.get("action", ""),
                        "method": form.get("method", ""),
                        "class": form.get("class", []),
                        "id": form.get("id", ""),
                    }
                )

            return {
                "title": title_text,
                "url": self.driver.current_url,
                "links": links,
                "buttons": buttons,
                "forms": forms,
                "page_source": page_source[:2000],  # 처음 2000자만
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

    def _call_openai_api(self, prompt: str) -> Dict:
        """OpenAI API 호출"""
        try:
            import openai

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

    def _execute_ai_instructions(
        self, ai_response: Dict, user_email: str = None
    ) -> Dict:
        """AI 지시 실행"""
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
                elements = self.driver.find_elements(By.TAG_NAME, "a")
                for element in elements:
                    if target.lower() in element.text.lower():
                        print(f"📝 AI 지시에 따른 링크 클릭: {element.text}")
                        element.click()
                        time.sleep(2)
                        return {
                            "success": True,
                            "message": "AI 지시에 따른 링크 클릭 완료",
                        }

            elif action == "button_click":
                # 버튼 클릭 처리
                elements = self.driver.find_elements(By.TAG_NAME, "button")
                for element in elements:
                    if target.lower() in element.text.lower():
                        print(f"📝 AI 지시에 따른 버튼 클릭: {element.text}")
                        element.click()
                        time.sleep(2)
                        return {
                            "success": True,
                            "message": "AI 지시에 따른 버튼 클릭 완료",
                        }

            elif action == "form_submit":
                # 폼 제출 처리
                forms = self.driver.find_elements(By.TAG_NAME, "form")
                for form in forms:
                    if user_email:
                        # 이메일 필드 찾아서 입력
                        email_inputs = form.find_elements(
                            By.CSS_SELECTOR, "input[type='email'], input[name*='email']"
                        )
                        for email_input in email_inputs:
                            email_input.clear()
                            email_input.send_keys(user_email)

                    submit_buttons = form.find_elements(
                        By.CSS_SELECTOR, "input[type='submit'], button[type='submit']"
                    )
                    for button in submit_buttons:
                        print(f"📝 AI 지시에 따른 폼 제출: {button.text}")
                        button.click()
                        time.sleep(2)
                        return {
                            "success": True,
                            "message": "AI 지시에 따른 폼 제출 완료",
                        }

            return {"success": False, "message": "AI 지시를 실행할 수 없습니다"}

        except Exception as e:
            return {"success": False, "message": f"AI 지시 실행 실패: {str(e)}"}

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
        }

    def _log_memory_usage(self, context: str = ""):
        """메모리 사용량 로깅"""
        try:
            import psutil

            process = psutil.Process()
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024
            print(f"📊 메모리 사용량 ({context}): {memory_mb:.1f} MB")
            self.logger.info(f"메모리 사용량 ({context}): {memory_mb:.1f} MB")
        except ImportError:
            print(f"📊 메모리 모니터링 불가 ({context})")
        except Exception as e:
            print(f"⚠️ 메모리 모니터링 오류: {str(e)}")

    def _cleanup_driver(self):
        """드라이버 정리 및 메모리 해제"""
        if self.driver:
            try:
                self.driver.quit()
                print("🧹 Chrome 드라이버 정리 완료")
            except Exception as e:
                print(f"⚠️ 드라이버 정리 중 오류: {str(e)}")
            finally:
                self.driver = None

        # 가비지 컬렉션 강제 실행
        import gc

        gc.collect()
        self._log_memory_usage("드라이버 정리 후")

    def _check_memory_limit(self) -> bool:
        """메모리 제한 체크"""
        try:
            import psutil

            process = psutil.Process()
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024

            # 500MB 제한 (Render 무료 플랜 기준)
            if memory_mb > 500:
                print(f"⚠️ 메모리 사용량 초과: {memory_mb:.1f} MB")
                return False
            return True
        except:
            return True  # 모니터링 불가시 계속 진행
