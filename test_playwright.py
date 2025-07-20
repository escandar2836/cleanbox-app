#!/usr/bin/env python3
"""
Playwright 구독해지 서비스 테스트 스크립트
"""

import asyncio
import sys
import os

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cleanbox.email.playwright_unsubscribe import (
    PlaywrightUnsubscribeService,
    process_unsubscribe_sync,
)


def test_playwright_service():
    """Playwright 서비스 테스트"""
    print("🧪 Playwright 구독해지 서비스 테스트 시작")

    # 테스트 URL (실제 구독해지 링크가 아닌 예시)
    test_url = "https://httpbin.org/status/200"

    try:
        # 동기식 래퍼 함수 테스트
        print(f"📝 테스트 URL: {test_url}")
        result = process_unsubscribe_sync(test_url)

        print(f"📊 결과: {result}")

        if result["success"]:
            print("✅ 테스트 성공!")
        else:
            print(f"❌ 테스트 실패: {result['message']}")

    except Exception as e:
        print(f"❌ 테스트 중 오류 발생: {str(e)}")


def test_memory_monitor():
    """메모리 모니터링 테스트"""
    print("🧪 메모리 모니터링 테스트 시작")

    try:
        from cleanbox.utils.memory_monitor import memory_monitor

        # 메모리 사용량 확인
        stats = memory_monitor.get_memory_stats()
        print(f"📊 메모리 통계: {stats}")

        # 메모리 제한 체크
        is_safe = memory_monitor.check_memory_limit()
        print(f"📊 메모리 안전 여부: {is_safe}")

    except Exception as e:
        print(f"❌ 메모리 모니터링 테스트 중 오류: {str(e)}")


def test_browser_manager():
    """브라우저 매니저 테스트"""
    print("🧪 브라우저 매니저 테스트 시작")

    try:
        from cleanbox.email.browser_manager import browser_manager

        # 브라우저 매니저 상태 확인
        stats = browser_manager.get_stats()
        print(f"📊 브라우저 매니저 통계: {stats}")

    except Exception as e:
        print(f"❌ 브라우저 매니저 테스트 중 오류: {str(e)}")


if __name__ == "__main__":
    print("🚀 Playwright 구독해지 서비스 테스트 시작")
    print("=" * 50)

    # 1. 메모리 모니터링 테스트
    test_memory_monitor()
    print()

    # 2. 브라우저 매니저 테스트
    test_browser_manager()
    print()

    # 3. Playwright 서비스 테스트
    test_playwright_service()
    print()

    print("🏁 테스트 완료")
