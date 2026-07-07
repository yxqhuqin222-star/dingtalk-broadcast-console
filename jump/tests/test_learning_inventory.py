import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from learning_inventory import (
    _clean_summary,
    _clean_url,
    load_inventory,
    mark_card_sent,
    parse_feed,
    save_inventory,
    select_card,
)


def card(category, url):
    return {
        "category": category,
        "title": "标题",
        "summary": "摘要",
        "source": "测试来源",
        "source_url": url,
        "published_at": "2026-07-03",
    }


class LearningInventoryTest(unittest.TestCase):
    def test_parse_feed_extracts_real_article_fields(self):
        xml = """<?xml version="1.0"?>
        <rss><channel><item>
          <title>Article title</title>
          <description><![CDATA[<p>这是一段长度足够、信息完整并且可以脱离标题独立理解的中文文章摘要，用于验证真实内容能够进入库存。</p>]]></description>
          <pubDate>Fri, 03 Jul 2026 10:00:00 GMT</pubDate>
          <link>https://example.com/article</link>
        </item></channel></rss>""".encode()
        items = parse_feed(xml, "Example", "科学")
        self.assertEqual("Article title", items[0]["title"])
        self.assertIn("信息完整", items[0]["summary"])
        self.assertEqual("https://example.com/article", items[0]["url"])

    def test_short_summary_is_rejected(self):
        xml = b"""<?xml version="1.0"?>
        <rss><channel><item>
          <title>Article title</title>
          <description>too short</description>
          <pubDate>Fri, 03 Jul 2026 10:00:00 GMT</pubDate>
          <link>https://example.com/article</link>
        </item></channel></rss>"""
        self.assertEqual([], parse_feed(xml, "Example", "科学"))

    def test_summary_with_photo_credit_is_rejected(self):
        xml = """<?xml version="1.0"?>
        <rss><channel><item>
          <title>Article title</title>
          <description>团队成员在实验室工作。研究所供图 ■本报记者 张三，后面还有一段看似完整但不适合直接播报的内容。</description>
          <pubDate>Fri, 03 Jul 2026 10:00:00 GMT</pubDate>
          <link>https://example.com/article</link>
        </item></channel></rss>""".encode()
        self.assertEqual([], parse_feed(xml, "Example", "科学"))

    def test_summary_removes_editor_metadata_and_uses_sentence_boundary(self):
        value = "作者 | 张三 编辑 | 李四 " + "完整信息。" * 30
        summary = _clean_summary(value)
        self.assertNotIn("作者", summary)
        self.assertLessEqual(len(summary), 180)
        self.assertTrue(summary.endswith("。"))

    def test_url_removes_tracking_parameters(self):
        self.assertEqual(
            "https://example.com/article?id=1",
            _clean_url(
                "https://example.com/article?id=1&utm_source=rss&f=rss"
            ),
        )

    def test_selection_avoids_previous_category(self):
        inventory = {
            "cards": [
                card("科学", "https://example.com/1"),
                card("历史", "https://example.com/2"),
            ],
            "last_category": "科学",
        }
        self.assertEqual("历史", select_card(inventory)["category"])

    def test_selection_avoids_exhaustion_dead_end(self):
        categories = ["科技"] * 12 + ["商业"] * 6 + ["科学"] * 4 + ["生活"] * 8
        inventory = {
            "cards": [
                card(category, f"https://example.com/{index}")
                for index, category in enumerate(categories)
            ],
            "sent_urls": [],
            "last_category": "",
        }
        selected_categories = []
        while selected := select_card(inventory):
            selected_categories.append(selected["category"])
            mark_card_sent(inventory, selected)
        self.assertEqual(30, len(selected_categories))
        self.assertTrue(
            all(
                current != following
                for current, following in zip(
                    selected_categories,
                    selected_categories[1:],
                )
            )
        )

    def test_sent_card_is_removed_and_never_requeued(self):
        selected = card("科学", "https://example.com/1")
        inventory = {
            "cards": [selected, card("历史", "https://example.com/2")],
            "sent_urls": [],
            "last_category": "",
        }
        mark_card_sent(inventory, selected)
        self.assertNotIn(selected, inventory["cards"])
        self.assertIn(selected["source_url"], inventory["sent_urls"])
        self.assertEqual("科学", inventory["last_category"])

    def test_inventory_round_trip_preserves_state(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "inventory.json"
            expected = {
                "cards": [card("科学", "https://example.com/1")],
                "sent_urls": ["https://example.com/old"],
                "last_category": "历史",
                "last_refresh_at": "2026-07-03T10:00:00",
                "last_error": "",
            }
            save_inventory(path, expected)
            self.assertEqual(expected, load_inventory(path))


if __name__ == "__main__":
    unittest.main()
