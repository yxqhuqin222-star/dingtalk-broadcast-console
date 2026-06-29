#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import random
import ssl
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, time as clock_time, timedelta
from html.parser import HTMLParser
from pathlib import Path

import certifi

from dingtalk_client import send_dingtalk_message


BROADCAST_SCHEDULE = {
    "morning": "10:00",
    "noon": "11:40",
    "industry": "16:30",
    "countdown": "17:30",
    "evening": "19:00",
}
DEFAULT_STATE_PATH = Path(__file__).with_name(".daily_broadcast_state.json")
DEFAULT_NEWS_STATE_PATH = Path(__file__).with_name(".dadao_message_state.json")
OWEN_LINKS_URL = "https://www.owenyoung.com/links"
JIKE_SELECTED_URL = "https://web.okjike.com/topic/63579abb6724cc583b9bba9a/selected"
DEFAULT_DADAO_SOURCE = "jike"
DADAO_SOURCE_LABELS = {"jike": "即刻精选", "owen": "Owen Links"}
INDUSTRY_ITEM_LIMIT = 10
OWEN_LINKS_PAGE_LIMIT = 11

DEFAULT_ENABLED = {
    "morning": True,
    "noon": True,
    "industry": True,
    "countdown": True,
    "evening": True,
}

LUNCH_OPTIONS = ["盖饭", "麻辣烫", "轻食沙拉", "牛肉面", "饺子", "日式便当", "砂锅粥"]
PSYCHOLOGY_FACTS = [
    "人们通常更容易记住一段信息的开头和结尾，这分别叫首因效应和近因效应。",
    "把未完成的事情记得更牢，常被称为蔡格尼克效应；写下明确的下一步有助于减少它带来的牵挂。",
    "人在判断某件事有多常见时，容易依赖最先想到的例子，这叫可得性启发。",
    "同样一件事用“获得”还是“失去”来描述，可能影响选择，这种现象叫框架效应。",
    "人们往往高估别人对自己外表和失误的关注程度，这被称为聚光灯效应。",
]
HISTORY_FACTS = [
    "古罗马人已经会使用类似现代“快餐店”的热食柜台，考古学家称这类店铺为 thermopolium。",
    "现存最早的纸币之一出现在中国北宋，名为“交子”，最初由民间商户发行。",
    "清明上河图并非只画清明节活动，它更像是一幅北宋城市生活的长卷记录。",
    "拿破仑并没有传说中那么矮；按当时法国计量换算，他的身高大约是 1.68 米。",
    "世界上最早有明确日期的印刷书籍之一，是公元 868 年印制的《金刚经》。",
]
MORNING_EXCERPTS = [
    (
        "“譬如祭坛石门中的落日，寂静的光辉平铺的一刻，地上的每一个坎坷都被映照得灿烂；"
        "譬如在园中最为落寞的时间，一群雨燕便出来高歌，把天地都叫喊得苍凉。”\n"
        "——史铁生《我与地坛》"
    ),
]

WEATHER_CODE_LABELS = {
    0: "晴",
    1: "大部晴朗",
    2: "多云",
    3: "阴",
    45: "有雾",
    48: "雾凇",
    51: "小毛毛雨",
    53: "毛毛雨",
    55: "强毛毛雨",
    56: "冻毛毛雨",
    57: "强冻毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    66: "冻雨",
    67: "强冻雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    77: "米雪",
    80: "小阵雨",
    81: "阵雨",
    82: "强阵雨",
    85: "小阵雪",
    86: "强阵雪",
    95: "雷雨",
    96: "雷雨伴小冰雹",
    99: "雷雨伴大冰雹",
}


@dataclass
class BroadcastConfig:
    city: str = "北京"
    dingtalk_keyword: str | None = None
    weather: str | None = None
    holiday_name: str | None = None
    next_holiday_name: str = "下个假期"
    next_holiday_date: date | None = None
    work_end: clock_time = clock_time(19, 0)
    enabled: dict[str, bool] = field(default_factory=lambda: dict(DEFAULT_ENABLED))
    lunch_options: list[str] = field(default_factory=lambda: list(LUNCH_OPTIONS))
    industry_source: str = DEFAULT_DADAO_SOURCE
    industry_news: list[dict[str, str]] = field(default_factory=list)
    tomorrow_reminders: list[str] = field(default_factory=list)
    sent_fact_ids: dict[str, set[str]] = field(
        default_factory=lambda: {"psychology": set(), "history": set()}
    )


