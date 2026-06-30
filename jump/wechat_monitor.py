#!/usr/bin/env python3
import argparse
import asyncio
import hashlib
import json
import re
import ssl
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import certifi
from bs4 import BeautifulSoup


DEFAULT_CONFIG_PATH = Path(__file__).with_name("wechat_monitors.json")
DEFAULT_STATE_PATH = Path(__file__).with_name(".wechat_monitor_state.json")
SEARCH_URL = "https://weixin.sogou.com/weixin"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
SHANGHAI_TZ = timezone(timedelta(hours=8))


def load_monitors(path=DEFAULT_CONFIG_PATH):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    monitors = data.get("wechat_monitors", [])
    required = ("id", "name", "query", "account")
    if not monitors or any(
        not isinstance(monitor, dict)
        or any(not monitor.get(field) for field in required)
        for monitor in monitors
    ):
        raise ValueError("wechat_monitors must contain id, name, query and account.")
    return monitors


def load_state(path=DEFAULT_STATE_PATH):
    path = Path(path)
    if not path.exists():
        return {"monitors": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(path, state):
    path = Path(path)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    temporary_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary_path.replace(path)


def search_url(query):
    return f"{SEARCH_URL}?{urllib.parse.urlencode({'type': 2, 'query': query})}"


def format_timestamp(value):
    if not value:
        return ""
    return datetime.fromtimestamp(int(value), SHANGHAI_TZ).strftime("%Y-%m-%d %H:%M")


def parse_sogou_results(html):
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for element in soup.select("ul.news-list li"):
        title_element = element.select_one("h3 a")
        account_element = element.select_one(".s-p .all-time-y2, .account")
        if not title_element or not account_element:
            continue
        timestamp_match = re.search(
            r"timeConvert\(['\"]?(\d+)",
            str(element),
        )
        title = " ".join(title_element.get_text(" ", strip=True).split())
        account = " ".join(account_element.get_text(" ", strip=True).split())
        published_at = format_timestamp(
            timestamp_match.group(1) if timestamp_match else ""
        )
        href = urllib.parse.urljoin(SEARCH_URL, title_element.get("href", ""))
        if title and account and published_at and href:
            results.append(
                {
                    "title": title,
                    "account": account,
                    "published_at": published_at,
                    "search_link": href,
                }
            )
    return results


def fetch_search_results(monitor):
    request = urllib.request.Request(
        search_url(monitor["query"]),
        headers={"User-Agent": USER_AGENT},
    )
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(request, timeout=20, context=ssl_context) as response:
        return parse_sogou_results(response.read(2_000_000))


def filter_monitor_results(monitor, results):
    title_prefix = monitor.get("title_prefix", "")
    return [
        item
        for item in results
        if item["account"] == monitor["account"]
        and (not title_prefix or item["title"].startswith(title_prefix))
    ]


def article_id(monitor, item):
    value = "\n".join(
        (monitor["id"], item["account"], item["title"], item["published_at"])
    )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalized_match_text(value):
    return "".join(value.split())


async def extract_article(monitor, item):
    from camoufox.async_api import AsyncCamoufox

    async with AsyncCamoufox(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(search_url(monitor["query"]), wait_until="domcontentloaded")
        candidates = page.locator("ul.news-list li")
        target = None
        for index in range(await candidates.count()):
            candidate = candidates.nth(index)
            title = " ".join(
                (await candidate.locator("h3 a").inner_text()).split()
            )
            account = " ".join(
                (await candidate.locator(".s-p .all-time-y2").inner_text()).split()
            )
            if (
                normalized_match_text(title)
                == normalized_match_text(item["title"])
                and account == item["account"]
            ):
                target = candidate.locator("h3 a")
                break
        if target is None:
            raise ValueError("Matching Sogou result disappeared.")
        async with page.expect_popup(timeout=10000) as popup_info:
            await target.click()
        article_page = await popup_info.value
        await article_page.wait_for_selector("#js_content", timeout=15000)
        await article_page.wait_for_timeout(1500)
        title = " ".join(
            (await article_page.locator("#activity-name").inner_text()).split()
        )
        content = (await article_page.locator("#js_content").inner_text()).strip()
        if not title or not content:
            raise ValueError("WeChat article is incomplete.")
        return {
            **item,
            "title": title,
            "content": content,
            "resolved_url": article_page.url,
            "extracted_at": datetime.now(SHANGHAI_TZ).isoformat(),
        }


def check_monitors(monitors, state, fetcher=fetch_search_results, extractor=None):
    now = datetime.now(SHANGHAI_TZ).isoformat()
    report = []
    for monitor in monitors:
        monitor_state = state["monitors"].setdefault(
            monitor["id"],
            {"seen_ids": [], "articles": [], "failures": {}},
        )
        monitor_state.setdefault("failures", {})
        try:
            items = filter_monitor_results(monitor, fetcher(monitor))
        except Exception as error:
            monitor_state["last_checked_at"] = now
            monitor_state["last_error"] = str(error)
            report.append({"monitor": monitor["name"], "status": "error"})
            continue

        item_ids = {article_id(monitor, item): item for item in items}
        if not monitor_state["seen_ids"]:
            monitor_state["seen_ids"] = sorted(item_ids)
            monitor_state["last_checked_at"] = now
            monitor_state["last_error"] = ""
            report.append(
                {
                    "monitor": monitor["name"],
                    "status": "initialized",
                    "count": len(item_ids),
                }
            )
            continue

        new_ids = [
            item_id
            for item_id in item_ids
            if item_id not in monitor_state["seen_ids"]
        ]
        for item_id in new_ids:
            item = item_ids[item_id]
            try:
                article = (
                    extractor(monitor, item)
                    if extractor
                    else asyncio.run(extract_article(monitor, item))
                )
                monitor_state["articles"].append({"id": item_id, **article})
                monitor_state["seen_ids"].append(item_id)
                monitor_state["failures"].pop(item_id, None)
            except Exception as error:
                monitor_state["failures"][item_id] = (
                    {"id": item_id, **item, "error": str(error)}
                )
        monitor_state["seen_ids"] = sorted(set(monitor_state["seen_ids"]))
        monitor_state["last_checked_at"] = now
        monitor_state["last_error"] = ""
        report.append(
            {
                "monitor": monitor["name"],
                "status": "checked",
                "new_count": len(new_ids),
            }
        )
    return report


def format_markdown_preview(article):
    source_url = article.get("resolved_url") or article.get("search_link", "")
    content_length = len(article.get("content", ""))
    return "\n".join(
        [
            "# 大道消息｜微信公众号",
            "",
            f"## {article['title']}",
            "",
            f"> 公众号：{article['account']}",
            f"> 发布时间：{article['published_at']}",
            "",
            f"正文已抓取，共 {content_length} 字，等待生成播报摘要。",
            "",
            f"[阅读原文]({source_url})",
        ]
    )


def collect_markdown_previews(state):
    previews = []
    for monitor_state in state.get("monitors", {}).values():
        previews.extend(
            format_markdown_preview(article)
            for article in monitor_state.get("articles", [])
        )
    return previews


def main():
    parser = argparse.ArgumentParser(description="微信公众号每日只读监测")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--state", default=str(DEFAULT_STATE_PATH))
    parser.add_argument(
        "--preview",
        action="store_true",
        help="输出已捕获新文章的钉钉 Markdown 预览，不发送消息",
    )
    args = parser.parse_args()

    state = load_state(args.state)
    if args.preview:
        previews = collect_markdown_previews(state)
        print("\n\n---\n\n".join(previews) if previews else "暂无已捕获的新文章。")
        return

    monitors = load_monitors(args.config)
    report = check_monitors(monitors, state)
    save_state(args.state, state)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
