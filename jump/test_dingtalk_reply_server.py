import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dingtalk_reply_server import build_reply, ensure_keyword, extract_text, main


class DingtalkReplyServerTest(unittest.TestCase):
    def test_extract_text_removes_mention(self):
        payload = {"text": {"content": "@小猪 你能干些什么"}}
        self.assertEqual("你能干些什么", extract_text(payload))

    def test_help_reply_lists_capabilities(self):
        reply = build_reply("你能干些什么")
        self.assertIn("我现在可以做这些", reply)
        self.assertIn("/今天吃什么", reply)

    def test_builtin_lunch_command_replies_without_llm(self):
        reply = build_reply("/今天吃什么")
        self.assertIn("换一个", reply)

    def test_llm_error_falls_back_to_builtin_reply(self):
        with patch("dingtalk_reply_server.call_llm", side_effect=RuntimeError("quota")):
            reply = build_reply("讲个笑话")
        self.assertIn("大模型暂时不可用", reply)

    def test_keyword_is_added_when_configured(self):
        with patch.dict(os.environ, {"DINGTALK_KEYWORD": "jump"}):
            self.assertEqual("jump｜你好", ensure_keyword("你好"))
            self.assertEqual("jump｜你好", ensure_keyword("jump｜你好"))

    def test_main_binds_to_all_interfaces_by_default(self):
        with patch("dingtalk_reply_server.ThreadingHTTPServer") as mock_server, patch("builtins.print"):
            main()
        self.assertEqual(("0.0.0.0", 8770), mock_server.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
