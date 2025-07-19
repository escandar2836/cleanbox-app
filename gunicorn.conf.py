import os

# Gunicorn 설정
bind = f"0.0.0.0:{os.environ.get('PORT', '5000')}"
workers = 2
worker_class = "sync"
worker_connections = 1000
timeout = 30
keepalive = 2
max_requests = 1000
max_requests_jitter = 50

# 로깅 설정
accesslog = "-"
errorlog = "-"
loglevel = "info"

# 프로세스 이름
proc_name = "cleanbox"

# 환경 변수
raw_env = ["CLEANBOX_ENV=production"]
