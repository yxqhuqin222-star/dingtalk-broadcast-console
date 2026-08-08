#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import random
import re
import ssl
import subprocess
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime, time as clock_time, timedelta
from html.parser import HTMLParser
from pathlib import Path

import certifi

from dingtalk_client import send_dingtalk_message
from learning_inventory import (
    INVENTORY_MINIMUM,
    load_inventory,
    mark_card_sent,
    refresh_inventory,
    save_inventory,
    select_card,
)


BROADCAST_SCHEDULE = {
    "morning": "10:00",
    "noon": "11:40",
    "midday_news": "12:00",
    "industry": "16:30",
    "countdown": "17:30",
    "evening": "19:00",
}
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DOCS_DIR = BASE_DIR / "docs"
STATE_DIR = BASE_DIR / "state"
PSYCHOLOGY_FACTS_PATH = DATA_DIR / "psychology_facts.json"
DEFAULT_STATE_PATH = STATE_DIR / ".daily_broadcast_state.json"
DEFAULT_NEWS_STATE_PATH = STATE_DIR / ".dadao_message_state.json"
DEFAULT_LEARNING_INVENTORY_PATH = STATE_DIR / ".learning_inventory.json"
AI_SIGNAL_DIR = Path("/Users/kityhello/.codex/skills/ai-signal")
AI_SIGNAL_PREPARE_SCRIPT = AI_SIGNAL_DIR / "scripts" / "prepare_digest.py"
AI_SIGNAL_MARK_SCRIPT = AI_SIGNAL_DIR / "scripts" / "mark_delivered.py"
AI_SIGNAL_USER_CONFIG = Path.home() / ".ai-signal" / "config.json"
DAILY_ARCHIVE_FILES = {
    "psychology": "心理学冷知识.md",
    "industry": "大道消息.md",
    "noon": "三分钟知识卡.md",
}
EVENING_QUOTES_PATH = Path(
    "/Users/kityhello/workplace/tech-docs/wenxue/📚 句子控精选 (2).md"
)
EVENING_QUOTES_FALLBACK_PATH = Path(
    "/Users/kityhello/workplace/tech-docs/wenxue/冬牧场-划线.md"
)
EVENING_CLOSINGS_PATH = DATA_DIR / "evening_closings.txt"
EVENING_MILESTONE = "小猪播报100天了～！"
COUNTDOWN_EXPERIENCES_PATH = DATA_DIR / "countdown_experiences.json"
DAILY_QUESTION_PATH = Path(
    "/Users/kityhello/workplace/tech-docs/wenxue/每日一问.md"
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
    "midday_news": True,
    "industry": True,
    "countdown": True,
    "evening": True,
}


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

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
    {
        "id": "technology",
        "title": "科技：理解数字世界",
        "source": "Cloudflare Learning Center",
        "source_url": "https://www.cloudflare.com/learning/",
        "cards": [
            {
                "title": "互联网并不是一朵云",
                "conclusion": "互联网是大量独立网络通过统一协议互相连接形成的系统，数据通常会被拆成小包，经由不同节点转发到目的地。",
                "example": "打开网页时，浏览器先找到服务器地址，再通过多个路由节点收发数据；某一段线路拥堵时，数据可能改走其他路径。",
                "question": "一次网页加载为什么可能同时依赖几十台不同公司的服务器？",
                "extension": "理解分层和分包后，就能区分网站、互联网、浏览器与云服务。它们相互配合，但并不是同一个东西。",
                "source_url": "https://www.cloudflare.com/learning/network-layer/how-does-the-internet-work/",
            },
        ],
    },
    {
        "id": "health",
        "title": "健康：读懂身体信号",
        "source": "World Health Organization",
        "source_url": "https://www.who.int/",
        "cards": [
            {
                "title": "久坐不能只靠下班运动抵消",
                "conclusion": "规律运动很重要，但长时间连续坐着仍应被主动打断。健康建议同时关注每周活动总量和一天中的静坐时间。",
                "example": "即使晚上跑步半小时，白天连续坐数小时也会让身体长期处于低活动状态；每隔一段时间起身走动能改变这种节奏。",
                "question": "今天哪个固定动作可以成为提醒自己起身活动的触发点？",
                "extension": "不必把每次活动都做成正式训练。接水、走楼梯或站着通话都能增加日常活动，身体不适时应听从专业医疗建议。",
                "source_url": "https://www.who.int/news-room/fact-sheets/detail/physical-activity",
            },
        ],
    },
    {
        "id": "art",
        "title": "艺术：学习如何观看",
        "source": "The Metropolitan Museum of Art",
        "source_url": "https://www.metmuseum.org/",
        "cards": [
            {
                "title": "看画不必先猜标准答案",
                "conclusion": "观看艺术品可以先从可观察的事实开始：人物、颜色、材质、光线和构图，再把感受与历史背景连接起来。",
                "example": "面对一幅陌生肖像，先描述人物姿态和视线，再查服装与委托背景，通常比一开始追问作品寓意更容易进入画面。",
                "question": "如果暂时不看作品说明，你最先注意到的三个视觉细节是什么？",
                "extension": "视觉分析不是拒绝知识，而是把观察和解释分开。这样既能保留自己的发现，也能检查后续资料是否真的得到画面支持。",
                "source_url": "https://www.metmuseum.org/learn/educators/curriculum-resources/art-of-seeing",
            },
        ],
    },
    {
        "id": "geography",
        "title": "地理：看见地球的结构",
        "source": "United States Geological Survey",
        "source_url": "https://www.usgs.gov/",
        "cards": [
            {
                "title": "大陆一直在缓慢移动",
                "conclusion": "地球表面的岩石圈被分成多个板块，它们以每年数厘米左右的速度移动，长期累积后会重塑海洋与大陆。",
                "example": "板块相撞可以抬升山脉，分离会形成新的洋壳，彼此错动则容易积累应力并产生地震。",
                "question": "如果板块移动如此缓慢，科学家如何确认它正在发生？",
                "extension": "现代卫星定位能直接测量板块位移，海底磁条带和化石分布则保存了更长时间尺度上的证据。",
                "source_url": "https://pubs.usgs.gov/gip/dynamic/dynamic.html",
            },
        ],
    },
    {
        "id": "language",
        "title": "语言：理解表达如何变化",
        "source": "Linguistic Society of America",
        "source_url": "https://www.linguisticsociety.org/",
        "cards": [
            {
                "title": "语言变化不是语言退化",
                "conclusion": "发音、词义和语法会随着使用者与社会环境变化。今天被视为规范的表达，也可能来自过去的创新或误用。",
                "example": "新技术会带来新词，群体接触会发生借词，常用结构还可能逐渐简化；变化并不自动意味着表达能力下降。",
                "question": "你最近接受了哪个过去觉得奇怪的新词或新用法？",
                "extension": "规范语言适合正式协作，描述语言则研究人们实际怎样说。区分两者，有助于同时理解规则与变化。",
                "source_url": "https://www.linguisticsociety.org/resource/what-language",
            },
        ],
    },
    {
        "id": "life",
        "title": "生活常识：降低日常风险",
        "source": "United States Department of Agriculture",
        "source_url": "https://www.usda.gov/",
        "cards": [
            {
                "title": "闻起来正常不代表食物安全",
                "conclusion": "导致食源性疾病的微生物不一定改变食物的气味、颜色或味道，判断安全不能只依赖感官。",
                "example": "熟食在室温放置过久，即使外观正常也可能进入微生物快速繁殖的温度区间；及时冷藏比事后闻一闻更可靠。",
                "question": "家里哪些食物最容易因为忘记时间而在室温放得过久？",
                "extension": "保持清洁、生熟分开、彻底加热并及时冷藏，是比凭经验试吃更稳妥的做法；高风险人群尤其需要谨慎。",
                "source_url": "https://www.fsis.usda.gov/food-safety/safe-food-handling-and-preparation/food-safety-basics",
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
    epoch = date(2026, 1, 5)
    elapsed_days = (day - epoch).days
    weeks, weekday = divmod(elapsed_days, 7)
    workday_index = weeks * 5 + min(weekday, 5)
    return LEARNING_THEMES[workday_index % len(LEARNING_THEMES)]


def format_learning_card(theme, card, day):
    lines = [
        f"三分钟知识卡｜{theme['title']}",
        f"今日标题：{card['title']}",
    ]
    lines.extend(
        [
            f"核心结论：{card['conclusion']}",
            f"举个例子：{card['example']}",
            f"多想一步：{card['question']}",
            f"补充说明：{card['extension']}",
            f"来源：{theme['source']} {card.get('source_url', theme['source_url'])}",
            "预计阅读：3 分钟",
        ]
    )
    return "\n".join(lines)


def format_dynamic_learning_card(card):
    return "\n".join(
        [
            f"三分钟知识卡｜{card['category']}",
            f"今日标题：{card['title']}",
            f"内容摘要：{card['summary']}",
            f"来源：{card['source']} {card['source_url']}",
        ]
    )


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


def learning_card_keys(theme, card_index, day, message):
    return {
        "theme_slots": f"{theme['id']}:{card_index}",
        "dates": day.isoformat(),
        "content": learning_content_id(message),
    }


def pick_unsent_fact(items, sent_ids, day, salt):
    unsent = [fact for fact in items if fact_id(fact) not in sent_ids]
    return stable_pick(unsent, day, salt)


def load_psychology_facts(path=PSYCHOLOGY_FACTS_PATH):
    path = Path(path)
    if not path.exists():
        return list(PSYCHOLOGY_FACTS)
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        entries = data.get("facts", [])
    else:
        entries = data
    facts = []
    for entry in entries:
        if isinstance(entry, str):
            fact = entry.strip()
        elif isinstance(entry, dict):
            fact = str(entry.get("text", "")).strip()
        else:
            fact = ""
        if fact:
            facts.append(fact)
    if not facts:
        raise ValueError(f"心理学冷知识题库为空：{path}")
    if len({fact_id(fact) for fact in facts}) != len(facts):
        raise ValueError(f"心理学冷知识题库包含重复内容：{path}")
    return facts


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


def ai_signal_item_url(item, *names):
    for name in names:
        value = item.get(name)
        if value:
            return value
    return ""


def ai_signal_score_text(text):
    keywords = (
        "agent", "agents", "model", "models", "claude", "openai",
        "anthropic", "gemini", "deepmind", "gpt", "reasoning",
        "inference", "robot", "gpu", "nvidia", "startup", "product",
        "人工智能", "大模型", "模型", "智能体", "推理", "机器人",
        "投资", "产品", "创业",
    )
    short_keywords = ("ai", "agi", "llm", "llms")
    lowered = (text or "").lower()
    score = sum(1 for keyword in keywords if keyword in lowered)
    score += sum(
        1
        for keyword in short_keywords
        if re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", lowered)
    )
    return score


def select_ai_signal_tweets(payload, limit=2):
    candidates = []
    for account in payload.get("x", []):
        for tweet in account.get("tweets", []):
            text = " ".join((tweet.get("text") or "").split())
            url = tweet.get("url")
            if not text or not url:
                continue
            score = (
                ai_signal_score_text(text),
                tweet.get("like_count", 0),
                tweet.get("retweet_count", 0),
            )
            candidates.append((score, account, tweet, text, url))
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[:limit]


def select_ai_signal_items(payload, key, limit=2):
    items = []
    for item in payload.get(key, []):
        url = ai_signal_item_url(item, "url", "link", "abs_url", "pdf_url")
        title = " ".join((item.get("title") or "").split())
        if not title or not url:
            continue
        text = " ".join(
            str(item.get(field) or "")
            for field in ("title", "summary", "description", "abstract")
        )
        items.append((ai_signal_score_text(text), item, title, url))
    items.sort(key=lambda value: value[0], reverse=True)
    return items[:limit]


def ai_signal_content_preferences(payload):
    config = payload.get("config") or {}
    return config.get("contentPreference") or {}


def ai_signal_should_skip(payload, name):
    preferences = ai_signal_content_preferences(payload)
    return name in set(preferences.get("skipByDefault") or [])


def ai_signal_investment_enabled(payload):
    preferences = ai_signal_content_preferences(payload)
    return preferences.get("includeInvestmentModule", True)


def ai_signal_text_blob(item):
    return " ".join(
        str(item.get(field) or "")
        for field in (
            "title",
            "text",
            "summary",
            "description",
            "abstract",
            "channel",
            "name",
            "handle",
        )
    )


def ai_signal_is_investment(text):
    lowered = text.lower()
    keywords = (
        "invest", "investment", "investing", "market", "markets",
        "capital", "allocators", "moat", "debt", "financing",
        "nvidia", "gpu", "neocloud", "hyperscaler", "inference",
        "semianalysis", "dylan", "pat dorsey", "投资", "融资",
        "市场", "资本", "护城河", "算力",
    )
    return any(keyword in lowered for keyword in keywords)


def ai_signal_is_noise(text):
    lowered = " ".join((text or "").lower().split())
    if lowered.count("@") >= 4:
        return True
    patterns = (
        "older kid",
        "good morning",
        "thank you",
        "thanks",
        "haha",
        "means a lot coming from you",
        "why use many kernel",
    )
    return any(pattern in lowered for pattern in patterns)


def ai_signal_source_name(item, account=None):
    if account:
        return account.get("name") or account.get("handle") or "X"
    return item.get("channel") or item.get("source_name") or item.get("source") or "AI Signal"


def ai_signal_title_for_item(item, account=None):
    if item.get("title"):
        return " ".join(item["title"].split())
    if item.get("text"):
        return truncate_text(" ".join(item["text"].split()), 72)
    return ai_signal_source_name(item, account)


def ai_signal_url_for_item(item):
    return ai_signal_item_url(item, "url", "link", "abs_url", "pdf_url")


def ai_signal_summary_for_item(item, account=None):
    source = ai_signal_source_name(item, account)
    text = " ".join((item.get("text") or item.get("description") or item.get("abstract") or item.get("summary") or "").split())
    lowered = f"{ai_signal_title_for_item(item, account)} {text}".lower()
    if "merge chat and agents" in lowered or ("openai" in lowered and "agents" in lowered):
        return f"{source} 的信号指向 ChatGPT、工具和 agent 能力继续合并，核心变量是它能否成为可被信任的行动入口。"
    if "coding" in lowered or "code" in lowered or "vercel" in lowered or "replit" in lowered:
        return f"{source} 的信号指向 AI coding 的竞争正在转向交付效率、软件质量和团队工作流，而不只是模型跑分。"
    if "agent" in lowered or "agents" in lowered or "智能体" in lowered:
        return f"{source} 的信号指向 agent 从单点工具进入工作流入口，重点看它能否稳定完成真实任务，而不只是展示能力。"
    if "inference" in lowered or "token" in lowered:
        return f"{source} 的信号指向 inference 可能成为长期需求主线，关键变量是模型能否持续完成有经济价值的工作。"
    if "nvidia" in lowered or "gpu" in lowered or "neocloud" in lowered or "hyperscaler" in lowered:
        return f"{source} 的信号指向 AI 基建竞争正在从芯片供给扩展到融资、数据中心、云生态和算力利用率。"
    if "moat" in lowered or "capital" in lowered or "invest" in lowered or "market" in lowered:
        return f"{source} 的信号适合放进投资模块看：真正要跟踪的是切换成本、客户 ROI、再投资空间和利润留存。"
    if text:
        return f"{source} 的信号值得跟踪：{truncate_text(text, 110)}"
    return f"{source} 有一条新动态，适合继续观察它对 AI 产品、商业化或投资判断的影响。"


def ai_signal_collect_items(payload):
    collected = []
    seen = set()
    for account in payload.get("x", []):
        for tweet in account.get("tweets", []):
            url = ai_signal_url_for_item(tweet)
            if not url:
                continue
            text = ai_signal_text_blob(tweet)
            if ai_signal_is_noise(text):
                continue
            dedupe_key = " ".join((tweet.get("text") or "").split()).lower() or url
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            base_score = ai_signal_score_text(text)
            is_investment = ai_signal_is_investment(text)
            if base_score == 0 and not is_investment:
                continue
            collected.append(
                {
                    "source": "x",
                    "account": account,
                    "item": tweet,
                    "url": url,
                    "score": (
                        base_score * 1000
                        + tweet.get("like_count", 0)
                        + tweet.get("retweet_count", 0) * 5
                    ),
                    "investment": is_investment,
                }
            )
    for key, source in (("podcasts", "podcast"), ("articles", "article")):
        for item in payload.get(key, []):
            url = ai_signal_url_for_item(item)
            if not url:
                continue
            text = ai_signal_text_blob(item)
            dedupe_key = url or ai_signal_title_for_item(item).lower()
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            base_score = ai_signal_score_text(text)
            is_investment = item.get("domain") == "invest" or ai_signal_is_investment(text)
            if base_score == 0 and not is_investment:
                continue
            collected.append(
                {
                    "source": source,
                    "account": None,
                    "item": item,
                    "url": url,
                    "score": base_score * 1000,
                    "investment": is_investment,
                }
            )
    if not ai_signal_should_skip(payload, "papers"):
        for item in payload.get("papers", []):
            url = ai_signal_url_for_item(item)
            if not url:
                continue
            text = ai_signal_text_blob(item)
            dedupe_key = item.get("arxiv_id") or url
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            base_score = ai_signal_score_text(text)
            if base_score == 0:
                continue
            collected.append(
                {
                    "source": "paper",
                    "account": None,
                    "item": item,
                    "url": url,
                    "score": base_score * 1000,
                    "investment": False,
                }
            )
    collected.sort(key=lambda value: value["score"], reverse=True)
    return collected


def ai_signal_render_section(lines, title, items, start_index, limit, unique_sources=True):
    selected = []
    used_sources = set()
    for item in items:
        source = ai_signal_source_name(item["item"], item["account"])
        if unique_sources and source in used_sources:
            continue
        selected.append(item)
        used_sources.add(source)
        if len(selected) == limit:
            break
    if len(selected) < limit:
        for item in items:
            if item in selected:
                continue
            selected.append(item)
            if len(selected) == limit:
                break
    if not selected:
        return start_index
    lines.append("")
    lines.append(f"**{title}**")
    for entry in selected:
        item = entry["item"]
        account = entry["account"]
        headline = ai_signal_title_for_item(item, account)
        source = ai_signal_source_name(item, account)
        lines.append("")
        lines.append(f"{start_index}. {source}：{truncate_text(headline, 54)}")
        lines.append(ai_signal_summary_for_item(item, account))
        lines.append(entry["url"])
        start_index += 1
    return start_index


def ai_signal_render_top_lines(lines, product_items, invest_items):
    signals = []
    if product_items:
        signals.append("AI 产品正在从“聊天/代码工具”继续推向“可执行工作流入口”。")
    if invest_items:
        signals.append("AI 投资主线继续围绕算力、融资结构、inference 需求和客户 ROI 展开。")
    if product_items or invest_items:
        signals.append("判断价值时优先看真实交付、使用频率、切换成本和利润留存，而不是单次发布热度。")
    if not signals:
        return
    lines.append("")
    lines.append("**今天最值得跟的 3 条线**")
    for index, signal in enumerate(signals[:3], 1):
        lines.append(f"{index}. {signal}")


def render_ai_signal_digest(manifest, payload):
    stats = manifest.get("stats") or {}
    lines = [
        "午间新闻",
        f"AI Signal｜X {stats.get('total_tweets', 0)} 条，播客 {stats.get('podcast_episodes', 0)} 期，论文 {stats.get('arxiv_papers', 0)} 篇。",
    ]
    warnings = manifest.get("warnings") or []
    if warnings:
        lines.append(f"提示：{warnings[0]}")

    items = ai_signal_collect_items(payload)
    product_items = [item for item in items if not item["investment"]]
    invest_items = [item for item in items if item["investment"]]

    index = ai_signal_render_section(lines, "AI 产品 / 商业 / 趋势", product_items, 1, 4)
    if ai_signal_investment_enabled(payload):
        ai_signal_render_section(lines, "投资模块", invest_items, 1, 4, unique_sources=False)
    ai_signal_render_top_lines(lines, product_items, invest_items)

    if not product_items and (not ai_signal_investment_enabled(payload) or not invest_items):
        lines.append("今天暂无符合已确认口径的新内容。")
    else:
        lines.append("想深读的话，可以直接说：展开第 1 条。")
    return "\n".join(lines)


def prepare_ai_signal_digest(include_seen=False):
    if not AI_SIGNAL_PREPARE_SCRIPT.exists():
        raise ValueError(f"找不到 ai-signal 脚本：{AI_SIGNAL_PREPARE_SCRIPT}")
    command = [sys.executable, str(AI_SIGNAL_PREPARE_SCRIPT)]
    if include_seen:
        command.append("--include-seen")
    result = subprocess.run(
        command,
        cwd=str(AI_SIGNAL_PREPARE_SCRIPT.parent),
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(f"AI Signal 生成失败：{truncate_text(result.stderr.strip(), 200)}")
    try:
        manifest = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("AI Signal 没有返回有效 JSON。") from exc
    payload_file = manifest.get("payload_file")
    if not payload_file:
        raise ValueError("AI Signal 没有生成 payload 文件。")
    payload = json.loads(Path(payload_file).read_text(encoding="utf-8"))
    if AI_SIGNAL_USER_CONFIG.exists():
        user_config = json.loads(AI_SIGNAL_USER_CONFIG.read_text(encoding="utf-8-sig"))
        payload.setdefault("config", {}).update(
            {
                "contentPreference": user_config.get("contentPreference", {}),
            }
        )
    return manifest, payload


def mark_ai_signal_delivered(mark_file):
    if not mark_file:
        return
    result = subprocess.run(
        [sys.executable, str(AI_SIGNAL_MARK_SCRIPT), "--file", str(mark_file)],
        cwd=str(AI_SIGNAL_MARK_SCRIPT.parent),
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(f"AI Signal 已发送标记失败：{truncate_text(result.stderr.strip(), 200)}")


def holiday_line(config, day):
    if config.holiday_name:
        return f"今日提醒：{config.holiday_name}"
    if config.next_holiday_date:
        days = (config.next_holiday_date - day).days
        if days >= 0:
            return f"假期雷达：距{config.next_holiday_name}还有 {days} 天"
    fact = pick_unsent_fact(
        load_psychology_facts(),
        config.sent_fact_ids["psychology"],
        day,
        "psychology-fact",
    )
    if fact:
        return f"心理学冷知识：{fact}"
    return "心理学冷知识题库已用完，等待补充新内容"


def next_weekend_days(day):
    return 4 - day.weekday() if day.weekday() < 5 else 0


def build_morning(config, day, now_time=None):
    reminder = holiday_line(config, day)
    excerpts = [
        quote
        for quote in load_literature_quotes()
        if evening_quote_id(quote["content"]) not in config.sent_evening_ids
    ][:3]
    if len(excerpts) < 3:
        raise ValueError("早安句子库剩余内容不足 3 条，已取消播报。")
    message = format_message(config, [
        "早安，冯驰。",
        weather_line(config),
        reminder,
        "今日摘抄：",
        *[
            f"{index}. {quote['content']}"
            for index, quote in enumerate(excerpts, 1)
        ],
    ])
    context = {
        "evening_ids": [
            evening_quote_id(quote["content"])
            for quote in excerpts
        ]
    }
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
    inventory = load_inventory(DEFAULT_LEARNING_INVENTORY_PATH)
    dynamic_card = select_card(inventory)
    if dynamic_card:
        message = format_dynamic_learning_card(dynamic_card)
        keys = {
            "theme_slots": f"dynamic:{dynamic_card['source_url']}",
            "dates": day.isoformat(),
            "content": learning_content_id(message),
        }
        if any(keys[kind] in config.sent_learning_ids[kind] for kind in keys):
            return None
        return Broadcast(
            "noon",
            BROADCAST_SCHEDULE["noon"],
            format_message(config, message.splitlines()),
            {
                "learning_keys": keys,
                "theme_id": dynamic_card["category"],
                "dynamic_card": dynamic_card,
            },
        )
    preferred_theme = learning_theme_for_day(day)
    preferred_index = LEARNING_THEMES.index(preferred_theme)
    ordered_themes = (
        LEARNING_THEMES[preferred_index:] + LEARNING_THEMES[:preferred_index]
    )
    for theme in ordered_themes:
        for card_index, card in enumerate(theme["cards"]):
            message = format_learning_card(theme, card, day)
            if not validate_learning_card(theme, card, message):
                continue
            keys = learning_card_keys(theme, card_index, day, message)
            if any(keys[kind] in config.sent_learning_ids[kind] for kind in keys):
                continue
            return Broadcast(
                "noon",
                BROADCAST_SCHEDULE["noon"],
                format_message(config, message.splitlines()),
                {
                    "learning_keys": keys,
                    "theme_id": theme["id"],
                    "card_index": card_index,
                },
            )
    return None


def build_midday_news(config, day, now_time=None):
    manifest, payload = prepare_ai_signal_digest()
    lines = render_ai_signal_digest(manifest, payload).splitlines()
    if (
        config.dingtalk_keyword
        and not any(config.dingtalk_keyword in line for line in lines)
        and len(lines) > 1
    ):
        lines[1] = f"{config.dingtalk_keyword}｜{lines[1]}"
    return Broadcast(
        "midday_news",
        BROADCAST_SCHEDULE["midday_news"],
        format_message(config, lines),
        {
            "ai_signal_delivery_mark_file": manifest.get("delivery_mark_file"),
            "ai_signal_stats": manifest.get("stats") or {},
        },
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
    experiences["今日小问题"] = load_daily_questions(DAILY_QUESTION_PATH)
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
    "midday_news": build_midday_news,
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
    write_json(path, data)


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
    write_json(path, data)


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
    write_json(path, data)


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
    write_json(path, data)


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
    write_json(path, data)


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
        standalone_items = item.get("items")
        if standalone_items is not None:
            content = [" ".join(value.split()) for value in standalone_items]
            if len(content) != 100 or len(set(content)) != 100:
                raise ValueError(f"{module}必须包含 100 条不重复文案。")
            experiences[module] = content
            continue
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


def load_daily_questions(path):
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    questions = []
    waiting_for_question = False
    headings = 0
    for line in lines:
        normalized = " ".join(line.split())
        if re.match(r"^\d+[.)、]\s*今日问题[：:]?$", normalized):
            headings += 1
            waiting_for_question = True
            continue
        if waiting_for_question and normalized:
            questions.append(normalized)
            waiting_for_question = False
    if not questions or len(questions) != headings:
        raise ValueError("每日一问文档格式错误，必须为编号、今日问题和问题正文。")
    if len(questions) != len(set(questions)):
        raise ValueError("每日一问文档包含重复问题。")
    return questions


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
    write_json(path, data)


def record_learning_card(config, broadcast):
    for kind, value in broadcast.context.get("learning_keys", {}).items():
        config.sent_learning_ids[kind].add(value)
    card = broadcast.context.get("dynamic_card")
    if card:
        inventory = load_inventory(DEFAULT_LEARNING_INVENTORY_PATH)
        save_inventory(
            DEFAULT_LEARNING_INVENTORY_PATH,
            mark_card_sent(inventory, card),
        )


def record_evening_quotes(config, broadcast):
    config.sent_evening_ids.update(broadcast.context.get("evening_ids", []))
    closing_id = broadcast.context.get("evening_closing_id")
    if closing_id:
        config.sent_evening_closing_ids.add(closing_id)


def record_countdown_content(config, broadcast):
    for module, content_id in broadcast.context.get("countdown_ids", {}).items():
        config.sent_countdown_ids[module].add(content_id)


def record_ai_signal_delivery(broadcast):
    if broadcast.kind == "midday_news":
        mark_ai_signal_delivered(broadcast.context.get("ai_signal_delivery_mark_file"))


def archive_daily_broadcast(broadcast, day, docs_dir=DOCS_DIR):
    if not broadcast:
        return
    archive_key = None
    content = broadcast.message.strip()
    if broadcast.kind == "morning" and broadcast.context.get("fact_category") == "psychology":
        archive_key = "psychology"
        content = f"心理学冷知识：{broadcast.context['fact']}"
    elif broadcast.kind == "industry":
        archive_key = "industry"
    elif broadcast.kind == "noon":
        archive_key = "noon"
    if not archive_key:
        return

    path = Path(docs_dir) / DAILY_ARCHIVE_FILES[archive_key]
    entry = f"## {day.isoformat()}\n\n{content}\n\n---\n\n"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if entry in existing:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        if existing and not existing.endswith("\n"):
            file.write("\n")
        file.write(entry)


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
    write_json(path, data)


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
        noon_key = f"{day.isoformat()}:noon"
        if (
            config.enabled.get("noon", False)
            and is_workday(day)
            and now.time() >= parse_time(BROADCAST_SCHEDULE["noon"])
            and noon_key not in sent_keys
        ):
            inventory = refresh_inventory(DEFAULT_LEARNING_INVENTORY_PATH)
            if len(inventory["cards"]) < INVENTORY_MINIMUM:
                print(
                    f"警告：三分钟知识卡库存仅剩 {len(inventory['cards'])} 条。"
                    f"{inventory.get('last_error', '')}",
                    file=sys.stderr,
                )
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
                archive_daily_broadcast(broadcast, day)
                record_learning_card(config, broadcast)
                record_evening_quotes(config, broadcast)
                record_countdown_content(config, broadcast)
                record_ai_signal_delivery(broadcast)
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
    if args.kind == "noon":
        inventory = refresh_inventory(DEFAULT_LEARNING_INVENTORY_PATH)
        if len(inventory["cards"]) < INVENTORY_MINIMUM:
            print(
                f"警告：三分钟知识卡库存仅剩 {len(inventory['cards'])} 条。"
                f"{inventory.get('last_error', '')}",
                file=sys.stderr,
            )
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
        archive_daily_broadcast(broadcast, day)
        record_learning_card(config, broadcast)
        record_evening_quotes(config, broadcast)
        record_countdown_content(config, broadcast)
        record_ai_signal_delivery(broadcast)
        save_sent_learning_ids(args.state, config.sent_learning_ids)
        save_sent_evening_ids(args.state, config.sent_evening_ids)
        save_sent_evening_closing_ids(
            args.state,
            config.sent_evening_closing_ids,
        )
        save_sent_countdown_ids(args.state, config.sent_countdown_ids)


if __name__ == "__main__":
    main()
