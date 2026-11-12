"""Secrets are replaced by default in `export` and `bundle`; --no-redact keeps them.

Every fake secret here is put together at run time, so no secret-shaped string sits in the repo for a
scanner to find.
"""
import json
import re
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rewindagents import bundle, export, redact, rewind, verify  # noqa: E402
from test_rewind import Agent, cli  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

GH = "gh" + "p_" + "A1b2C3d4" * 5                     # 40 chars after the prefix
GH_PAT = "github" + "_pat_" + "11ABCDEFG0" * 4
ANT = "sk-" + "ant-api03-" + "Zz9" * 12
OAI = "sk-" + "proj-" + "Qw3rTy" * 6
POLAR = "polar" + "_oat_" + "x7" * 15
WHSEC = "wh" + "sec_" + "MfKQ9r8GKYqrTwjUPD8ILPZI"
AWS = "AK" + "IA" + "QWERTYUIOP234567"
PEM = ("-----BEGIN " + "RSA PRIVATE KEY-----\n" + "MIIEow" * 10 + "\n" + "abcd" * 16 + "\n"
       + "-----END " + "RSA PRIVATE KEY-----")
BEARER = "eyJ" + "hbGciOi" * 4
ALL = [GH, GH_PAT, ANT, OAI, POLAR, WHSEC, AWS, BEARER]


class TestText(unittest.TestCase):
    def test_each_kind_is_replaced_and_named(self):
        cases = {GH: "github token", GH_PAT: "github token", ANT: "anthropic key", OAI: "openai key",
                 POLAR: "polar token", WHSEC: "webhook secret", AWS: "aws key id", PEM: "private key"}
        for secret, kind in cases.items():
            out, n = redact.text(f"before {secret} after")
            self.assertEqual(n, 1, kind)
            self.assertNotIn(secret, out)
            self.assertEqual(out, f"before [redacted {kind}] after")

    def test_authorization_header_keeps_name_and_scheme(self):
        out, n = redact.text(f'curl -H "Authorization: Bearer {BEARER}" https://api.example')
        self.assertEqual(n, 1)
        self.assertIn('"Authorization: Bearer [redacted authorization]"', out)
        out, _ = redact.text(f"Proxy-Authorization: Basic {BEARER}")
        self.assertEqual(out, "Proxy-Authorization: Basic [redacted authorization]")

    def test_secret_named_assignments_in_any_form(self):
        for line in (f"DB_PASSWORD=hunter2hunter", f'"client_secret": "s3cr3t-value"',
                     f"aws_secret_access_key = wJalrXUtnFEMIK7MDENG", f"export GITHUB_TOKEN={GH}",
                     f"x-api-key: abcdef123456"):
            out, n = redact.text(line)
            self.assertGreaterEqual(n, 1, line)
            self.assertIn("[redacted", out, line)
        self.assertNotIn("hunter2hunter", redact.text("DB_PASSWORD=hunter2hunter")[0])

    def test_lookalikes_are_left_alone(self):
        for s in ("max_tokens: 4000", "input_tokens=812", "tokenizer = load()", "polar_cl_x",
                  "sk-short", "a" * 64, "ghp_short", "the password is in the vault",
                  "AKIAlowercase0000000"):
            self.assertEqual(redact.text(s), (s, 0), s)

    def test_running_twice_changes_nothing_more(self):
        once, n = redact.text(f"TOKEN={GH} and {ANT}")
        self.assertEqual(n, 2)
        self.assertEqual(redact.text(once), (once, 0))

    def test_env_files_lose_every_value(self):
        env = "HOST=db.internal\nexport PORT=5432\nNAME='prod'\n# a comment\n"
        out, n = redact.text(env, env_file=True)
        self.assertEqual(n, 3)
        self.assertEqual(out, "HOST=[redacted env value]\nexport PORT=[redacted env value]\n"
                              "NAME='[redacted env value]'\n# a comment\n")
        self.assertEqual(redact.text(env), (env, 0))          # the same text in another file: nothing secret-shaped
        self.assertTrue(redact.is_env_file("/p/.env") and redact.is_env_file("cfg/.env.local"))
        self.assertFalse(redact.is_env_file("/p/env.py") or redact.is_env_file("/p/.envrc") or redact.is_env_file(None))

    def test_values_walk_json_and_honour_secret_keys_and_env_paths(self):
        v = {"command": f"echo {GH}", "headers": {"api_key": "plain-looking-value"},
             "list": [ANT, 3, None], "max_tokens": 4000}
        out, n = redact.value(v)
        self.assertEqual(n, 3)
        self.assertEqual(out["headers"]["api_key"], "[redacted secret value]")
        self.assertEqual(out["max_tokens"], 4000)
        self.assertNotIn(GH, json.dumps(out))
        w, n = redact.value({"file_path": "/p/.env", "content": "HOST=x.internal\n"})
        self.assertEqual((w["content"], w["file_path"], n), ("HOST=[redacted env value]\n", "/p/.env", 1))

    def test_bytes_that_are_not_utf8_come_back_as_they_were(self):
        raw = b"\xff\xfe" + GH.encode()
        self.assertEqual(redact.data(raw), (raw, 0))
        self.assertEqual(redact.data(None), (None, 0))
        self.assertEqual(redact.data(f"k {GH}\n".encode())[0], b"k [redacted github token]\n")


