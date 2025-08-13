#!/usr/bin/env python3
import re
import ipaddress

from flask import Flask, request, jsonify
from functools import wraps
from concurrent.futures import ThreadPoolExecutor

from logging_setup import setup_logger
from scanner import scan_ip, scan_prefix
from config import SCANNER_API_KEY, ALLOWED_SOURCE, MAX_WORKERS, API_PORT, API_IP

app = Flask(__name__)
logger = setup_logger('scanner_api')

app.config["MAX_CONTENT_LENGTH"] = 1024

executor = ThreadPoolExecutor(max_workers=int(MAX_WORKERS))

def require_auth(f):
    @wraps(f)
    def inner(*args, **kwargs):
        src = request.headers.get("X-Forwarded-For", request.remote_addr).split(",")[0].strip()
        if ALLOWED_SOURCE and src != ALLOWED_SOURCE:
            app.logger.warning(f"Blocked request from {src}")
            return jsonify(error="forbidden"), 403

        key = request.headers.get("X-API-KEY", "")
        if key != SCANNER_API_KEY:
            app.logger.warning(f"Invalid API key from {src}")
            return jsonify(error="unauthorized"), 401

        return f(*args, **kwargs)
    return inner


def sanitize(val: str) -> str:
    return re.sub(r"[^0-9A-Fa-f\.:/\-]", "", val or "")


@app.errorhandler(413)
def too_large(_):
    # Triggered by MAX_CONTENT_LENGTH
    return jsonify(error="request_too_large"), 413


@app.route("/scan/ip", methods=["POST"])
@require_auth
def ip_endpoint():
    # Enforce JSON content-type
    if request.mimetype != "application/json":
        return jsonify(error="content_type_must_be_json"), 415

    data = request.get_json(silent=True) or {}
    ip = sanitize(data.get("ip", ""))

    try:
        ipaddress.ip_address(ip)
    except ValueError:
        return jsonify(error="invalid_ip"), 400

    executor.submit(scan_ip, ip, 32)
    app.logger.info(f"Queued IP scan: {ip}")
    return jsonify(status=f"queued ip {ip}"), 202


@app.route("/scan/prefix", methods=["POST"])
@require_auth
def prefix_endpoint():
    # Enforce JSON content-type
    if request.mimetype != "application/json":
        return jsonify(error="content_type_must_be_json"), 415

    data = request.get_json(silent=True) or {}
    pref = sanitize(data.get("prefix", ""))

    try:
        ipaddress.ip_network(pref, strict=False)
    except ValueError:
        return jsonify(error="invalid_prefix"), 400

    executor.submit(scan_prefix, pref)
    app.logger.info(f"Queued prefix scan: {pref}")
    return jsonify(status=f"queued prefix {pref}"), 202


@app.route("/healthz", methods=["GET"])
def health():
    return jsonify(status="ok"), 200


if __name__ == "__main__":
    app.run(host=API_IP, port=int(API_PORT))
