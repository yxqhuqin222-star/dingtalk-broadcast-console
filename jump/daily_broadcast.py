#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import random
import re
import ssl
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
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
EVENING_QUOTES_PATH = Path(
    "/Users/kityhello/workplace/知识库/wenxue/📚 句子控精选 (2).md"
)
EVENING_QUOTES_FALLBACK_PATH = Path(
    "/Users/kityhello/workplace/知识库/wenxue/冬牧场-划线.md"
)
EVENING_CLOSINGS_PATH = Path(__file__).with_name("evening_closings.txt")
EVENING_MILESTONE = "小猪播报100天了～！"
COUNTDOWN_EXPERIENCES_PATH = Path(__file__).with_name(
    "countdown_experiences.json"
)
COUNTDOWN_MODULES = (
    "情绪温度",
    "办公室观察题",
    "一分钟放空",
    "今日小问题",
    "下班通行证",
)
OWEN_LINKS_URL = "https://www.owenyoung.com/links"
JIKE_SELECTED_URL = "https://web.okjike.com/topic/63579abb6724cc583b9bba9a/selected"
DEFAULT_DADAO_SOURCE = "jike"
DADAO_SOURCE_LABELS = {
    "jike": "即刻精选",
    "owen": "Owen Links",
    "wechat": "微信公众号",
    "feeds": "内容订阅",
}
INDUSTRY_ITEM_LIMIT = 10
OWEN_LINKS_PAGE_LIMIT = 11
WECHAT_SUMMARY_LIMIT = 200

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
LEARNING_CARD_MIN_LENGTH = 250
LEARNING_CARD_MAX_LENGTH = 400
LEARNING_THEMES = [
    {
        "id": "psychology",
        "title": "心理学：看见大脑的快捷方式",
        "source": "APA Dictionary of Psychology",
        "source_url": "https://dictionary.apa.org/",
        "cards": [
            {
                "title": "注意力不是无限资源",
                "conclusion": "人的注意力更像一束会移动的聚光灯，而不是能同时照亮所有事情的顶灯。所谓多任务，通常是在不同任务之间快速切换。",
                "example": "一边回群消息一边写方案，看似同时推进，实际每次切换都要重新找回上下文；任务越复杂，重新进入状态的成本越明显。",
                "question": "今天能否给最重要的一项工作留出二十分钟不切换窗口？",
                "extension": "这不是要求全天保持专注，而是把需要深入思考的任务集中处理，把回复消息、查资料等浅任务放进单独时段。",
            },
            {
                "title": "框架会改变选择",
                "conclusion": "同一个结果用“得到”或“失去”来描述，可能让人做出不同选择，这叫框架效应。",
                "example": "“成功率为九成”和“失败率为一成”表达的是同一组数据，但给人的安全感经常不同。产品文案、汇报和新闻标题都会利用这种差异。",
                "question": "遇到重要选择时，能否把描述改写成相反框架再判断一次？",
                "extension": "改写不会自动给出正确答案，但能暴露自己是否被措辞牵着走。最好同时查看绝对数量、比例和时间范围。",
            },
            {
                "title": "未完成的事为何挥之不去",
                "conclusion": "没有结束的任务更容易留在记忆里，常被称为蔡格尼克效应；模糊的未完成状态尤其占用心智。",
                "example": "“准备汇报”会一直让人惦记，而写成“打开文档，列出三个标题”后，大脑更容易把它当成已有去处的任务。",
                "question": "现在最挂心的一件事，能否写成一个五分钟内可开始的动作？",
                "extension": "关键不是立刻做完，而是留下清楚的下一步和恢复线索。下次回来时不用重新判断从哪里开始。",
            },
            {
                "title": "聚光灯并没有一直照着你",
                "conclusion": "人们容易高估别人对自己外表、表达失误和尴尬瞬间的关注，这被称为聚光灯效应。",
                "example": "会议里说错一个词，自己可能反复回想半天，但多数同事很快就把注意力转回自己的任务和感受。",
                "question": "如果别人犯了同样的小错，你会记多久？",
                "extension": "用同一把尺子看自己和别人，能减少无效的自我审查。需要修正的问题及时修正，其余部分不必反复重播。",
            },
            {
                "title": "本周知识拼图",
                "conclusion": "注意力解释我们如何接收信息，框架效应解释措辞如何影响判断，未完成效应和聚光灯效应则解释一些挥之不去的心理负担。",
                "example": "处理复杂工作时，可以先关掉切换入口；做决定时改写正反框架；暂停任务时留下下一步；出现小失误时换成旁观者视角。",
                "question": "本周四个方法中，哪一个最值得下周继续保留？",
                "extension": "它们不是给行为贴标签的诊断工具，而是四个观察角度。先在具体场景中试一次，再判断是否对自己有帮助。",
            },
        ],
    },
    {
        "id": "history",
        "title": "历史：日常生活如何被发明",
        "source": "Encyclopaedia Britannica",
        "source_url": "https://www.britannica.com/",
        "cards": [
            {
                "title": "纸币不是突然出现的",
                "conclusion": "纸币的形成不是一次孤立发明，而是贸易扩大、金属货币携带不便与信用网络共同推动的结果。",
                "example": "北宋四川商人先用交子替代沉重铁钱，后来官方接管发行。新工具先解决真实摩擦，再逐渐形成制度。",
                "question": "今天哪些看似稳定的制度，最初也只是临时解决方案？",
                "extension": "观察一项制度时，除了记住发明者和年份，更值得追问它替代了什么、降低了什么成本，以及谁为信用负责。",
            },
            {
                "title": "古代城市也有快餐",
                "conclusion": "快速购买熟食并不是现代都市才有的需求，人口密集、居住空间有限的古城同样发展出外食网络。",
                "example": "庞贝遗址中的 thermopolium 设有嵌入柜台的大陶罐，向居民出售热食；很多住所并不具备完整厨房。",
                "question": "一种消费习惯背后，是否往往藏着住房和劳动结构？",
                "extension": "从吃饭方式可以反推城市密度、燃料成本和家庭空间。日常器物常常比宏大事件更直接地保存普通人的生活。",
            },
            {
                "title": "时间为什么被切得这么整齐",
                "conclusion": "统一时间不仅是钟表技术的结果，也与铁路、通信和跨地区协作密切相关。",
                "example": "各地按太阳位置使用地方时，在长途铁路出现后会造成时刻表混乱。标准时区让调度和通信拥有共同坐标。",
                "question": "我们习以为常的时间纪律，解决的到底是谁的协作问题？",
                "extension": "技术让精确计时成为可能，组织网络则让统一计时变得必要。很多标准都是在连接规模扩大后才真正普及。",
            },
            {
                "title": "一幅画也能成为城市档案",
                "conclusion": "图像不仅表现审美，也能保存道路、商业、交通和社会分工等历史线索。",
                "example": "《清明上河图》呈现船运、桥梁、店铺和街市活动。研究者会把画面与文献、考古证据对照，而不是把它当成现场照片。",
                "question": "今天的街景照片，百年后可能告诉人们哪些生活细节？",
                "extension": "历史证据需要交叉验证。图像能提供文献没有的细节，也会受到作者选择、表现目的和时代习惯影响。",
            },
            {
                "title": "本周知识拼图",
                "conclusion": "纸币、外食、标准时间和城市图像共同说明：历史并不只由重大事件组成，日常制度也在回应运输、空间与协作成本。",
                "example": "钱太重催生信用凭证，住宅条件推动熟食销售，铁路推动统一时间，城市画卷则留下生活网络的可视记录。",
                "question": "如果研究今天的办公室生活，你会选择哪三件日常物品作为证据？",
                "extension": "把历史看作问题与解决方案的连续变化，会比孤立背诵年份更容易形成结构，也更容易理解制度为何出现。",
            },
        ],
    },
    {
        "id": "science",
        "title": "科学：熟悉世界里的反直觉",
        "source": "NASA Science",
        "source_url": "https://science.nasa.gov/",
        "cards": [
            {
                "title": "我们看到的是过去",
                "conclusion": "光传播需要时间，因此看得越远，就等于看见越早以前的状态；“此刻的宇宙”无法被我们同时看见。",
                "example": "太阳光到达地球约需八分钟。抬头看到的太阳，是它大约八分钟前发出的光形成的图像。",
                "question": "如果所有观察都有延迟，我们平常说的“实时”到底有多实时？",
                "extension": "在日常距离中延迟小到可以忽略，但在天文学尺度上，距离本身就成为时间标尺，望远镜也因此像观察过去的机器。",
            },
            {
                "title": "季节不是因为离太阳远近",
                "conclusion": "地球季节的主要原因是地轴倾斜，而不是公转过程中与太阳距离的简单变化。",
                "example": "北半球倾向太阳时，阳光照射更直接、白昼更长，于是进入夏季；与此同时南半球正经历冬季。",
                "question": "一个听起来直观的解释，是否能同时解释南北半球相反的季节？",
                "extension": "检验解释时，可以寻找它必须同时说明的现象。能解释一个局部事实，却与其他事实冲突的说法通常还不完整。",
            },
            {
                "title": "天空为何不是紫色",
                "conclusion": "短波长光更容易被大气散射，但人眼敏感度、太阳光谱和高层吸收共同影响了我们感知到的天空颜色。",
                "example": "紫光波长比蓝光更短，理论上散射更强；但太阳辐射、臭氧吸收和视觉系统让日间天空主要呈蓝色。",
                "question": "颜色究竟只属于物体，还是光线、环境和观察者共同产生的体验？",
                "extension": "科学解释常由多个机制共同组成。只抓住“短波散射更强”这一条规律，还不足以预测最终的人类视觉结果。",
            },
            {
                "title": "失重并不是没有重力",
                "conclusion": "轨道上的宇航员仍受到地球引力；失重感来自飞船和宇航员一起持续自由落体。",
                "example": "空间站不断向地球下落，同时横向速度足够快，使地球表面持续弯离它，于是形成绕地轨道。",
                "question": "电梯突然下降时短暂变轻的感觉，与轨道失重有什么共同点？",
                "extension": "“没有重量感”和“没有引力”是两件事。区分测量结果与产生结果的机制，是理解反直觉科学现象的关键。",
            },
            {
                "title": "本周知识拼图",
                "conclusion": "光速让远方成为过去，地轴倾斜塑造季节，大气和视觉共同产生蓝天，持续自由落体则创造轨道失重。",
                "example": "四个现象都提醒我们：直觉适合日常尺度，但面对巨大距离、复合机制或持续运动时，需要用模型重新解释。",
                "question": "本周哪个现象最改变你的直觉？你能用两句话向别人解释吗？",
                "extension": "真正理解不只是记住结论，还包括知道旧解释错在哪里、新解释能同时预测哪些现象，以及它的适用范围。",
            },
        ],
    },
    {
        "id": "business",
        "title": "商业：看懂选择背后的成本",
        "source": "Harvard Business Review",
        "source_url": "https://hbr.org/",
        "cards": [
            {
                "title": "真正的成本是放弃了什么",
                "conclusion": "机会成本不是账单上的支出，而是选择一个方案时放弃的最佳替代方案价值。",
                "example": "免费参加两小时会议没有现金支出，但可能放弃了完成方案、拜访客户或休息恢复的机会。",
                "question": "今天占用时间最多的事情，其最佳替代用途是什么？",
                "extension": "机会成本不能把所有可能性相加，只比较最有价值的那个替代选项。它能帮助我们看见“免费”决策中的隐性代价。",
            },
            {
                "title": "沉没成本不该指挥未来",
                "conclusion": "已经发生且无法收回的投入，不应成为继续投入的唯一理由；未来决策要比较新增成本和新增收益。",
                "example": "看了一半但毫无收获的课程，继续看完并不能把过去的时间拿回来，只会决定接下来的时间如何使用。",
                "question": "如果今天才第一次面对这个项目，你还会选择继续吗？",
                "extension": "停止并不代表过去的选择愚蠢，当时的信息可能支持那个决定。成熟的判断是根据当前信息更新，而不是维护一致形象。",
            },
            {
                "title": "指标会改变行为",
                "conclusion": "一旦某个指标成为强目标，人们就会围绕它优化，指标与真实目的之间的偏差也可能随之扩大。",
                "example": "只考核工单关闭数量，可能促使团队拆分工单或过早关闭，而不一定真正提高问题解决质量。",
                "question": "你正在关注的指标，最容易被怎样“做漂亮”？",
                "extension": "指标不是不能用，而是需要配对约束、抽样检查和结果指标。先写清真正目的，再判断数字是否仍是可靠代理。",
            },
            {
                "title": "规模扩大不等于单位成本永远下降",
                "conclusion": "规模经济能摊薄固定成本，但协调复杂度、管理层级和边际需求也可能让规模继续扩大后收益递减。",
                "example": "小团队共享信息靠直接沟通，人数增加后会议、流程和接口都会变多，新增成员未必立即带来同等产出。",
                "question": "当前问题需要更多资源，还是需要减少协调和等待？",
                "extension": "讨论扩张时要区分生产成本与协调成本。前者可能下降，后者却可能快速上升，最终效果取决于两者的合计。",
            },
            {
                "title": "本周知识拼图",
                "conclusion": "机会成本帮助比较替代选择，沉没成本提醒忽略无法收回的投入，指标偏差和规模边界则帮助检查组织优化是否偏离目的。",
                "example": "做决定前问放弃了什么；继续项目前只看未来；设指标时想象如何作弊；扩团队前先定位瓶颈究竟在哪里。",
                "question": "下周做一个重要决定时，你准备先使用哪一个问题？",
                "extension": "这些概念不是追求每次都算得精确，而是提供一套检查清单，让隐性成本、激励偏差和协调负担进入讨论。",
            },
        ],
    },
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
    wechat_feed_urls: list[str] = field(default_factory=list)
    content_feeds: list[dict[str, str]] = field(default_factory=list)
    tomorrow_reminders: list[str] = field(default_factory=list)
    sent_learning_ids: dict[str, set[str]] = field(
        default_factory=lambda: {"theme_slots": set(), "dates": set(), "content": set()}
    )
    sent_fact_ids: dict[str, set[str]] = field(
        default_factory=lambda: {"psychology": set(), "history": set()}
    )
    sent_evening_ids: set[str] = field(default_factory=set)
    sent_evening_closing_ids: set[str] = field(default_factory=set)
    sent_countdown_ids: dict[str, set[str]] = field(
        default_factory=lambda: {module: set() for module in COUNTDOWN_MODULES}
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


class TextContentParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def parse_owen_links(html):
    parser = OwenLinksParser()
    parser.feed(html)
    return parser.items


def html_to_text(value):
    parser = TextContentParser()
    parser.feed(value or "")
    return " ".join("".join(parser.parts).split())


def truncate_text(value, limit):
    return value if len(value) <= limit else f"{value[:limit].rstrip()}…"


def xml_local_name(tag):
    return tag.rsplit("}", 1)[-1]


def xml_child_text(element, *names):
    for child in element:
        if xml_local_name(child.tag) in names:
            return "".join(child.itertext()).strip()
    return ""


def parse_wechat_feed(xml):
    root = ET.fromstring(xml)
    channel = next(
        (element for element in root.iter() if xml_local_name(element.tag) == "channel"),
        None,
    )
    feed_author = xml_child_text(channel, "title") if channel is not None else ""
    entries = [
        element
        for element in root.iter()
        if xml_local_name(element.tag) in ("item", "entry")
    ]
    result = []
    for entry in entries:
        link = xml_child_text(entry, "link")
        if not link:
            link_element = next(
                (
                    child
                    for child in entry
                    if xml_local_name(child.tag) == "link" and child.get("href")
                ),
                None,
            )
            link = link_element.get("href", "") if link_element is not None else ""
        item = {
            "title": html_to_text(xml_child_text(entry, "title")),
            "author": html_to_text(
                xml_child_text(entry, "creator", "author") or feed_author
            ),
            "published_at": html_to_text(
                xml_child_text(entry, "pubDate", "published", "updated")
            ),
            "summary": truncate_text(
                html_to_text(
                    xml_child_text(entry, "description", "summary", "content")
                ),
                WECHAT_SUMMARY_LIMIT,
            ),
            "url": link.strip(),
        }
        if all(item.values()):
            result.append(item)
    return result


def fetch_content_feeds(feeds, sent_ids=None):
    sent_ids = set(sent_ids or ())
    news = []
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    for feed in feeds:
        feed_url = feed["url"]
        request = urllib.request.Request(
            feed_url,
            headers={"User-Agent": "jump-dingtalk-broadcast/1.0"},
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=15,
                context=ssl_context,
            ) as response:
                items = parse_wechat_feed(response.read())
        except (OSError, ET.ParseError):
            continue
        for item in items:
            if item["url"] in sent_ids:
                continue
            item["source_name"] = feed.get("name") or item["author"]
            news.append(item)
            sent_ids.add(item["url"])
            if len(news) == INDUSTRY_ITEM_LIMIT:
                return news
    return news


def fetch_wechat_feeds(feed_urls, sent_ids=None):
    feeds = [{"name": "", "url": url} for url in feed_urls]
    return fetch_content_feeds(feeds, sent_ids)


def fetch_owen_links(sent_urls=None):
    sent_urls = set(sent_urls or ())
    news = []
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    for page in range(1, OWEN_LINKS_PAGE_LIMIT + 1):
        url = OWEN_LINKS_URL
        if page > 1:
            url = f"https://www.owenyoung.com/archive?format=link&view=list&page={page}"
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "jump-dingtalk-broadcast/1.0"},
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=15,
                context=ssl_context,
            ) as response:
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
    if "wechat_feed_urls" in data:
        if not isinstance(data["wechat_feed_urls"], list):
            raise ValueError("wechat_feed_urls must be a JSON array.")
        config.wechat_feed_urls = data["wechat_feed_urls"]
    if "content_feeds" in data:
        feeds = data["content_feeds"]
        if not isinstance(feeds, list) or any(
            not isinstance(feed, dict) or not feed.get("name") or not feed.get("url")
            for feed in feeds
        ):
            raise ValueError("content_feeds must contain name and url objects.")
        config.content_feeds = feeds
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


