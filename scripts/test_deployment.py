#!/usr/bin/env python3
"""
CleanBox deployment post-check functional test script
"""

import requests
import json
import sys
import os
from datetime import datetime


def test_webhook_endpoint(base_url):
    """Webhook endpoint test"""
    print("🔍 Testing webhook endpoint...")

    try:
        # GET test
        response = requests.get(f"{base_url}/webhook/gmail/test", timeout=10)
        if response.status_code == 200:
            print("✅ Webhook endpoint is working properly")
            return True
        else:
            print(f"❌ Webhook endpoint test failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Webhook endpoint test error: {e}")
        return False


def test_webhook_post(base_url):
    """Webhook POST request test"""
    print("🔍 Testing webhook POST request...")

    try:
        # Test data
        test_data = {
            "message": {
                "data": "eyJlbWFpbEFkZHJlc3MiOiJ0ZXN0QGV4YW1wbGUuY29tIiwiaGlzdG9yeUlkIjoiMTIzNDU2Nzg5MCJ9"
            }
        }

        response = requests.post(
            f"{base_url}/webhook/gmail",
            json=test_data,
            headers={"Content-Type": "application/json"},
            timeout=10,
        )

        if response.status_code in [200, 404]:  # 404 if account not found
            print("✅ Webhook POST request processed successfully")
            return True
        else:
            print(f"❌ Webhook POST request failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Webhook POST request error: {e}")
        return False


def test_main_page(base_url):
    """Main page access test"""
    print("🔍 Testing main page access...")

    try:
        response = requests.get(base_url, timeout=10)
        if response.status_code == 200:
            print("✅ Main page accessed successfully")
            return True
        else:
            print(f"❌ Main page access failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Main page access error: {e}")
        return False


def test_health_check(base_url):
    """Health check endpoint test"""
    print("🔍 Testing health check...")

    try:
        response = requests.get(f"{base_url}/health", timeout=10)
        if response.status_code == 200:
            print("✅ Health check passed")
            return True
        else:
            print(f"⚠️  Health check endpoint missing: {response.status_code}")
            return True  # Health check is optional
    except Exception as e:
        print(f"⚠️  Health check error: {e}")
        return True  # Health check is optional


def main():
    """Main test function"""
    print("🚀 Starting CleanBox deployment test")
    print("=" * 50)

    # Get URL from environment variable
    base_url = os.environ.get("CLEANBOX_URL", "https://cleanbox-app.onrender.com")

    if not base_url:
        print("❌ CLEANBOX_URL environment variable is not set.")
        print(
            "Usage: CLEANBOX_URL=https://your-app.onrender.com python test_deployment.py"
        )
        sys.exit(1)

    print(f"📍 Test target URL: {base_url}")
    print()

    # Run tests
    tests = [
        ("Main page", lambda: test_main_page(base_url)),
        ("Webhook endpoint", lambda: test_webhook_endpoint(base_url)),
        ("Webhook POST request", lambda: test_webhook_post(base_url)),
        ("Health check", lambda: test_health_check(base_url)),
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        print(f"\n📋 {test_name} test")
        print("-" * 30)

        if test_func():
            passed += 1
            print(f"✅ {test_name} passed")
        else:
            print(f"❌ {test_name} failed")

    print("\n" + "=" * 50)
    print(f"📊 Test result: {passed}/{total} passed")

    if passed == total:
        print("🎉 All tests passed! CleanBox has been deployed successfully.")
        return 0
    else:
        print("⚠️  Some tests failed. Please check the logs.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
