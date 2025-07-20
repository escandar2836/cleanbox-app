#!/bin/bash

# 빠른 빌드 스크립트
echo "🚀 CleanBox 빠른 빌드 시작"

# 빌드 타입 선택
BUILD_TYPE=${1:-fast}

case $BUILD_TYPE in
    "fast")
        echo "⚡ 빠른 빌드 (멀티스테이지)"
        docker build -f Dockerfile.fast -t cleanbox-app:fast .
        ;;
    "simple")
        echo "📦 간단한 빌드"
        docker build -f Dockerfile.simple -t cleanbox-app:simple .
        ;;
    "full")
        echo "🔧 전체 빌드"
        docker build -f Dockerfile -t cleanbox-app:full .
        ;;
    *)
        echo "❌ 알 수 없는 빌드 타입: $BUILD_TYPE"
        echo "사용법: ./build.sh [fast|simple|full]"
        exit 1
        ;;
esac

echo "✅ 빌드 완료!"
echo "실행: docker run -p 8000:8000 cleanbox-app:$BUILD_TYPE" 