def learning_content_id(message):
    return hashlib.sha256(" ".join(message.split()).encode("utf-8")).hexdigest()


def learning_theme_for_day(day):
    week_index = day.isocalendar().week - 1
    return LEARNING_THEMES[week_index % len(LEARNING_THEMES)]


def format_learning_card(theme, card, day):
    weekday = day.weekday()
    yesterday = ""
    if weekday > 0:
        yesterday = f"昨日回响：{theme['cards'][weekday - 1]['conclusion']}"
    lines = [
        f"三分钟知识卡｜{theme['title']}（{weekday + 1}/5）",
        f"今日标题：{card['title']}",
    ]
    if yesterday:
        lines.append(yesterday)
    lines.extend(
        [
            f"核心结论：{card['conclusion']}",
            f"举个例子：{card['example']}",
            f"多想一步：{card['question']}",
            f"补充说明：{card['extension']}",
            f"来源：{theme['source']} {theme['source_url']}",
            "预计阅读：3 分钟",
        ]
    )
    return "\n".join(lines)


def validate_learning_card(theme, card, message):
    required = ("title", "conclusion", "example", "question", "extension")
    if any(not card.get(field) for field in required):
        return False
    parsed_url = urllib.parse.urlparse(theme.get("source_url", ""))
    if not theme.get("id") or not theme.get("title") or not theme.get("source"):
        return False
    if parsed_url.scheme not in ("http", "https") or not parsed_url.netloc:
        return False
    return LEARNING_CARD_MIN_LENGTH <= len(message) <= LEARNING_CARD_MAX_LENGTH


