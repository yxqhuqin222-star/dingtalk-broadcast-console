import json
import os
import unittest
from unittest.mock import patch

from dingtalk_client import send_dingtalk_message


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


if __name__ == "__main__":
    unittest.main()
