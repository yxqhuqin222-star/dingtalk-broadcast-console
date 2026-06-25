#!/usr/bin/env python3
import argparse
import base64
import csv
import hashlib
import hmac
import json
import os
import time
import urllib.parse
import urllib.request
from decimal import Decimal
from pathlib import Path


TARGET_LASTFROM = "out_wxst_wxstqt_1774945025540"
TARGET_GRADES = {"三年级", "四年级", "五年级", "六年级"}
DEFAULT_KEYWORD = "成单"
DEFAULT_TEMPLATE = "{keyword} 小学1元-纷格进量：{count}"


def build_report(csv_path):
    return build_report_from_rows(read_csv_rows(csv_path))


def read_csv_rows(csv_path):
    with csv_path.open("r", encoding="gbk", newline="") as file:
        return list(csv.DictReader(file))


def count_matching_rows(
    rows,
    lastfrom=TARGET_LASTFROM,
    grades=TARGET_GRADES,
    amount_column="订单实付金额",
    amount_value="1",
):
    count = 0
    target_amount = Decimal(str(amount_value))
    for row in rows:
        if row["lastfrom值"] != lastfrom:
            continue
        if row["课程年级"] not in grades:
            continue
        if Decimal(row[amount_column]) == target_amount:
            count += 1
    return count


def count_rows_by_filters(rows, filters, amount_column="订单实付金额", amount_value="1"):
    count = 0
    target_amount = Decimal(str(amount_value))
    for row in rows:
        matched = True
        for column, allowed_values in filters:
            if row.get(column) not in allowed_values:
                matched = False
                break
        if matched and Decimal(row[amount_column]) == target_amount:
            count += 1
    return count


def build_report_from_rows(
    rows,
    lastfrom=TARGET_LASTFROM,
    grades=TARGET_GRADES,
    amount_column="订单实付金额",
    amount_value="1",
    template=DEFAULT_TEMPLATE,
    keyword=DEFAULT_KEYWORD,
):
    count = count_matching_rows(rows, lastfrom, grades, amount_column, amount_value)
    return template.format(count=count, keyword=keyword)


def build_report_with_filters(
    rows,
    filters,
    amount_column="订单实付金额",
    amount_value="1",
    template=DEFAULT_TEMPLATE,
    keyword=DEFAULT_KEYWORD,
):
    count = count_rows_by_filters(rows, filters, amount_column, amount_value)
    return template.format(count=count, keyword=keyword)


def signed_webhook(webhook, secret):
    if not secret:
        return webhook
    timestamp = str(round(time.time() * 1000))
    string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), string_to_sign, hashlib.sha256).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(digest))
    separator = "&" if "?" in webhook else "?"
    return f"{webhook}{separator}timestamp={timestamp}&sign={sign}"


def parse_csv_values(value):
    if not value:
        return []
    return [item.strip() for item in value.replace("，", ",").split(",") if item.strip()]


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
    with urllib.request.urlopen(request, timeout=10) as response:
        return final_message, json.loads(response.read().decode("utf-8"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path", nargs="?", default=Path(__file__).with_name("demo.csv"))
    parser.add_argument("--send", action="store_true")
    args = parser.parse_args()

    message = build_report(Path(args.csv_path))
    print(message)

    if args.send:
        print(send_dingtalk_message(message)[1])


if __name__ == "__main__":
    main()
