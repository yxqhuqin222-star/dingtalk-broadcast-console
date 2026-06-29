import json
import unittest
import sys
from datetime import date, datetime
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
    fetch_owen_links,
    filter_unsent_news,
    load_sent_news_ids,
    load_sent_news_urls,
    load_sent_keys,
    load_sent_fact_ids,
    parse_owen_links,
    news_item_id,
    save_sent_news_ids,
    save_sent_news_urls,
    save_sent_keys,
    save_sent_fact_ids,
)


class DailyBroadcastTest(unittest.TestCase):
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

    def test_noon_broadcast_is_always_a_history_fact(self):
        config = BroadcastConfig()
        for day_number in range(22, 27):
            with self.subTest(day_number=day_number):
                broadcast = build_broadcast("noon", config, date(2026, 6, day_number))
                self.assertIn("午间历史冷知识", broadcast.message)
                self.assertEqual("history", broadcast.context["fact_category"])

    def test_fact_categories_do_not_repeat_sent_content(self):
        config = BroadcastConfig(weather="晴")
        first_morning = build_broadcast("morning", config, date(2026, 6, 22))
        first_noon = build_broadcast("noon", config, date(2026, 6, 22))
        config.sent_fact_ids["psychology"].add(first_morning.context["fact_id"])
        config.sent_fact_ids["history"].add(first_noon.context["fact_id"])

        second_morning = build_broadcast("morning", config, date(2026, 6, 23))
        second_noon = build_broadcast("noon", config, date(2026, 6, 23))
        self.assertNotEqual(first_morning.context["fact_id"], second_morning.context["fact_id"])
        self.assertNotEqual(first_noon.context["fact_id"], second_noon.context["fact_id"])

    def test_fact_pool_exhaustion_does_not_repeat(self):
        config = BroadcastConfig(weather="晴")
        from daily_broadcast import HISTORY_FACTS, PSYCHOLOGY_FACTS, fact_id

        config.sent_fact_ids["psychology"] = {fact_id(fact) for fact in PSYCHOLOGY_FACTS}
        config.sent_fact_ids["history"] = {fact_id(fact) for fact in HISTORY_FACTS}
        morning = build_broadcast("morning", config, date(2026, 6, 26))
        noon = build_broadcast("noon", config, date(2026, 6, 26))
        self.assertIn("心理学冷知识题库已用完", morning.message)
        self.assertIn("历史冷知识题库已用完", noon.message)
        self.assertNotIn("fact_id", morning.context)
        self.assertNotIn("fact_id", noon.context)

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
        self.assertIn("——史铁生《我与地坛》", morning.message)
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
                self.assertLessEqual(len(lines), 6)

    def test_countdown_uses_seven_pm_as_default_work_end(self):
        broadcast = build_broadcast(
            "countdown",
            BroadcastConfig(),
            date(2026, 6, 26),
            now_time=datetime(2026, 6, 26, 17, 30).time(),
        )
        self.assertIn("距下班约 1 小时 30 分钟", broadcast.message)

    def test_evening_broadcast_omits_tomorrow_reminder(self):
        config = BroadcastConfig(tomorrow_reminders=["上午同步本周重点"])
        broadcast = build_broadcast("evening", config, date(2026, 6, 26))
        self.assertIn("晚间收尾", broadcast.message)
        self.assertIn("收工前 5 分钟", broadcast.message)
        self.assertNotIn("明日提醒", broadcast.message)

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