@dataclass
class Broadcast:
    kind: str
    scheduled_at: str
    message: str
    context: dict[str, object]


class OwenLinksParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items = []
        self.current = None
        self.capture_title = False

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "article" and attributes.get("data-format") == "link":
            self.current = {}
            return
        classes = attributes.get("class", "").split()
        if self.current is not None and tag == "a" and "feed-link-title-link" in classes:
            self.current["url"] = attributes.get("href", "")
            self.capture_title = True

    def handle_data(self, data):
        if self.capture_title:
            self.current["title"] = self.current.get("title", "") + data

    def handle_endtag(self, tag):
        if tag == "a" and self.capture_title:
            self.capture_title = False
        if tag == "article" and self.current is not None:
            title = " ".join(self.current.get("title", "").split())
            url = self.current.get("url", "")
            if title and url:
                self.items.append({"title": title, "url": url})
            self.current = None


def parse_owen_links(html):
    parser = OwenLinksParser()
    parser.feed(html)
    return parser.items


def fetch_owen_links(sent_urls=None):
    sent_urls = set(sent_urls or ())
    news = []
    for page in range(1, OWEN_LINKS_PAGE_LIMIT + 1):
        url = OWEN_LINKS_URL
        if page > 1:
            url = f"https://www.owenyoung.com/archive?format=link&view=list&page={page}"
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "jump-dingtalk-broadcast/1.0"},
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                items = parse_owen_links(response.read().decode("utf-8", errors="replace"))
        except OSError:
            break
        for item in items:
            if item["url"] in sent_urls:
                continue
            news.append(item)
            sent_urls.add(item["url"])
            if len(news) == INDUSTRY_ITEM_LIMIT:
                return news
    return news


def parse_date(value):
    if not value:
        return None
    return date.fromisoformat(value)


def parse_time(value):
    hour, minute = value.split(":", 1)
    return clock_time(int(hour), int(minute))


def load_config(path=None):
    config = BroadcastConfig()
    if path:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    else:
        data = {}

    config.city = data.get("city") or os.environ.get("BROADCAST_CITY", config.city)
    config.dingtalk_keyword = data.get("dingtalk_keyword") or os.environ.get("DINGTALK_KEYWORD")
    config.weather = data.get("weather") or os.environ.get("BROADCAST_WEATHER")
    config.holiday_name = data.get("holiday_name") or os.environ.get("BROADCAST_HOLIDAY_NAME")
    config.next_holiday_name = data.get("next_holiday_name") or os.environ.get(
        "BROADCAST_NEXT_HOLIDAY_NAME",
        config.next_holiday_name,
    )
    config.next_holiday_date = parse_date(
        data.get("next_holiday_date") or os.environ.get("BROADCAST_NEXT_HOLIDAY_DATE")
    )
    if data.get("work_end") or os.environ.get("BROADCAST_WORK_END"):
        config.work_end = parse_time(data.get("work_end") or os.environ["BROADCAST_WORK_END"])
    if "enabled" in data:
        config.enabled.update(data["enabled"])
    if data.get("lunch_options"):
        config.lunch_options = data["lunch_options"]
    config.industry_source = data.get("industry_source", DEFAULT_DADAO_SOURCE)
    if config.industry_source not in DADAO_SOURCE_LABELS:
        raise ValueError(f"Unknown industry source: {config.industry_source}")
    if data.get("industry_news"):
        config.industry_news = data["industry_news"]
    if data.get("tomorrow_reminders"):
        config.tomorrow_reminders = data["tomorrow_reminders"]
    return config


def is_workday(day):
    return day.weekday() < 5


def stable_pick(items, day, salt):
    if not items:
        return None
    seed = f"{day.isoformat()}:{salt}"
    return random.Random(seed).choice(items)