def learning_card_keys(theme, day, message):
    return {
        "theme_slots": f"{theme['id']}:{day.weekday()}",
        "dates": day.isoformat(),
        "content": learning_content_id(message),
    }


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
    excerpt = next(
        (
            quote
            for quote in load_literature_quotes()
            if evening_quote_id(quote["content"]) not in config.sent_evening_ids
        ),
        None,
    )
    if excerpt is None:
        raise ValueError("文学句子库已全部播报完毕，请补充新内容。")
    message = format_message(config, [
        "早安，冯驰。",
        weather_line(config),
        reminder,
        "今日摘抄：",
        excerpt["content"],
    ])
    context = {"evening_ids": [evening_quote_id(excerpt["content"])]}
    if reminder.startswith("心理学冷知识："):
        fact = reminder.removeprefix("心理学冷知识：")
        context.update(
            {
                "fact": fact,
                "fact_category": "psychology",
                "fact_id": fact_id(fact),
            }
        )
    return Broadcast("morning", BROADCAST_SCHEDULE["morning"], message, context)


def build_noon(config, day, now_time=None):
    if day.weekday() >= 5:
        return None
    theme = learning_theme_for_day(day)
    card = theme["cards"][day.weekday()]
    message = format_learning_card(theme, card, day)
    if not validate_learning_card(theme, card, message):
        return None
    keys = learning_card_keys(theme, day, message)
    if any(keys[kind] in config.sent_learning_ids[kind] for kind in keys):
        return None
    return Broadcast(
        "noon",
        BROADCAST_SCHEDULE["noon"],
        format_message(config, message.splitlines()),
        {"learning_keys": keys, "theme_id": theme["id"]},
    )


