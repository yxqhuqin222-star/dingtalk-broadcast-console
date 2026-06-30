#!/usr/bin/env python3
import csv
import io
import json
import argparse
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from send_report import (
    DEFAULT_KEYWORD,
    DEFAULT_TEMPLATE,
    build_report_with_filters,
    count_rows_by_filters,
    parse_csv_values,
    send_dingtalk_message,
)


ROOT = Path(__file__).resolve().parent
INDEX_HTML = ROOT / "index.html"
FIXED_CSV_PATH = Path("/Users/kityhello/workplace/project/work/bobao/demo.csv")
DEFAULT_GRADES = "三四五六年级"


def decode_csv(data):
    last_error = None
    for encoding in ("utf-8-sig", "gb18030", "gbk"):
        try:
            text = data.decode(encoding)
            return list(csv.DictReader(io.StringIO(text)))
        except UnicodeDecodeError as error:
            last_error = error
    raise ValueError(f"无法识别 CSV 编码：{last_error}")


def parse_values(column, value):
    value = value.strip()
    if "," in value or "，" in value:
        return {item.strip() for item in value.replace("，", ",").split(",") if item.strip()}
    if column == "课程年级":
        value = value.replace("年级", "")
        return {f"{char}年级" for char in value if char.strip()}
    if "|" in value:
        return {item.strip() for item in value.split("|") if item.strip()}
    return {value}


def build_filters(fields):
    filters = []
    for index in (1, 2):
        column = fields.get(f"filterColumn{index}", "").strip()
        value = fields.get(f"filterValue{index}", "").strip()
        if column and value:
            filters.append((column, parse_values(column, value)))
    return filters


def build_message_payload(rows, fields):
    filters = build_filters(fields)
    amount_column = fields.get("amountColumn", "订单实付金额").strip()
    amount_value = fields.get("amountValue", "1").strip()
    message = build_report_with_filters(
        rows,
        filters=filters,
        amount_column=amount_column,
        amount_value=amount_value,
        template=fields.get("template", DEFAULT_TEMPLATE).strip(),
        keyword=fields.get("keyword", DEFAULT_KEYWORD).strip(),
    )
    count = count_rows_by_filters(rows, filters, amount_column, amount_value)
    return message, count


def json_response(handler, status, payload):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def parse_multipart(headers, body):
    message = BytesParser(policy=policy.default).parsebytes(
        b"Content-Type: "
        + headers.get("Content-Type", "").encode("utf-8")
        + b"\r\nMIME-Version: 1.0\r\n\r\n"
        + body
    )
    fields = {}
    files = {}
    for part in message.iter_parts():
        disposition = part.get_params(header="content-disposition", failobj=[])
        params = {key: value for key, value in disposition}
        name = params.get("name")
        if not name:
            continue
        filename = params.get("filename")
        payload = part.get_payload(decode=True) or b""
        if filename:
            files[name] = payload
        else:
            charset = part.get_content_charset() or "utf-8"
            fields[name] = payload.decode(charset)
    return fields, files


class Handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path not in ("/", "/index.html"):
            self.send_error(404)
            return
        body = INDEX_HTML.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path not in ("/api/broadcast", "/api/preview"):
            self.send_error(404)
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        fields, _ = parse_multipart(self.headers, self.rfile.read(content_length))
        try:
            file_data = FIXED_CSV_PATH.read_bytes()
        except OSError as error:
            json_response(
                self,
                500,
                {"ok": False, "error": f"无法读取固定 CSV 文件 {FIXED_CSV_PATH}：{error}"},
            )
            return

        try:
            rows = decode_csv(file_data)
            message, count = build_message_payload(rows, fields)
            if self.path == "/api/preview":
                json_response(
                    self,
                    200,
                    {"ok": True, "message": message, "count": count, "rows": len(rows)},
                )
                return

            try:
                final_message, dingtalk_result = send_dingtalk_message(
                    message,
                    at_mobiles=parse_csv_values(fields.get("atMobiles", "")),
                    at_user_ids=parse_csv_values(fields.get("atUserIds", "")),
                    is_at_all=fields.get("isAtAll", "").lower() in ("1", "true", "on", "yes"),
                )
            except Exception as error:
                json_response(self, 500, {"ok": False, "message": message, "error": str(error)})
                return
            json_response(
                self,
                200,
                {
                    "ok": dingtalk_result.get("errcode") == 0,
                    "message": final_message,
                    "count": count,
                    "dingtalk": dingtalk_result,
                    "rows": len(rows),
                },
            )
        except Exception as error:
            json_response(self, 500, {"ok": False, "error": str(error)})

    def log_message(self, format, *args):
        return


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"播报配置页：http://127.0.0.1:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
