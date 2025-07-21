#!/usr/bin/env python3
"""
Playwright browser installation status check script
"""

import os
import subprocess
import sys


def check_playwright_installation():
    """Check Playwright installation status"""
    print("🔍 Checking Playwright installation status")

    try:
        # Check Playwright version
        result = subprocess.run(
            ["playwright", "--version"], capture_output=True, text=True
        )
        if result.returncode == 0:
            print(f"✅ Playwright version: {result.stdout.strip()}")
        else:
            print(f"❌ Playwright installation failed: {result.stderr}")
            return False
    except FileNotFoundError:
        print("❌ Playwright command not found")
        return False

    return True


def check_browser_installation():
    """Check browser installation status"""
    print("\n🔍 Checking browser installation status")

    try:
        # Check browser installation
        result = subprocess.run(
            ["playwright", "install", "chromium", "--dry-run"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print("✅ Chromium browser installed")
        else:
            print(f"❌ Chromium browser installation failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Error while checking browser: {str(e)}")
        return False

    return True


def check_browser_path():
    """Check browser path"""
    print("\n🔍 Checking browser path")

    # Check environment variable
    playwright_browsers_path = os.environ.get(
        "PLAYWRIGHT_BROWSERS_PATH", "/ms-playwright"
    )
    print(f"📝 PLAYWRIGHT_BROWSERS_PATH: {playwright_browsers_path}")

    # Check browser executable path (including wildcard pattern)
    import glob

    chrome_paths = [
        os.path.join(playwright_browsers_path, "chromium-*/chrome-linux/chrome"),
        os.path.join(playwright_browsers_path, "chromium-*/chrome-linux/chromium"),
        "/root/.cache/ms-playwright/chromium-*/chrome-linux/chrome",
        "/root/.cache/ms-playwright/chromium-*/chrome-linux/chromium",
        "~/.cache/ms-playwright/chromium-*/chrome-linux/chrome",
        "~/.cache/ms-playwright/chromium-*/chrome-linux/chromium",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/usr/bin/google-chrome",
    ]

    for path_pattern in chrome_paths:
        if "*" in path_pattern:
            # Handle wildcard pattern
            matches = glob.glob(path_pattern)
            if matches:
                print(f"✅ Chromium executable found: {matches[0]}")
                return True
        elif os.path.exists(path_pattern):
            print(f"✅ Chromium executable found: {path_pattern}")
            return True

    print("❌ Chromium executable not found")
    return False


def install_browsers():
    """Install browsers"""
    print("\n🔧 Trying to install browsers")

    try:
        # Install Chromium
        result = subprocess.run(
            ["playwright", "install", "chromium"], capture_output=True, text=True
        )
        if result.returncode == 0:
            print("✅ Chromium installed successfully")
        else:
            print(f"❌ Chromium installation failed: {result.stderr}")
            return False

        # Install dependencies
        result = subprocess.run(
            ["playwright", "install-deps", "chromium"], capture_output=True, text=True
        )
        if result.returncode == 0:
            print("✅ Browser dependencies installed successfully")
        else:
            print(f"❌ Browser dependencies installation failed: {result.stderr}")
            return False

    except Exception as e:
        print(f"❌ Error during browser installation: {str(e)}")
        return False

    return True


def main():
    """Main function"""
    print("🚀 Playwright browser status check start")
    print("=" * 50)

    # 1. Check Playwright installation
    playwright_ok = check_playwright_installation()

    # 2. Check browser installation
    browser_ok = check_browser_installation()

    # 3. Check browser path
    path_ok = check_browser_path()

    print("\n📊 Summary:")
    print(f"Playwright installation: {'✅' if playwright_ok else '❌'}")
    print(f"Browser installation: {'✅' if browser_ok else '❌'}")
    print(f"Browser path: {'✅' if path_ok else '❌'}")

    if not (playwright_ok and browser_ok and path_ok):
        print("\n🔧 Trying to fix issues...")
        if install_browsers():
            print("✅ Browser installation complete")
        else:
            print("❌ Browser installation failed")
            sys.exit(1)
    else:
        print("\n✅ All checks passed!")


if __name__ == "__main__":
    main()