def fact_id(fact):
    return hashlib.sha256(" ".join(fact.split()).encode("utf-8")).hexdigest()


def pick_unsent_fact(items, sent_ids, day, salt):
    unsent = [fact for fact in items if fact_id(fact) not in sent_ids]
    return stable_pick(unsent, day, salt)


def format_message(config, lines):
    keyword = config.dingtalk_keyword
    if keyword and not any(keyword in line for line in lines):
        lines = [f"{keyword}｜{lines[0]}"] + lines[1:]
    return "\n".join(lines)


def fetch_json(url):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "jump-dingtalk-broadcast/1.0"},
    )
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(request, timeout=10, context=ssl_context) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_weather(city):
    geocoding_query = urllib.parse.urlencode(
        {"name": city, "count": 1, "language": "zh", "format": "json"}
    )
    geocoding = fetch_json(
        f"https://geocoding-api.open-meteo.com/v1/search?{geocoding_query}"
    )
    locations = geocoding.get("results") or []
    if not locations:
        raise ValueError(f"找不到城市：{city}")

    location = locations[0]
    forecast_query = urllib.parse.urlencode(
        {
            "latitude": location["latitude"],
            "longitude": location["longitude"],
            "current": "temperature_2m,weather_code",
            "daily": (
                "temperature_2m_max,temperature_2m_min,"
                "precipitation_probability_max"
            ),
            "timezone": "auto",
            "forecast_days": 1,
        }
    )
    forecast = fetch_json(f"https://api.open-meteo.com/v1/forecast?{forecast_query}")
    current = forecast["current"]
    daily = forecast["daily"]
    weather = WEATHER_CODE_LABELS.get(current["weather_code"], "天气状况未知")
    temperature = round(current["temperature_2m"])
    high = round(daily["temperature_2m_max"][0])
    low = round(daily["temperature_2m_min"][0])
    rain = round(daily["precipitation_probability_max"][0])
    return f"{weather}，当前 {temperature}℃，今日 {low}～{high}℃，降水概率 {rain}%"


def weather_line(config):
    if config.weather:
        return f"{config.city}天气：{config.weather}"
    try:
        weather = fetch_weather(config.city)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return f"{config.city}天气：暂时无法获取，出门前记得看一眼天气应用"
    return f"{config.city}天气：{weather}"


def holiday_line(config, day):
    if config.holiday_name:
        return f"今日提醒：{config.holiday_name}"
    if config.next_holiday_date:
        days = (config.next_holiday_date - day).days
        if days >= 0:
            return f"假期雷达：距{config.next_holiday_name}还有 {days} 天"
    fact = pick_unsent_fact(
        PSYCHOLOGY_FACTS,
        config.sent_fact_ids["psychology"],
        day,
        "psychology-fact",
    )
    if fact:
        return f"心理学冷知识：{fact}"
    return "心理学冷知识题库已用完，等待补充新内容"


def next_weekend_days(day):
    return 5 - day.weekday() if day.weekday() < 5 else 0


def build_morning(config, day, now_time=None):
    reminder = holiday_line(config, day)
    message = format_message(config, [
        "早安，冯驰。",
        weather_line(config),
        reminder,
        "今日摘抄：",
        stable_pick(MORNING_EXCERPTS, day, "morning-excerpt"),
    ])
    context = {}
    if reminder.startswith("心理学冷知识："):
        fact = reminder.removeprefix("心理学冷知识：")
        context = {"fact": fact, "fact_category": "psychology", "fact_id": fact_id(fact)}
    return Broadcast("morning", BROADCAST_SCHEDULE["morning"], message, context)


def build_noon(config, day, now_time=None):
    fact = pick_unsent_fact(
        HISTORY_FACTS,
        config.sent_fact_ids["history"],
        day,
        "history-fact",
    )
    if fact:
        lines = ["午间历史冷知识。", fact, "吃饭时可以顺手把这个知识点消化掉。"]
        context = {"fact": fact, "fact_category": "history", "fact_id": fact_id(fact)}
    else:
        lines = ["午间历史冷知识。", "历史冷知识题库已用完，等待补充新内容。"]
        context = {}
    return Broadcast("noon", BROADCAST_SCHEDULE["noon"], format_message(config, lines), context)