def build_industry(config, day, now_time=None):
    news = config.industry_news[:INDUSTRY_ITEM_LIMIT]
    source = config.industry_source
    source_label = DADAO_SOURCE_LABELS[source]
    lines = [f"大道消息｜{source_label}。"]
    if not news:
        if source == "jike":
            lines.extend(["需要使用 Chrome 的即刻登录态读取精选内容。", "当前没有可发送的新内容。"])
        elif source in ("wechat", "feeds"):
            lines.extend(["暂时无法读取内容订阅源。", "今天不发送过期内容。"])
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
        elif source == "owen":
            summary = f"：{item['summary']}" if item.get("summary") else ""
            lines.append(f"{index}. {item.get('title', '未命名资讯')}{summary}{link}")
        else:
            lines.append(
                f"{index}. [{item.get('source_name') or item['author']}｜"
                f"{item['published_at']}] {item['title']}"
            )
            lines.append(item["summary"])
            lines.append(f"原文：{item['url']}")
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
    experiences = load_countdown_experiences(COUNTDOWN_EXPERIENCES_PATH)
    selected = {}
    for module in COUNTDOWN_MODULES:
        selected[module] = next(
            (
                content
                for content in experiences[module]
                if fact_id(content) not in config.sent_countdown_ids[module]
            ),
            None,
        )
        if selected[module] is None:
            raise ValueError(f"{module}文案已全部播报完毕，请补充新内容。")
    lines = [
        "摸鱼日历。",
        f"距下班约 {minutes // 60} 小时 {minutes % 60} 分钟。",
        f"距周末还有 {weekend_days} 天。",
    ]
    lines.extend(
        f"{module}：{selected[module]}"
        for module in COUNTDOWN_MODULES
    )
    return Broadcast(
        "countdown",
        BROADCAST_SCHEDULE["countdown"],
        format_message(config, lines),
        {
            "minutes_to_off": minutes,
            "countdown_ids": {
                module: fact_id(content)
                for module, content in selected.items()
            },
        },
    )


