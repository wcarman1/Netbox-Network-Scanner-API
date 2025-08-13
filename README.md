# Netbox Network Scanner API Service Setup

This guide explains how to deploy the standalone scan server that receives requests from NetBox Network Scanner Plugin and runs your network scans.

## Prerequisites

- A Linux server (Tested on Rocky 9.6) 
- Uses `python3` `python3-pip` `fping` `iproute`
- A user in netbox to use for updating IPAM from the scanner. I used `NetboxScanner` with permissions to IP Address and Prefix (view, add, change).
- Create an API Key (with write enabled) in Netbox for the user.

## 1. Create a Virtualenv & Install

```bash
dnf install -y epel-release
dnf install -y python3 python3-pip fping iproute
cd /opt
git clone https://github.com/wcarman1/Netbox-Network-Scanner-API.git netbox-scanner-api
cd netbox-scanner-api
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 2. update config.py

```
SCANNER_API_KEY = "your-scanner-api-key"
NETBOX_API_TOKEN = "your-netbox-api-key"

ALLOWED_SOURCE = "netbox-server-ip"
NETBOX_URL = "http://netbox-server-ip:8001"
```
  tip: if you'd like to generate an api key run `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`

## 3. Create and Start Service
```bash
ln -s /opt/netbox-scanner-api/netbox-scanner-api.service /etc/systemd/system/netbox-scanner-api.service
sudo systemctl daemon-reload
systemctl enable --now netbox-scanner-api
```

## 4. Verify & Test

- **Health check**: `curl http://localhost:5001/healthz` or from netbox server `curl http://scanner-ip:5001/healthz`
- Test (from netbox server or ALLOWED_SOURCE):
```bash
curl -sS -X POST http://API-server-IP:5001/scan/ip \
  -H "X-API-KEY: your-scanner-api-key" \
  --json '{"ip":"10.0.0.5"}'
```
You should see: `{"status":"queued ip 10.0.0.5"}`

## 5. Logging
setup log rotate
```bash
ln -s /opt/netbox-scanner-api/netbox-scanner-api /etc/logrotate.d/netbox-scanner-api
```

## 6. Troubleshooting

- Check application logs: `/var/log/netbox_scanner_api.log`
- Check systemd logs: `journalctl -u netbox-scanner-api`
- Ensure NetboxScanner user has proper write permissions in NetBox.
- When testing make sure you test from the device sat as ALLOWED_SOURCE
