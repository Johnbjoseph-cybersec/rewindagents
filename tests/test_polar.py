"""Polar checkout + webhook code (R8, billing/polar.py). No network: every request goes through a fake `send`.
The webhook keys and signed content follow Polar's delivery page and the Standard Webhooks spec (cited in the
module); one vector below was signed outside this code, so the check is not the code agreeing with itself."""
import base64
import hashlib
import hmac
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import urllib.request
from contextlib import redirect_stderr, redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "billing", "polar.py")
PRODUCT = "6c3b8a5e-2f1d-4c7e-9a0b-1d2e3f4a5b6c"
TOKEN = "polar_oat_" + "x" * 30           # fake, shaped like the docs' example


def load():
    spec = importlib.util.spec_from_file_location("polar", PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


polar = load()
CFG = polar.load_config()


class FakeSend:
    def __init__(self, status=201, reply=None):
        self.status, self.reply, self.requests = status, reply, []

    def __call__(self, req: urllib.request.Request):
        self.requests.append(req)
        raw = self.reply if isinstance(self.reply, bytes) else json.dumps(self.reply).encode()
        return self.status, raw


class TestRequests(unittest.TestCase):
    def test_checkout_session_body(self):
        url, body = polar.checkout_request([PRODUCT], CFG, customer_email="a@example.org", metadata={"plan": "cloud"})
        self.assertEqual(url, "https://sandbox-api.polar.sh/v1/checkouts/")
        self.assertEqual(body["products"], [PRODUCT])
        self.assertEqual(body["success_url"], CFG["site_url"] + "pricing.html?checkout_id={CHECKOUT_ID}")
        self.assertEqual(body["customer_email"], "a@example.org")
        self.assertEqual(body["metadata"], {"plan": "cloud"})
        self.assertNotIn("product_id", body)

    def test_checkout_link_body(self):
        url, body = polar.link_request([PRODUCT], CFG, label="Cloud")
        self.assertEqual(url, "https://sandbox-api.polar.sh/v1/checkout-links/")
        self.assertEqual(body, {"payment_processor": "stripe", "products": [PRODUCT], "label": "Cloud",
                                "success_url": polar.success_url(CFG)})

    def test_sandbox_unless_asked(self):
        self.assertTrue(polar.checkout_request([PRODUCT], CFG)[0].startswith("https://sandbox-api.polar.sh/v1/"))
        self.assertTrue(polar.checkout_request([PRODUCT], CFG, "production")[0].startswith("https://api.polar.sh/v1/"))
        with self.assertRaises(polar.PolarError):
            polar.checkout_request([PRODUCT], CFG, "live")

    def test_success_url_comes_from_config(self):
        cfg = {**CFG, "site_url": "https://example.org/x/"}
        self.assertEqual(polar.success_url(cfg), "https://example.org/x/pricing.html?checkout_id={CHECKOUT_ID}")
        with open(PATH, encoding="utf-8") as f:
            self.assertNotIn(CFG["site_url"], f.read())

    def test_bad_input_is_refused(self):
        for bad in ([], ["not-a-uuid"], [PRODUCT, "12"]):
            with self.assertRaises(polar.PolarError):
                polar.checkout_request(bad, CFG)
        for md in ({"k" * 41: "v"}, {"k": "v" * 501}, {"k": ["list"]}, {str(i): i for i in range(51)}):
            with self.assertRaises(polar.PolarError):
                polar.link_request([PRODUCT], CFG, metadata=md)
        polar.link_request([PRODUCT], CFG, metadata={str(i): i for i in range(50)})


class TestPost(unittest.TestCase):
    def test_request_carries_bearer_token_and_json(self):
        send = FakeSend(reply={"id": "c1", "url": "https://sandbox.polar.sh/checkout/abc"})
        url, body = polar.checkout_request([PRODUCT], CFG)
        out = polar.created_url(polar.post(url, body, TOKEN, send=send))
        self.assertEqual(out, "https://sandbox.polar.sh/checkout/abc")
        req = send.requests[0]
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(req.full_url, url)
        self.assertEqual(req.get_header("Authorization"), "Bearer " + TOKEN)
        self.assertEqual(req.get_header("Content-type"), "application/json")
        self.assertEqual(json.loads(req.data), body)

    def test_errors_never_carry_the_token(self):
        send = FakeSend(status=401, reply={"detail": "bad token " + TOKEN})
        with self.assertRaises(polar.PolarError) as cm:
            polar.post(*polar.checkout_request([PRODUCT], CFG), TOKEN, send=send)
        self.assertIn("401", str(cm.exception))
        self.assertNotIn(TOKEN, str(cm.exception))
        self.assertIn("[token]", str(cm.exception))

        def boom(req):
            raise OSError("connection to " + TOKEN + " refused")
        with self.assertRaises(polar.PolarError) as cm:
            polar.post(*polar.checkout_request([PRODUCT], CFG), TOKEN, send=boom)
        self.assertNotIn(TOKEN, str(cm.exception))

    def test_no_token_no_request(self):
        send = FakeSend()
        with self.assertRaises(polar.PolarError) as cm:
            polar.post(*polar.checkout_request([PRODUCT], CFG), "", send=send)
        self.assertIn(polar.TOKEN_ENV, str(cm.exception))
        self.assertEqual(send.requests, [])

    def test_reply_without_https_url_is_an_error(self):
        for reply in ({}, {"url": "http://x"}, {"url": None}, []):
            with self.assertRaises(polar.PolarError):
                polar.created_url(reply)
        with self.assertRaises(polar.PolarError):
            polar.post(*polar.checkout_request([PRODUCT], CFG), TOKEN, send=FakeSend(reply=b"<html>"))

    def test_write_checkout_url_changes_only_that_key(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "config.json")
            shutil.copy(polar.CONFIG, path)
            polar.write_checkout_url("https://sandbox.polar.sh/checkout/link", path)
            got = polar.load_config(path)
            self.assertEqual(got, {**CFG, "checkout_url": "https://sandbox.polar.sh/checkout/link"})

    def test_token_only_from_the_environment(self):
        with open(PATH, encoding="utf-8") as f:
            src = f.read()
        self.assertNotRegex(src, r'add_argument\("--(token|secret)')
        self.assertNotRegex(src, r"print\([^)]*token", "nothing prints the token")


def standard_secret(raw=b"0123456789abcdef0123456789abcdef"):
    return "whsec_" + base64.b64encode(raw).decode(), raw


def signed(key, msg_id="msg_1", ts=1_800_000_000, body=b'{"type": "order.paid", "data": {}}'):
    mac = hmac.new(key, ("%s.%d." % (msg_id, ts)).encode() + body, hashlib.sha256).digest()
    return {"webhook-id": msg_id, "webhook-timestamp": str(ts),
            "webhook-signature": "v1," + base64.b64encode(mac).decode()}, body


class TestWebhook(unittest.TestCase):
    NOW = 1_800_000_000

    def test_third_party_vector(self):
        # The Svix / Standard Webhooks example delivery (secret, id, timestamp, body, signature), typed from
        # memory, not from a fetched page: its signature was made outside this code, and it verifies here,
        # which a mistyped or invented vector cannot do.
        secret = "whsec_MfKQ9r8GKYqrTwjUPD8ILPZIo2LaLaSw"
        headers = {"webhook-id": "msg_p5jXN8AQM9LWM0D4loKWxJek", "webhook-timestamp": "1614265330",
                   "webhook-signature": "v1,g0hM9SsE+OTPJTGt/tmIKtSyZlE3uFJELVlNIOLJ1OE="}
        self.assertEqual(polar.verify(secret, headers, b'{"test": 2432232314}', now=1614265330), {"test": 2432232314})

    def test_standard_webhooks_secret(self):
        secret, raw = standard_secret()
        headers, body = signed(raw)
        self.assertEqual(polar.verify(secret, headers, body, now=self.NOW)["type"], "order.paid")

    def test_older_polar_secret_uses_the_whole_string(self):
        # Polar, delivery page: before 8 September 2026 "Key is the UTF-8 bytes of the full whsec_... string"
        secret = "whsec_" + "polar-older-secret-not-base64!"
        headers, body = signed(secret.encode())
        polar.verify(secret, headers, body, now=self.NOW)
        secret2, _ = standard_secret()
        headers, body = signed(secret2.encode())
        polar.verify(secret2, headers, body, now=self.NOW)

    def test_rejections(self):
        secret, raw = standard_secret()
        headers, body = signed(raw)
        cases = {
            "tampered body": (headers, body.replace(b"paid", b"refunded"), self.NOW),
            "other id": ({**headers, "webhook-id": "msg_2"}, body, self.NOW),
            "too old": (headers, body, self.NOW + polar.TOLERANCE + 1),
            "from the future": (headers, body, self.NOW - polar.TOLERANCE - 1),
            "missing header": ({k: v for k, v in headers.items() if k != "webhook-signature"}, body, self.NOW),
            "bad timestamp": ({**headers, "webhook-timestamp": "soon"}, body, self.NOW),
            "other scheme": ({**headers, "webhook-signature": "v1a," + headers["webhook-signature"][3:]}, body, self.NOW),
        }
        for name, (h, b, now) in cases.items():
            with self.assertRaises(polar.WebhookError, msg=name):
                polar.verify(secret, h, b, now=now)
        with self.assertRaises(polar.WebhookError):
            polar.verify("whsec_" + base64.b64encode(b"another key entirely!!").decode(), headers, body, now=self.NOW)
        with self.assertRaises(polar.WebhookError):
            polar.verify("", headers, body, now=self.NOW)

    def test_edges_of_tolerance_and_header_case_and_lists(self):
        secret, raw = standard_secret()
        headers, body = signed(raw)
        polar.verify(secret, headers, body, now=self.NOW + polar.TOLERANCE)
        polar.verify(secret, {k.title(): v for k, v in headers.items()}, body, now=self.NOW)
        listed = {**headers, "webhook-signature": "v1,AAAA " + headers["webhook-signature"] + " v2,BBBB"}
        polar.verify(secret, listed, body, now=self.NOW)

    def test_signed_but_not_json(self):
        secret, raw = standard_secret()
        headers, body = signed(raw, body=b"not json")
        with self.assertRaises(polar.WebhookError):
            polar.verify(secret, headers, body, now=self.NOW)


class TestCli(unittest.TestCase):
    def run_cli(self, args, env_extra):
        env = {k: v for k, v in os.environ.items() if k not in (polar.TOKEN_ENV, polar.SECRET_ENV)}
        env.update(env_extra)
        return subprocess.run([sys.executable, PATH] + args, capture_output=True, text=True, env=env, timeout=60)

    def test_verify_command(self):
        secret, raw = standard_secret()
        import time
        headers, body = signed(raw, ts=int(time.time()))
        with tempfile.TemporaryDirectory() as d:
            hp, bp = os.path.join(d, "h.json"), os.path.join(d, "b.json")
            with open(hp, "w") as f:
                json.dump(headers, f)
            with open(bp, "wb") as f:
                f.write(body)
            ok = self.run_cli(["verify", "--headers", hp, "--body", bp], {polar.SECRET_ENV: secret})
            self.assertEqual(ok.returncode, 0, ok.stderr)
            self.assertEqual(ok.stdout.strip(), "ok msg_1 order.paid")
            bad = self.run_cli(["verify", "--headers", hp, "--body", bp], {polar.SECRET_ENV: secret + "x"})
            self.assertEqual(bad.returncode, 1)
            self.assertIn("rejected: no signature matches", bad.stderr)
            self.assertNotIn(secret, bad.stdout + bad.stderr)

    def test_checkout_without_token_stops_before_the_network(self):
        r = self.run_cli(["checkout", "--product", PRODUCT], {})
        self.assertEqual(r.returncode, 2)
        self.assertIn("no token: set " + polar.TOKEN_ENV, r.stderr)
        r = self.run_cli(["link", "--product", "nope"], {polar.TOKEN_ENV: TOKEN})
        self.assertEqual(r.returncode, 2)
        self.assertNotIn(TOKEN, r.stdout + r.stderr)

    def test_link_write_config_in_process(self):
        send = FakeSend(reply={"url": "https://sandbox.polar.sh/checkout/polar_cl_x"})
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "config.json")
            shutil.copy(polar.CONFIG, path)
            old_cfg, old_send = polar.CONFIG, polar.SEND
            polar.CONFIG, polar.SEND = type(old_cfg)(path), send
            os.environ[polar.TOKEN_ENV] = TOKEN
            try:
                out = io.StringIO()
                with redirect_stdout(out), redirect_stderr(io.StringIO()):
                    rc = polar.main(["link", "--product", PRODUCT, "--write-config"])
            finally:
                polar.CONFIG, polar.SEND = old_cfg, old_send
                del os.environ[polar.TOKEN_ENV]
            self.assertEqual(rc, 0)
            self.assertIn("https://sandbox.polar.sh/checkout/polar_cl_x", out.getvalue())
            self.assertEqual(polar.load_config(path)["checkout_url"], "https://sandbox.polar.sh/checkout/polar_cl_x")
            self.assertEqual(send.requests[0].full_url, "https://sandbox-api.polar.sh/v1/checkout-links/")
            self.assertNotIn(TOKEN, out.getvalue())
        self.assertIsNone(CFG["checkout_url"], "the committed config stays without a checkout until a product exists")


class TestPlacement(unittest.TestCase):
    def test_billing_is_stdlib_and_not_in_the_package(self):
        with open(PATH, encoding="utf-8") as f:
            src = f.read()
        mods = {m.split(".")[0] for m in re.findall(r"^(?:import|from)\s+([\w.]+)", src, re.M)}
        self.assertTrue(mods <= set(sys.stdlib_module_names) | {"__future__"}, mods - set(sys.stdlib_module_names))
        self.assertFalse(os.path.exists(os.path.join(ROOT, "src", "rewindagents", "polar.py")))
        with open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8") as f:
            self.assertIn('where = ["src"]', f.read())

    def test_readme_matches_the_code(self):
        with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as f:
            readme = f.read()
        self.assertIn("more than %d minutes from now" % (polar.TOLERANCE // 60), readme)
        for name in (polar.TOKEN_ENV, polar.SECRET_ENV, "sandbox-api.polar.sh", "--write-config", "has not yet talked"):
            self.assertIn(name, readme)
        self.assertIn(polar.API["sandbox"].split("//")[1].split("/")[0], readme)


if __name__ == "__main__":
    unittest.main()
