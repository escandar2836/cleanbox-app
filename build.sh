#!/bin/bash

# Fast build script
echo "🚀 CleanBox fast build start"

# Select build type
BUILD_TYPE=${1:-fast}

case $BUILD_TYPE in
    "fast")
        echo "⚡ Fast build (multi-stage)"
        docker build -f Dockerfile.fast -t cleanbox-app:fast .
        ;;
    "simple")
        echo "📦 Simple build"
        docker build -f Dockerfile.simple -t cleanbox-app:simple .
        ;;
    "optimized")
        echo "🚀 Optimized build"
        docker build -f Dockerfile.optimized -t cleanbox-app:optimized .
        ;;
    "full")
        echo "🔧 Full build"
        docker build -f Dockerfile -t cleanbox-app:full .
        ;;
    "test")
        echo "🧪 Browser install test"
        docker run --rm cleanbox-app:optimized python check_playwright.py
        ;;
    "fix")
        echo "🔧 Browser install issue fix"
        docker run --rm -it cleanbox-app:optimized bash -c "chmod +x fix_playwright.sh && ./fix_playwright.sh"
        ;;
    *)
        echo "❌ Unknown build type: $BUILD_TYPE"
        echo "Usage: ./build.sh [fast|simple|full]"
        exit 1
        ;;
esac

echo "✅ Build complete!"
echo "Run: docker run -p 8000:8000 cleanbox-app:$BUILD_TYPE" 