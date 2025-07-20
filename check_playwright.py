#!/usr/bin/env python3
"""
Playwright 브라우저 설치 상태 확인 스크립트
"""

import os
import subprocess
import sys


def check_playwright_installation():
    """Playwright 설치 상태 확인"""
    print("🔍 Playwright 설치 상태 확인")

    try:
        # Playwright 버전 확인
        result = subprocess.run(
            ["playwright", "--version"], capture_output=True, text=True
        )
        if result.returncode == 0:
            print(f"✅ Playwright 버전: {result.stdout.strip()}")
        else:
            print(f"❌ Playwright 설치 안됨: {result.stderr}")
            return False
    except FileNotFoundError:
        print("❌ Playwright 명령어를 찾을 수 없습니다")
        return False

    return True


def check_browser_installation():
    """브라우저 설치 상태 확인"""
    print("\n🔍 브라우저 설치 상태 확인")

    try:
        # 브라우저 설치 확인
        result = subprocess.run(
            ["playwright", "install", "chromium", "--dry-run"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print("✅ Chromium 브라우저 설치됨")
        else:
            print(f"❌ Chromium 브라우저 설치 안됨: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ 브라우저 확인 중 오류: {str(e)}")
        return False

    return True


def check_browser_path():
    """브라우저 경로 확인"""
    print("\n🔍 브라우저 경로 확인")

    # 환경 변수 확인
    playwright_browsers_path = os.environ.get(
        "PLAYWRIGHT_BROWSERS_PATH", "/ms-playwright"
    )
    print(f"📝 PLAYWRIGHT_BROWSERS_PATH: {playwright_browsers_path}")

    # 브라우저 실행 파일 경로 확인
    chromium_path = os.path.join(
        playwright_browsers_path, "chromium-1091/chrome-linux/chrome"
    )
    if os.path.exists(chromium_path):
        print(f"✅ Chromium 실행 파일 발견: {chromium_path}")
        return True
    else:
        print(f"❌ Chromium 실행 파일 없음: {chromium_path}")

        # 다른 가능한 경로들 확인
        possible_paths = [
            os.path.join(playwright_browsers_path, "chromium-*/chrome-linux/chrome"),
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
        ]

        for path in possible_paths:
            if os.path.exists(path):
                print(f"✅ 대체 경로 발견: {path}")
                return True

        return False


def install_browsers():
    """브라우저 설치"""
    print("\n🔧 브라우저 설치 시도")

    try:
        # Chromium 설치
        result = subprocess.run(
            ["playwright", "install", "chromium"], capture_output=True, text=True
        )
        if result.returncode == 0:
            print("✅ Chromium 설치 성공")
        else:
            print(f"❌ Chromium 설치 실패: {result.stderr}")
            return False

        # 의존성 설치
        result = subprocess.run(
            ["playwright", "install-deps", "chromium"], capture_output=True, text=True
        )
        if result.returncode == 0:
            print("✅ 브라우저 의존성 설치 성공")
        else:
            print(f"❌ 브라우저 의존성 설치 실패: {result.stderr}")
            return False

    except Exception as e:
        print(f"❌ 브라우저 설치 중 오류: {str(e)}")
        return False

    return True


def main():
    """메인 함수"""
    print("🚀 Playwright 브라우저 상태 확인")
    print("=" * 50)

    # 1. Playwright 설치 확인
    playwright_ok = check_playwright_installation()

    # 2. 브라우저 설치 확인
    browser_ok = check_browser_installation()

    # 3. 브라우저 경로 확인
    path_ok = check_browser_path()

    print("\n📊 결과 요약:")
    print(f"Playwright 설치: {'✅' if playwright_ok else '❌'}")
    print(f"브라우저 설치: {'✅' if browser_ok else '❌'}")
    print(f"브라우저 경로: {'✅' if path_ok else '❌'}")

    if not (playwright_ok and browser_ok and path_ok):
        print("\n🔧 문제 해결 시도...")
        if install_browsers():
            print("✅ 브라우저 설치 완료")
        else:
            print("❌ 브라우저 설치 실패")
            sys.exit(1)
    else:
        print("\n✅ 모든 검사 통과!")


if __name__ == "__main__":
    main()