def build_industry(config, day, now_time=None):
    news = config.industry_news[:INDUSTRY_ITEM_LIMIT]
    source = config.industry_source
    source_label = DADAO_SOURCE_LABELS[source]
    lines = [f"大道消息｜{source_label}。"]
    if not news:
        if source == "jike":
            lines.extend(["需要使用 Chrome 的即刻登录态读取精选内容。", "当前没有可发送的新内容。"])
        else:
            lines.extend(["暂时无法读取 Owen Links。", "今天不发送过期内容。"])
    for index, item in enumerate(news, 1):
        link = f" {item['url']}" if item.get("url") else ""
        if source == "jike":
            validate_jike_item(item)
            metadata = [
                str(value)
                for value in (
                    item.get("author"),
                    item.get("published_at"),
                )
                if value
            ]
            prefix = f"[{'｜'.join(metadata)}] " if metadata else ""
            lines.append(f"{index}. {prefix}{item['content']}")
            if link:
                lines.append(f"原文：{item['url']}")
        else:
            summary = f"：{item['summary']}" if item.get("summary") else ""
            lines.append(f"{index}. {item.get('title', '未命名资讯')}{summary}{link}")
    return Broadcast(
        "industry",
        BROADCAST_SCHEDULE["industry"],
        format_message(config, lines),
        {"news": news, "source": source},
    )


