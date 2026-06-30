import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from dingtalk_client import (
    prepare_authorized_markdown,
    send_dingtalk_markdown,
    send_dingtalk_markdown_file,
    send_dingtalk_message,
)


class Response:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return json.dumps({"errcode": 0, "errmsg": "ok"}).encode("utf-8")


class DingtalkClientTest(unittest.TestCase):
    def test_send_uses_explicit_ssl_context(self):
        with patch.dict(os.environ, {"DINGTALK_WEBHOOK": "https://example.com/webhook"}), patch(
            "dingtalk_client.urllib.request.urlopen",
            return_value=Response(),
        ) as urlopen:
            send_dingtalk_message("测试")

        self.assertIsNotNone(urlopen.call_args.kwargs["context"])

    def test_send_markdown_uses_markdown_payload(self):
        with patch.dict(os.environ, {"DINGTALK_WEBHOOK": "https://example.com/webhook"}), patch(
            "dingtalk_client.urllib.request.urlopen",
            return_value=Response(),
        ) as urlopen:
            final_markdown, result = send_dingtalk_markdown(
                "文章标题",
                "# 文章标题\n\n正文",
            )

        request = urlopen.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual("markdown", payload["msgtype"])
        self.assertEqual("文章标题", payload["markdown"]["title"])
        self.assertEqual("# 文章标题\n\n正文", payload["markdown"]["text"])
        self.assertEqual(final_markdown, payload["markdown"]["text"])
        self.assertEqual({"errcode": 0, "errmsg": "ok"}, result)
        self.assertIsNotNone(urlopen.call_args.kwargs["context"])

    def test_prepare_authorized_markdown_removes_marker_and_local_images(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "article.md"
            path.write_text(
                "\n".join(
                    [
                        "# 我的文章",
                        "> 内容权限：用户原创",
                        "",
                        "正文",
                        "![示意图](images/example.png)",
                        "![远程图](https://example.com/image.png)",
                    ]
                ),
                encoding="utf-8",
            )
            title, markdown = prepare_authorized_markdown(path)

        self.assertEqual("我的文章", title)
        self.assertNotIn("内容权限", markdown)
        self.assertIn("> [图片：示意图]", markdown)
        self.assertNotIn("images/example.png", markdown)
        self.assertIn("![远程图](https://example.com/image.png)", markdown)

    def test_prepare_markdown_rejects_missing_rights_marker(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "article.md"
            path.write_text("# 未授权文章\n\n正文", encoding="utf-8")
            with self.assertRaises(PermissionError):
                prepare_authorized_markdown(path)

    def test_send_authorized_markdown_file_uses_file_title(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "article.md"
            path.write_text(
                "# 授权文章\n> 内容权限：已获全文转发授权\n\n正文",
                encoding="utf-8",
            )
            with patch("dingtalk_client.send_dingtalk_markdown") as send:
                send.return_value = ("正文", {"errcode": 0})
                send_dingtalk_markdown_file(path)

        send.assert_called_once()
        self.assertEqual("授权文章", send.call_args.args[0])
        self.assertNotIn("内容权限", send.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
