#!/bin/bash

# Playwright 브라우저 설치 문제 해결 스크립트

echo "🔧 Playwright 브라우저 설치 문제 해결 시작"

# 1. Playwright 재설치
echo "📦 Playwright 재설치..."
pip uninstall playwright -y
pip install playwright==1.40.0

# 2. 브라우저 완전 제거 후 재설치
echo "🧹 기존 브라우저 제거..."
rm -rf /ms-playwright 2>/dev/null || true
rm -rf ~/.cache/ms-playwright 2>/dev/null || true

# 3. 브라우저 재설치
echo "📥 브라우저 재설치..."
playwright install chromium
playwright install-deps chromium

# 4. 설치 확인
echo "✅ 설치 확인..."
playwright install chromium --dry-run

# 5. 브라우저 경로 확인
echo "🔍 브라우저 경로 확인..."
ls -la /ms-playwright/ 2>/dev/null || echo "브라우저 디렉토리 없음"
find /ms-playwright -name "chrome" -type f 2>/dev/null || echo "Chrome 실행 파일 없음"

# 6. 환경 변수 설정
echo "⚙️ 환경 변수 설정..."
export PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
export DISPLAY=:99

echo "✅ Playwright 브라우저 설치 문제 해결 완료"
echo "실행: python check_playwright.py" 