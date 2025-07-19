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
        unsubscribe_links = []

        # 1. 이메일 헤더에서 List-Unsubscribe 필드 확인
        if email_headers:
            list_unsubscribe = email_headers.get("List-Unsubscribe", "")
            if list_unsubscribe:
                # 여러 링크가 있을 수 있음 (쉼표로 구분)
                links = [link.strip() for link in list_unsubscribe.split(",")]
                unsubscribe_links.extend(links)

        # 2. 이메일 본문에서 구독해지 링크 패턴 검색
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

        for pattern in patterns:
            matches = re.findall(pattern, email_content, re.IGNORECASE)
            unsubscribe_links.extend(matches)

        # 3. HTML 태그에서 링크 추출
        soup = BeautifulSoup(email_content, "html.parser")
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
                    break

        # 중복 제거 및 유효한 URL만 필터링
        valid_links = []
        for link in set(unsubscribe_links):
            if self._is_valid_unsubscribe_url(link):
                valid_links.append(link)

        return valid_links

    def _is_valid_unsubscribe_url(self, url: str) -> bool:
        """유효한 구독해지 URL인지 확인"""
        try:
            parsed = urlparse(url)
            return parsed.scheme in ["http", "https"] and parsed.netloc
        except:
            return False

    def process_unsubscribe_with_selenium(self, unsubscribe_url: str) -> Dict:
        """Selenium을 사용한 고급 구독해지 처리"""
        result = {"success": False, "message": "", "steps": []}

        try:
            if not self.setup_driver():
                result["message"] = "브라우저 드라이버 설정 실패"
                return result

            self.logger.info(f"구독해지 페이지 접속: {unsubscribe_url}")
            result["steps"].append(f"페이지 접속: {unsubscribe_url}")

            # 페이지 로드
            self.driver.get(unsubscribe_url)
            time.sleep(3)  # 페이지 로딩 대기

            # 구독해지 버튼/링크 찾기 및 클릭
            unsubscribe_found = self._find_and_click_unsubscribe_elements()

            if unsubscribe_found:
                result["success"] = True
                result["message"] = "구독해지가 성공적으로 처리되었습니다"
                result["steps"].append("구독해지 버튼 클릭 완료")
            else:
                result["message"] = "구독해지 버튼을 찾을 수 없습니다"
                result["steps"].append("구독해지 버튼을 찾을 수 없음")

        except TimeoutException:
            result["message"] = "페이지 로딩 시간 초과"
            result["steps"].append("페이지 로딩 시간 초과")
        except Exception as e:
            result["message"] = f"구독해지 처리 중 오류: {str(e)}"
            result["steps"].append(f"오류 발생: {str(e)}")
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
        """폼 제출 시도"""
        try:
            # 구독해지 관련 폼 찾기
            forms = self.driver.find_elements(By.TAG_NAME, "form")

            for form in forms:
                form_html = form.get_attribute("innerHTML").lower()

                # 구독해지 관련 키워드가 포함된 폼
                unsubscribe_keywords = ["unsubscribe", "opt-out", "cancel", "구독해지"]
                if any(keyword in form_html for keyword in unsubscribe_keywords):

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

    def process_unsubscribe_simple(self, unsubscribe_url: str) -> Dict:
        """간단한 구독해지 처리 (requests 사용)"""
        result = {"success": False, "message": "", "steps": []}

        try:
            # 페이지 접속
            response = requests.get(unsubscribe_url, timeout=10)
            response.raise_for_status()

            result["steps"].append(f"페이지 접속: {unsubscribe_url}")

            # HTML 파싱
            soup = BeautifulSoup(response.content, "html.parser")

            # 구독해지 링크 찾기
            unsubscribe_link = self._find_unsubscribe_link_simple(soup)

            if unsubscribe_link:
                # 구독해지 링크 클릭
                if unsubscribe_link.startswith("http"):
                    final_url = unsubscribe_link
                else:
                    final_url = urljoin(unsubscribe_url, unsubscribe_link)

                requests.get(final_url, timeout=10)
                result["success"] = True
                result["message"] = "구독해지가 성공적으로 처리되었습니다"
                result["steps"].append("구독해지 링크 클릭 완료")
            else:
                result["message"] = "구독해지 링크를 찾을 수 없습니다"
                result["steps"].append("구독해지 링크를 찾을 수 없음")

        except Exception as e:
            result["message"] = f"구독해지 처리 중 오류: {str(e)}"
            result["steps"].append(f"오류 발생: {str(e)}")

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
        # 구독해지 링크 추출
        unsubscribe_links = self.extract_unsubscribe_links(email_content, email_headers)

        if not unsubscribe_links:
            return {
                "success": False,
                "message": "구독해지 링크를 찾을 수 없습니다",
                "steps": ["구독해지 링크 추출 실패"],
            }

        # 첫 번째 링크로 시도
        unsubscribe_url = unsubscribe_links[0]

        # 먼저 간단한 방법 시도
        result = self.process_unsubscribe_simple(unsubscribe_url)

        # 간단한 방법이 실패하면 Selenium 사용
        if not result["success"]:
            self.logger.info("간단한 방법 실패, Selenium 사용")
            result = self.process_unsubscribe_with_selenium(unsubscribe_url)

        return result
