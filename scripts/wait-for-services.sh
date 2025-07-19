#!/bin/bash

# 서비스 대기 스크립트
# PostgreSQL이 완전히 준비될 때까지 대기합니다.

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

echo "🎉 모든 서비스가 준비되었습니다!"
echo "CleanBox를 시작합니다..."

# 원래 명령어 실행
exec "$@" 