def secret_session(d):
    """Step 1 writes .env, step 2 rewrites it (only the key changes), step 3 a curl with a bearer token,
    step 4 writes app.py holding an Anthropic key."""
    a = Agent(d)
    a.write(".env", f"HOST=db.internal\nAPI_KEY={OAI}\n")
    a.write(".env", f"HOST=db.internal\nAPI_KEY={GH}\n")
    a.bash(f'curl -H "Authorization: Bearer {BEARER}" https://api.example/v1')
    a.write("app.py", f'KEY = "{ANT}"\nprint(1)\n')
    return a


class TestExport(unittest.TestCase):
    def test_page_has_no_secret_and_says_how_many_were_replaced(self):
        with TemporaryDirectory() as d:
            a = secret_session(d)
            data = export.export(a.log, out=Path(d, "page.html"))
            page = Path(d, "page.html").read_text()
            for s in ALL + ["db.internal"]:
                self.assertNotIn(s, page)
            self.assertIn("[redacted", page)
            self.assertGreater(data["redacted"], 0)
            self.assertIn(f"{data['redacted']} secret values replaced with [redacted ...]", page)
            # step 2 changed only the key: the page says so rather than "unchanged"
            step2 = data["steps"][1]["files"][0]
            self.assertEqual(step2["change"]["note"], "changed only inside redacted values")

    def test_no_redact_keeps_everything_and_says_so(self):
        with TemporaryDirectory() as d:
            a = secret_session(d)
            data = export.export(a.log, out=Path(d, "page.html"), redact=False)
            page = Path(d, "page.html").read_text()
            for s in (OAI, GH, BEARER, ANT):
                self.assertIn(s, page)
            self.assertEqual(data["redacted"], 0)
            self.assertIn("Exported with --no-redact: secrets were not looked for.", page)

    def test_summary_is_redacted_before_it_is_cut(self):
        with TemporaryDirectory() as d:
            a = Agent(d)
            a.bash("echo " + "a" * 100 + " " + GH)              # the token straddles the 120-character cut
            data = export.build(a.log, contents=False)
            self.assertNotIn(GH[:8], data["steps"][0]["summary"])
            self.assertEqual(data["redacted"], 1)                 # the summary only: no contents on the page

    def test_cli_prints_the_count_and_honours_no_redact(self):
        with TemporaryDirectory() as d:
            a = secret_session(d)
            code, out, _ = cli("--log", str(a.log), "export", "--out", str(Path(d, "p.html")))
            self.assertEqual(code, 0)
            self.assertRegex(out, r"\n  \d+ secret values replaced with \[redacted \.\.\.\]; --no-redact keeps them\n")
            self.assertNotIn(GH, Path(d, "p.html").read_text())
            code, out, _ = cli("--log", str(a.log), "export", "--no-redact", "--out", str(Path(d, "q.html")))
            self.assertEqual(code, 0)
            self.assertIn("secrets kept as recorded (--no-redact)", out)
            self.assertIn(GH, Path(d, "q.html").read_text())


