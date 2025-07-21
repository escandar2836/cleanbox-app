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

# Local imports
from .playwright_unsubscribe import (
    PlaywrightUnsubscribeService,
    process_unsubscribe_sync,
)


class AdvancedUnsubscribeService:
    """고급 구독해지 서비스 (Playwright 기반)"""

    def __init__(self):
        self.setup_logging()
        self.playwright_service = PlaywrightUnsubscribeService()

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
        if not os.path.exists("logs"):
            os.makedirs("logs")
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
        """이메일에서 구독해지 링크 추출 (Playwright 서비스 사용)"""
        return self.playwright_service.extract_unsubscribe_links(
            email_content, email_headers
        )

    def _is_valid_unsubscribe_url(self, url: str) -> bool:
        """유효한 구독해지 URL인지 확인"""
        try:
            parsed = urlparse(url)
            return parsed.scheme in ["http", "https"] and bool(parsed.netloc)
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

            if not has_marketing_content:
                print(f"📝 마케팅 콘텐츠가 없음 - 개인 이메일로 판단")
                return True

            return False

        except Exception as e:
            print(f"⚠️ 개인 이메일 감지 중 오류: {str(e)}")
            return False

    def process_unsubscribe_simple(self, unsubscribe_url: str) -> Dict:
        """간단한 구독해지 처리 (Playwright 서비스 사용)"""
        try:
            print(f"🔧 간단한 구독해지 처리 시작: {unsubscribe_url}")

            # Playwright 서비스를 사용하여 처리 (동기식 래퍼 사용)
            result = process_unsubscribe_sync(unsubscribe_url)

            return result

        except Exception as e:
            print(f"❌ 간단한 구독해지 처리 실패: {str(e)}")
            return {
                "success": False,
                "message": f"구독해지 처리 실패: {str(e)}",
                "error_details": str(e),
            }

    def _find_unsubscribe_link_simple(self, soup: BeautifulSoup) -> Optional[str]:
        """간단한 구독해지 링크 찾기"""
        try:
            # 구독해지 관련 링크 찾기
            unsubscribe_keywords = [
                "unsubscribe",
                "opt-out",
                "remove",
                "cancel",
                "구독해지",
                "구독취소",
                "수신거부",
                "수신취소",
            ]

            for link in soup.find_all("a", href=True):
                href = link.get("href", "").lower()
                link_text = link.get_text().lower()

                for keyword in unsubscribe_keywords:
                    if keyword in href or keyword in link_text:
                        return link["href"]

            return None

        except Exception as e:
            print(f"⚠️ 구독해지 링크 찾기 실패: {str(e)}")
            return None

    def process_unsubscribe_advanced(
        self, email_content: str, email_headers: Dict = None, user_email: str = None
    ) -> Dict:
        """고급 구독해지 처리 (Playwright 서비스 사용)"""
        try:
            print(f"🔧 고급 구독해지 처리 시작")

            # 구독해지 링크 추출
            unsubscribe_links = self.extract_unsubscribe_links(
                email_content, email_headers
            )

            if not unsubscribe_links:
                return {
                    "success": False,
                    "message": "구독해지 링크를 찾을 수 없습니다.",
                    "error_type": "no_unsubscribe_link",
                    "error_details": "이메일에서 구독해지 링크를 찾을 수 없습니다.",
                }

            print(f"📝 발견된 구독해지 링크: {unsubscribe_links}")

            # 각 링크에 대해 구독해지 시도
            failed_links = []
            for i, link in enumerate(unsubscribe_links):
                print(f"📝 링크 {i + 1}/{len(unsubscribe_links)} 처리: {link}")

                result = process_unsubscribe_sync(link, user_email)

                if result["success"]:
                    return {
                        "success": True,
                        "message": f"구독해지 성공: {result['message']}",
                        "processed_url": link,
                        "processing_time": result.get("processing_time", 0),
                    }
                else:
                    failed_links.append(
                        {
                            "link_number": i + 1,
                            "url": link,
                            "error": result.get("message", "알 수 없는 오류"),
                        }
                    )

            # 모든 링크 실패
            return {
                "success": False,
                "message": "모든 구독해지 링크에서 실패했습니다.",
                "error_type": "all_links_failed",
                "error_details": f"{len(failed_links)}개의 구독해지 링크를 시도했지만 모두 실패했습니다.",
                "failed_links": failed_links,
                "attempted_links": unsubscribe_links,
            }

        except Exception as e:
            print(f"❌ 고급 구독해지 처리 실패: {str(e)}")
            return {
                "success": False,
                "message": f"고급 구독해지 처리 실패: {str(e)}",
                "error_details": str(e),
            }

    def process_unsubscribe_with_mechanicalsoup_ai(
        self, unsubscribe_url: str, user_email: str = None
    ) -> Dict:
        """Playwright + AI를 활용한 범용 구독해지 처리 (기존 함수명 유지)"""
        return process_unsubscribe_sync(unsubscribe_url, user_email)

    def test_unsubscribe_service(
        self, service_name: str, test_url: str, user_email: str = None
    ) -> Dict:
        """구독해지 서비스 테스트"""
        try:
            print(f"🧪 구독해지 서비스 테스트 시작: {service_name}")

            # Playwright 서비스를 사용하여 테스트
            result = process_unsubscribe_sync(test_url, user_email)

            return {
                "service_name": service_name,
                "test_url": test_url,
                "success": result["success"],
                "message": result["message"],
                "processing_time": result.get("processing_time", 0),
            }

        except Exception as e:
            print(f"❌ 구독해지 서비스 테스트 실패: {str(e)}")
            return {
                "service_name": service_name,
                "test_url": test_url,
                "success": False,
                "message": f"테스트 실패: {str(e)}",
                "error_details": str(e),
            }

    def run_comprehensive_tests(self, test_cases: List[Dict]) -> Dict:
        """종합 테스트 실행"""
        try:
            print(f"🧪 종합 테스트 시작: {len(test_cases)}개 케이스")

            results = []
            passed = 0
            failed = 0

            for test_case in test_cases:
                result = self.test_unsubscribe_service(
                    test_case["service_name"],
                    test_case["test_url"],
                    test_case.get("user_email"),
                )

                results.append(result)

                if result["success"]:
                    passed += 1
                else:
                    failed += 1

            return {
                "total_tests": len(test_cases),
                "passed": passed,
                "failed": failed,
                "success_rate": (passed / len(test_cases) * 100) if test_cases else 0,
                "results": results,
            }

        except Exception as e:
            print(f"❌ 종합 테스트 실패: {str(e)}")
            return {
                "total_tests": 0,
                "passed": 0,
                "failed": 0,
                "success_rate": 0,
                "error": str(e),
            }

    def get_test_cases(self) -> List[Dict]:
        """테스트 케이스 목록 반환"""
        return [
            {
                "service_name": "Netflix",
                "test_url": "https://www.netflix.com/account",
                "description": "Netflix 구독 해지 테스트",
            },
            {
                "service_name": "Spotify",
                "test_url": "https://www.spotify.com/account/subscription/",
                "description": "Spotify 구독 해지 테스트",
            },
            {
                "service_name": "YouTube",
                "test_url": "https://www.youtube.com/paid_memberships",
                "description": "YouTube Premium 구독 해지 테스트",
            },
        ]

    def analyze_failure_cases(self, test_results: Dict) -> Dict:
        """실패 케이스 분석"""
        try:
            failed_results = [
                result
                for result in test_results.get("results", [])
                if not result.get("success", False)
            ]

            failure_analysis = {
                "total_failures": len(failed_results),
                "failure_reasons": {},
                "service_failure_counts": {},
            }

            for result in failed_results:
                service_name = result.get("service_name", "Unknown")
                message = result.get("message", "Unknown error")

                # 서비스별 실패 횟수
                failure_analysis["service_failure_counts"][service_name] = (
                    failure_analysis["service_failure_counts"].get(service_name, 0) + 1
                )

                # 실패 이유 분석
                if "timeout" in message.lower():
                    failure_analysis["failure_reasons"]["timeout"] = (
                        failure_analysis["failure_reasons"].get("timeout", 0) + 1
                    )
                elif "element not found" in message.lower():
                    failure_analysis["failure_reasons"]["element_not_found"] = (
                        failure_analysis["failure_reasons"].get("element_not_found", 0)
                        + 1
                    )
                elif "network" in message.lower():
                    failure_analysis["failure_reasons"]["network_error"] = (
                        failure_analysis["failure_reasons"].get("network_error", 0) + 1
                    )
                else:
                    failure_analysis["failure_reasons"]["other"] = (
                        failure_analysis["failure_reasons"].get("other", 0) + 1
                    )

            return failure_analysis

        except Exception as e:
            print(f"❌ 실패 케이스 분석 실패: {str(e)}")
            return {"error": str(e)}

    def log_unsubscribe_attempt(
        self, url: str, user_email: str = None, start_time: float = None
    ) -> None:
        """구독해지 시도 로깅"""
        self.stats["total_attempts"] += 1
        self.logger.info(f"구독해지 시도: {url}, 사용자: {user_email}")

    def log_unsubscribe_result(
        self, result: Dict, processing_time: float, url: str
    ) -> None:
        """구독해지 결과 로깅"""
        if result.get("success"):
            self.stats["successful_unsubscribes"] += 1
        else:
            self.stats["failed_unsubscribes"] += 1

        self.stats["processing_times"].append(processing_time)
        self.logger.info(
            f"구독해지 결과: {result.get('message', 'N/A')}, "
            f"처리시간: {processing_time:.2f}초, URL: {url}"
        )

    def log_ai_analysis(self, ai_response: Dict, url: str) -> None:
        """AI 분석 로깅"""
        self.logger.info(f"AI 분석 결과: {ai_response}, URL: {url}")

    def get_statistics(self) -> Dict:
        """통계 정보 반환"""
        playwright_stats = self.playwright_service.get_statistics()

        return {
            "total_attempts": self.stats["total_attempts"]
            + playwright_stats["total_attempts"],
            "successful_unsubscribes": self.stats["successful_unsubscribes"]
            + playwright_stats["successful_unsubscribes"],
            "failed_unsubscribes": self.stats["failed_unsubscribes"]
            + playwright_stats["failed_unsubscribes"],
            "success_rate": playwright_stats["success_rate"],
            "average_processing_time": playwright_stats["average_processing_time"],
            "service_success_rates": self.stats["service_success_rates"],
            "error_counts": self.stats["error_counts"],
        }

    def export_statistics_report(self, filename: str = None) -> str:
        """통계 보고서 내보내기"""
        try:
            if not filename:
                filename = f"unsubscribe_statistics_{int(time.time())}.json"

            stats = self.get_statistics()

            with open(filename, "w", encoding="utf-8") as f:
                json.dump(stats, f, ensure_ascii=False, indent=2)

            print(f"📊 통계 보고서 저장됨: {filename}")
            return filename

        except Exception as e:
            print(f"❌ 통계 보고서 내보내기 실패: {str(e)}")
            return ""

    def log_performance_metrics(
        self, url: str, method: str, processing_time: float, success: bool
    ) -> None:
        """성능 메트릭 로깅"""
        self.logger.info(
            f"성능 메트릭: URL={url}, Method={method}, "
            f"Time={processing_time:.2f}s, Success={success}"
        )

    def monitor_system_health(self) -> Dict:
        """시스템 상태 모니터링"""
        try:
            # Playwright 서비스 상태 확인
            playwright_stats = self.playwright_service.get_statistics()

            return {
                "status": "healthy",
                "playwright_service": {
                    "total_attempts": playwright_stats["total_attempts"],
                    "success_rate": playwright_stats["success_rate"],
                    "average_processing_time": playwright_stats[
                        "average_processing_time"
                    ],
                },
                "advanced_service": {
                    "total_attempts": self.stats["total_attempts"],
                    "successful_unsubscribes": self.stats["successful_unsubscribes"],
                    "failed_unsubscribes": self.stats["failed_unsubscribes"],
                },
                "timestamp": time.time(),
            }

        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": time.time(),
            }