def build_countdown(config, day, now_time=None):
    now_time = now_time or datetime.now().time()
    now_dt = datetime.combine(day, now_time)
    end_dt = datetime.combine(day, config.work_end)
    minutes = max(0, int((end_dt - now_dt).total_seconds() // 60))
    weekend_days = next_weekend_days(day)
    holiday = "今日进度：普通工作日，继续稳步收尾"
    if config.holiday_name:
        holiday = f"今日提醒：{config.holiday_name}"
    elif config.next_holiday_date:
        days = (config.next_holiday_date - day).days
        if days >= 0:
            holiday = f"假期雷达：距{config.next_holiday_name}还有 {days} 天"
    lines = [
        "摸鱼日历。",
        f"距下班约 {minutes // 60} 小时 {minutes % 60} 分钟。",
        f"距周末还有 {weekend_days} 天。",
        holiday,
        "稳住，今天已经进入后半程。",
    ]
    return Broadcast("countdown", BROADCAST_SCHEDULE["countdown"], format_message(config, lines), {"minutes_to_off": minutes})


def build_evening(config, day, now_time=None):
    lines = [
        "晚间收尾。",
        "今天辛苦了，可以给自己留一个清爽的断点。",
        "收工前 5 分钟，把明早第一步写下来就很好。",
    ]
    return Broadcast("evening", BROADCAST_SCHEDULE["evening"], format_message(config, lines), {"reminders": config.tomorrow_reminders[:3]})


BUILDERS = {
    "morning": build_morning,
    "noon": build_noon,
    "industry": build_industry,
    "countdown": build_countdown,
    "evening": build_evening,
}


def build_broadcast(kind, config, day=None, now_time=None, allow_non_workday=False):
    day = day or date.today()
    if kind not in BUILDERS:
        raise ValueError(f"Unknown broadcast kind: {kind}")
    if not config.enabled.get(kind, False):
        return None
    if not allow_non_workday and not is_workday(day):
        return None
    return BUILDERS[kind](config, day, now_time)


def due_broadcasts(config, now=None, sent_keys=None):
    now = now or datetime.now()
    sent_keys = sent_keys or set()
    result = []
    if not is_workday(now.date()):
        return result
    for kind, scheduled_at in BROADCAST_SCHEDULE.items():
        scheduled_time = parse_time(scheduled_at)
        key = f"{now.date().isoformat()}:{kind}"
        if now.time() >= scheduled_time and key not in sent_keys:
            if kind == "industry" and not config.industry_news:
                continue
            broadcast = build_broadcast(kind, config, now.date(), now.time())
            if broadcast:
                result.append((key, broadcast))
    return result


def load_sent_keys(path):
    path = Path(path)
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    return set(data.get("sent_keys", []))


def save_sent_keys(path, sent_keys):
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    data["sent_keys"] = sorted(sent_keys)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_sent_fact_ids(path):
    path = Path(path)
    if not path.exists():
        return {"psychology": set(), "history": set()}
    data = json.loads(path.read_text(encoding="utf-8"))
    facts = data.get("sent_fact_ids", {})
    return {
        "psychology": set(facts.get("psychology", [])),
        "history": set(facts.get("history", [])),
    }


def save_sent_fact_ids(path, sent_fact_ids):
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    data["sent_fact_ids"] = {
        category: sorted(ids)
        for category, ids in sent_fact_ids.items()
    }
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def validate_jike_item(item):
    missing = [
        field
        for field in ("author", "published_at", "content", "url")
        if not item.get(field)
    ]
    if missing:
        raise ValueError(f"Jike item is missing required fields: {', '.join(missing)}")


def news_item_id(source, item):
    if source == "jike":
        validate_jike_item(item)
        content = " ".join(item["content"].split())
        return hashlib.sha256(content.encode("utf-8")).hexdigest()
    if source == "owen":
        url = item.get("url")
        if not url:
            raise ValueError("Owen Links item is missing url.")
        return url
    raise ValueError(f"Unknown industry source: {source}")


def filter_unsent_news(items, source, sent_ids, limit=INDUSTRY_ITEM_LIMIT):
    result = []
    seen = set(sent_ids)
    for item in items:
        item_id = news_item_id(source, item)
        if item_id in seen:
            continue
        result.append(item)
        seen.add(item_id)
        if len(result) == limit:
            break
    return result


def load_sent_news_ids(source, path=DEFAULT_NEWS_STATE_PATH):
    path = Path(path)
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    if "sources" in data:
        return set(data["sources"].get(source, {}).get("sent_ids", []))
    if source == "owen":
        return set(data.get("sent_urls", []))
    return set()


def save_sent_news_ids(path, source, sent_ids):
    path = Path(path)
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        data = {}
    if "sources" not in data:
        old_owen_ids = data.pop("sent_urls", [])
        data["sources"] = {"owen": {"sent_ids": old_owen_ids}}
    data["sources"][source] = {"sent_ids": sorted(sent_ids)}
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_sent_news_urls(path=DEFAULT_NEWS_STATE_PATH):
    return load_sent_news_ids("owen", path)


def save_sent_news_urls(path, sent_urls):
    save_sent_news_ids(path, "owen", sent_urls)


def load_news_file(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("News file must contain a JSON array.")
    return data


def answer_followup(text, last_broadcast=None, config=None, day=None):
    text = text.strip()
    config = config or BroadcastConfig()
    day = day or date.today()
    if text == "/答案":
        answer = (last_broadcast or {}).get("context", {}).get("answer")
        return f"答案：{answer}" if answer else "这条播报没有可揭晓的答案。"
    if text == "/今天吃什么" or "换一个午餐" in text:
        lunch = stable_pick(config.lunch_options, day + timedelta(days=1), "lunch-reroll")
        return f"换一个：{lunch}。"
    if text.startswith("/投票 "):
        topic = text.removeprefix("/投票 ").strip()
        return f"已收到投票题：{topic}\n请大家直接回复选项。"
    if "新闻" in text and last_broadcast and last_broadcast.get("kind") == "industry":
        return "可以展开。请回复第几条，例如：展开第 1 条。"
    return "收到。这个问题可以交给大模型继续回答；当前播报模块会保留最近一条播报上下文。"


def print_broadcast(broadcast):
    if not broadcast:
        print("今天不发送这类播报。")
        return
    print(broadcast.message)


def main():
    parser = argparse.ArgumentParser(description="同事群钉钉机器人日常播报")
    parser.add_argument(
        "kind",
        choices=tuple(BROADCAST_SCHEDULE) + ("due",),
        help="要生成的播报类型；due 会发送当前时间之前尚未发送的播报",
    )
    parser.add_argument("--config", help="JSON 配置文件路径")
    parser.add_argument("--date", help="按指定日期生成，格式 YYYY-MM-DD")
    parser.add_argument("--now", help="当前时间，格式 HH:MM；用于倒计时或 due")
    parser.add_argument("--state", default=str(DEFAULT_STATE_PATH), help="due 模式的已发送状态文件")
    parser.add_argument(
        "--source",
        choices=tuple(DADAO_SOURCE_LABELS),
        help="大道消息来源；默认使用即刻精选，明确指定 owen 时使用 Owen Links",
    )
    parser.add_argument("--items-file", help="即刻精选的浏览器读取结果，JSON 数组格式")
    parser.add_argument("--send", action="store_true", help="发送到钉钉群")
    args = parser.parse_args()

    config = load_config(args.config)
    config.industry_source = args.source or config.industry_source
    day = parse_date(args.date) or date.today()
    now_time = parse_time(args.now) if args.now else None

    if args.kind == "due":
        now = datetime.combine(day, now_time or datetime.now().time())
        sent_keys = load_sent_keys(args.state)
        config.sent_fact_ids = load_sent_fact_ids(args.state)
        sent_news_ids = load_sent_news_ids(config.industry_source)
        industry_key = f"{day.isoformat()}:industry"
        if (
            config.industry_source == "owen"
            and config.enabled.get("industry", False)
            and is_workday(day)
            and now.time() >= parse_time(BROADCAST_SCHEDULE["industry"])
            and industry_key not in sent_keys
        ):
            config.industry_news = fetch_owen_links(sent_news_ids)
        broadcasts = due_broadcasts(config, now, sent_keys)
        if not broadcasts:
            print("当前没有待发送播报。")
            return
        for key, broadcast in broadcasts:
            print_broadcast(broadcast)
            if args.send:
                print(send_dingtalk_message(broadcast.message)[1])
                if broadcast.kind == "industry":
                    sent_news_ids.update(
                        news_item_id(config.industry_source, item)
                        for item in broadcast.context["news"]
                    )
                    save_sent_news_ids(
                        DEFAULT_NEWS_STATE_PATH,
                        config.industry_source,
                        sent_news_ids,
                    )
                if broadcast.context.get("fact_id"):
                    config.sent_fact_ids[broadcast.context["fact_category"]].add(
                        broadcast.context["fact_id"]
                    )
                sent_keys.add(key)
        if args.send:
            save_sent_keys(args.state, sent_keys)
            save_sent_fact_ids(args.state, config.sent_fact_ids)
        return

    config.sent_fact_ids = load_sent_fact_ids(args.state)
    sent_news_ids = set()
    if args.kind == "industry" and config.enabled.get("industry", False):
        sent_news_ids = load_sent_news_ids(config.industry_source)
        if config.industry_source == "owen":
            config.industry_news = fetch_owen_links(sent_news_ids)
        elif args.items_file:
            config.industry_news = filter_unsent_news(
                load_news_file(args.items_file),
                "jike",
                sent_news_ids,
            )
    broadcast = build_broadcast(
        args.kind,
        config,
        day,
        now_time,
        allow_non_workday=args.kind == "industry",
    )
    print_broadcast(broadcast)
    if args.send and broadcast:
        if broadcast.kind == "industry" and not broadcast.context["news"]:
            raise SystemExit("没有可发送的新大道消息，已取消发送。")
        print(send_dingtalk_message(broadcast.message)[1])
        if broadcast.kind == "industry":
            sent_news_ids.update(
                news_item_id(config.industry_source, item)
                for item in broadcast.context["news"]
            )
            save_sent_news_ids(DEFAULT_NEWS_STATE_PATH, config.industry_source, sent_news_ids)
        if broadcast.context.get("fact_id"):
            config.sent_fact_ids[broadcast.context["fact_category"]].add(
                broadcast.context["fact_id"]
            )
            save_sent_fact_ids(args.state, config.sent_fact_ids)


if __name__ == "__main__":
    main()
