#!/bin/bash

# Playwright browser install issue fix script

echo "🔧 Starting Playwright browser install issue fix"

# 1. Reinstall Playwright
echo "📦 Reinstalling Playwright..."
pip uninstall playwright -y
pip install playwright==1.40.0

# 2. Remove all browser directories before reinstall
echo "🧹 Removing old browser directories..."
rm -rf /ms-playwright 2>/dev/null || true
rm -rf ~/.cache/ms-playwright 2>/dev/null || true

# 3. Reinstall browser
echo "📤 Reinstalling browser..."
playwright install chromium
playwright install-deps chromium

# 4. Check install
echo "✅ Checking install..."
playwright install chromium --dry-run

# 5. Check browser path
echo "🔍 Checking browser path..."
ls -la /ms-playwright/ 2>/dev/null || echo "No browser directory found"
find /ms-playwright -name "chrome" -type f 2>/dev/null || echo "No Chrome executable found"

# 6. Set environment variables
echo "⚙️  Setting environment variables..."
export PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
export DISPLAY=:99

echo "✅ Playwright browser install issue fix complete"
echo "Run: python check_playwright.py" 