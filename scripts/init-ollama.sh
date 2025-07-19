#!/bin/bash

# Ollama 초기화 스크립트
# 이 스크립트는 Ollama 서비스가 시작되고 필요한 모델을 다운로드합니다.

set -e

echo "🚀 Ollama 초기화 시작..."

# Ollama 서비스가 시작될 때까지 대기
echo "⏳ Ollama 서비스 시작 대기 중..."
until curl -s http://ollama:11434/api/tags > /dev/null 2>&1; do
    echo "Ollama 서비스가 아직 준비되지 않았습니다. 10초 후 재시도..."
    sleep 10
done

echo "✅ Ollama 서비스가 시작되었습니다."

# 필요한 모델 목록
MODELS=("llama2:7b-chat-q4_0")

# 각 모델 확인 및 다운로드
for model in "${MODELS[@]}"; do
    echo "🔍 모델 확인 중: $model"
    
    # 모델이 이미 있는지 확인
    if curl -s http://ollama:11434/api/tags | grep -q "\"name\":\"$model\""; then
        echo "✅ 모델이 이미 존재합니다: $model"
    else
        echo "📥 모델 다운로드 중: $model"
        ollama pull "$model"
        echo "✅ 모델 다운로드 완료: $model"
    fi
done

echo "🎉 Ollama 초기화 완료!"
echo "사용 가능한 모델:"
ollama list

echo "🎉 Ollama 초기화가 성공적으로 완료되었습니다!"

# 스크립트 완료 후 종료
exit 0 