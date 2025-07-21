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
    """Advanced Unsubscribe Service (Playwright-based)"""

    def __init__(self):
        self.setup_logging()
        self.playwright_service = PlaywrightUnsubscribeService()

        # Timeout settings
        self.timeouts = {
            "page_load": 30,
            "element_wait": 10,
            "api_call": 15,
            "retry_delay": 2,
        }

    def setup_logging(self):
        """Setup logging"""
        logging.basicConfig(
            level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
        )
        self.logger = logging.getLogger(__name__)

        # Add file logging
        if not os.path.exists("logs"):
            os.makedirs("logs")
        file_handler = logging.FileHandler("logs/unsubscribe_service.log")
        file_handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)

        # Initialize stats
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
        """Extract unsubscribe links from email (using Playwright service)"""
        return self.playwright_service.extract_unsubscribe_links(
            email_content, email_headers
        )

    def _is_valid_unsubscribe_url(self, url: str) -> bool:
        """Check if URL is a valid unsubscribe link"""
        try:
            parsed = urlparse(url)
            return parsed.scheme in ["http", "https"] and bool(parsed.netloc)
        except:
            return False

    def _detect_personal_email(
        self, email_content: str, email_headers: Dict = None
    ) -> bool:
        """Detect personal email"""
        try:
            # 1. Check sender domain
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
                        print(f"Personal domain detected: {domain}")
                        return True

            # 2. Analyze email content
            content_lower = email_content.lower()

            # Check for marketing keywords
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
                print(f"No marketing content - considered personal email")
                return True

            return False

        except Exception as e:
            print(f"Error detecting personal email: {str(e)}")
            return False

    def process_unsubscribe_simple(self, unsubscribe_url: str) -> Dict:
        """Simple unsubscribe processing (using Playwright service)"""
        try:
            print(f"🔧 Starting simple unsubscribe processing: {unsubscribe_url}")

            # Use Playwright service for processing (sync wrapper)
            result = process_unsubscribe_sync(unsubscribe_url)

            return result

        except Exception as e:
            print(f"❌ Failed simple unsubscribe processing: {str(e)}")
            return {
                "success": False,
                "message": f"Unsubscribe processing failed: {str(e)}",
                "error_details": str(e),
            }

    def _find_unsubscribe_link_simple(self, soup: BeautifulSoup) -> Optional[str]:
        """Find simple unsubscribe link"""
        try:
            # Find unsubscribe-related links
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
            print(f"⚠️ Failed to find unsubscribe link: {str(e)}")
            return None

    async def process_unsubscribe_advanced(
        self, email_content: str, email_headers: Dict = None, user_email: str = None
    ) -> Dict:
        """Advanced unsubscribe processing (using Playwright service, with AI fallback)"""
        try:
            print(f"🔧 Starting advanced unsubscribe processing (async, AI fallback)")

            # Extract unsubscribe links (AI fallback 포함)
            unsubscribe_links = await self.playwright_service.extract_unsubscribe_links_with_ai_fallback(
                email_content, email_headers, user_email
            )

            if not unsubscribe_links:
                return {
                    "success": False,
                    "message": "No unsubscribe link found (even with AI).",
                    "error_type": "no_unsubscribe_link",
                    "error_details": "Could not find unsubscribe link in email (AI fallback also failed).",
                }

            print(f"📝 Found unsubscribe links: {unsubscribe_links}")

            # Try unsubscribe for each link
            failed_links = []
            for i, link in enumerate(unsubscribe_links):
                print(f"📝 Processing link {i + 1}/{len(unsubscribe_links)}: {link}")

                result = await self.playwright_service.process_unsubscribe_async(
                    link, user_email
                )

                if result["success"]:
                    return {
                        "success": True,
                        "message": f"Unsubscribe success: {result['message']}",
                        "processed_url": link,
                        "processing_time": result.get("processing_time", 0),
                    }
                else:
                    failed_links.append(
                        {
                            "link_number": i + 1,
                            "url": link,
                            "error": result.get("message", "Unknown error"),
                        }
                    )

            # All links failed
            return {
                "success": False,
                "message": "Failed on all unsubscribe links.",
                "error_type": "all_links_failed",
                "error_details": f"Tried {len(failed_links)} unsubscribe links, all failed.",
                "failed_links": failed_links,
                "attempted_links": unsubscribe_links,
            }

        except Exception as e:
            print(f"❌ Failed advanced unsubscribe processing: {str(e)}")
            return {
                "success": False,
                "message": f"Advanced unsubscribe processing failed: {str(e)}",
                "error_details": str(e),
            }

    def process_unsubscribe_with_mechanicalsoup_ai(
        self, unsubscribe_url: str, user_email: str = None
    ) -> Dict:
        """Universal unsubscribe processing using Playwright + AI (legacy function name kept)"""
        return process_unsubscribe_sync(unsubscribe_url, user_email)

    def test_unsubscribe_service(
        self, service_name: str, test_url: str, user_email: str = None
    ) -> Dict:
        """Unsubscribe service test"""
        try:
            print(f"🧪 Starting unsubscribe service test: {service_name}")

            # Use Playwright service for testing
            result = process_unsubscribe_sync(test_url, user_email)

            return {
                "service_name": service_name,
                "test_url": test_url,
                "success": result["success"],
                "message": result["message"],
                "processing_time": result.get("processing_time", 0),
            }

        except Exception as e:
            print(f"❌ Unsubscribe service test failed: {str(e)}")
            return {
                "service_name": service_name,
                "test_url": test_url,
                "success": False,
                "message": f"Test failed: {str(e)}",
                "error_details": str(e),
            }

    def run_comprehensive_tests(self, test_cases: List[Dict]) -> Dict:
        """Run comprehensive tests"""
        try:
            print(f"🧪 Starting comprehensive tests: {len(test_cases)} cases")

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
            print(f"❌ Comprehensive tests failed: {str(e)}")
            return {
                "total_tests": 0,
                "passed": 0,
                "failed": 0,
                "success_rate": 0,
                "error": str(e),
            }

    def get_test_cases(self) -> List[Dict]:
        """Return test cases list"""
        return [
            {
                "service_name": "Netflix",
                "test_url": "https://www.netflix.com/account",
                "description": "Netflix unsubscribe test",
            },
            {
                "service_name": "Spotify",
                "test_url": "https://www.spotify.com/account/subscription/",
                "description": "Spotify unsubscribe test",
            },
            {
                "service_name": "YouTube",
                "test_url": "https://www.youtube.com/paid_memberships",
                "description": "YouTube Premium unsubscribe test",
            },
        ]

    def analyze_failure_cases(self, test_results: Dict) -> Dict:
        """Analyze failure cases"""
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

                # Service-wise failure counts
                failure_analysis["service_failure_counts"][service_name] = (
                    failure_analysis["service_failure_counts"].get(service_name, 0) + 1
                )

                # Analyze failure reasons
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
            print(f"❌ Failed to analyze failure cases: {str(e)}")
            return {"error": str(e)}

    def log_unsubscribe_attempt(
        self, url: str, user_email: str = None, start_time: float = None
    ) -> None:
        """Log unsubscribe attempt"""
        self.stats["total_attempts"] += 1
        self.logger.info(f"Unsubscribe attempt: {url}, User: {user_email}")

    def log_unsubscribe_result(
        self, result: Dict, processing_time: float, url: str
    ) -> None:
        """Log unsubscribe result"""
        if result.get("success"):
            self.stats["successful_unsubscribes"] += 1
        else:
            self.stats["failed_unsubscribes"] += 1

        self.stats["processing_times"].append(processing_time)
        self.logger.info(
            f"Unsubscribe result: {result.get('message', 'N/A')}, "
            f"Processing time: {processing_time:.2f}s, URL: {url}"
        )

    def log_ai_analysis(self, ai_response: Dict, url: str) -> None:
        """Log AI analysis"""
        self.logger.info(f"AI analysis result: {ai_response}, URL: {url}")

    def get_statistics(self) -> Dict:
        """Return statistics information"""
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
        """Export statistics report"""
        try:
            if not filename:
                filename = f"unsubscribe_statistics_{int(time.time())}.json"

            stats = self.get_statistics()

            with open(filename, "w", encoding="utf-8") as f:
                json.dump(stats, f, ensure_ascii=False, indent=2)

            print(f"📊 Statistics report saved: {filename}")
            return filename

        except Exception as e:
            print(f"❌ Failed to export statistics report: {str(e)}")
            return ""

    def log_performance_metrics(
        self, url: str, method: str, processing_time: float, success: bool
    ) -> None:
        """Log performance metrics"""
        self.logger.info(
            f"Performance metrics: URL={url}, Method={method}, "
            f"Time={processing_time:.2f}s, Success={success}"
        )

    def monitor_system_health(self) -> Dict:
        """Monitor system health"""
        try:
            # Check Playwright service status
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
