"""R31: a secret cut in half by the 4,000-char clip is still redacted in `export` and `bundle`.

The hook keeps the first MAX_INPUT_CHARS of a long input and the first MAX_RESULT_CHARS of a long result
(hook.clip_input, hook._clip). A token that starts just before the cut leaves a prefix too short for its
pattern (sk-ant- needs 20 characters, a PEM block needs its END line), so the page and the bundle showed it.
Driven through the real hook process for every pattern in redact.py; every fake secret is built at run time.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from rewindagents import bundle, export, hook, log, redact  # noqa: E402

# (name, text before the secret's material, the material). The material starts SHOWN characters before
# the cut, so the head ends inside it.
CASES = [
    ("anthropic key", "key " + "sk-" + "ant-api03-", "Zz9" * 12),
    ("openai key", "key " + "sk-" + "proj-", "Qw3rTy" * 6),
    ("github token", "tok " + "gh" + "p_", "A1b2C3d4" * 5),
    ("github pat", "tok " + "github" + "_pat_", "11ABCDEFG0" * 4),
    ("polar token", "tok " + "polar" + "_oat_", "x7" * 15),
    ("webhook secret", "sig " + "wh" + "sec_", "MfKQ9r8GKYqrTwjUPD8ILPZI"),
    ("aws key id", "id " + "AK" + "IA", "QWERTYUIOP234567"),
    ("authorization", "-H 'Authorization: Bearer ", "eyJ" + "hbGciOi" * 4),
    ("secret value", "DB_PASS" + "WORD=", "hunter2hunter2"),
    ("private key", "-----BEGIN " + "RSA PRIVATE KEY-----\n",
     "MIIEow" * 10 + "\n" + "abcd" * 16 + "\n" + "-----END " + "RSA PRIVATE KEY-----"),
]
SHOWN = 10          # characters of the material left in the head: below every pattern's minimum length
SHOWN_SHORT = 3     # a secret value needs 4 characters after NAME=


def straddle(prefix: str, material: str, shown: int, bound: int) -> str:
    """Text longer than `bound` whose first `bound` characters end `shown` characters into the material."""
    lead = bound - len(prefix) - shown
    return "a " * (lead // 2) + "a" * (lead % 2) + prefix + material + " tail" * 400


def run_hook(agent: str, payload: dict, cwd: Path) -> None:
    env = dict(os.environ, PYTHONPATH=str(SRC))
    r = subprocess.run([sys.executable, "-m", "rewindagents", "hook", "--agent", agent],
                       input=json.dumps(payload).encode("utf-8"), capture_output=True, cwd=cwd, env=env, timeout=120)
    assert r.returncode == 0 and b"not recorded" not in r.stderr, r.stderr


def record_write(root: Path, name: str, content: str) -> Path:
    """A Write of `content` to `name`, pre and post, through the real hook. Returns the log."""
    target = root / name
    target.write_text("old\n", encoding="utf-8")
    base = {"session_id": "s1", "cwd": str(root), "tool_name": "Write",
            "tool_input": {"file_path": str(target), "content": content}}
    run_hook("claude", {**base, "hook_event_name": "PreToolUse"}, root)
    target.write_text(content, encoding="utf-8")
    run_hook("claude", {**base, "hook_event_name": "PostToolUse", "tool_response": {"success": True}}, root)
    return root / ".rewindagents" / "log.jsonl"


def record_read(root: Path, response: str) -> Path:
    """A Read whose tool response is `response`, through the real hook (the result side: hook._clip)."""
    (root / "r.txt").write_text("r\n", encoding="utf-8")
    base = {"session_id": "s1", "cwd": str(root), "tool_name": "Read", "tool_input": {"file_path": str(root / "r.txt")}}
    run_hook("claude", {**base, "hook_event_name": "PreToolUse"}, root)
    run_hook("claude", {**base, "hook_event_name": "PostToolUse", "tool_response": response}, root)
    return root / ".rewindagents" / "log.jsonl"


def shared(root: Path, lg: Path) -> tuple[str, str]:
    """(export page, bundle file) as text, both with the defaults (redaction on)."""
    export.export(lg, out=root / "page.html")
    bundle.bundle(lg, root / "s.bundle")
    return ((root / "page.html").read_text(encoding="utf-8"), (root / "s.bundle").read_text(encoding="utf-8"))


class CutSecretThroughHook(unittest.TestCase):
    def check(self, record, bound: int, field) -> None:
        for name, prefix, material in CASES:
            for shown in ((SHOWN, SHOWN_SHORT) if name == "secret value" else (SHOWN,)):
                with self.subTest(name=name, shown=shown), tempfile.TemporaryDirectory() as d:
                    root = Path(d).resolve()
                    text = straddle(prefix, material, shown, bound)
                    lg = record(root, text)
                    self.assertTrue(log.verify(lg)[0])
                    head = field(log.read(lg)[-1])
                    self.assertTrue(head["truncated"])
                    fragment = material[:shown]
                    self.assertTrue(head["head"].endswith(fragment), "the cut is not inside the secret")
                    # ten characters of a key are unique on their own; three need the NAME= before them
                    needle = fragment if shown >= SHOWN else prefix.split()[-1] + fragment
                    page, bun = shared(root, lg)
                    for where, out in (("export", page), ("bundle", bun)):
                        self.assertNotIn(needle, out, where)
                    self.assertIn("redacted", page)

    def test_input_head(self):
        self.check(lambda root, text: record_write(root, "big.txt", text), hook.MAX_INPUT_CHARS,
                   lambda r: r["args"]["input"]["content"])

    def test_result_head(self):
        self.check(record_read, hook.MAX_RESULT_CHARS, lambda r: r["result"])

    def test_env_file_head_loses_every_value(self):
        """A clipped .env input is still read as a .env file: every NAME=value in its head is replaced,
        including the line the cut ends inside."""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            content = "".join(f"HOST_{i}=db{i}.internal\n" for i in range(400))
            lg = record_write(root, ".env", content)
            head = log.read(lg)[-1]["args"]["input"]["content"]["head"]
            self.assertIn("db0.internal", head)
            page, bun = shared(root, lg)
            for where, out in (("export", page), ("bundle", bun)):
                self.assertNotIn(".internal", out, where)
                self.assertNotIn("=db", out, where)


class CutHead(unittest.TestCase):
    """redact.value on the clip shape the hook writes."""
    def clip(self, text: str) -> dict:
        return hook._clip(text)

    def test_head_ending_in_no_secret_shape_is_kept(self):
        for tail in ("a" * 50, "the password is", "max_tokens: 4000", "gh", "x" * 4000):
            pad = hook.MAX_RESULT_CHARS - len(tail)
            c = self.clip("x " * (pad // 2) + " " * (pad % 2) + tail + " more" * 10)
            self.assertTrue(c["head"].endswith(tail))
            out, n = redact.value(c)
            self.assertEqual((out, n), (c, 0), tail)

    def test_head_ending_in_a_key_prefix_is_replaced(self):
        # it cannot be told from a cut key, so it goes: a page loses a few characters, never a key
        pad = hook.MAX_RESULT_CHARS - len("sk-short")
        c = self.clip("x " * (pad // 2) + "sk-short" + " more" * 10)
        self.assertTrue(redact.value(c)[0]["head"].endswith("x [redacted openai key]"))

    def test_whole_secret_before_the_cut_counts_once(self):
        ant = "sk-" + "ant-api03-" + "Zz9" * 12
        c = self.clip("y " * 1000 + ant + " " + "z " * 2000)
        out, n = redact.value(c)
        self.assertEqual(n, 1)
        self.assertNotIn(ant, json.dumps(out))

    def test_cut_secret_counts_once_and_keeps_the_shape(self):
        ant = "sk-" + "ant-api03-" + "Zz9" * 12
        c = self.clip(straddle("k ", ant, 12, hook.MAX_RESULT_CHARS))
        out, n = redact.value(c)
        self.assertEqual(n, 1)
        self.assertEqual(sorted(out), ["chars", "head", "truncated"])
        self.assertEqual(out["chars"], c["chars"])
        self.assertTrue(out["head"].endswith("k [redacted anthropic key]"))
        self.assertEqual(redact.value(out), (out, 0))           # running twice changes nothing more

    def test_pem_block_begun_far_before_the_cut_goes_from_its_begin_line(self):
        begin = "-----BEGIN " + "OPENSSH PRIVATE KEY-----\n"
        c = self.clip("z " * 500 + begin + ("b3BlbnNzaC1rZXk" * 4 + "\n") * 300)
        out, n = redact.value(c)
        self.assertEqual(n, 1)
        self.assertEqual(out["head"], "z " * 500 + "[redacted private key]")

    def test_slow_regex_shapes_stay_fast(self):
        # the secret-value pattern is quadratic on a long run of name characters; only the tail is searched
        import time
        t = time.perf_counter()
        redact.value(self.clip("a.b-c_" * 1000))
        self.assertLess(time.perf_counter() - t, 1.0)

    def test_a_string_that_is_not_a_clip_is_not_judged_cut(self):
        out, n = redact.value({"note": "a " * 10 + "sk-" + "ant-api03-" + "Zz9Zz9"})
        self.assertEqual(n, 0)


if __name__ == "__main__":
    unittest.main()
