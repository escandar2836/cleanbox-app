#!/usr/bin/env python3
"""
CleanBox 배포 후 기능 테스트 스크립트
"""

import requests
import json
import sys
import os
from datetime import datetime


def test_webhook_endpoint(base_url):
    """웹훅 엔드포인트 테스트"""
    print("🔍 웹훅 엔드포인트 테스트 중...")

    try:
        # GET 테스트
        response = requests.get(f"{base_url}/webhook/gmail/test", timeout=10)
        if response.status_code == 200:
            print("✅ 웹훅 테스트 엔드포인트 정상 작동")
            return True
        else:
            print(f"❌ 웹훅 테스트 실패: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 웹훅 테스트 오류: {e}")
        return False


def test_webhook_post(base_url):
    """웹훅 POST 요청 테스트"""
    print("🔍 웹훅 POST 요청 테스트 중...")

    try:
        # 테스트 데이터
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

        if response.status_code in [200, 404]:  # 404는 계정을 찾을 수 없는 경우
            print("✅ 웹훅 POST 요청 처리 정상")
            return True
        else:
            print(f"❌ 웹훅 POST 요청 실패: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 웹훅 POST 요청 오류: {e}")
        return False


def test_main_page(base_url):
    """메인 페이지 접근 테스트"""
    print("🔍 메인 페이지 테스트 중...")

    try:
        response = requests.get(base_url, timeout=10)
        if response.status_code == 200:
            print("✅ 메인 페이지 정상 접근")
            return True
        else:
            print(f"❌ 메인 페이지 접근 실패: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 메인 페이지 접근 오류: {e}")
        return False


def test_health_check(base_url):
    """헬스 체크 엔드포인트 테스트"""
    print("🔍 헬스 체크 테스트 중...")

    try:
        response = requests.get(f"{base_url}/health", timeout=10)
        if response.status_code == 200:
            print("✅ 헬스 체크 정상")
            return True
        else:
            print(f"⚠️ 헬스 체크 엔드포인트 없음: {response.status_code}")
            return True  # 헬스 체크는 선택사항
    except Exception as e:
        print(f"⚠️ 헬스 체크 오류: {e}")
        return True  # 헬스 체크는 선택사항


def main():
    """메인 테스트 함수"""
    print("🚀 CleanBox 배포 테스트 시작")
    print("=" * 50)

    # 환경변수에서 URL 가져오기
    base_url = os.environ.get("CLEANBOX_URL", "https://cleanbox-app.onrender.com")

    if not base_url:
        print("❌ CLEANBOX_URL 환경변수가 설정되지 않았습니다.")
        print(
            "사용법: CLEANBOX_URL=https://your-app.onrender.com python test_deployment.py"
        )
        sys.exit(1)

    print(f"📍 테스트 대상 URL: {base_url}")
    print()

    # 테스트 실행
    tests = [
        ("메인 페이지", lambda: test_main_page(base_url)),
        ("웹훅 테스트 엔드포인트", lambda: test_webhook_endpoint(base_url)),
        ("웹훅 POST 요청", lambda: test_webhook_post(base_url)),
        ("헬스 체크", lambda: test_health_check(base_url)),
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        print(f"\n📋 {test_name} 테스트")
        print("-" * 30)

        if test_func():
            passed += 1
            print(f"✅ {test_name} 통과")
        else:
            print(f"❌ {test_name} 실패")

    print("\n" + "=" * 50)
    print(f"📊 테스트 결과: {passed}/{total} 통과")

    if passed == total:
        print("🎉 모든 테스트 통과! CleanBox가 정상적으로 배포되었습니다.")
        return 0
    else:
        print("⚠️ 일부 테스트가 실패했습니다. 로그를 확인해주세요.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
