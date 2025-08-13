import os

# API auth
SCANNER_API_KEY = "your-scanner-api-key"
NETBOX_API_TOKEN = "your-netbox-api-key"

# Netbox server IP
ALLOWED_SOURCE = "netbox-server-ip"
NETBOX_URL = "http://netbox-server-ip:8001"

# Threading
MAX_WORKERS = 3
MAX_CONCURRENT_IP_SCANS = 128
SCAN_TIMEOUT = 3600

#API server
API_IP= "0.0.0.0" #Listening IP for Scanner
API_PORT= 5001    #Listening Port for Scanner

# Logging
LOG_PATH = "/var/log/netbox_scanner_api.log"
LOG_LEVEL  = "WARNING"
LOG_MAX_BYTES = 10000000
LOG_BACKUP_COUNT = 2
