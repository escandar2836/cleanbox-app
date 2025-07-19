#!/bin/bash

# 서비스 대기 스크립트
# PostgreSQL과 Ollama가 완전히 준비될 때까지 대기합니다.

set -e

echo "🔍 서비스 준비 상태 확인 중..."

# 환경변수 검증
echo "🔍 환경변수 검증 중..."
python scripts/validate-env.py

# PostgreSQL 대기
echo "⏳ PostgreSQL 연결 확인 중..."
until pg_isready -h postgres -U $POSTGRES_USER -d $POSTGRES_DB; do
    echo "PostgreSQL이 아직 준비되지 않았습니다. 5초 후 재시도..."
    sleep 5
done
echo "✅ PostgreSQL 연결 성공!"

# Ollama 대기 (선택적)
echo "⏳ Ollama 서비스 확인 중..."
max_retries=30
retry_count=0

while [ $retry_count -lt $max_retries ]; do
    if curl -s http://ollama:11434/api/tags > /dev/null 2>&1; then
        echo "✅ Ollama 서비스 연결 성공!"
        break
    fi
    echo "Ollama가 아직 준비되지 않았습니다. 10초 후 재시도... ($((retry_count + 1))/$max_retries)"
    sleep 10
    retry_count=$((retry_count + 1))
done

if [ $retry_count -eq $max_retries ]; then
    echo "⚠️  Ollama 서비스 연결 실패. CleanBox는 계속 시작됩니다."
fi

echo "🎉 모든 서비스가 준비되었습니다!"
echo "CleanBox를 시작합니다..."

# 원래 명령어 실행
exec "$@" 