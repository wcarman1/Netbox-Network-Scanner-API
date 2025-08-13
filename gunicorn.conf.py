import os, sys

APP_DIR = os.path.dirname(__file__)
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from config import SCAN_TIMEOUT, MAX_WORKERS, API_PORT, API_IP

bind = f"{API_IP}:{API_PORT}"
workers = int(MAX_WORKERS)
timeout = int(SCAN_TIMEOUT)
max_requests = 1000
max_requests_jitter = 200

accesslog = "-"
errorlog  = "-"
