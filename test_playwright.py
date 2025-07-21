#!/usr/bin/env python3
"""
Playwright unsubscribe service test script
"""

import asyncio
import sys
import os

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cleanbox.email.playwright_unsubscribe import (
    PlaywrightUnsubscribeService,
    process_unsubscribe_sync,
)


def test_playwright_service():
    """Playwright service test"""
    print("🧪 Playwright unsubscribe service test start")

    # Test URL (example, not actual unsubscribe link)
    test_url = "https://httpbin.org/status/200"

    try:
        # Test sync wrapper function
        print(f"📝 Test URL: {test_url}")
        result = process_unsubscribe_sync(test_url)

        print(f"📊 Result: {result}")

        if result["success"]:
            print("✅ Test passed!")
        else:
            print(f"❌ Test failed: {result['message']}")

    except Exception as e:
        print(f"❌ Error during test: {str(e)}")


def test_memory_monitor():
    """Memory monitor test"""
    print("🧪 Memory monitor test start")

    try:
        from cleanbox.utils.memory_monitor import memory_monitor

        # Check memory usage
        stats = memory_monitor.get_memory_stats()
        print(f"📊 Memory stats: {stats}")

        # Check memory limit
        is_safe = memory_monitor.check_memory_limit()
        print(f"📊 Memory safe: {is_safe}")

    except Exception as e:
        print(f"❌ Error during memory monitor test: {str(e)}")


def test_browser_manager():
    """Browser manager test"""
    print("🧪 Browser manager test start")

    try:
        from cleanbox.email.browser_manager import browser_manager

        # Check browser manager status
        stats = browser_manager.get_stats()
        print(f"📊 Browser manager stats: {stats}")

    except Exception as e:
        print(f"❌ Error during browser manager test: {str(e)}")


if __name__ == "__main__":
    print("🚀 Playwright unsubscribe service test start")
    print("=" * 50)

    # 1. Memory monitor test
    test_memory_monitor()
    print()

    # 2. Browser manager test
    test_browser_manager()
    print()

    # 3. Playwright service test
    test_playwright_service()
    print()

    print("🏁 Test complete")