def build_evening(config, day, now_time=None):
    quotes = load_literature_quotes()
    unsent = [
        quote
        for quote in quotes
        if evening_quote_id(quote["content"]) not in config.sent_evening_ids
    ][:3]
    if len(unsent) < 3:
        raise ValueError("晚间句子库剩余内容不足 3 条，已取消播报。")
    closings = load_evening_closings(EVENING_CLOSINGS_PATH)
    closing = next(
        (
            item
            for item in closings
            if evening_quote_id(item) not in config.sent_evening_closing_ids
        ),
        None,
    )
    if (
        closing is None
        and evening_quote_id(EVENING_MILESTONE)
        not in config.sent_evening_closing_ids
    ):
        closing = EVENING_MILESTONE
    if closing is None:
        raise ValueError("晚间下班文案已全部播报完毕，请补充新内容。")
    lines = ["晚间收尾。"]
    lines.extend(
        f"{index}. {quote['content']}"
        for index, quote in enumerate(unsent, 1)
    )
    lines.append(f"驰子，{closing}")
    return Broadcast(
        "evening",
        BROADCAST_SCHEDULE["evening"],
        format_message(config, lines),
        {
            "evening_ids": [
                evening_quote_id(quote["content"])
                for quote in unsent
            ],
            "evening_dates": [quote["date"] for quote in unsent],
            "evening_closing_id": evening_quote_id(closing),
        },
    )


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
                config.sent_evening_ids.update(
                    broadcast.context.get("evening_ids", [])
                )
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


