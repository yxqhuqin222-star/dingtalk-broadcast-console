import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from wechat_monitor import (
    article_id,
    check_monitors,
    collect_markdown_previews,
    filter_monitor_results,
    format_markdown_preview,
    load_state,
    normalized_match_text,
    parse_sogou_results,
    save_state,
)


MONITOR = {
    "id": "lijigang-weekly",
    "name": "李继刚｜人生周报",
    "query": "人生周报 李继刚",
    "account": "李继刚",
    "title_prefix": "人生周报",
}


def result(title, account="李继刚", published_at="2026-06-28 23:41"):
    return {
        "title": title,
        "account": account,
        "published_at": published_at,
        "search_link": "https://weixin.sogou.com/link?example",
    }


class WechatMonitorTest(unittest.TestCase):
    def test_parse_and_filter_realistic_sogou_results(self):
        html = """
        <ul class="news-list">
          <li>
            <h3><a href="/link?url=v079"><em>人生周报</em>v079: 凹凸</a></h3>
            <div class="s-p"><span class="all-time-y2">李继刚</span>
              <span class="s2"><script>document.write(timeConvert('1782661301'))</script></span>
            </div>
          </li>
          <li>
            <h3><a href="/link?url=other">李继刚的认知坐标系</a></h3>
            <div class="s-p"><span class="all-time-y2">其他账号</span>
              <span class="s2"><script>document.write(timeConvert('1782661301'))</script></span>
            </div>
          </li>
        </ul>
        """
        results = parse_sogou_results(html)
        filtered = filter_monitor_results(MONITOR, results)
        self.assertEqual(["人生周报 v079: 凹凸"], [item["title"] for item in filtered])
        self.assertEqual("李继刚", filtered[0]["account"])

    def test_title_matching_ignores_emphasis_whitespace(self):
        self.assertEqual(
            normalized_match_text("人生周报 v078:鱼"),
            normalized_match_text("人生周报v078:鱼"),
        )

    def test_first_check_builds_baseline_without_new_article(self):
        state = {"monitors": {}}
        report = check_monitors(
            [MONITOR],
            state,
            fetcher=lambda monitor: [result("人生周报 v079"), result("人生周报 v078")],
        )
        monitor_state = state["monitors"][MONITOR["id"]]
        self.assertEqual("initialized", report[0]["status"])
        self.assertEqual(2, len(monitor_state["seen_ids"]))
        self.assertEqual([], monitor_state["articles"])

    def test_later_check_extracts_only_new_article(self):
        old_item = result("人生周报 v079")
        state = {
            "monitors": {
                MONITOR["id"]: {
                    "seen_ids": [article_id(MONITOR, old_item)],
                    "articles": [],
                }
            }
        }
        new_item = result("人生周报 v080", published_at="2026-07-05 20:00")
        report = check_monitors(
            [MONITOR],
            state,
            fetcher=lambda monitor: [new_item, old_item],
            extractor=lambda monitor, item: {**item, "content": "新正文"},
        )
        monitor_state = state["monitors"][MONITOR["id"]]
        self.assertEqual(1, report[0]["new_count"])
        self.assertEqual("人生周报 v080", monitor_state["articles"][0]["title"])
        self.assertEqual("新正文", monitor_state["articles"][0]["content"])

    def test_failed_extraction_is_retried_until_success(self):
        old_item = result("人生周报 v079")
        new_item = result("人生周报 v080", published_at="2026-07-05 20:00")
        state = {
            "monitors": {
                MONITOR["id"]: {
                    "seen_ids": [article_id(MONITOR, old_item)],
                    "articles": [],
                }
            }
        }

        def fail(monitor, item):
            raise RuntimeError("temporary limit")

        check_monitors(
            [MONITOR],
            state,
            fetcher=lambda monitor: [new_item, old_item],
            extractor=fail,
        )
        monitor_state = state["monitors"][MONITOR["id"]]
        new_id = article_id(MONITOR, new_item)
        self.assertNotIn(new_id, monitor_state["seen_ids"])
        self.assertIn(new_id, monitor_state["failures"])

        check_monitors(
            [MONITOR],
            state,
            fetcher=lambda monitor: [new_item, old_item],
            extractor=lambda monitor, item: {**item, "content": "新正文"},
        )
        self.assertIn(new_id, monitor_state["seen_ids"])
        self.assertNotIn(new_id, monitor_state["failures"])

    def test_state_round_trip(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            state = {"monitors": {MONITOR["id"]: {"seen_ids": ["one"], "articles": []}}}
            save_state(path, state)
            self.assertEqual(state, load_state(path))

    def test_markdown_preview_contains_metadata_and_original_link(self):
        article = {
            "title": "人生周报 v080",
            "account": "李继刚",
            "published_at": "2026-07-05 20:00",
            "content": "正文内容",
            "resolved_url": "https://mp.weixin.qq.com/s/example",
        }
        preview = format_markdown_preview(article)
        self.assertIn("# 大道消息｜微信公众号", preview)
        self.assertIn("## 人生周报 v080", preview)
        self.assertIn("> 公众号：李继刚", preview)
        self.assertIn("正文已抓取，共 4 字", preview)
        self.assertIn(
            "[阅读原文](https://mp.weixin.qq.com/s/example)",
            preview,
        )

    def test_collect_markdown_previews_uses_captured_articles_only(self):
        article = {
            "title": "人生周报 v080",
            "account": "李继刚",
            "published_at": "2026-07-05 20:00",
            "content": "正文内容",
            "search_link": "https://weixin.sogou.com/link?example",
        }
        state = {
            "monitors": {
                MONITOR["id"]: {
                    "seen_ids": [],
                    "articles": [article],
                    "failures": {"failed": {"title": "失败文章"}},
                }
            }
        }
        previews = collect_markdown_previews(state)
        self.assertEqual(1, len(previews))
        self.assertIn("人生周报 v080", previews[0])


if __name__ == "__main__":
    unittest.main()
