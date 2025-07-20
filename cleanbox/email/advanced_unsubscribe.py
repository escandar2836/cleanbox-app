# Standard library imports
import logging
import re
import time
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
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service


class AdvancedUnsubscribeService:
    """고급 구독해지 서비스"""

    def __init__(self):
        self.driver = None
        self.setup_logging()

    def setup_logging(self):
        """로깅 설정"""
        logging.basicConfig(
            level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
        )
        self.logger = logging.getLogger(__name__)

    def setup_driver(self, headless: bool = True):
        """Selenium 드라이버 설정"""
        try:
            chrome_options = Options()
            if headless:
                chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument(
                "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )

            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            self.driver.set_page_load_timeout(30)
            return True
        except Exception as e:
            self.logger.error(f"드라이버 설정 실패: {str(e)}")
            return False

    def close_driver(self):
        """드라이버 종료"""
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                self.logger.error(f"드라이버 종료 실패: {str(e)}")

    def extract_unsubscribe_links(
        self, email_content: str, email_headers: Dict = None
    ) -> List[str]:
        """이메일에서 구독해지 링크 추출 (고급)"""
        print(f"🔍 extract_unsubscribe_links 시작")
        unsubscribe_links = []

        # 1. 이메일 헤더에서 List-Unsubscribe 필드 확인
        if email_headers:
            list_unsubscribe = email_headers.get("List-Unsubscribe", "")
            print(f"📝 List-Unsubscribe 헤더: {list_unsubscribe}")
            if list_unsubscribe:
                # 여러 링크가 있을 수 있음 (쉼표로 구분)
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

            # 구독해지 관련 텍스트가 포함된 링크
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

    def process_unsubscribe_with_selenium(self, unsubscribe_url: str) -> Dict:
        """Selenium을 사용한 고급 구독해지 처리 (재시도 로직 포함)"""
        result = {"success": False, "message": "", "steps": []}
        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                if not self.setup_driver():
                    result["message"] = "브라우저 드라이버 설정 실패"
                    return result

                self.logger.info(
                    f"구독해지 페이지 접속 (시도 {retry_count + 1}/{max_retries}): {unsubscribe_url}"
                )
                result["steps"].append(
                    f"페이지 접속 (시도 {retry_count + 1}): {unsubscribe_url}"
                )

                # 페이지 로드
                self.driver.get(unsubscribe_url)
                time.sleep(3)  # 페이지 로딩 대기

                # 구독해지 버튼/링크 찾기 및 클릭
                unsubscribe_found = self._find_and_click_unsubscribe_elements()

                if unsubscribe_found:
                    result["success"] = True
                    result["message"] = "구독해지가 성공적으로 처리되었습니다"
                    result["steps"].append("구독해지 버튼 클릭 완료")
                    break
                else:
                    result["message"] = "구독해지 버튼을 찾을 수 없습니다"
                    result["steps"].append("구독해지 버튼을 찾을 수 없음")

                    # 재시도 전 대기
                    if retry_count < max_retries - 1:
                        time.sleep(2)
                        retry_count += 1
                        continue
                    else:
                        break

            except TimeoutException:
                result["message"] = "페이지 로딩 시간 초과"
                result["steps"].append(
                    f"페이지 로딩 시간 초과 (시도 {retry_count + 1})"
                )

                if retry_count < max_retries - 1:
                    retry_count += 1
                    time.sleep(2)
                    continue
                else:
                    break

            except Exception as e:
                result["message"] = f"구독해지 처리 중 오류: {str(e)}"
                result["steps"].append(f"오류 발생 (시도 {retry_count + 1}): {str(e)}")

                if retry_count < max_retries - 1:
                    retry_count += 1
                    time.sleep(2)
                    continue
                else:
                    break
            finally:
                self.close_driver()

        return result

    def _find_and_click_unsubscribe_elements(self) -> bool:
        """구독해지 요소 찾기 및 클릭"""
        unsubscribe_selectors = [
            # 버튼
            "button[contains(text(), 'Unsubscribe')]",
            "button[contains(text(), '구독해지')]",
            "button[contains(text(), 'Cancel')]",
            "button[contains(text(), 'Remove')]",
            "button[contains(text(), 'Opt-out')]",
            # 링크
            "a[contains(text(), 'Unsubscribe')]",
            "a[contains(text(), '구독해지')]",
            "a[contains(text(), 'Cancel')]",
            "a[contains(text(), 'Remove')]",
            "a[contains(text(), 'Opt-out')]",
            # input 버튼
            "input[value*='Unsubscribe']",
            "input[value*='구독해지']",
            "input[value*='Cancel']",
            # 일반적인 클래스명
            ".unsubscribe",
            ".opt-out",
            ".cancel",
            ".remove",
            "[class*='unsubscribe']",
            "[class*='opt-out']",
            # ID 기반
            "#unsubscribe",
            "#opt-out",
            "#cancel",
        ]

        for selector in unsubscribe_selectors:
            try:
                # 요소 찾기
                element = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                )

                # 스크롤하여 요소가 보이도록
                self.driver.execute_script(
                    "arguments[0].scrollIntoView(true);", element
                )
                time.sleep(1)

                # 클릭
                element.click()
                self.logger.info(f"구독해지 요소 클릭: {selector}")

                # 클릭 후 페이지 변화 대기
                time.sleep(3)

                return True

            except (TimeoutException, NoSuchElementException):
                continue

        # 폼 제출 시도
        return self._try_form_submission()

    def _try_form_submission(self) -> bool:
        """폼 제출 시도 (AI 에이전트 기능 강화)"""
        try:
            # 구독해지 관련 폼 찾기
            forms = self.driver.find_elements(By.TAG_NAME, "form")

            for form in forms:
                form_html = form.get_attribute("innerHTML").lower()

                # 구독해지 관련 키워드가 포함된 폼
                unsubscribe_keywords = ["unsubscribe", "opt-out", "cancel", "구독해지"]
                if any(keyword in form_html for keyword in unsubscribe_keywords):

                    # AI 에이전트: 폼 필드 자동 작성
                    self._fill_form_fields_ai(form)

                    # 폼 내의 submit 버튼 찾기
                    submit_buttons = form.find_elements(
                        By.CSS_SELECTOR,
                        "input[type='submit'], button[type='submit'], button",
                    )

                    for button in submit_buttons:
                        button_text = button.text.lower()
                        if any(
                            keyword in button_text for keyword in unsubscribe_keywords
                        ):
                            button.click()
                            time.sleep(3)
                            self.logger.info("구독해지 폼 제출 완료")
                            return True

        except Exception as e:
            self.logger.error(f"폼 제출 시도 실패: {str(e)}")

        return False

    def _fill_form_fields_ai(self, form) -> None:
        """AI 에이전트: 폼 필드 자동 작성"""
        try:
            # CSRF 토큰 자동 처리
            self._handle_csrf_token(form)

            # 이메일 입력 필드 찾기 및 작성
            email_inputs = form.find_elements(
                By.CSS_SELECTOR,
                "input[type='email'], input[name*='email'], input[placeholder*='email'], input[id*='email']",
            )

            for email_input in email_inputs:
                if not email_input.get_attribute("value"):
                    # 이메일 주소 추출 시도 (현재는 기본값 사용)
                    email_input.send_keys("user@example.com")
                    self.logger.info("이메일 필드 자동 작성")

            # 체크박스 처리 (구독해지 관련)
            checkboxes = form.find_elements(By.CSS_SELECTOR, "input[type='checkbox']")

            for checkbox in checkboxes:
                checkbox_name = checkbox.get_attribute("name") or ""
                checkbox_id = checkbox.get_attribute("id") or ""
                checkbox_value = checkbox.get_attribute("value") or ""

                # 구독해지 관련 체크박스 자동 체크
                if any(
                    keyword in (checkbox_name + checkbox_id + checkbox_value).lower()
                    for keyword in [
                        "unsubscribe",
                        "opt-out",
                        "cancel",
                        "구독해지",
                        "remove",
                    ]
                ):
                    if not checkbox.is_selected():
                        checkbox.click()
                        self.logger.info(
                            f"구독해지 체크박스 자동 체크: {checkbox_name}"
                        )

            # 라디오 버튼 처리
            radio_buttons = form.find_elements(By.CSS_SELECTOR, "input[type='radio']")

            for radio in radio_buttons:
                radio_name = radio.get_attribute("name") or ""
                radio_value = radio.get_attribute("value") or ""

                # 구독해지 관련 라디오 버튼 선택
                if any(
                    keyword in (radio_name + radio_value).lower()
                    for keyword in [
                        "unsubscribe",
                        "opt-out",
                        "cancel",
                        "구독해지",
                        "remove",
                    ]
                ):
                    radio.click()
                    self.logger.info(f"구독해지 라디오 버튼 선택: {radio_name}")

            # 드롭다운 처리
            select_elements = form.find_elements(By.TAG_NAME, "select")

            for select in select_elements:
                select_name = select.get_attribute("name") or ""

                # 구독해지 관련 드롭다운 처리
                if any(
                    keyword in select_name.lower()
                    for keyword in [
                        "unsubscribe",
                        "opt-out",
                        "cancel",
                        "구독해지",
                        "remove",
                    ]
                ):
                    try:
                        from selenium.webdriver.support.ui import Select

                        select_obj = Select(select)

                        # 구독해지 관련 옵션 찾기
                        for option in select_obj.options:
                            option_text = option.text.lower()
                            if any(
                                keyword in option_text
                                for keyword in [
                                    "unsubscribe",
                                    "opt-out",
                                    "cancel",
                                    "구독해지",
                                    "remove",
                                ]
                            ):
                                select_obj.select_by_visible_text(option.text)
                                self.logger.info(
                                    f"구독해지 드롭다운 선택: {option.text}"
                                )
                                break
                    except Exception as e:
                        self.logger.warning(f"드롭다운 처리 실패: {str(e)}")

            # 텍스트 입력 필드 처리 (이름, 이유 등)
            text_inputs = form.find_elements(
                By.CSS_SELECTOR, "input[type='text'], textarea"
            )

            for text_input in text_inputs:
                input_name = text_input.get_attribute("name") or ""
                input_placeholder = text_input.get_attribute("placeholder") or ""

                # 이름 필드
                if any(
                    keyword in (input_name + input_placeholder).lower()
                    for keyword in ["name", "이름", "name"]
                ):
                    if not text_input.get_attribute("value"):
                        text_input.send_keys("User")
                        self.logger.info("이름 필드 자동 작성")

                # 이유 필드
                elif any(
                    keyword in (input_name + input_placeholder).lower()
                    for keyword in ["reason", "comment", "이유", "comment"]
                ):
                    if not text_input.get_attribute("value"):
                        text_input.send_keys("No longer interested")
                        self.logger.info("이유 필드 자동 작성")

        except Exception as e:
            self.logger.error(f"폼 필드 자동 작성 실패: {str(e)}")

    def _handle_csrf_token(self, form) -> None:
        """CSRF 토큰 자동 처리"""
        try:
            # CSRF 토큰 필드 찾기
            csrf_inputs = form.find_elements(
                By.CSS_SELECTOR,
                "input[name*='csrf'], input[name*='token'], input[name*='_token'], input[type='hidden']",
            )

            for csrf_input in csrf_inputs:
                input_name = csrf_input.get_attribute("name") or ""
                input_value = csrf_input.get_attribute("value") or ""

                # CSRF 토큰이 비어있으면 페이지에서 찾기
                if not input_value and any(
                    keyword in input_name.lower()
                    for keyword in ["csrf", "token", "_token"]
                ):
                    # 페이지에서 CSRF 토큰 찾기
                    page_csrf = self.driver.find_elements(
                        By.CSS_SELECTOR,
                        "meta[name='csrf-token'], input[name*='csrf'], input[name*='token']",
                    )

                    for meta in page_csrf:
                        token_value = meta.get_attribute(
                            "content"
                        ) or meta.get_attribute("value")
                        if token_value:
                            csrf_input.send_keys(token_value)
                            self.logger.info("CSRF 토큰 자동 설정")
                            break

        except Exception as e:
            self.logger.warning(f"CSRF 토큰 처리 실패: {str(e)}")

    def process_unsubscribe_simple(self, unsubscribe_url: str) -> Dict:
        """간단한 구독해지 처리 (requests 사용)"""
        print(f"🔍 process_unsubscribe_simple 시작: {unsubscribe_url}")
        result = {"success": False, "message": "", "steps": []}

        try:
            # 페이지 접속
            print(f"📝 페이지 접속 시도: {unsubscribe_url}")
            response = requests.get(unsubscribe_url, timeout=10)
            response.raise_for_status()
            print(f"✅ 페이지 접속 성공 - 상태 코드: {response.status_code}")

            result["steps"].append(f"페이지 접속: {unsubscribe_url}")

            # HTML 파싱
            print(f"📝 HTML 파싱 시작")
            soup = BeautifulSoup(response.content, "html.parser")
            print(f"✅ HTML 파싱 완료")

            # 구독해지 링크 찾기
            print(f"📝 구독해지 링크 검색 시작")
            unsubscribe_link = self._find_unsubscribe_link_simple(soup)
            print(f"📝 찾은 구독해지 링크: {unsubscribe_link}")

            if unsubscribe_link:
                # 구독해지 링크 클릭
                if unsubscribe_link.startswith("http"):
                    final_url = unsubscribe_link
                else:
                    final_url = urljoin(unsubscribe_url, unsubscribe_link)

                print(f"📝 최종 구독해지 URL: {final_url}")
                print(f"📝 구독해지 링크 클릭 시도")

                requests.get(final_url, timeout=10)
                result["success"] = True
                result["message"] = "구독해지가 성공적으로 처리되었습니다"
                result["steps"].append("구독해지 링크 클릭 완료")
                print(f"✅ 구독해지 링크 클릭 성공")
            else:
                result["message"] = "구독해지 링크를 찾을 수 없습니다"
                result["steps"].append("구독해지 링크를 찾을 수 없음")
                print(f"❌ 구독해지 링크를 찾을 수 없음")

        except Exception as e:
            result["message"] = f"구독해지 처리 중 오류: {str(e)}"
            result["steps"].append(f"오류 발생: {str(e)}")
            print(f"❌ process_unsubscribe_simple 예외 발생: {str(e)}")

        print(f"📝 process_unsubscribe_simple 결과: {result}")
        return result

    def _find_unsubscribe_link_simple(self, soup: BeautifulSoup) -> Optional[str]:
        """간단한 구독해지 링크 찾기"""
        unsubscribe_texts = [
            "unsubscribe",
            "opt-out",
            "remove",
            "cancel",
            "구독해지",
            "구독취소",
            "수신거부",
            "수신취소",
        ]

        for text in unsubscribe_texts:
            # 텍스트가 포함된 링크 찾기
            link = soup.find("a", string=re.compile(text, re.IGNORECASE))
            if link and link.get("href"):
                return link["href"]

            # 텍스트가 포함된 버튼 찾기 (onclick은 제외)
            button = soup.find("button", string=re.compile(text, re.IGNORECASE))
            if button and button.get("href"):  # href 속성이 있는 경우만
                return button["href"]

        return None

    def process_unsubscribe_advanced(
        self, email_content: str, email_headers: Dict = None
    ) -> Dict:
        """고급 구독해지 처리 (자동 방법 선택)"""
        print(f"🔍 AdvancedUnsubscribeService.process_unsubscribe_advanced 시작")
        print(f"📝 이메일 내용 길이: {len(email_content)}")
        print(f"📝 이메일 헤더: {email_headers}")

        result = {"success": False, "message": "", "steps": [], "progress": 0}

        # 1단계: 구독해지 링크 추출
        result["steps"].append("🔍 이메일에서 구독해지 링크 검색 중...")
        result["progress"] = 10
        print(f"📝 구독해지 링크 추출 시작")

        unsubscribe_links = self.extract_unsubscribe_links(email_content, email_headers)
        print(f"📝 추출된 링크 수: {len(unsubscribe_links)}")
        if unsubscribe_links:
            print(f"📝 추출된 링크들: {unsubscribe_links}")

        if not unsubscribe_links:
            result["message"] = "구독해지 링크를 찾을 수 없습니다"
            result["steps"].append("❌ 구독해지 링크 추출 실패")
            result["progress"] = 100
            print(f"❌ 구독해지 링크를 찾을 수 없음")
            return result

        result["steps"].append(f"✅ 구독해지 링크 {len(unsubscribe_links)}개 발견")
        result["progress"] = 20
        print(f"✅ 구독해지 링크 {len(unsubscribe_links)}개 발견")

        # 모든 링크에 대해 시도
        for i, unsubscribe_url in enumerate(unsubscribe_links):
            progress_per_link = 70 // len(unsubscribe_links)  # 70%를 링크 수로 나눔
            current_progress = 20 + (i * progress_per_link)

            result["steps"].append(
                f"🌐 링크 {i + 1}/{len(unsubscribe_links)} 처리 중: {unsubscribe_url[:50]}..."
            )
            result["progress"] = current_progress

            print(
                f"📝 링크 {i + 1}/{len(unsubscribe_links)} 처리 시작: {unsubscribe_url}"
            )
            self.logger.info(
                f"구독해지 링크 시도 ({i + 1}/{len(unsubscribe_links)}): {unsubscribe_url}"
            )

            # 웹사이트별 특별 처리
            result["steps"].append("🔧 웹사이트별 특별 처리 시도...")
            print(f"📝 웹사이트별 특별 처리 시도: {unsubscribe_url}")
            website_specific_result = self._handle_website_specific_logic(
                unsubscribe_url
            )
            print(f"📝 웹사이트별 처리 결과: {website_specific_result}")

            if website_specific_result["success"]:
                print(f"✅ 웹사이트별 처리 성공")
                result["steps"].extend(website_specific_result["steps"])
                result["success"] = True
                result["message"] = website_specific_result["message"]
                result["progress"] = 100
                return result

            # 먼저 간단한 방법 시도
            result["steps"].append("📡 간단한 HTTP 요청 시도...")
            print(f"📝 간단한 HTTP 요청 시도: {unsubscribe_url}")
            simple_result = self.process_unsubscribe_simple(unsubscribe_url)
            print(f"📝 간단한 HTTP 요청 결과: {simple_result}")

            # 간단한 방법이 실패하면 Selenium 사용
            if not simple_result["success"]:
                result["steps"].append("🤖 Selenium 브라우저 자동화 시도...")
                print(f"📝 Selenium 브라우저 자동화 시도: {unsubscribe_url}")
                simple_result = self.process_unsubscribe_with_selenium(unsubscribe_url)
                print(f"📝 Selenium 처리 결과: {simple_result}")

            if simple_result["success"]:
                print(f"✅ 링크 {i + 1} 처리 성공")
                result["steps"].extend(simple_result["steps"])
                result["success"] = True
                result["message"] = simple_result["message"]
                result["progress"] = 100
                return result
            else:
                print(
                    f"❌ 링크 {i + 1} 처리 실패: {simple_result.get('message', '알 수 없는 오류')}"
                )
                result["steps"].append(f"❌ 링크 {i + 1} 처리 실패")

        # 모든 링크 실패
        result["steps"].append("❌ 모든 구독해지 링크에서 실패했습니다")
        result["message"] = "모든 구독해지 링크에서 실패했습니다"
        result["progress"] = 100
        return result

    def _handle_website_specific_logic(self, url: str) -> Dict:
        """웹사이트별 특별 처리 로직"""
        try:
            from urllib.parse import urlparse

            parsed_url = urlparse(url)
            domain = parsed_url.netloc.lower()

            # 특정 웹사이트별 처리
            if "mailchimp" in domain:
                return self._handle_mailchimp_unsubscribe(url)
            elif "sendgrid" in domain:
                return self._handle_sendgrid_unsubscribe(url)
            elif "mailgun" in domain:
                return self._handle_mailgun_unsubscribe(url)
            elif "amazon" in domain:
                return self._handle_amazon_unsubscribe(url)
            elif "google" in domain:
                return self._handle_google_unsubscribe(url)

            # 기본 처리
            return {"success": False, "message": "", "steps": []}

        except Exception as e:
            self.logger.warning(f"웹사이트별 처리 실패: {str(e)}")
            return {"success": False, "message": "", "steps": []}

    def _handle_mailchimp_unsubscribe(self, url: str) -> Dict:
        """Mailchimp 구독해지 처리"""
        try:
            if not self.setup_driver():
                return {"success": False, "message": "드라이버 설정 실패", "steps": []}

            self.driver.get(url)
            time.sleep(3)

            # Mailchimp 특정 요소 찾기
            unsubscribe_button = self.driver.find_element(
                By.CSS_SELECTOR, "button[data-testid='unsubscribe-button']"
            )
            if unsubscribe_button:
                unsubscribe_button.click()
                time.sleep(2)

                # 확인 버튼 클릭
                confirm_button = self.driver.find_element(
                    By.CSS_SELECTOR, "button[data-testid='confirm-button']"
                )
                if confirm_button:
                    confirm_button.click()
                    time.sleep(2)

                    return {
                        "success": True,
                        "message": "Mailchimp 구독해지 완료",
                        "steps": [
                            "Mailchimp 페이지 접속",
                            "구독해지 버튼 클릭",
                            "확인 버튼 클릭",
                        ],
                    }

            return {"success": False, "message": "Mailchimp 구독해지 실패", "steps": []}

        except Exception as e:
            return {
                "success": False,
                "message": f"Mailchimp 처리 오류: {str(e)}",
                "steps": [],
            }
        finally:
            self.close_driver()

    def _handle_sendgrid_unsubscribe(self, url: str) -> Dict:
        """SendGrid 구독해지 처리"""
        try:
            if not self.setup_driver():
                return {"success": False, "message": "드라이버 설정 실패", "steps": []}

            self.driver.get(url)
            time.sleep(3)

            # SendGrid 특정 요소 찾기
            unsubscribe_link = self.driver.find_element(
                By.CSS_SELECTOR, "a[href*='unsubscribe']"
            )
            if unsubscribe_link:
                unsubscribe_link.click()
                time.sleep(2)

                return {
                    "success": True,
                    "message": "SendGrid 구독해지 완료",
                    "steps": ["SendGrid 페이지 접속", "구독해지 링크 클릭"],
                }

            return {"success": False, "message": "SendGrid 구독해지 실패", "steps": []}

        except Exception as e:
            return {
                "success": False,
                "message": f"SendGrid 처리 오류: {str(e)}",
                "steps": [],
            }
        finally:
            self.close_driver()

    def _handle_mailgun_unsubscribe(self, url: str) -> Dict:
        """Mailgun 구독해지 처리"""
        try:
            if not self.setup_driver():
                return {"success": False, "message": "드라이버 설정 실패", "steps": []}

            self.driver.get(url)
            time.sleep(3)

            # Mailgun 특정 요소 찾기
            unsubscribe_button = self.driver.find_element(
                By.CSS_SELECTOR, "button[type='submit']"
            )
            if unsubscribe_button:
                unsubscribe_button.click()
                time.sleep(2)

                return {
                    "success": True,
                    "message": "Mailgun 구독해지 완료",
                    "steps": ["Mailgun 페이지 접속", "구독해지 버튼 클릭"],
                }

            return {"success": False, "message": "Mailgun 구독해지 실패", "steps": []}

        except Exception as e:
            return {
                "success": False,
                "message": f"Mailgun 처리 오류: {str(e)}",
                "steps": [],
            }
        finally:
            self.close_driver()

    def _handle_amazon_unsubscribe(self, url: str) -> Dict:
        """Amazon 구독해지 처리"""
        try:
            if not self.setup_driver():
                return {"success": False, "message": "드라이버 설정 실패", "steps": []}

            self.driver.get(url)
            time.sleep(3)

            # Amazon 특정 요소 찾기
            unsubscribe_button = self.driver.find_element(
                By.CSS_SELECTOR, "input[type='submit'][value*='Unsubscribe']"
            )
            if unsubscribe_button:
                unsubscribe_button.click()
                time.sleep(2)

                return {
                    "success": True,
                    "message": "Amazon 구독해지 완료",
                    "steps": ["Amazon 페이지 접속", "구독해지 버튼 클릭"],
                }

            return {"success": False, "message": "Amazon 구독해지 실패", "steps": []}

        except Exception as e:
            return {
                "success": False,
                "message": f"Amazon 처리 오류: {str(e)}",
                "steps": [],
            }
        finally:
            self.close_driver()

    def _handle_google_unsubscribe(self, url: str) -> Dict:
        """Google 구독해지 처리"""
        try:
            if not self.setup_driver():
                return {"success": False, "message": "드라이버 설정 실패", "steps": []}

            self.driver.get(url)
            time.sleep(3)

            # Google 특정 요소 찾기
            unsubscribe_button = self.driver.find_element(
                By.CSS_SELECTOR, "button[aria-label*='Unsubscribe']"
            )
            if unsubscribe_button:
                unsubscribe_button.click()
                time.sleep(2)

                return {
                    "success": True,
                    "message": "Google 구독해지 완료",
                    "steps": ["Google 페이지 접속", "구독해지 버튼 클릭"],
                }

            return {"success": False, "message": "Google 구독해지 실패", "steps": []}

        except Exception as e:
            return {
                "success": False,
                "message": f"Google 처리 오류: {str(e)}",
                "steps": [],
            }
        finally:
            self.close_driver()
