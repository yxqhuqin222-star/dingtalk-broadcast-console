import json
import re
import ssl
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path

import certifi


INVENTORY_TARGET = 30
INVENTORY_MINIMUM = 10
REFRESH_INTERVAL = timedelta(hours=6)
SUMMARY_MIN_LENGTH = 40
SUMMARY_MAX_LENGTH = 180
SUMMARY_NOISE_MARKERS = (
    "供图",
    "图源",
    "■本报记者",
    "文｜",
    "文|",
    "编译|",
)
CATEGORY_KEYWORDS = (
    ("健康", ("医疗", "健康", "医院", "疾病", "药物", "养老", "生物医药")),
    ("科学", ("科学", "科研", "研究", "实验", "论文", "核聚变", "天文")),
    (
        "科技",
        (
            "AI",
            "人工智能",
            "芯片",
            "机器人",
            "手机",
            "软件",
            "汽车",
            "电池",
            "互联网",
            "数据中心",
            "鸿蒙",
            "iPhone",
            "Apple",
            "智能",
        ),
    ),
    ("生活", ("生活", "家居", "客厅", "租房", "电影", "游戏", "阅读")),
)
QUALITY_FEEDS = (
    ("科学网", "科学", "https://www.sciencenet.cn/xml/news-0.aspx?di=0"),
    ("少数派", "数字生活", "https://sspai.com/feed"),
    ("爱范儿", "科技", "https://www.ifanr.com/feed"),
    ("36氪", "商业", "https://36kr.com/feed"),
    ("钛媒体", "商业科技", "https://www.tmtpost.com/rss.xml"),
)


class _TextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def _html_to_text(value):
    parser = _TextParser()
    parser.feed(value or "")
    return " ".join("".join(parser.parts).split())


def _clean_summary(value):
    value = _html_to_text(value)
    value = value.split("#欢迎关注", 1)[0].rstrip()
    value = re.sub(
        r"^作者\s*\|\s*\S+\s+编辑\s*\|\s*\S+\s*",
        "",
        value,
    )
    for suffix in ("查看全文", "阅读原文"):
        if suffix in value:
            value = value.split(suffix, 1)[0].rstrip("。；;，, ")
    if value.endswith(("...", "…")):
        shortened = value.rstrip(".… ")
        boundary = max(
            shortened.rfind(mark)
            for mark in ("。", "！", "？", "；")
        )
        value = shortened[: boundary + 1] if boundary >= SUMMARY_MIN_LENGTH else ""
    if len(value) > SUMMARY_MAX_LENGTH:
        shortened = value[: SUMMARY_MAX_LENGTH + 1]
        boundary = max(
            shortened.rfind(mark)
            for mark in ("。", "！", "？", "；")
        )
        value = shortened[: boundary + 1] if boundary >= SUMMARY_MIN_LENGTH else ""
    value = re.sub(r"^■\S+\s+", "", value)
    return value.lstrip("·.• \t").strip()


def _category_for_item(item):
    text = f"{item['title']} {item['summary']}"
    for category, keywords in CATEGORY_KEYWORDS:
        if any(keyword in text for keyword in keywords):
            return category
    return item["default_category"]


def _clean_url(value):
    parsed = urllib.parse.urlsplit(value.strip())
    query = [
        (key, item)
        for key, item in urllib.parse.parse_qsl(
            parsed.query,
            keep_blank_values=True,
        )
        if not key.startswith("utm_") and key not in {"f", "from"}
    ]
    return urllib.parse.urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urllib.parse.urlencode(query),
            "",
        )
    )


def _local_name(tag):
    return tag.rsplit("}", 1)[-1]


def _child_text(element, *names):
    for child in element:
        if _local_name(child.tag) in names:
            return "".join(child.itertext()).strip()
    return ""


