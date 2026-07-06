import json
import unittest
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from daily_broadcast import (
    BROADCAST_SCHEDULE,
    BroadcastConfig,
    answer_followup,
    build_broadcast,
    due_broadcasts,
    fetch_weather,
    fetch_content_feeds,
    fetch_owen_links,
    fetch_wechat_feeds,
    filter_unsent_news,
    load_sent_news_ids,
    load_sent_news_urls,
    load_config,
    load_sent_keys,
    load_sent_fact_ids,
    load_sent_evening_closing_ids,
    load_sent_evening_ids,
    load_sent_countdown_ids,
    load_sent_learning_ids,
    LEARNING_THEMES,
    format_learning_card,
    validate_learning_card,
    parse_owen_links,
    parse_wechat_feed,
    prepare_industry_news,
    news_item_id,
    save_sent_news_ids,
    save_sent_news_urls,
    save_sent_keys,
    save_sent_fact_ids,
    save_sent_evening_closing_ids,
    save_sent_evening_ids,
    save_sent_countdown_ids,
    save_sent_learning_ids,
    evening_quote_id,
    load_evening_closings,
    load_evening_quotes,
    load_literature_quotes,
    load_numbered_quotes,
    load_countdown_experiences,
    COUNTDOWN_EXPERIENCES_PATH,
    COUNTDOWN_MODULES,
    EVENING_CLOSINGS_PATH,
    EVENING_MILESTONE,
)


