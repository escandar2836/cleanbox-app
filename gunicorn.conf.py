# Gunicorn settings (optimized for deployment environment)
import multiprocessing

# Server socket
bind = "0.0.0.0:8000"
backlog = 2048

# Worker process
workers = 1  # Use only 1 to save memory
worker_class = "sync"
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 50
preload_app = True
timeout = 120  # Increased from 30s to 120s
keepalive = 2

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process name
proc_name = "cleanbox"

# User/group
user = None
group = None

# Temporary directory
tmp_upload_dir = None

# Security
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

# Memory related settings
max_requests = 100  # Prevent memory leaks
max_requests_jitter = 10
worker_tmp_dir = "/dev/shm"  # Default temp directory for memory

# Debug
reload = False
reload_engine = "auto"
spew = False

# Check
check_config = False
preload_app = True
disable_redirect_access_to_syslog = False

# SSL (if needed)
keyfile = None
certfile = None