def load_sent_learning_ids(path):
    path = Path(path)
    if not path.exists():
        return {"theme_slots": set(), "dates": set(), "content": set()}
    data = json.loads(path.read_text(encoding="utf-8"))
    learning = data.get("sent_learning_ids", {})
    return {
        kind: set(learning.get(kind, []))
        for kind in ("theme_slots", "dates", "content")
    }


def load_sent_evening_ids(path):
    path = Path(path)
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    return set(data.get("sent_evening_ids", []))


def save_sent_evening_ids(path, sent_evening_ids):
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    data["sent_evening_ids"] = sorted(sent_evening_ids)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_sent_evening_closing_ids(path):
    path = Path(path)
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    return set(data.get("sent_evening_closing_ids", []))


def save_sent_evening_closing_ids(path, sent_evening_closing_ids):
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    data["sent_evening_closing_ids"] = sorted(sent_evening_closing_ids)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_sent_countdown_ids(path):
    path = Path(path)
    if not path.exists():
        return {module: set() for module in COUNTDOWN_MODULES}
    data = json.loads(path.read_text(encoding="utf-8"))
    sent = data.get("sent_countdown_ids", {})
    return {
        module: set(sent.get(module, []))
        for module in COUNTDOWN_MODULES
    }


def save_sent_countdown_ids(path, sent_countdown_ids):
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    data["sent_countdown_ids"] = {
        module: sorted(sent_countdown_ids[module])
        for module in COUNTDOWN_MODULES
    }
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_evening_quotes(path):
    path = Path(path)
    sections = []
    current_date = None
    for line in path.read_text(encoding="utf-8").splitlines():
        heading = re.match(r"^## (\d{4}-\d{2}-\d{2})\b", line)
        if heading:
            current_date = heading.group(1)
            continue
        quote = re.match(r"^\d+\.\s+(.+)$", line)
        if current_date and quote:
            sections.append(
                {
                    "date": current_date,
                    "content": " ".join(quote.group(1).split()),
                }
            )
    return sorted(sections, key=lambda item: item["date"])