class TestBundle(unittest.TestCase):
    def test_bundle_carries_no_secret_and_still_imports_and_rewinds(self):
        with TemporaryDirectory() as src, TemporaryDirectory() as dst:
            a = secret_session(src)
            before_log = a.log.read_bytes()
            out = Path(src, "s.bundle")
            d = bundle.bundle(a.log, out)
            text = out.read_text()
            raw = json.loads(text)
            decoded = b"".join(__import__("base64").b64decode(v) for v in raw["objects"].values()).decode()
            for s in ALL:
                self.assertNotIn(s, text)
                self.assertNotIn(s, decoded)
            self.assertNotIn("db.internal", decoded)              # the stored .env copy lost its values
            self.assertGreater(d["redacted"], 0)
            self.assertEqual(raw["redacted"], d["redacted"])
            self.assertEqual(a.log.read_bytes(), before_log)      # the source log is not touched
            dest_log = Path(dst, ".rewindagents", "log.jsonl")
            got = bundle.import_bundle(out, dest_log)
            self.assertEqual(got["steps"], 4)
            self.assertTrue(verify(dest_log)[0])
            self.assertNotIn(GH, dest_log.read_text())
            # rewinding to step 1 in the clone writes the placeholder, not the key
            rewind.rewind(dest_log, 1, "s1")
            self.assertEqual(Path(dst, ".env").read_text(), "HOST=[redacted env value]\nAPI_KEY=[redacted env value]\n")

    def test_no_redact_carries_the_session_exactly(self):
        with TemporaryDirectory() as src, TemporaryDirectory() as dst:
            a = secret_session(src)
            out = Path(src, "s.bundle")
            d = bundle.bundle(a.log, out, redact=False)
            self.assertIsNone(d["redacted"])
            self.assertIn(GH, out.read_text())
            bundle.import_bundle(out, Path(dst, ".rewindagents", "log.jsonl"))
            rewind.rewind(Path(dst, ".rewindagents", "log.jsonl"), 1, "s1")
            self.assertEqual(Path(dst, ".env").read_text(), f"HOST=db.internal\nAPI_KEY={OAI}\n")

    def test_a_redacted_bundle_is_still_checked_like_any_other(self):
        with TemporaryDirectory() as src, TemporaryDirectory() as dst:
            a = secret_session(src)
            out = Path(src, "s.bundle")
            bundle.bundle(a.log, out)
            b = json.loads(out.read_text())
            b["records"][0]["args"]["note"] = "edited"
            b["digest"] = bundle.digest(b)
            out.write_text(json.dumps(b))
            with self.assertRaisesRegex(bundle.BundleError, "record 1: contents altered"):
                bundle.import_bundle(out, Path(dst, ".rewindagents", "log.jsonl"))

    def test_cli_bundle_prints_the_count_and_honours_no_redact(self):
        with TemporaryDirectory() as d:
            a = secret_session(d)
            code, out, _ = cli("--log", str(a.log), "bundle", "--out", str(Path(d, "a.bundle")))
            self.assertEqual(code, 0)
            self.assertRegex(out, r"\d+ secret values replaced with \[redacted \.\.\.\]")
            code, out, _ = cli("--log", str(a.log), "bundle", "--no-redact", "--out", str(Path(d, "b.bundle")))
            self.assertEqual(code, 0)
            self.assertIn("secrets kept as recorded (--no-redact)", out)
            self.assertIn(GH, Path(d, "b.bundle").read_text())


class TestReadme(unittest.TestCase):
    def test_readme_documents_the_default_and_the_opt_out(self):
        readme = (ROOT / "README.md").read_text()
        self.assertIn("rewindagents export --no-redact", readme)
        self.assertIn("rewindagents bundle --no-redact", readme)
        for kind in ("AWS", "GitHub", "Polar", "OpenAI", "Anthropic", "private key", ".env", "Authorization"):
            self.assertIn(kind, readme)


if __name__ == "__main__":
    unittest.main()
