# syntax=docker/dockerfile:1
FROM python:3.11-slim

# System package update and required tool installation (all at once)
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    ca-certificates \
    procps \
    curl \
    gcc \
    g++ \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy and install Python dependencies (cache optimized)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Install Playwright browser
RUN playwright install chromium
RUN playwright install-deps chromium

# Playwright environment variable
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Memory limit and performance optimization environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV CHROME_HEADLESS=1
ENV CHROME_NO_SANDBOX=1
ENV CHROME_DISABLE_DEV_SHM=1

# Memory limit settings (Render free plan standard)
ENV NODE_OPTIONS="--max-old-space-size=128"
ENV CHROME_MEMORY_LIMIT=128

# Copy application code (copy at the end to leverage cache)
COPY . .

# Expose port
EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

# Run application
CMD ["gunicorn", "--config", "gunicorn.conf.py", "app:app"] 