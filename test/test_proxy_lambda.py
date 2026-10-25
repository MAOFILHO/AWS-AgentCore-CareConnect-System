import importlib.util
import json
import unittest
from pathlib import Path
from unittest import mock

PATH = (
    Path(__file__).resolve().parent.parent
    / "Docs/Repo/lambda-functions/careconnect-agentcore-proxy/lambda_function.py"
)
spec = importlib.util.spec_from_file_location("proxy_lambda", PATH)
proxy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proxy)

SITE = "https://site.example.com"


def event(prompt="hi", origin=SITE):
    return {
        "httpMethod": "POST",
        "headers": {"Origin": origin},
        "body": json.dumps({"prompt": prompt}),
    }


class FailingClient:
    def invoke_agent_runtime(self, **_):
        raise RuntimeError("secret arn:aws:... detail")


class Stream:
    def __init__(self, text):
        self.text = text

    def read(self):
        return self.text.encode()


class ReplyClient:
    def __init__(self, text):
        self.text = text

    def invoke_agent_runtime(self, **_):
        return {"response": Stream(self.text)}


class ProxyLambdaTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(proxy, "ALLOWED_ORIGIN", SITE)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_other_origin_gets_no_cors_allowance(self):
        out = proxy.lambda_handler(event(origin="https://evil.example"), None)
        self.assertNotIn("Access-Control-Allow-Origin", out["headers"])

    def test_no_origin_gets_no_cors_allowance(self):
        out = proxy.lambda_handler({"body": "{}"}, None)
        self.assertNotIn("Access-Control-Allow-Origin", out["headers"])

    def test_configured_origin_is_allowed(self):
        out = proxy.lambda_handler(event(prompt=""), None)
        self.assertEqual(out["headers"]["Access-Control-Allow-Origin"], SITE)

    def test_failed_invoke_returns_short_error_only(self):
        with mock.patch.object(proxy, "_client", return_value=FailingClient()):
            out = proxy.lambda_handler(event(), None)
        self.assertEqual(out["statusCode"], 500)
        self.assertEqual(json.loads(out["body"]), {"error": "Request failed."})

    def test_failed_client_creation_returns_short_error_only(self):
        with mock.patch.object(proxy, "_client", side_effect=RuntimeError("boom")):
            out = proxy.lambda_handler(event(), None)
        self.assertEqual(out["statusCode"], 500)
        self.assertEqual(json.loads(out["body"]), {"error": "Request failed."})

    def run_proxy(self, payload):
        text = payload if isinstance(payload, str) else json.dumps(payload)
        with mock.patch.object(proxy, "_client", return_value=ReplyClient(text)):
            return proxy.lambda_handler(event(prompt="secret question"), None)

    def test_passes_through_each_decision(self):
        for decision, cites in [("allow", ["s3://d/a.md"]), ("escalate", []), ("block", []), ("stop", [])]:
            with self.subTest(decision):
                sent = {"decision": decision, "reply": "ok", "citations": cites}
                out = self.run_proxy(sent)
                self.assertEqual(out["statusCode"], 200)
                self.assertEqual(json.loads(out["body"]), {**sent, "staged": False})

    def test_passes_staged_through(self):
        sent = {"decision": "allow", "reply": "ok", "citations": [], "staged": True}
        self.assertEqual(json.loads(self.run_proxy(sent)["body"]), sent)

    def test_other_shapes_return_fixed_error(self):
        bad = [
            "plain text",
            {"answer": "x"},
            {"decision": "allow", "reply": "ok"},
            {"decision": "maybe", "reply": "ok", "citations": []},
            {"decision": "allow", "reply": "ok", "citations": [1]},
            {"decision": "allow", "reply": "ok", "citations": [], "request": "secret question"},
        ]
        for payload in bad:
            with self.subTest(payload):
                out = self.run_proxy(payload)
                self.assertEqual(out["statusCode"], 500)
                self.assertEqual(json.loads(out["body"]), {"error": "Request failed."})
                self.assertNotIn("secret question", out["body"])

    def test_bad_body_has_no_detail(self):
        out = proxy.lambda_handler({"headers": {"Origin": SITE}, "body": "{"}, None)
        self.assertEqual(out["statusCode"], 400)
        self.assertEqual(set(json.loads(out["body"])), {"error"})

    def test_missing_prompt_is_400(self):
        out = proxy.lambda_handler(event(prompt="  "), None)
        self.assertEqual(out["statusCode"], 400)


if __name__ == "__main__":
    unittest.main()
