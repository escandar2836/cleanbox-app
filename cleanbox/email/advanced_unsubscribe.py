# Standard library imports
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
import mechanicalsoup


class AdvancedUnsubscribeService:
    """고급 구독해지 서비스"""

    def __init__(self):
        self.setup_logging()

        # 타임아웃 설정
        self.timeouts = {
            "page_load": 30,
            "element_wait": 10,
            "api_call": 15,
            "retry_delay": 2,
        }

    def setup_logging(self):
        """로깅 설정"""
        logging.basicConfig(
            level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
        )
        self.logger = logging.getLogger(__name__)

        # 파일 로깅 추가
        file_handler = logging.FileHandler("logs/unsubscribe_service.log")
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

    def _detect_personal_email(
        self, email_content: str, email_headers: Dict = None
    ) -> bool:
        """개인 이메일 감지"""
        try:
            # 1. 발신자 도메인 확인
            if email_headers:
                from_header = email_headers.get("From", "").lower()
                personal_domains = [
                    "gmail.com",
                    "naver.com",
                    "daum.net",
                    "outlook.com",
                    "hotmail.com",
                    "yahoo.com",
                    "icloud.com",
                    "me.com",
                ]

                for domain in personal_domains:
                    if domain in from_header:
                        print(f"📝 개인 도메인 감지: {domain}")
                        return True

            # 2. 이메일 내용 분석
            content_lower = email_content.lower()

            # 마케팅 관련 키워드가 없는지 확인
            marketing_keywords = [
                "unsubscribe",
                "opt-out",
                "구독해지",
                "수신거부",
                "marketing",
                "promotion",
                "offer",
                "deal",
                "sale",
                "newsletter",
                "news letter",
                "email preferences",
                "manage subscription",
                "subscription settings",
            ]

            has_marketing_content = any(
                keyword in content_lower for keyword in marketing_keywords
            )

            # 개인적 내용 키워드 확인
            personal_keywords = [
                "hello",
                "hi",
                "dear",
                "안녕하세요",
                "안녕",
                "best regards",
                "sincerely",
                "감사합니다",
                "고맙습니다",
                "personal",
                "private",
                "개인",
            ]

            has_personal_content = any(
                keyword in content_lower for keyword in personal_keywords
            )

            # 구독해지 링크가 없고 개인적 내용이 있으면 개인 이메일로 판단
            if not has_marketing_content and has_personal_content:
                print(f"📝 개인 이메일로 감지됨 (내용 분석)")
                return True

            return False

        except Exception as e:
            print(f"❌ 개인 이메일 감지 중 오류: {str(e)}")
            return False

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
        self, email_content: str, email_headers: Dict = None, user_email: str = None
    ) -> Dict:
        """고급 구독해지 처리 (MechanicalSoup + AI만 사용)"""
        print(f"🔍 AdvancedUnsubscribeService.process_unsubscribe_advanced 시작")
        print(f"📝 이메일 내용 길이: {len(email_content)}")
        print(f"📝 이메일 헤더: {email_headers}")
        print(f"📝 사용자 이메일: {user_email}")

        result = {
            "success": False,
            "message": "",
            "steps": [],
            "progress": 0,
            "error_type": None,
            "error_details": None,
            "is_personal_email": False,
        }

        # 1단계: 개인 이메일 감지
        result["steps"].append("🔍 이메일 유형 분석 중...")
        result["progress"] = 5
        print(f"📝 개인 이메일 감지 시작")

        is_personal = self._detect_personal_email(email_content, email_headers)
        result["is_personal_email"] = is_personal
        print(f"📝 개인 이메일 여부: {is_personal}")

        if is_personal:
            result["steps"].append("📧 개인 이메일로 감지됨")
            result["message"] = (
                "이 이메일은 개인 발송자로 보입니다. 구독해지 링크가 없을 수 있습니다."
            )
            result["error_type"] = "personal_email"
            result["error_details"] = (
                "개인 이메일은 일반적으로 구독해지 기능이 없습니다."
            )
            result["progress"] = 100
            return result

        # 2단계: 구독해지 링크 추출
        result["steps"].append("🔍 이메일에서 구독해지 링크 검색 중...")
        result["progress"] = 15
        print(f"📝 구독해지 링크 추출 시작")

        unsubscribe_links = self.extract_unsubscribe_links(email_content, email_headers)
        print(f"📝 추출된 링크 수: {len(unsubscribe_links)}")
        if unsubscribe_links:
            print(f"📝 추출된 링크들: {unsubscribe_links}")

        if not unsubscribe_links:
            result["message"] = "구독해지 링크를 찾을 수 없습니다"
            result["error_type"] = "no_unsubscribe_link"
            result["error_details"] = (
                "이메일에서 구독해지 링크를 찾을 수 없습니다. 마케팅 이메일이 아니거나 링크가 숨겨져 있을 수 있습니다."
            )
            result["steps"].append("❌ 구독해지 링크 추출 실패")
            result["progress"] = 100
            print(f"❌ 구독해지 링크를 찾을 수 없음")
            return result

        result["steps"].append(f"✅ 구독해지 링크 {len(unsubscribe_links)}개 발견")
        result["progress"] = 20
        print(f"✅ 구독해지 링크 {len(unsubscribe_links)}개 발견")

        # 모든 링크에 대해 시도
        for i, unsubscribe_url in enumerate(unsubscribe_links):
            progress_per_link = 70 // len(unsubscribe_links)
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

            # 1단계: 간단한 HTTP 요청 시도
            result["steps"].append("🔧 간단한 HTTP 요청 시도...")
            print(f"📝 간단한 HTTP 요청 시도: {unsubscribe_url}")
            simple_result = self.process_unsubscribe_simple(unsubscribe_url)

            if simple_result["success"]:
                print(f"✅ 링크 {i + 1} 처리 성공 (간단한 HTTP)")
                result["steps"].extend(simple_result.get("steps", []))
                result["success"] = True
                result["message"] = simple_result["message"]
                result["progress"] = 100
                return result

            # 2단계: MechanicalSoup + AI 자동화 시도
            result["steps"].append("🤖 MechanicalSoup + AI 자동화 시도...")
            print(f"📝 MechanicalSoup + AI 자동화 시도: {unsubscribe_url}")
            mechanicalsoup_result = self.process_unsubscribe_with_mechanicalsoup_ai(
                unsubscribe_url, user_email
            )

            if mechanicalsoup_result["success"]:
                print(f"✅ 링크 {i + 1} 처리 성공 (MechanicalSoup + AI)")
                result["steps"].extend(mechanicalsoup_result.get("steps", []))
                result["success"] = True
                result["message"] = mechanicalsoup_result["message"]
                result["progress"] = 100
                return result

            # 모든 방법이 실패한 경우
            error_msg = mechanicalsoup_result.get("message", "알 수 없는 오류")
            print(f"❌ 링크 {i + 1} 처리 실패: {error_msg}")
            result["steps"].append(f"❌ 링크 {i + 1} 처리 실패: {error_msg}")

            # 실패한 링크 정보 저장
            if "failed_links" not in result:
                result["failed_links"] = []
            result["failed_links"].append(
                {"url": unsubscribe_url, "error": error_msg, "link_number": i + 1}
            )

        # 모든 링크 실패
        result["steps"].append("❌ 모든 구독해지 링크에서 실패했습니다")
        result["message"] = (
            "모든 구독해지 링크에서 실패했습니다. 수동으로 구독해지하시거나 나중에 다시 시도해주세요."
        )
        result["error_type"] = "all_links_failed"
        result["error_details"] = (
            f"총 {len(unsubscribe_links)}개의 구독해지 링크를 시도했지만 모두 실패했습니다. 각 링크별 실패 이유를 확인해보세요."
        )
        result["progress"] = 100
        print(f"❌ 모든 구독해지 링크 실패 - 총 {len(unsubscribe_links)}개 링크 시도")
        return result

    # ==================== MechanicalSoup 기반 처리 함수들 ====================

    def process_unsubscribe_with_mechanicalsoup_ai(
        self, unsubscribe_url: str, user_email: str = None
    ) -> Dict:
        """MechanicalSoup + OpenAI API를 활용한 범용 구독해지 처리 (에러 처리 강화)"""
        start_time = time.time()

        # 로깅 시작
        self.log_unsubscribe_attempt(unsubscribe_url, user_email, start_time)

        max_retries = 2
        retry_count = 0

        while retry_count <= max_retries:
            try:
                print(
                    f"🔧 MechanicalSoup + AI 구독해지 시도 (시도 {retry_count + 1}/{max_retries + 1}): {unsubscribe_url}"
                )

                browser = mechanicalsoup.StatefulBrowser()
                browser.set_user_agent(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )

                # 타임아웃 설정
                browser.session.timeout = self.timeouts["page_load"]

                # 1단계: 초기 페이지 접속
                print(f"📝 1단계: 초기 페이지 접속")
                response = browser.open(unsubscribe_url)
                if not response.ok:
                    error_msg = f"페이지 접속 실패: HTTP {response.status_code}"
                    print(f"❌ {error_msg}")
                    if retry_count < max_retries:
                        retry_count += 1
                        print(f"🔄 재시도 {retry_count}/{max_retries}")
                        time.sleep(self.timeouts["retry_delay"])
                        continue
                    else:
                        processing_time = time.time() - start_time
                        result = {"success": False, "message": error_msg}
                        self.log_unsubscribe_result(
                            result, processing_time, unsubscribe_url
                        )
                        self.log_performance_metrics(
                            unsubscribe_url, "mechanicalsoup", processing_time, False
                        )
                        return result

                soup = browser.get_current_page()
                print(f"✅ 초기 페이지 접속 성공")

                # 2단계: 기본 구독해지 시도
                basic_result = self._try_basic_unsubscribe(browser, soup, user_email)
                if basic_result["success"]:
                    processing_time = time.time() - start_time
                    self.log_unsubscribe_result(
                        basic_result, processing_time, unsubscribe_url
                    )
                    self.log_performance_metrics(
                        unsubscribe_url, "mechanicalsoup", processing_time, True
                    )
                    return basic_result

                # 3단계: OpenAI API로 페이지 분석 및 처리
                print(f"📝 3단계: OpenAI API로 페이지 분석")
                ai_result = self._analyze_page_with_ai(browser, soup, user_email)

                # AI 분석 결과 로깅
                if "action" in ai_result:
                    self.log_ai_analysis(ai_result, unsubscribe_url)

                if ai_result["success"]:
                    processing_time = time.time() - start_time
                    self.log_unsubscribe_result(
                        ai_result, processing_time, unsubscribe_url
                    )
                    self.log_performance_metrics(
                        unsubscribe_url, "mechanicalsoup_ai", processing_time, True
                    )
                    return ai_result

                # 모든 방법 실패
                error_msg = "구독해지 요소를 찾을 수 없습니다"
                print(f"❌ {error_msg}")
                if retry_count < max_retries:
                    retry_count += 1
                    print(f"🔄 재시도 {retry_count}/{max_retries}")
                    time.sleep(self.timeouts["retry_delay"])
                    continue
                else:
                    processing_time = time.time() - start_time
                    result = {"success": False, "message": error_msg}
                    self.log_unsubscribe_result(
                        result, processing_time, unsubscribe_url
                    )
                    self.log_performance_metrics(
                        unsubscribe_url, "mechanicalsoup", processing_time, False
                    )
                    return result

            except Exception as e:
                error_msg = f"처리 오류: {str(e)}"
                print(f"❌ {error_msg}")
                if retry_count < max_retries:
                    retry_count += 1
                    print(f"🔄 재시도 {retry_count}/{max_retries}")
                    time.sleep(self.timeouts["retry_delay"])
                    continue
                else:
                    processing_time = time.time() - start_time
                    result = {"success": False, "message": error_msg}
                    self.log_unsubscribe_result(
                        result, processing_time, unsubscribe_url
                    )
                    self.log_performance_metrics(
                        unsubscribe_url, "mechanicalsoup", processing_time, False
                    )
                    return result

        processing_time = time.time() - start_time
        result = {"success": False, "message": "최대 재시도 횟수 초과"}
        self.log_unsubscribe_result(result, processing_time, unsubscribe_url)
        self.log_performance_metrics(
            unsubscribe_url, "mechanicalsoup", processing_time, False
        )
        return result

    def _try_basic_unsubscribe(self, browser, soup, user_email: str = None) -> Dict:
        """기본 구독해지 시도 (2단계 프로세스 지원)"""
        try:
            # 1. 구독해지 링크 찾기
            unsubscribe_links = []
            for link in soup.find_all("a", href=True):
                href = link.get("href", "").lower()
                text = link.get_text().lower()

                if any(
                    keyword in href or keyword in text
                    for keyword in [
                        "unsubscribe",
                        "구독해지",
                        "구독취소",
                        "수신거부",
                        "opt-out",
                        "remove",
                        "cancel",
                        "subscription",
                        "email preferences",
                        "manage subscription",
                        "subscription settings",
                        "email settings",
                        "preferences",
                        "settings",
                        "account",
                        "profile",
                        "수신취소",
                        "수신거부",
                        "이메일 설정",
                        "계정 설정",
                        "프로필",
                    ]
                ):
                    unsubscribe_links.append(link["href"])
                    print(f"📝 구독해지 링크 발견: {link['href']}")

            # 2. 링크 클릭 시도 (1단계)
            for link in unsubscribe_links:
                try:
                    if not link.startswith("http"):
                        link = urljoin(browser.get_url(), link)

                    print(f"📝 구독해지 링크 클릭 시도 (1단계): {link}")
                    response = browser.open(link)
                    if response.ok:
                        print(f"✅ 구독해지 링크 클릭 성공 (1단계)")

                        # 2단계: 추가 페이지에서 구독해지 시도
                        print(f"📝 2단계: 추가 페이지에서 구독해지 시도")
                        second_page_result = self._try_second_page_unsubscribe(
                            browser, user_email
                        )
                        if second_page_result["success"]:
                            return second_page_result
                        else:
                            # 1단계만 성공한 경우도 성공으로 처리
                            return {
                                "success": True,
                                "message": "구독해지 링크 클릭 완료 (1단계)",
                            }
                except Exception as e:
                    print(f"❌ 링크 클릭 실패: {str(e)}")
                    continue

            # 3. 폼 제출 시도
            forms = soup.find_all("form")
            for form in forms:
                try:
                    # 향상된 폼 필드 채우기
                    self._fill_form_fields_enhanced(form, user_email)

                    submit_buttons = form.find_all("input", type="submit")
                    for button in submit_buttons:
                        if any(
                            keyword in button.get("value", "").lower()
                            for keyword in [
                                "unsubscribe",
                                "구독해지",
                                "submit",
                                "confirm",
                            ]
                        ):
                            print(f"📝 구독해지 폼 제출 시도")
                            response = browser.submit(form, form.url)
                            if response.ok:
                                print(f"✅ 구독해지 폼 제출 성공")

                                # 2단계: 추가 페이지에서 구독해지 시도
                                print(f"📝 2단계: 추가 페이지에서 구독해지 시도")
                                second_page_result = self._try_second_page_unsubscribe(
                                    browser, user_email
                                )
                                if second_page_result["success"]:
                                    return second_page_result
                                else:
                                    return {
                                        "success": True,
                                        "message": "구독해지 폼 제출 완료 (1단계)",
                                    }
                except Exception as e:
                    print(f"❌ 폼 제출 실패: {str(e)}")
                    continue

            return {"success": False, "message": "기본 방법으로 구독해지 실패"}

        except Exception as e:
            return {"success": False, "message": f"기본 처리 오류: {str(e)}"}

    def _try_second_page_unsubscribe(self, browser, user_email: str = None) -> Dict:
        """2단계 페이지에서 구독해지 시도"""
        try:
            soup = browser.get_current_page()

            # 1. 구독해지 버튼 찾기
            unsubscribe_buttons = []
            for button in soup.find_all("button"):
                button_text = button.get_text().lower()
                if any(
                    keyword in button_text
                    for keyword in [
                        "unsubscribe",
                        "구독해지",
                        "구독취소",
                        "confirm",
                        "확인",
                        "취소",
                    ]
                ):
                    unsubscribe_buttons.append(button)
                    print(f"📝 2단계 구독해지 버튼 발견: {button_text}")

            # 2. 구독해지 링크 찾기
            unsubscribe_links = []
            for link in soup.find_all("a", href=True):
                link_text = link.get_text().lower()
                if any(
                    keyword in link_text
                    for keyword in [
                        "unsubscribe",
                        "구독해지",
                        "구독취소",
                        "confirm",
                        "확인",
                    ]
                ):
                    unsubscribe_links.append(link)
                    print(f"📝 2단계 구독해지 링크 발견: {link_text}")

            # 3. 버튼 클릭 시도
            for button in unsubscribe_buttons:
                try:
                    form = button.find_parent("form")
                    if form:
                        print(f"📝 2단계 구독해지 버튼 클릭 시도")
                        response = browser.submit(form, form.url)
                        if response.ok:
                            print(f"✅ 2단계 구독해지 버튼 클릭 성공")
                            return {"success": True, "message": "2단계 구독해지 완료"}
                except Exception as e:
                    print(f"❌ 2단계 버튼 클릭 실패: {str(e)}")
                    continue

            # 4. 링크 클릭 시도
            for link in unsubscribe_links:
                try:
                    href = link["href"]
                    if not href.startswith("http"):
                        href = urljoin(browser.get_url(), href)

                    print(f"📝 2단계 구독해지 링크 클릭 시도: {href}")
                    response = browser.open(href)
                    if response.ok:
                        print(f"✅ 2단계 구독해지 링크 클릭 성공")
                        return {"success": True, "message": "2단계 구독해지 완료"}
                except Exception as e:
                    print(f"❌ 2단계 링크 클릭 실패: {str(e)}")
                    continue

            # 5. 폼 제출 시도
            forms = soup.find_all("form")
            for form in forms:
                try:
                    if user_email:
                        email_inputs = form.find_all("input", type="email")
                        for email_input in email_inputs:
                            email_input["value"] = user_email

                    submit_buttons = form.find_all("input", type="submit")
                    for button in submit_buttons:
                        if any(
                            keyword in button.get("value", "").lower()
                            for keyword in [
                                "unsubscribe",
                                "구독해지",
                                "confirm",
                                "확인",
                            ]
                        ):
                            print(f"📝 2단계 구독해지 폼 제출 시도")
                            response = browser.submit(form, form.url)
                            if response.ok:
                                print(f"✅ 2단계 구독해지 폼 제출 성공")
                                return {
                                    "success": True,
                                    "message": "2단계 구독해지 완료",
                                }
                except Exception as e:
                    print(f"❌ 2단계 폼 제출 실패: {str(e)}")
                    continue

            return {
                "success": False,
                "message": "2단계 구독해지 요소를 찾을 수 없습니다",
            }

        except Exception as e:
            return {"success": False, "message": f"2단계 처리 오류: {str(e)}"}

    def _analyze_page_with_ai(self, browser, soup, user_email: str = None) -> Dict:
        """OpenAI API를 사용하여 페이지 분석 및 구독해지 처리"""
        try:
            print(f"🤖 OpenAI API로 페이지 분석 시작")

            # 페이지 정보 수집
            page_info = self._extract_page_info(soup)

            # AI 프롬프트 생성
            prompt = self._create_ai_prompt(page_info, user_email)

            # OpenAI API 호출
            api_response = self._call_openai_api(prompt)

            if not api_response["success"]:
                print(f"❌ OpenAI API 호출 실패: {api_response.get('message')}")
                return {
                    "success": False,
                    "message": api_response.get("message", "API 호출 실패"),
                }

            # AI 응답 파싱
            try:
                ai_response = json.loads(api_response["content"])
                print(f"🤖 AI 분석 결과: {ai_response}")
            except json.JSONDecodeError:
                print(f"❌ AI 응답 JSON 파싱 실패: {api_response['content']}")
                return {"success": False, "message": "AI 응답 파싱 실패"}

            # AI 지시사항 실행
            result = self._execute_ai_instructions(browser, ai_response, user_email)

            if result["success"]:
                print(f"✅ AI 지시사항 실행 성공")
                return result
            else:
                print(f"❌ AI 지시사항 실행 실패: {result.get('message')}")
                return result

        except Exception as e:
            error_msg = f"AI 분석 실패: {str(e)}"
            print(f"❌ {error_msg}")
            return {"success": False, "message": error_msg}

    def _extract_page_info(self, soup):
        """페이지 정보 수집"""
        page_info = {
            "url": "",
            "title": soup.find("title").get_text() if soup.find("title") else "",
            "forms": [],
            "buttons": [],
            "links": [],
            "text_content": "",
        }

        # 폼 정보 수집
        forms = soup.find_all("form")
        for form in forms:
            form_info = {
                "action": form.get("action", ""),
                "method": form.get("method", "get"),
                "inputs": [],
            }

            # 폼 내부 입력 필드들
            inputs = form.find_all("input")
            for input_field in inputs:
                input_info = {
                    "type": input_field.get("type", "text"),
                    "name": input_field.get("name", ""),
                    "id": input_field.get("id", ""),
                    "value": input_field.get("value", ""),
                    "placeholder": input_field.get("placeholder", ""),
                }
                form_info["inputs"].append(input_info)

            page_info["forms"].append(form_info)

        # 버튼 정보 수집
        buttons = soup.find_all(["button", "input"])
        for button in buttons:
            if button.name == "button" or button.get("type") in ["submit", "button"]:
                button_info = {
                    "text": button.get_text().strip(),
                    "type": button.get("type", "button"),
                    "name": button.get("name", ""),
                    "id": button.get("id", ""),
                    "class": button.get("class", []),
                }
                page_info["buttons"].append(button_info)

        # 링크 정보 수집
        links = soup.find_all("a")
        for link in links:
            link_info = {
                "text": link.get_text().strip(),
                "href": link.get("href", ""),
                "title": link.get("title", ""),
                "class": link.get("class", []),
            }
            page_info["links"].append(link_info)

        # 텍스트 내용 수집 (구독해지 관련 키워드 포함)
        text_content = soup.get_text()
        page_info["text_content"] = text_content[:1000]  # 처음 1000자만

        return page_info

    def _create_ai_prompt(self, page_info: Dict, user_email: str = None) -> str:
        """OpenAI API용 프롬프트 생성 (최적화된 버전)"""
        prompt = f"""
당신은 웹페이지에서 구독해지 기능을 찾아 실행하는 전문가입니다.

현재 페이지 정보:
- URL: {page_info['url']}
- 제목: {page_info['title']}
- 사용자 이메일: {user_email if user_email else '없음'}

페이지 구조 분석:
- 폼 개수: {len(page_info['forms'])}
- 버튼 개수: {len(page_info['buttons'])}
- 링크 개수: {len(page_info['links'])}

구독해지 관련 요소를 찾아서 다음 중 하나의 방법으로 처리해주세요:

1. **구독해지 링크 클릭**: "unsubscribe", "구독해지", "opt-out", "remove" 등의 텍스트가 포함된 링크
2. **구독해지 폼 제출**: 구독해지 관련 폼을 찾아서 제출
3. **구독해지 버튼 클릭**: "unsubscribe", "구독해지", "confirm" 등의 텍스트가 포함된 버튼
4. **이메일 입력 후 구독해지**: 이메일 필드를 찾아서 사용자 이메일을 입력한 후 구독해지

주요 고려사항:
- 2단계 프로세스일 수 있음 (첫 페이지에서 링크 클릭 후 두 번째 페이지에서 구독해지)
- 폼에는 이메일 필드, 체크박스, 라디오 버튼 등이 포함될 수 있음
- 구독해지 관련 키워드: unsubscribe, opt-out, 구독해지, 구독취소, 수신거부, remove, cancel
- 확인 관련 키워드: confirm, 확인, proceed, continue

응답 형식:
{{
    "action": "link_click|form_submit|button_click|email_input",
    "target": "클릭할 링크 텍스트 또는 폼/버튼 정보",
    "email_field": "이메일 입력 필드명 (필요시)",
    "reason": "선택한 이유",
    "confidence": "높음|중간|낮음"
}}

구독해지 관련 요소가 없다면:
{{
    "action": "none",
    "reason": "구독해지 요소를 찾을 수 없음",
    "confidence": "낮음"
}}

페이지 내용 일부:
{page_info['text_content'][:1000]}
"""
        return prompt

    def _call_openai_api(self, prompt: str) -> Dict:
        """OpenAI API 호출 (최신 버전 1.x 호환)"""
        try:
            from openai import OpenAI

            # OpenAI 클라이언트 초기화
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

            # API 호출
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "system",
                        "content": "당신은 웹페이지 분석 전문가입니다. 구독해지 페이지를 분석하여 사용자가 구독을 해지할 수 있도록 도와주세요.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=500,
                temperature=0.1,
            )

            # 응답 파싱
            if response.choices and len(response.choices) > 0:
                content = response.choices[0].message.content
                print(f"🤖 OpenAI API 응답: {content}")
                return {"success": True, "content": content}
            else:
                print("❌ OpenAI API 응답이 비어있습니다")
                return {"success": False, "message": "API 응답이 비어있습니다"}

        except Exception as e:
            error_msg = f"OpenAI API 호출 실패: {str(e)}"
            print(f"❌ {error_msg}")
            return {"success": False, "message": error_msg}

    def _execute_ai_instructions(
        self, browser, ai_response: Dict, user_email: str = None
    ) -> Dict:
        """AI 응답에 따른 처리 실행"""
        try:
            action = ai_response.get("action", "none")

            if action == "none":
                return {
                    "success": False,
                    "message": ai_response.get(
                        "reason", "구독해지 요소를 찾을 수 없습니다"
                    ),
                }

            elif action == "link_click":
                # 링크 클릭 처리
                target_text = ai_response.get("target", "")
                soup = browser.get_current_page()

                for link in soup.find_all("a", href=True):
                    if target_text.lower() in link.get_text().lower():
                        href = link["href"]
                        if not href.startswith("http"):
                            href = urljoin(browser.get_url(), href)

                        print(f"📝 AI 지시에 따른 링크 클릭: {href}")
                        response = browser.open(href)
                        if response.ok:
                            return {
                                "success": True,
                                "message": "AI 지시에 따른 링크 클릭 완료",
                            }

            elif action == "form_submit":
                # 폼 제출 처리
                target_info = ai_response.get("target", {})
                soup = browser.get_current_page()

                for form in soup.find_all("form"):
                    if self._match_form_criteria(form, target_info):
                        # 이메일 필드 채우기
                        email_field = ai_response.get("email_field")
                        if email_field and user_email:
                            email_input = form.find("input", {"name": email_field})
                            if email_input:
                                email_input["value"] = user_email

                        print(f"📝 AI 지시에 따른 폼 제출")
                        response = browser.submit(form, form.url)
                        if response.ok:
                            return {
                                "success": True,
                                "message": "AI 지시에 따른 폼 제출 완료",
                            }

            elif action == "button_click":
                # 버튼 클릭 처리
                target_text = ai_response.get("target", "")
                soup = browser.get_current_page()

                for button in soup.find_all("button"):
                    if target_text.lower() in button.get_text().lower():
                        form = button.find_parent("form")
                        if form:
                            print(f"📝 AI 지시에 따른 버튼 클릭")
                            response = browser.submit(form, form.url)
                            if response.ok:
                                return {
                                    "success": True,
                                    "message": "AI 지시에 따른 버튼 클릭 완료",
                                }

            return {"success": False, "message": "AI 지시 실행 실패"}

        except Exception as e:
            return {"success": False, "message": f"AI 지시 실행 오류: {str(e)}"}

    def _match_form_criteria(self, form, target_info: Dict) -> bool:
        """폼이 AI 지시 조건과 일치하는지 확인"""
        try:
            # 간단한 매칭 로직
            form_action = form.get("action", "")
            form_method = form.get("method", "get")

            if target_info.get("action") and target_info["action"] not in form_action:
                return False

            if target_info.get("method") and target_info["method"] != form_method:
                return False

            return True

        except:
            return False

    # ==================== 테스트 및 검증 함수들 ====================

    def test_unsubscribe_service(
        self, service_name: str, test_url: str, user_email: str = None
    ) -> Dict:
        """특정 이메일 서비스에 대한 구독해지 테스트"""
        try:
            print(f"🧪 {service_name} 구독해지 테스트 시작: {test_url}")

            # 테스트 시작 시간
            start_time = time.time()

            # 구독해지 시도
            result = self.process_unsubscribe_with_mechanicalsoup_ai(
                test_url, user_email
            )

            # 테스트 완료 시간
            end_time = time.time()
            processing_time = end_time - start_time

            # 결과에 테스트 정보 추가
            result["test_info"] = {
                "service_name": service_name,
                "test_url": test_url,
                "processing_time": processing_time,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            }

            print(
                f"🧪 {service_name} 테스트 완료: {'성공' if result['success'] else '실패'} ({processing_time:.2f}초)"
            )
            return result

        except Exception as e:
            print(f"❌ {service_name} 테스트 실패: {str(e)}")
            return {
                "success": False,
                "message": f"테스트 실패: {str(e)}",
                "test_info": {
                    "service_name": service_name,
                    "test_url": test_url,
                    "processing_time": 0,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                },
            }

    def run_comprehensive_tests(self, test_cases: List[Dict]) -> Dict:
        """종합적인 구독해지 테스트 실행"""
        print(f"🧪 종합 테스트 시작: {len(test_cases)}개 케이스")

        test_results = {
            "total_tests": len(test_cases),
            "successful_tests": 0,
            "failed_tests": 0,
            "total_processing_time": 0,
            "results": [],
        }

        for i, test_case in enumerate(test_cases):
            print(f"🧪 테스트 {i + 1}/{len(test_cases)}: {test_case['service_name']}")

            result = self.test_unsubscribe_service(
                test_case["service_name"],
                test_case["test_url"],
                test_case.get("user_email"),
            )

            test_results["results"].append(result)
            test_results["total_processing_time"] += result["test_info"][
                "processing_time"
            ]

            if result["success"]:
                test_results["successful_tests"] += 1
            else:
                test_results["failed_tests"] += 1

        # 성공률 계산
        success_rate = (
            test_results["successful_tests"] / test_results["total_tests"]
        ) * 100
        test_results["success_rate"] = success_rate
        test_results["average_processing_time"] = (
            test_results["total_processing_time"] / test_results["total_tests"]
        )

        print(f"🧪 종합 테스트 완료:")
        print(f"   - 총 테스트: {test_results['total_tests']}")
        print(f"   - 성공: {test_results['successful_tests']}")
        print(f"   - 실패: {test_results['failed_tests']}")
        print(f"   - 성공률: {success_rate:.1f}%")
        print(f"   - 평균 처리 시간: {test_results['average_processing_time']:.2f}초")

        return test_results

    def get_test_cases(self) -> List[Dict]:
        """기본 테스트 케이스 목록"""
        return [
            {
                "service_name": "Mailchimp",
                "test_url": "https://mailchimp.com/unsubscribe/",
                "user_email": "test@example.com",
            },
            {
                "service_name": "Stibee",
                "test_url": "https://page.stibee.com/unsubscribe/",
                "user_email": "test@example.com",
            },
            {
                "service_name": "SendGrid",
                "test_url": "https://sendgrid.com/unsubscribe/",
                "user_email": "test@example.com",
            },
            {
                "service_name": "Mailgun",
                "test_url": "https://mailgun.com/unsubscribe/",
                "user_email": "test@example.com",
            },
            {
                "service_name": "Amazon SES",
                "test_url": "https://amazon.com/unsubscribe/",
                "user_email": "test@example.com",
            },
        ]

    def analyze_failure_cases(self, test_results: Dict) -> Dict:
        """실패 케이스 분석"""
        failure_analysis = {
            "total_failures": 0,
            "failure_reasons": {},
            "service_specific_failures": {},
            "recommendations": [],
        }

        for result in test_results["results"]:
            if not result["success"]:
                failure_analysis["total_failures"] += 1

                # 실패 이유 분석
                error_message = result.get("message", "알 수 없는 오류")
                failure_analysis["failure_reasons"][error_message] = (
                    failure_analysis["failure_reasons"].get(error_message, 0) + 1
                )

                # 서비스별 실패 분석
                service_name = result["test_info"]["service_name"]
                if service_name not in failure_analysis["service_specific_failures"]:
                    failure_analysis["service_specific_failures"][service_name] = []
                failure_analysis["service_specific_failures"][service_name].append(
                    {
                        "url": result["test_info"]["test_url"],
                        "error": error_message,
                        "processing_time": result["test_info"]["processing_time"],
                    }
                )

        # 개선 권장사항 생성
        if failure_analysis["total_failures"] > 0:
            failure_analysis["recommendations"].append(
                "실패한 서비스에 대한 특별 처리 로직 추가 필요"
            )
            failure_analysis["recommendations"].append("AI 프롬프트 최적화 필요")
            failure_analysis["recommendations"].append("타임아웃 설정 조정 필요")

        return failure_analysis

    def _fill_form_fields_enhanced(self, form, user_email: str = None) -> None:
        """향상된 폼 필드 자동 채우기"""
        try:
            # 1. 이메일 필드 채우기
            if user_email:
                email_inputs = form.find_all("input", type="email")
                for email_input in email_inputs:
                    email_input["value"] = user_email
                    print(f"📝 이메일 필드 채움: {user_email}")

                # 이메일 타입이 아닌 이메일 필드도 찾기
                text_inputs = form.find_all("input", type="text")
                for text_input in text_inputs:
                    input_name = text_input.get("name", "").lower()
                    input_id = text_input.get("id", "").lower()
                    input_placeholder = text_input.get("placeholder", "").lower()

                    if any(
                        keyword in input_name
                        or keyword in input_id
                        or keyword in input_placeholder
                        for keyword in ["email", "mail", "e-mail"]
                    ):
                        text_input["value"] = user_email
                        print(f"📝 텍스트 이메일 필드 채움: {user_email}")

            # 2. 체크박스 처리
            checkboxes = form.find_all("input", type="checkbox")
            for checkbox in checkboxes:
                checkbox_name = checkbox.get("name", "").lower()
                checkbox_id = checkbox.get("id", "").lower()

                # 구독해지 관련 체크박스는 체크 해제
                if any(
                    keyword in checkbox_name or keyword in checkbox_id
                    for keyword in ["unsubscribe", "opt-out", "구독해지", "수신거부"]
                ):
                    checkbox["checked"] = False
                    print(f"📝 구독해지 체크박스 해제")

                # 구독 관련 체크박스는 체크 해제
                elif any(
                    keyword in checkbox_name or keyword in checkbox_id
                    for keyword in ["subscribe", "구독", "수신"]
                ):
                    checkbox["checked"] = False
                    print(f"📝 구독 체크박스 해제")

            # 3. 라디오 버튼 처리
            radio_buttons = form.find_all("input", type="radio")
            for radio in radio_buttons:
                radio_name = radio.get("name", "").lower()
                radio_value = radio.get("value", "").lower()

                # 구독해지 관련 라디오 버튼 선택
                if any(
                    keyword in radio_value
                    for keyword in ["unsubscribe", "opt-out", "구독해지", "수신거부"]
                ):
                    radio["checked"] = True
                    print(f"📝 구독해지 라디오 버튼 선택: {radio_value}")

                # 구독 관련 라디오 버튼 해제
                elif any(
                    keyword in radio_value for keyword in ["subscribe", "구독", "수신"]
                ):
                    radio["checked"] = False
                    print(f"📝 구독 라디오 버튼 해제: {radio_value}")

            # 4. 숨겨진 필드 처리
            hidden_inputs = form.find_all("input", type="hidden")
            for hidden_input in hidden_inputs:
                hidden_name = hidden_input.get("name", "").lower()
                hidden_value = hidden_input.get("value", "").lower()

                # 구독해지 관련 숨겨진 필드 설정
                if any(
                    keyword in hidden_name for keyword in ["action", "type", "mode"]
                ):
                    if "unsubscribe" in hidden_name or "opt-out" in hidden_name:
                        hidden_input["value"] = "unsubscribe"
                        print(f"📝 숨겨진 필드 설정: {hidden_name} = unsubscribe")

            # 5. 셀렉트 박스 처리
            select_elements = form.find_all("select")
            for select in select_elements:
                select_name = select.get("name", "").lower()

                # 구독해지 관련 셀렉트 박스 처리
                if any(
                    keyword in select_name
                    for keyword in [
                        "unsubscribe",
                        "opt-out",
                        "cancel",
                        "구독해지",
                        "remove",
                    ]
                ):
                    options = select.find_all("option")
                    for option in options:
                        option_value = option.get("value", "").lower()
                        option_text = option.get_text().lower()

                        # 구독해지 옵션 선택
                        if any(
                            keyword in option_value or keyword in option_text
                            for keyword in [
                                "unsubscribe",
                                "opt-out",
                                "cancel",
                                "구독해지",
                                "remove",
                            ]
                        ):
                            option["selected"] = True
                            print(f"📝 셀렉트 박스 옵션 선택: {option_text}")
                            break

                        # 구독 옵션 해제
                        elif any(
                            keyword in option_value or keyword in option_text
                            for keyword in ["subscribe", "구독", "수신"]
                        ):
                            option["selected"] = False
                            print(f"📝 셀렉트 박스 옵션 해제: {option_text}")

        except Exception as e:
            print(f"❌ 폼 필드 채우기 실패: {str(e)}")

    # ==================== 로깅 및 모니터링 함수들 ====================

    def log_unsubscribe_attempt(
        self, url: str, user_email: str = None, start_time: float = None
    ) -> None:
        """구독해지 시도 로깅"""
        self.stats["total_attempts"] += 1

        log_data = {
            "url": url,
            "user_email": user_email,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "attempt_number": self.stats["total_attempts"],
        }

        self.logger.info(f"구독해지 시도: {log_data}")
        print(f"📊 구독해지 시도 #{self.stats['total_attempts']}: {url}")

    def log_unsubscribe_result(
        self, result: Dict, processing_time: float, url: str
    ) -> None:
        """구독해지 결과 로깅"""
        if result["success"]:
            self.stats["successful_unsubscribes"] += 1
            self.logger.info(f"구독해지 성공: {url} ({processing_time:.2f}초)")
            print(f"✅ 구독해지 성공: {url} ({processing_time:.2f}초)")
        else:
            self.stats["failed_unsubscribes"] += 1
            error_msg = result.get("message", "알 수 없는 오류")
            self.logger.warning(
                f"구독해지 실패: {url} - {error_msg} ({processing_time:.2f}초)"
            )
            print(f"❌ 구독해지 실패: {url} - {error_msg} ({processing_time:.2f}초)")

            # 에러 카운트 업데이트
            if error_msg not in self.stats["error_counts"]:
                self.stats["error_counts"][error_msg] = 0
            self.stats["error_counts"][error_msg] += 1

        # 처리 시간 기록
        self.stats["processing_times"].append(processing_time)

        # 서비스별 성공률 업데이트
        domain = urlparse(url).netloc
        if domain not in self.stats["service_success_rates"]:
            self.stats["service_success_rates"][domain] = {"success": 0, "total": 0}

        self.stats["service_success_rates"][domain]["total"] += 1
        if result["success"]:
            self.stats["service_success_rates"][domain]["success"] += 1

    def log_ai_analysis(self, ai_response: Dict, url: str) -> None:
        """AI 분석 결과 로깅"""
        log_data = {
            "url": url,
            "ai_action": ai_response.get("action"),
            "ai_target": ai_response.get("target"),
            "ai_confidence": ai_response.get("confidence"),
            "ai_reason": ai_response.get("reason"),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

        self.logger.info(f"AI 분석 결과: {log_data}")
        print(
            f"🤖 AI 분석: {ai_response.get('action')} - {ai_response.get('confidence')}"
        )

    def get_statistics(self) -> Dict:
        """현재 통계 정보 반환"""
        total_attempts = self.stats["total_attempts"]
        if total_attempts == 0:
            return {"message": "아직 통계 데이터가 없습니다"}

        success_rate = (self.stats["successful_unsubscribes"] / total_attempts) * 100
        avg_processing_time = (
            sum(self.stats["processing_times"]) / len(self.stats["processing_times"])
            if self.stats["processing_times"]
            else 0
        )

        # 서비스별 성공률 계산
        service_stats = {}
        for domain, data in self.stats["service_success_rates"].items():
            if data["total"] > 0:
                service_stats[domain] = {
                    "success_rate": (data["success"] / data["total"]) * 100,
                    "total_attempts": data["total"],
                    "successful_attempts": data["success"],
                }

        # 상위 에러 분석
        top_errors = sorted(
            self.stats["error_counts"].items(), key=lambda x: x[1], reverse=True
        )[:5]

        return {
            "total_attempts": total_attempts,
            "successful_unsubscribes": self.stats["successful_unsubscribes"],
            "failed_unsubscribes": self.stats["failed_unsubscribes"],
            "overall_success_rate": success_rate,
            "average_processing_time": avg_processing_time,
            "service_statistics": service_stats,
            "top_errors": top_errors,
            "last_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

    def export_statistics_report(self, filename: str = None) -> str:
        """통계 리포트 생성 및 내보내기"""
        if filename is None:
            filename = f"unsubscribe_stats_{time.strftime('%Y%m%d_%H%M%S')}.json"

        stats = self.get_statistics()

        try:
            import json

            with open(filename, "w", encoding="utf-8") as f:
                json.dump(stats, f, ensure_ascii=False, indent=2)

            print(f"📊 통계 리포트 저장: {filename}")
            return filename

        except Exception as e:
            print(f"❌ 통계 리포트 저장 실패: {str(e)}")
            return None

    def log_performance_metrics(
        self, url: str, method: str, processing_time: float, success: bool
    ) -> None:
        """성능 메트릭 로깅"""
        metric_data = {
            "url": url,
            "method": method,  # "simple", "mechanicalsoup", "selenium"
            "processing_time": processing_time,
            "success": success,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

        self.logger.info(f"성능 메트릭: {metric_data}")

        # 성능 경고
        if processing_time > 30:
            self.logger.warning(f"느린 처리 시간: {url} - {processing_time:.2f}초")
        elif processing_time > 60:
            self.logger.error(f"매우 느린 처리 시간: {url} - {processing_time:.2f}초")

    def monitor_system_health(self) -> Dict:
        """시스템 상태 모니터링"""
        import psutil

        health_data = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "cpu_usage": psutil.cpu_percent(),
            "memory_usage": psutil.virtual_memory().percent,
            "disk_usage": psutil.disk_usage("/").percent,
            "total_attempts": self.stats["total_attempts"],
            "success_rate": (
                self.stats["successful_unsubscribes"]
                / max(self.stats["total_attempts"], 1)
            )
            * 100,
        }

        # 경고 조건 체크
        warnings = []
        if health_data["cpu_usage"] > 80:
            warnings.append("CPU 사용률이 높습니다")
        if health_data["memory_usage"] > 80:
            warnings.append("메모리 사용률이 높습니다")
        if health_data["disk_usage"] > 90:
            warnings.append("디스크 사용률이 높습니다")

        health_data["warnings"] = warnings

        self.logger.info(f"시스템 상태: {health_data}")
        return health_data