def load_numbered_quotes(path):
    path = Path(path)
    quotes = []
    for line in path.read_text(encoding="utf-8").splitlines():
        quote = re.match(r"^\d+\.\s+(.+)$", line)
        if quote:
            quotes.append(
                {
                    "date": path.stem,
                    "content": " ".join(quote.group(1).split()),
                }
            )
    return quotes


def load_literature_quotes():
    return [
        *load_evening_quotes(EVENING_QUOTES_PATH),
        *load_numbered_quotes(EVENING_QUOTES_FALLBACK_PATH),
    ]


def load_evening_closings(path):
    closings = [
        " ".join(line.split())
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(closings) != 100 or len(set(closings)) != 100:
        raise ValueError("晚间下班文案必须包含 100 条不重复内容。")
    return closings


def load_countdown_experiences(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    experiences = {}
    for module in COUNTDOWN_MODULES:
        item = data.get(module, {})
        starts = item.get("starts", [])
        ends = item.get("ends", [])
        content = [
            f"{start}{end}"
            for start in starts
            for end in ends
        ]
        if len(starts) != 10 or len(ends) != 10 or len(set(content)) != 100:
            raise ValueError(f"{module}必须生成 100 条不重复文案。")
        experiences[module] = sorted(
            content,
            key=lambda value: hashlib.sha256(
                f"{module}:{value}".encode("utf-8")
            ).hexdigest(),
        )
    return experiences


def evening_quote_id(content):
    normalized = " ".join(content.split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def save_sent_learning_ids(path, sent_learning_ids):
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    data["sent_learning_ids"] = {
        kind: sorted(ids)
        for kind, ids in sent_learning_ids.items()
    }
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def record_learning_card(config, broadcast):
    for kind, value in broadcast.context.get("learning_keys", {}).items():
        config.sent_learning_ids[kind].add(value)


def record_evening_quotes(config, broadcast):
    config.sent_evening_ids.update(broadcast.context.get("evening_ids", []))
    closing_id = broadcast.context.get("evening_closing_id")
    if closing_id:
        config.sent_evening_closing_ids.add(closing_id)


def record_countdown_content(config, broadcast):
    for module, content_id in broadcast.context.get("countdown_ids", {}).items():
        config.sent_countdown_ids[module].add(content_id)


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
    if source in ("wechat", "feeds"):
        url = item.get("url")
        if not url:
            raise ValueError("Feed item is missing url.")
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


def prepare_industry_news(config, items_file=None, state_path=DEFAULT_NEWS_STATE_PATH):
    source = config.industry_source
    sent_ids = load_sent_news_ids(source, state_path)
    if source == "owen":
        config.industry_news = fetch_owen_links(sent_ids)
        return sent_ids
    if source == "wechat":
        config.industry_news = fetch_wechat_feeds(config.wechat_feed_urls, sent_ids)
        return sent_ids
    if source == "feeds":
        config.industry_news = fetch_content_feeds(config.content_feeds, sent_ids)
        return sent_ids
    if items_file:
        config.industry_news = filter_unsent_news(
            load_news_file(items_file),
            "jike",
            sent_ids,
        )
    if config.industry_news:
        return sent_ids

    config.industry_source = "owen"
    sent_ids = load_sent_news_ids("owen", state_path)
    config.industry_news = fetch_owen_links(sent_ids)
    return sent_ids


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
        help="大道消息来源；默认使用即刻精选，也可指定 owen、wechat 或 feeds",
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
        config.sent_learning_ids = load_sent_learning_ids(args.state)
        config.sent_evening_ids = load_sent_evening_ids(args.state)
        config.sent_evening_closing_ids = load_sent_evening_closing_ids(args.state)
        config.sent_countdown_ids = load_sent_countdown_ids(args.state)
        sent_news_ids = set()
        industry_key = f"{day.isoformat()}:industry"
        if (
            config.enabled.get("industry", False)
            and is_workday(day)
            and now.time() >= parse_time(BROADCAST_SCHEDULE["industry"])
            and industry_key not in sent_keys
        ):
            sent_news_ids = prepare_industry_news(config)
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
                record_learning_card(config, broadcast)
                record_evening_quotes(config, broadcast)
                record_countdown_content(config, broadcast)
                sent_keys.add(key)
        if args.send:
            save_sent_keys(args.state, sent_keys)
            save_sent_fact_ids(args.state, config.sent_fact_ids)
            save_sent_learning_ids(args.state, config.sent_learning_ids)
            save_sent_evening_ids(args.state, config.sent_evening_ids)
            save_sent_evening_closing_ids(
                args.state,
                config.sent_evening_closing_ids,
            )
            save_sent_countdown_ids(args.state, config.sent_countdown_ids)
        return

    config.sent_fact_ids = load_sent_fact_ids(args.state)
    config.sent_learning_ids = load_sent_learning_ids(args.state)
    config.sent_evening_ids = load_sent_evening_ids(args.state)
    config.sent_evening_closing_ids = load_sent_evening_closing_ids(args.state)
    config.sent_countdown_ids = load_sent_countdown_ids(args.state)
    sent_news_ids = set()
    if args.kind == "industry" and config.enabled.get("industry", False):
        sent_news_ids = prepare_industry_news(config, args.items_file)
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
        record_learning_card(config, broadcast)
        record_evening_quotes(config, broadcast)
        record_countdown_content(config, broadcast)
        save_sent_learning_ids(args.state, config.sent_learning_ids)
        save_sent_evening_ids(args.state, config.sent_evening_ids)
        save_sent_evening_closing_ids(
            args.state,
            config.sent_evening_closing_ids,
        )
        save_sent_countdown_ids(args.state, config.sent_countdown_ids)


if __name__ == "__main__":
    main()
