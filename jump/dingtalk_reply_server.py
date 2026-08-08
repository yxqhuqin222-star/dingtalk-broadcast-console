#!/usr/bin/env python3
import argparse
import json
import logging
import os
import re
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from daily_broadcast import BroadcastConfig, answer_followup
from dingtalk_client import send_dingtalk_message


SYSTEM_PROMPT = (
    "你是一个同事群里的轻量 AI 助手。回答要简短、清楚、友好；"
    "能直接给结论时不要铺垫，默认使用中文。"
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("dingtalk_reply_server")


def json_response(handler, status, payload):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def extract_text(payload):
    text = ""
    if isinstance(payload.get("text"), dict):
        text = payload["text"].get("content", "")
    if not text:
        text = payload.get("content", "")
    if not text and isinstance(payload.get("messageContent"), dict):
        text = payload["messageContent"].get("text", "")
    text = re.sub(r"@\S+\s*", "", text).strip()
    return text


def ensure_keyword(message):
    keyword = os.environ.get("DINGTALK_KEYWORD")
    if keyword and keyword not in message:
        return f"{keyword}｜{message}"
    return message


def send_to_session_webhook(webhook, message):
    payload = json.dumps(
        {"msgtype": "text", "text": {"content": ensure_keyword(message)}},
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        webhook,
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def call_llm(question):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None

    payload = json.dumps(
        {
            "model": os.environ.get("OPENAI_MODEL", "gpt-4.1-mini"),
            "input": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": question},
            ],
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))
    return data.get("output_text")


def build_reply(text, payload=None):
    if not text:
        return "我在。你可以问问题，也可以试试 /今天吃什么、/答案、/投票 A vs B。"

    if any(keyword in text for keyword in ("能干什么", "能干些什么", "你会什么", "帮助", "help")):
        return "\n".join(
            [
                "我现在可以做这些：",
                "1. 回答同事群里的简单问题",
                "2. 处理 /今天吃什么、/答案、/投票 A vs B",
                "3. 阅读早安、三分钟知识卡、行业小报、摸鱼日历等定时播报",
                "4. 配好 OPENAI_API_KEY 后，可以把普通问题交给大模型回答",
            ]
        )

    if text.startswith("/") or any(keyword in text for keyword in ("换一个午餐", "新闻")):
        return answer_followup(text, config=BroadcastConfig(lunch_options=["盖饭", "麻辣烫", "牛肉面", "轻食沙拉"]))

    try:
        llm_reply = call_llm(text)
    except Exception:
        llm_reply = None
    if llm_reply:
        return llm_reply

    return "我收到啦。当前大模型暂时不可用，只能回复内置命令；可以试试 /今天吃什么 或问我“你能干什么”。"


def reply_to_dingtalk(payload, reply):
    session_webhook = payload.get("sessionWebhook") or payload.get("session_webhook")
    if session_webhook:
        return send_to_session_webhook(session_webhook, reply)
    return send_dingtalk_message(ensure_keyword(reply))[1]


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/health":
            self.send_error(404)
            return
        json_response(self, 200, {"ok": True})

    def do_POST(self):
        if self.path != "/dingtalk/callback":
            self.send_error(404)
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        try:
            raw_body = self.rfile.read(content_length).decode("utf-8")
            payload = json.loads(raw_body)
            text = extract_text(payload)
            logger.info("received callback path=%s text=%r", self.path, text)
            reply = build_reply(text, payload)
            dingtalk_result = reply_to_dingtalk(payload, reply)
            logger.info("reply sent reply=%r dingtalk=%r", reply, dingtalk_result)
            json_response(self, 200, {"ok": True, "reply": reply, "dingtalk": dingtalk_result})
        except Exception as error:
            logger.exception("callback failed: %s", error)
            json_response(self, 500, {"ok": False, "error": str(error)})

    def log_message(self, format, *args):
        return


def main():
    parser = argparse.ArgumentParser(description="钉钉机器人 @ 消息回复服务")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8770)
    args, _ = parser.parse_known_args()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"钉钉机器人回复服务：http://{args.host}:{args.port}/dingtalk/callback")
    server.serve_forever()


if __name__ == "__main__":
    main()