class DailyBroadcastTest(unittest.TestCase):
    def setUp(self):
        self.inventory_patch = patch(
            "daily_broadcast.load_inventory",
            return_value={
                "cards": [],
                "sent_urls": [],
                "last_category": "",
                "last_refresh_at": "",
                "last_error": "",
            },
        )
        self.inventory_patch.start()

    def tearDown(self):
        self.inventory_patch.stop()

    def test_broadcast_schedule_uses_configured_times(self):
        self.assertEqual("10:00", BROADCAST_SCHEDULE["morning"])
        self.assertEqual("11:40", BROADCAST_SCHEDULE["noon"])
        self.assertEqual("19:00", BROADCAST_SCHEDULE["evening"])

    def test_morning_reminder_is_a_psychology_fact(self):
        config = BroadcastConfig(weather="晴")
        broadcast = build_broadcast("morning", config, date(2026, 6, 26))
        self.assertIn("心理学冷知识：", broadcast.message)
        self.assertNotIn("今日提醒", broadcast.message)
        self.assertEqual("psychology", broadcast.context["fact_category"])
        self.assertEqual(3, len(broadcast.context["evening_ids"]))

    def test_morning_excerpt_skips_sent_literature(self):
        quotes = load_evening_quotes(
            "/Users/kityhello/workplace/tech-docs/wenxue/📚 句子控精选 (2).md"
        )
        config = BroadcastConfig(
            weather="晴",
            sent_evening_ids={evening_quote_id(quotes[0]["content"])},
        )

        broadcast = build_broadcast("morning", config, date(2026, 7, 2))

        self.assertNotIn(quotes[0]["content"], broadcast.message)
        for index, quote in enumerate(quotes[1:4], 1):
            self.assertIn(f"{index}. {quote['content']}", broadcast.message)

    def test_numbered_quotes_are_loaded_in_number_order(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "冬牧场-划线.md"
            path.write_text(
                "# 《冬牧场》划线\n\n1. 第一句\n\n2. 第二句\n",
                encoding="utf-8",
            )

            quotes = load_numbered_quotes(path)

        self.assertEqual(["第一句", "第二句"], [quote["content"] for quote in quotes])
        self.assertEqual(["冬牧场-划线"] * 2, [quote["date"] for quote in quotes])

    def test_literature_quotes_switch_to_numbered_fallback(self):
        with TemporaryDirectory() as directory:
            primary = Path(directory) / "primary.md"
            fallback = Path(directory) / "fallback.md"
            primary.write_text(
                "## 2026-07-01\n\n1. 句子控最后一句\n",
                encoding="utf-8",
            )
            fallback.write_text(
                "# 《冬牧场》划线\n\n1. 冬牧场第一句\n\n2. 冬牧场第二句\n",
                encoding="utf-8",
            )
            with patch("daily_broadcast.EVENING_QUOTES_PATH", primary), patch(
                "daily_broadcast.EVENING_QUOTES_FALLBACK_PATH",
                fallback,
            ):
                quotes = load_literature_quotes()

        self.assertEqual(
            ["句子控最后一句", "冬牧场第一句", "冬牧场第二句"],
            [quote["content"] for quote in quotes],
        )

    def test_due_morning_and_evening_do_not_share_literature(self):
        config = BroadcastConfig(weather="晴")
        sent = {
            "2026-07-02:noon",
            "2026-07-02:industry",
            "2026-07-02:countdown",
        }

        due = due_broadcasts(
            config,
            datetime(2026, 7, 2, 19, 0),
            sent,
        )
        broadcasts = {broadcast.kind: broadcast for _, broadcast in due}

        morning_ids = set(broadcasts["morning"].context["evening_ids"])
        evening_ids = set(broadcasts["evening"].context["evening_ids"])
        self.assertTrue(morning_ids.isdisjoint(evening_ids))

    def test_noon_broadcast_rotates_categories_each_workday(self):
        config = BroadcastConfig()
        theme_ids = []
        day = date(2026, 6, 22)
        while len(theme_ids) < 10:
            if day.weekday() < 5:
                with self.subTest(day=day):
                    broadcast = build_broadcast("noon", config, day)
                    self.assertIn("三分钟知识卡", broadcast.message)
                    self.assertIn("来源：", broadcast.message)
                    self.assertIn("预计阅读：3 分钟", broadcast.message)
                    theme_ids.append(broadcast.context["theme_id"])
            day += timedelta(days=1)
        self.assertEqual(len(theme_ids), len(set(theme_ids)))

    def test_noon_prefers_dynamic_inventory_card(self):
        dynamic_card = {
            "category": "健康",
            "title": "测试标题",
            "summary": "测试摘要",
            "source": "WHO",
            "source_url": "https://example.com/health",
            "published_at": "2026-07-03",
        }
        with patch(
            "daily_broadcast.load_inventory",
            return_value={
                "cards": [dynamic_card],
                "sent_urls": [],
                "last_category": "科学",
            },
        ):
            broadcast = build_broadcast(
                "noon",
                BroadcastConfig(),
                date(2026, 7, 6),
            )
        self.assertEqual("健康", broadcast.context["theme_id"])
        self.assertIn("来源：WHO https://example.com/health", broadcast.message)

    def test_psychology_fact_does_not_repeat_sent_content(self):
        config = BroadcastConfig(weather="晴")
        first_morning = build_broadcast("morning", config, date(2026, 6, 22))
        config.sent_fact_ids["psychology"].add(first_morning.context["fact_id"])

        second_morning = build_broadcast("morning", config, date(2026, 6, 23))
        self.assertNotEqual(first_morning.context["fact_id"], second_morning.context["fact_id"])

    def test_fact_pool_exhaustion_does_not_repeat(self):
        config = BroadcastConfig(weather="晴")
        from daily_broadcast import PSYCHOLOGY_FACTS, fact_id

        config.sent_fact_ids["psychology"] = {fact_id(fact) for fact in PSYCHOLOGY_FACTS}
        morning = build_broadcast("morning", config, date(2026, 6, 26))
        self.assertIn("心理学冷知识题库已用完", morning.message)
        self.assertNotIn("fact_id", morning.context)

    def test_all_learning_cards_meet_length_and_source_rules(self):
        monday = date(2026, 6, 22)
        for theme in LEARNING_THEMES:
            for weekday, card in enumerate(theme["cards"]):
                with self.subTest(theme=theme["id"], weekday=weekday):
                    message = format_learning_card(theme, card, monday.replace(day=22 + weekday))
                    self.assertGreaterEqual(len(message), 250)
                    self.assertLessEqual(len(message), 400)
                    self.assertTrue(theme["source_url"].startswith("https://"))

    def test_learning_card_rejects_missing_or_invalid_source(self):
        theme = {**LEARNING_THEMES[0], "source_url": "not-a-url"}
        card = theme["cards"][0]
        message = format_learning_card(theme, card, date(2026, 6, 22))
        self.assertFalse(validate_learning_card(theme, card, message))

    def test_learning_card_rejects_content_over_length_limit(self):
        theme = LEARNING_THEMES[0]
        card = {**theme["cards"][0], "extension": "过长内容" * 100}
        message = format_learning_card(theme, card, date(2026, 6, 22))
        self.assertFalse(validate_learning_card(theme, card, message))

    def test_learning_card_does_not_repeat_yesterday_review(self):
        config = BroadcastConfig()
        monday = build_broadcast("noon", config, date(2026, 6, 22))
        tuesday = build_broadcast("noon", config, date(2026, 6, 23))
        self.assertNotIn("昨日回响：", monday.message)
        self.assertNotIn("昨日回响：", tuesday.message)

    def test_friday_learning_card_is_not_forced_to_weekly_summary(self):
        broadcast = build_broadcast("noon", BroadcastConfig(), date(2026, 6, 26))
        self.assertNotIn("本周知识拼图", broadcast.message)

    def test_learning_card_uses_three_level_deduplication(self):
        day = date(2026, 6, 22)
        config = BroadcastConfig()
        first = build_broadcast("noon", config, day)
        for kind, value in first.context["learning_keys"].items():
            duplicate_config = BroadcastConfig()
            duplicate_config.sent_learning_ids[kind].add(value)
            with self.subTest(kind=kind):
                duplicate = build_broadcast("noon", duplicate_config, day)
                if kind == "dates":
                    self.assertIsNone(duplicate)
                else:
                    self.assertIsNotNone(duplicate)
                    self.assertNotEqual(
                        first.context["learning_keys"]["theme_slots"],
                        duplicate.context["learning_keys"]["theme_slots"],
                    )

    def test_learning_state_is_persisted_without_losing_other_state(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            save_sent_keys(path, {"2026-06-22:morning"})
            expected = {
                "theme_slots": {"psychology:0"},
                "dates": {"2026-06-22"},
                "content": {"content-hash"},
            }
            save_sent_learning_ids(path, expected)
            self.assertEqual(expected, load_sent_learning_ids(path))
            self.assertEqual({"2026-06-22:morning"}, load_sent_keys(path))

    def test_sent_fact_ids_are_persisted_without_losing_sent_keys(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            save_sent_keys(path, {"2026-06-26:morning"})
            save_sent_fact_ids(path, {"psychology": {"psych-id"}, "history": {"history-id"}})
            self.assertEqual({"2026-06-26:morning"}, load_sent_keys(path))
            self.assertEqual(
                {"psychology": {"psych-id"}, "history": {"history-id"}},
                load_sent_fact_ids(path),
            )

    def test_weather_is_loaded_from_open_meteo(self):
        class Response:
            def __init__(self, data):
                self.body = json.dumps(data).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return self.body

        responses = [
            Response({"results": [{"latitude": 39.9042, "longitude": 116.4074}]}),
            Response(
                {
                    "current": {"temperature_2m": 28.4, "weather_code": 2},
                    "daily": {
                        "temperature_2m_max": [31.2],
                        "temperature_2m_min": [21.8],
                        "precipitation_probability_max": [40],
                    },
                }
            ),
        ]
        with patch("daily_broadcast.urllib.request.urlopen", side_effect=responses):
            self.assertEqual(
                "多云，当前 28℃，今日 22～31℃，降水概率 40%",
                fetch_weather("北京"),
            )

    def test_morning_uses_weather_source_without_moyu_score(self):
        with patch(
            "daily_broadcast.fetch_weather",
            return_value="晴，当前 26℃，今日 20～30℃，降水概率 10%",
        ):
            morning = build_broadcast("morning", BroadcastConfig(), date(2026, 6, 26))
        self.assertIn("早安，冯驰。", morning.message)
        self.assertIn("北京天气：晴，当前 26℃，今日 20～30℃，降水概率 10%", morning.message)
        self.assertIn("今日摘抄：", morning.message)
        self.assertEqual(3, len(morning.context["evening_ids"]))
        self.assertNotIn("摸鱼指数", morning.message)
        self.assertNotIn("moyu_score", morning.context)

    def test_weather_failure_has_fallback(self):
        with patch("daily_broadcast.fetch_weather", side_effect=OSError):
            morning = build_broadcast("morning", BroadcastConfig(), date(2026, 6, 26))
        self.assertIn("天气：暂时无法获取", morning.message)

    def test_owen_links_parser_extracts_all_links(self):
        html = "".join(
            f'<article data-format="link"><h2><a class="feed-link-title-link" '
            f'href="https://example.com/{index}">消息 {index}</a></h2></article>'
            for index in range(1, 12)
        )
        self.assertEqual(
            [{"title": f"消息 {index}", "url": f"https://example.com/{index}"} for index in range(1, 12)],
            parse_owen_links(html),
        )

    def test_industry_broadcast_contains_ten_links(self):
        config = BroadcastConfig(
            industry_source="owen",
            industry_news=[
                {"title": f"消息 {index}", "url": f"https://example.com/{index}"}
                for index in range(1, 11)
            ]
        )
        broadcast = build_broadcast("industry", config, date(2026, 6, 26))
        self.assertEqual(11, len(broadcast.message.splitlines()))
        self.assertIn("10. 消息 10", broadcast.message)

    def test_owen_links_fetch_skips_previously_sent_urls(self):
        class Response:
            def __init__(self, html):
                self.body = html.encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return self.body

        def page(start):
            return "".join(
                f'<article data-format="link"><h2><a class="feed-link-title-link" '
                f'href="https://example.com/{index}">消息 {index}</a></h2></article>'
                for index in range(start, start + 10)
            )

        sent_urls = {f"https://example.com/{index}" for index in range(1, 11)}
        with patch(
            "daily_broadcast.urllib.request.urlopen",
            side_effect=[Response(page(1)), Response(page(11))],
        ):
            news = fetch_owen_links(sent_urls)
        self.assertEqual(
            [f"https://example.com/{index}" for index in range(11, 21)],
            [item["url"] for item in news],
        )

    def test_owen_links_fetch_uses_explicit_ssl_context(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b""

        with patch(
            "daily_broadcast.urllib.request.urlopen",
            return_value=Response(),
        ) as urlopen:
            fetch_owen_links()
        self.assertIsNotNone(urlopen.call_args.kwargs["context"])

    def test_wechat_feed_parser_extracts_complete_articles(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/">
          <channel>
            <title>示例公众号</title>
            <item>
              <title><![CDATA[文章标题]]></title>
              <link>https://mp.weixin.qq.com/s/example</link>
              <dc:creator><![CDATA[作者]]></dc:creator>
              <pubDate>Mon, 29 Jun 2026 08:00:00 +0800</pubDate>
              <description><![CDATA[<p>文章 <strong>摘要</strong></p>]]></description>
            </item>
          </channel>
        </rss>""".encode()
        self.assertEqual(
            [
                {
                    "title": "文章标题",
                    "author": "作者",
                    "published_at": "Mon, 29 Jun 2026 08:00:00 +0800",
                    "summary": "文章 摘要",
                    "url": "https://mp.weixin.qq.com/s/example",
                }
            ],
            parse_wechat_feed(xml),
        )

    def test_wechat_feed_summary_is_truncated(self):
        xml = f"""<rss><channel><title>公众号</title><item>
            <title>文章标题</title>
            <link>https://mp.weixin.qq.com/s/example</link>
            <pubDate>2026-06-29</pubDate>
            <description>{"摘要" * 150}</description>
        </item></channel></rss>"""
        item = parse_wechat_feed(xml)[0]
        self.assertEqual(201, len(item["summary"]))
        self.assertTrue(item["summary"].endswith("…"))

    def test_wechat_feed_urls_are_loaded_from_config(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "industry_source": "wechat",
                        "wechat_feed_urls": ["https://rss.example.com/feed"],
                    }
                ),
                encoding="utf-8",
            )
            config = load_config(path)
        self.assertEqual("wechat", config.industry_source)
        self.assertEqual(["https://rss.example.com/feed"], config.wechat_feed_urls)

    def test_generic_content_feeds_are_loaded_from_config(self):
        feeds = [
            {"name": "公众号", "url": "https://rss.example.com/wechat.xml"},
            {"name": "网站", "url": "https://example.com/feed.xml"},
        ]
        with TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps({"industry_source": "feeds", "content_feeds": feeds}),
                encoding="utf-8",
            )
            config = load_config(path)
        self.assertEqual("feeds", config.industry_source)
        self.assertEqual(feeds, config.content_feeds)

    def test_generic_content_feeds_use_configured_source_name(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return """<rss><channel><title>原始名称</title><item>
                    <title>新文章</title>
                    <link>https://example.com/new</link>
                    <pubDate>2026-06-30</pubDate>
                    <description>摘要</description>
                </item></channel></rss>""".encode()

        feeds = [{"name": "配置名称", "url": "https://example.com/feed.xml"}]
        with patch("daily_broadcast.urllib.request.urlopen", return_value=Response()):
            news = fetch_content_feeds(feeds)
        self.assertEqual("配置名称", news[0]["source_name"])

    def test_generic_content_feed_broadcast(self):
        config = BroadcastConfig(
            industry_source="feeds",
            industry_news=[
                {
                    "title": "网站文章",
                    "author": "作者",
                    "source_name": "示例网站",
                    "published_at": "2026-06-30",
                    "summary": "文章摘要",
                    "url": "https://example.com/article",
                }
            ],
        )
        broadcast = build_broadcast("industry", config, date(2026, 6, 30))
        self.assertIn("大道消息｜内容订阅", broadcast.message)
        self.assertIn("[示例网站｜2026-06-30] 网站文章", broadcast.message)

    def test_wechat_feed_fetch_skips_sent_urls(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return """<rss><channel><title>公众号</title><item>
                    <title>新文章</title>
                    <link>https://mp.weixin.qq.com/s/new</link>
                    <pubDate>2026-06-29</pubDate>
                    <description>摘要</description>
                </item></channel></rss>""".encode()

        with patch("daily_broadcast.urllib.request.urlopen", return_value=Response()):
            news = fetch_wechat_feeds(
                ["https://rss.example.com/feed"],
                {"https://mp.weixin.qq.com/s/sent"},
            )
        self.assertEqual(["https://mp.weixin.qq.com/s/new"], [item["url"] for item in news])

    def test_wechat_broadcast_uses_separate_source_and_history(self):
        item = {
            "title": "文章标题",
            "author": "示例公众号",
            "published_at": "2026-06-29",
            "summary": "文章摘要",
            "url": "https://mp.weixin.qq.com/s/example",
        }
        config = BroadcastConfig(industry_source="wechat", industry_news=[item])
        broadcast = build_broadcast("industry", config, date(2026, 6, 26))
        self.assertIn("大道消息｜微信公众号", broadcast.message)
        self.assertIn("1. [示例公众号｜2026-06-29] 文章标题", broadcast.message)
        self.assertIn("文章摘要", broadcast.message)
        self.assertIn("原文：https://mp.weixin.qq.com/s/example", broadcast.message)

        with TemporaryDirectory() as directory:
            state_path = Path(directory) / "news-state.json"
            save_sent_news_ids(state_path, "jike", {"jike-hash"})
            save_sent_news_ids(state_path, "wechat", {item["url"]})
            self.assertEqual({item["url"]}, load_sent_news_ids("wechat", state_path))
            self.assertEqual({"jike-hash"}, load_sent_news_ids("jike", state_path))

    def test_explicit_wechat_source_does_not_fall_back_to_owen(self):
        config = BroadcastConfig(
            industry_source="wechat",
            wechat_feed_urls=["https://rss.example.com/feed"],
        )
        with TemporaryDirectory() as directory, patch(
            "daily_broadcast.fetch_wechat_feeds",
            return_value=[],
        ) as fetch_wechat, patch("daily_broadcast.fetch_owen_links") as fetch_owen:
            sent_ids = prepare_industry_news(
                config,
                state_path=Path(directory) / "news-state.json",
            )
        self.assertEqual("wechat", config.industry_source)
        self.assertEqual([], config.industry_news)
        self.assertEqual(set(), sent_ids)
        fetch_wechat.assert_called_once_with(config.wechat_feed_urls, set())
        fetch_owen.assert_not_called()

    def test_sent_news_urls_are_persisted(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "news-state.json"
            save_sent_news_urls(path, {"https://example.com/1"})
            self.assertEqual({"https://example.com/1"}, load_sent_news_urls(path))

    def test_jike_items_are_deduplicated_by_normalized_content_hash(self):
        base_item = {
            "author": "作者",
            "published_at": "刚刚",
            "url": "https://web.okjike.com/originalPosts/old",
        }
        sent_id = news_item_id("jike", {**base_item, "content": "同一条   正文"})
        news = filter_unsent_news(
            [
                {
                    **base_item,
                    "title": "旧内容",
                    "content": " 同一条 正文 ",
                },
                {
                    **base_item,
                    "title": "新内容",
                    "content": "新的正文",
                    "url": "https://web.okjike.com/originalPosts/new",
                },
            ],
            "jike",
            {sent_id},
        )
        self.assertEqual(["新内容"], [item["title"] for item in news])

    def test_jike_item_requires_complete_preview_fields(self):
        with self.assertRaisesRegex(ValueError, "author, published_at, url"):
            news_item_id("jike", {"content": "正文"})

    def test_two_sources_persist_independent_histories(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "news-state.json"
            save_sent_news_ids(path, "jike", {"jike-hash"})
            save_sent_news_ids(path, "owen", {"https://example.com/1"})
            self.assertEqual({"jike-hash"}, load_sent_news_ids("jike", path))
            self.assertEqual({"https://example.com/1"}, load_sent_news_ids("owen", path))

    def test_default_industry_source_is_jike(self):
        broadcast = build_broadcast("industry", BroadcastConfig(), date(2026, 6, 26))
        self.assertIn("大道消息｜即刻精选", broadcast.message)
        self.assertIn("Chrome 的即刻登录态", broadcast.message)

    def test_industry_falls_back_to_owen_when_jike_is_unavailable(self):
        config = BroadcastConfig()
        with TemporaryDirectory() as directory, patch(
            "daily_broadcast.fetch_owen_links",
            return_value=[{"title": "Owen 消息", "url": "https://example.com/owen"}],
        ) as fetch:
            sent_ids = prepare_industry_news(
                config,
                state_path=Path(directory) / "news-state.json",
            )
        self.assertEqual("owen", config.industry_source)
        self.assertEqual("Owen 消息", config.industry_news[0]["title"])
        self.assertEqual(set(), sent_ids)
        fetch.assert_called_once_with(set())

    def test_industry_keeps_jike_when_unsent_items_are_available(self):
        config = BroadcastConfig()
        items = [
            {
                "author": "作者",
                "published_at": "刚刚",
                "content": "即刻正文",
                "url": "https://web.okjike.com/originalPosts/example",
            }
        ]
        with TemporaryDirectory() as directory:
            items_path = Path(directory) / "items.json"
            items_path.write_text(json.dumps(items), encoding="utf-8")
            with patch("daily_broadcast.fetch_owen_links") as fetch:
                prepare_industry_news(
                    config,
                    items_path,
                    Path(directory) / "news-state.json",
                )
        self.assertEqual("jike", config.industry_source)
        self.assertEqual(items, config.industry_news)
        fetch.assert_not_called()

    def test_industry_fallback_uses_owen_history(self):
        config = BroadcastConfig()
        with TemporaryDirectory() as directory:
            state_path = Path(directory) / "news-state.json"
            save_sent_news_ids(state_path, "jike", {"jike-hash"})
            save_sent_news_ids(state_path, "owen", {"https://example.com/sent"})
            with patch(
                "daily_broadcast.fetch_owen_links",
                return_value=[],
            ) as fetch:
                sent_ids = prepare_industry_news(config, state_path=state_path)
        self.assertEqual({"https://example.com/sent"}, sent_ids)
        fetch.assert_called_once_with({"https://example.com/sent"})

    def test_jike_broadcast_uses_author_time_content_and_original_url(self):
        config = BroadcastConfig(
            industry_news=[
                {
                    "author": "作者",
                    "published_at": "2 小时前",
                    "content": "正文",
                    "like_count": 12,
                    "comment_count": 3,
                    "url": "https://web.okjike.com/originalPosts/example",
                }
            ]
        )
        broadcast = build_broadcast("industry", config, date(2026, 6, 26))
        self.assertIn("1. [作者｜2 小时前] 正文", broadcast.message)
        self.assertIn(
            "原文：https://web.okjike.com/originalPosts/example",
            broadcast.message,
        )
        self.assertNotIn("赞 12", broadcast.message)
        self.assertNotIn("评 3", broadcast.message)

    def test_manual_industry_broadcast_can_run_on_weekends(self):
        config = BroadcastConfig(
            industry_news=[
                {
                    "author": "作者",
                    "published_at": "刚刚",
                    "content": "周末精选",
                    "url": "https://web.okjike.com/originalPosts/weekend",
                }
            ]
        )
        broadcast = build_broadcast(
            "industry",
            config,
            date(2026, 6, 27),
            allow_non_workday=True,
        )
        self.assertIn("周末精选", broadcast.message)

    def test_owen_source_remains_available(self):
        config = BroadcastConfig(industry_source="owen")
        broadcast = build_broadcast("industry", config, date(2026, 6, 26))
        self.assertIn("大道消息｜Owen Links", broadcast.message)
        self.assertIn("暂时无法读取 Owen Links", broadcast.message)

    def test_industry_broadcast_is_named_dadao_news(self):
        broadcast = build_broadcast("industry", BroadcastConfig(), date(2026, 6, 26))
        self.assertIn("大道消息", broadcast.message)

    def test_each_workday_broadcast_has_short_message(self):
        config = BroadcastConfig(weather="晴，12-22 度")
        for kind in ("morning", "noon", "industry", "countdown", "evening"):
            with self.subTest(kind=kind):
                broadcast = build_broadcast(kind, config, date(2026, 6, 26))
                self.assertIsNotNone(broadcast)
                lines = broadcast.message.splitlines()
                self.assertGreaterEqual(len(lines), 3)
                maximum = 9 if kind in ("noon", "countdown") else 7 if kind == "morning" else 6
                self.assertLessEqual(len(lines), maximum)

    def test_countdown_uses_seven_pm_as_default_work_end(self):
        broadcast = build_broadcast(
            "countdown",
            BroadcastConfig(),
            date(2026, 6, 26),
            now_time=datetime(2026, 6, 26, 17, 30).time(),
        )
        self.assertIn("距下班约 1 小时 30 分钟", broadcast.message)

    def test_countdown_contains_all_five_experience_modules(self):
        broadcast = build_broadcast(
            "countdown",
            BroadcastConfig(),
            date(2026, 7, 2),
            now_time=datetime(2026, 7, 2, 17, 30).time(),
        )

        for module in COUNTDOWN_MODULES:
            self.assertIn(f"{module}：", broadcast.message)
        self.assertEqual(
            set(COUNTDOWN_MODULES),
            set(broadcast.context["countdown_ids"]),
        )

    def test_countdown_has_100_unique_items_per_module(self):
        experiences = load_countdown_experiences(COUNTDOWN_EXPERIENCES_PATH)

        for module in COUNTDOWN_MODULES:
            with self.subTest(module=module):
                self.assertEqual(100, len(experiences[module]))
                self.assertEqual(100, len(set(experiences[module])))

    def test_today_question_uses_100_standalone_questions(self):
        raw = json.loads(COUNTDOWN_EXPERIENCES_PATH.read_text(encoding="utf-8"))
        questions = raw["今日小问题"]["items"]

        self.assertEqual(100, len(questions))
        self.assertEqual(100, len(set(questions)))
        self.assertNotIn("starts", raw["今日小问题"])
        self.assertNotIn("ends", raw["今日小问题"])

    def test_countdown_skips_sent_content(self):
        experiences = load_countdown_experiences(COUNTDOWN_EXPERIENCES_PATH)
        config = BroadcastConfig()
        for module in COUNTDOWN_MODULES:
            config.sent_countdown_ids[module].add(
                evening_quote_id(experiences[module][0])
            )

        broadcast = build_broadcast(
            "countdown",
            config,
            date(2026, 7, 2),
            now_time=datetime(2026, 7, 2, 17, 30).time(),
        )

        for module in COUNTDOWN_MODULES:
            self.assertNotIn(
                f"{module}：{experiences[module][0]}",
                broadcast.message,
            )
            self.assertIn(
                f"{module}：{experiences[module][1]}",
                broadcast.message,
            )

    def test_countdown_sent_ids_share_state_file(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            expected = {
                module: {f"{module}-id"}
                for module in COUNTDOWN_MODULES
            }
            save_sent_keys(path, {"2026-07-02:morning"})
            save_sent_countdown_ids(path, expected)

            self.assertEqual(expected, load_sent_countdown_ids(path))
            self.assertEqual({"2026-07-02:morning"}, load_sent_keys(path))

    def test_evening_broadcast_uses_three_oldest_unsent_quotes(self):
        quotes = load_evening_quotes(
            "/Users/kityhello/workplace/tech-docs/wenxue/📚 句子控精选 (2).md"
        )
        config = BroadcastConfig()
        broadcast = build_broadcast("evening", config, date(2026, 6, 26))

        self.assertEqual(3, len(broadcast.context["evening_ids"]))
        self.assertEqual(["2026-06-01"] * 3, broadcast.context["evening_dates"])
        for quote in quotes[:3]:
            self.assertIn(quote["content"], broadcast.message)
        self.assertIn(
            f"驰子，{load_evening_closings(EVENING_CLOSINGS_PATH)[0]}",
            broadcast.message,
        )

    def test_evening_broadcast_skips_sent_quotes_and_crosses_dates(self):
        quotes = load_evening_quotes(
            "/Users/kityhello/workplace/tech-docs/wenxue/📚 句子控精选 (2).md"
        )
        june_first = [quote for quote in quotes if quote["date"] == "2026-06-01"]
        config = BroadcastConfig(
            sent_evening_ids={
                evening_quote_id(quote["content"])
                for quote in june_first[:-2]
            }
        )

        broadcast = build_broadcast("evening", config, date(2026, 6, 26))

        self.assertEqual(
            ["2026-06-01", "2026-06-01", "2026-06-03"],
            broadcast.context["evening_dates"],
        )

    def test_evening_sent_ids_share_state_file(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            save_sent_keys(path, {"2026-06-26:morning"})
            save_sent_evening_ids(path, {"quote-id"})
            save_sent_evening_closing_ids(path, {"closing-id"})

            self.assertEqual({"quote-id"}, load_sent_evening_ids(path))
            self.assertEqual(
                {"closing-id"},
                load_sent_evening_closing_ids(path),
            )
            self.assertEqual({"2026-06-26:morning"}, load_sent_keys(path))

    def test_evening_closing_changes_after_sent(self):
        closings = load_evening_closings(EVENING_CLOSINGS_PATH)
        config = BroadcastConfig(
            sent_evening_closing_ids={evening_quote_id(closings[0])}
        )

        broadcast = build_broadcast("evening", config, date(2026, 6, 26))

        self.assertIn(closings[1], broadcast.message)
        self.assertNotIn(closings[0], broadcast.message)

    def test_evening_uses_milestone_after_100_closings(self):
        closings = load_evening_closings(EVENING_CLOSINGS_PATH)
        config = BroadcastConfig(
            sent_evening_closing_ids={
                evening_quote_id(closing)
                for closing in closings
            }
        )

        broadcast = build_broadcast("evening", config, date(2026, 6, 26))

        self.assertIn(f"驰子，{EVENING_MILESTONE}", broadcast.message)

    def test_weekend_broadcast_is_silent(self):
        config = BroadcastConfig()
        self.assertIsNone(build_broadcast("morning", config, date(2026, 6, 27)))

    def test_disabled_module_is_silent(self):
        config = BroadcastConfig()
        config.enabled["industry"] = False
        self.assertIsNone(build_broadcast("industry", config, date(2026, 6, 26)))

    def test_fallbacks_when_external_data_missing(self):
        config = BroadcastConfig()
        with patch("daily_broadcast.fetch_weather", side_effect=OSError):
            morning = build_broadcast("morning", config, date(2026, 6, 26))
        industry = build_broadcast("industry", config, date(2026, 6, 26))
        self.assertIn("天气：暂时无法获取", morning.message)
        self.assertIn("Chrome 的即刻登录态", industry.message)

    def test_due_broadcasts_send_each_time_point_once(self):
        config = BroadcastConfig()
        now = datetime(2026, 6, 26, 17, 45)
        sent = {"2026-06-26:morning", "2026-06-26:noon"}
        due = due_broadcasts(config, now, sent)
        self.assertEqual(["countdown"], [broadcast.kind for _, broadcast in due])

    def test_due_broadcasts_can_include_preloaded_jike_news(self):
        config = BroadcastConfig(
            industry_news=[
                {
                    "author": "作者",
                    "published_at": "刚刚",
                    "content": "正文",
                    "url": "https://web.okjike.com/originalPosts/example",
                }
            ]
        )
        now = datetime(2026, 6, 26, 17, 45)
        sent = {"2026-06-26:morning", "2026-06-26:noon"}
        due = due_broadcasts(config, now, sent)
        self.assertEqual(["industry", "countdown"], [broadcast.kind for _, broadcast in due])

    def test_sent_keys_are_persisted_for_due_mode(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            save_sent_keys(path, {"2026-06-26:morning"})
            self.assertEqual({"2026-06-26:morning"}, load_sent_keys(path))

    def test_followup_can_answer_noon_question(self):
        last_broadcast = {
            "kind": "noon",
            "context": {"answer": "1971 年。"},
        }
        self.assertEqual("答案：1971 年。", answer_followup("/答案", last_broadcast))

    def test_followup_handles_lunch_and_poll_commands(self):
        config = BroadcastConfig(lunch_options=["牛肉面"])
        self.assertIn("牛肉面", answer_followup("/今天吃什么", config=config, day=date(2026, 6, 26)))
        self.assertIn("A vs B", answer_followup("/投票 A vs B"))


if __name__ == "__main__":
    unittest.main()