def parse_feed(xml, source, default_category):
    root = ET.fromstring(xml)
    result = []
    for entry in root.iter():
        if _local_name(entry.tag) not in ("item", "entry"):
            continue
        link = _child_text(entry, "link")
        if not link:
            link_node = next(
                (
                    child
                    for child in entry
                    if _local_name(child.tag) == "link" and child.get("href")
                ),
                None,
            )
            link = link_node.get("href", "") if link_node is not None else ""
        item = {
            "source": source,
            "default_category": default_category,
            "title": _html_to_text(_child_text(entry, "title")),
            "summary": _clean_summary(
                _child_text(entry, "description", "summary", "content")
            ),
            "published_at": _html_to_text(
                _child_text(entry, "pubDate", "published", "updated")
            ),
            "url": _clean_url(link),
        }
        if (
            item["title"]
            and SUMMARY_MIN_LENGTH <= len(item["summary"]) <= SUMMARY_MAX_LENGTH
            and not any(
                marker in item["summary"]
                for marker in SUMMARY_NOISE_MARKERS
            )
            and item["url"]
        ):
            result.append(item)
    return result


def fetch_feed_candidates(feeds=QUALITY_FEEDS):
    context = ssl.create_default_context(cafile=certifi.where())
    source_items = []
    for source, category, url in feeds:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "jump-dingtalk-broadcast/1.0"},
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=20,
                context=context,
            ) as response:
                source_items.append(
                    parse_feed(response.read(), source, category)
                )
        except (OSError, ET.ParseError):
            continue
    candidates = []
    for index in range(max((len(items) for items in source_items), default=0)):
        for items in source_items:
            if index < len(items):
                candidates.append(items[index])
    return candidates


def load_inventory(path):
    path = Path(path)
    if not path.exists():
        return {
            "cards": [],
            "sent_urls": [],
            "last_category": "",
            "last_refresh_at": "",
            "last_error": "",
        }
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("cards", [])
    data.setdefault("sent_urls", [])
    data.setdefault("last_category", "")
    data.setdefault("last_refresh_at", "")
    data.setdefault("last_error", "")
    return data


def save_inventory(path, inventory):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def refresh_inventory(path, force=False, target=INVENTORY_TARGET):
    inventory = load_inventory(path)
    if len(inventory["cards"]) >= target:
        return inventory
    if not force and inventory["last_refresh_at"]:
        last_refresh = datetime.fromisoformat(inventory["last_refresh_at"])
        if datetime.now() - last_refresh < REFRESH_INTERVAL:
            return inventory
    inventory["last_refresh_at"] = datetime.now().isoformat(timespec="seconds")
    known_urls = {
        *inventory["sent_urls"],
        *(card["source_url"] for card in inventory["cards"]),
    }
    candidates = [
        item
        for item in fetch_feed_candidates()
        if item["url"] not in known_urls
    ]
    needed = target - len(inventory["cards"])
    inventory["cards"].extend(
        {
            "category": _category_for_item(item),
            "title": item["title"],
            "summary": item["summary"],
            "source": item["source"],
            "source_url": item["url"],
            "published_at": item["published_at"],
        }
        for item in candidates[:needed]
    )
    inventory["last_error"] = ""
    save_inventory(path, inventory)
    return inventory


def select_card(inventory):
    last_category = inventory.get("last_category", "")
    counts = Counter(
        card["category"]
        for card in inventory.get("cards", [])
        if card["category"] != last_category
    )
    if not counts:
        return None
    category = counts.most_common(1)[0][0]
    return next(
        (
            card
            for card in inventory.get("cards", [])
            if card["category"] == category
        ),
        None,
    )


def mark_card_sent(inventory, card):
    inventory["cards"] = [
        item
        for item in inventory["cards"]
        if item["source_url"] != card["source_url"]
    ]
    inventory["sent_urls"] = sorted(
        {*inventory["sent_urls"], card["source_url"]}
    )
    inventory["last_category"] = card["category"]
    return inventory
