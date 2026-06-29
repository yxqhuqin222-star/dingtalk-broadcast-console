#!/usr/bin/env python3
import base64
import hashlib
import hmac
import json
import os
import ssl
import time
import urllib.parse
import urllib.request
from pathlib import Path

import certifi


def load_local_env():
    for path in (Path(__file__).resolve().parent / ".env.local", Path(__file__).resolve().parent / ".env"):
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_local_env()


def signed_webhook(webhook, secret):
    if not secret:
        return webhook
    timestamp = str(round(time.time() * 1000))
    string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), string_to_sign, hashlib.sha256).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(digest))
    separator = "&" if "?" in webhook else "?"
    return f"{webhook}{separator}timestamp={timestamp}&sign={sign}"


def add_at_text(message, at_mobiles=None, at_user_ids=None, is_at_all=False):
    if is_at_all:
        return message if "@所有人" in message else f"{message} @所有人"

    at_parts = [f"@{item}" for item in (at_mobiles or []) + (at_user_ids or [])]
    missing_parts = [part for part in at_parts if part not in message]
    if not missing_parts:
        return message
    return f"{message} {' '.join(missing_parts)}"


def send_dingtalk_message(message, at_mobiles=None, at_user_ids=None, is_at_all=False):
    webhook = os.environ.get("DINGTALK_WEBHOOK")
    if not webhook:
        raise RuntimeError("Missing DINGTALK_WEBHOOK environment variable.")

    final_message = add_at_text(message, at_mobiles, at_user_ids, is_at_all)
    payload = json.dumps(
        {
            "msgtype": "text",
            "text": {"content": final_message},
            "at": {
                "atMobiles": at_mobiles or [],
                "atUserIds": at_user_ids or [],
                "isAtAll": is_at_all,
            },
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        signed_webhook(webhook, os.environ.get("DINGTALK_SECRET")),
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(request, timeout=10, context=ssl_context) as response:
        return final_message, json.loads(response.read().decode("utf-8"))
