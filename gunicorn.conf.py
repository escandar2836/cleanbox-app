# Gunicorn 설정 (배포 환경 최적화)
import multiprocessing

# 서버 소켓
bind = "0.0.0.0:8000"
backlog = 2048

# Worker 프로세스
workers = 1  # 메모리 절약을 위해 1개만 사용
worker_class = "sync"
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 50
preload_app = True
timeout = 120  # 30초 → 120초로 증가
keepalive = 2

# 로깅
accesslog = "-"
errorlog = "-"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# 프로세스 이름
proc_name = "cleanbox"

# 사용자/그룹
user = None
group = None

# 임시 디렉토리
tmp_upload_dir = None

# 보안
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

# 메모리 관련 설정
max_requests = 100  # 메모리 누수 방지
max_requests_jitter = 10
worker_tmp_dir = "/dev/shm"  # 메모리 기반 임시 디렉토리

# 디버그
reload = False
reload_engine = "auto"
spew = False

# 체크
check_config = False
preload_app = True
disable_redirect_access_to_syslog = False

# SSL (필요시)
keyfile = None
certfile = None
