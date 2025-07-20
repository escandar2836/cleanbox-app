# syntax=docker/dockerfile:1
FROM python:3.11-slim

# 시스템 패키지 업데이트 및 필수 도구 설치 (한 번에 처리)
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    ca-certificates \
    procps \
    curl \
    gcc \
    g++ \
    python3-dev \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# 작업 디렉토리 설정
WORKDIR /app

# Python 의존성 복사 및 설치 (캐시 최적화)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Chrome 환경 변수 설정
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver

# 메모리 제한 및 성능 최적화 환경 변수
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV CHROME_HEADLESS=1
ENV CHROME_NO_SANDBOX=1
ENV CHROME_DISABLE_DEV_SHM=1

# 메모리 제한 설정 (Render 무료 플랜 기준)
ENV NODE_OPTIONS="--max-old-space-size=128"
ENV CHROME_MEMORY_LIMIT=128

# 애플리케이션 코드 복사 (마지막에 복사하여 캐시 활용)
COPY . .

# 포트 노출
EXPOSE 8000

# 헬스체크 추가
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

# 애플리케이션 실행
CMD ["gunicorn", "--config", "gunicorn.conf.py", "app:app"] 