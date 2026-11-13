"""Replace secrets with a placeholder before a session leaves the machine (`export` and `bundle`).

What is replaced, each by `[redacted <kind>]`:
- AWS access key ids (AKIA..., ASIA...);
- GitHub tokens (ghp_, gho_, ghu_, ghs_, ghr_, github_pat_);
- Polar organization access tokens (polar_oat_) and Standard Webhooks secrets (whsec_);
- Anthropic keys (sk-ant-...) and OpenAI keys (sk-..., sk-proj-...);
- PEM private key blocks (-----BEGIN ... PRIVATE KEY----- to its END line);
- the credential in an Authorization or Proxy-Authorization header (the header name and scheme stay);
- the value of an assignment whose name says it is a secret (..._SECRET, ..._TOKEN, PASSWORD, API_KEY,
  aws_secret_access_key and the like; max_tokens is not one), in `NAME=value`, `NAME: value` or
  `"name": "value"` form, and a recorded input's or result's field with such a name;
- in a file named .env or .env.<anything>, the value of every `NAME=value` line.

A value the hook clipped to its first characters (is_clip) also loses a secret its cut ends inside
(cut_start), and a clipped .env input is still read as a .env file.

It works on text. Bytes that are not UTF-8 are left as they are. It is pattern matching, so a secret with
none of these shapes stays: read the page or the bundle before you pass it on.
"""
from __future__ import annotations

import re
from pathlib import PurePath
from typing import Any

# The keyword must end the name or be followed by `_`: max_tokens and tokenizer are not secrets.
_SECRET_NAME = (r"[A-Za-z0-9_.-]*(?:SECRET|TOKEN|PASSWORD|PASSWD|API[_-]?KEY|ACCESS[_-]?KEY|PRIVATE[_-]?KEY|CREDENTIALS?)"
                r"(?:_[A-Za-z0-9_]*)?(?![A-Za-z0-9])")
_SECRET_KEY = re.compile(r"(?i)^" + _SECRET_NAME + r"$")

# (kind, pattern, group holding the secret: 0 = the whole match)
_PATTERNS: list[tuple[str, re.Pattern, int]] = [
    ("private key", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----", re.S), 0),
    ("anthropic key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}"), 0),
    ("openai key", re.compile(r"\bsk-(?:proj-|svcacct-|admin-)?[A-Za-z0-9_-]{20,}"), 0),
    ("github token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{22,})"), 0),
    ("polar token", re.compile(r"\bpolar_oat_[A-Za-z0-9_-]{16,}"), 0),
    ("webhook secret", re.compile(r"\bwhsec_[A-Za-z0-9+/=_-]{16,}"), 0),
    ("aws key id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), 0),
    ("authorization", re.compile(r"(?i)\b(?:proxy-)?authorization\s*:\s*(?:(?:bearer|basic|token|digest)\s+)?"
                                 r"([^\s\"'\\,]+)"), 1),
    ("secret value", re.compile(r"(?i)(?<![A-Za-z0-9_])[\"']?" + _SECRET_NAME + r"[\"']?\s*[:=]\s*[\"']?"
                                r"([^\s\"'\\,;&|]{4,})"), 1),
]
_ENV_LINE = re.compile(r"(?m)^(\s*(?:export\s+)?[A-Za-z_][A-Za-z0-9_]*\s*=[ \t]*)([\"']?)(.+?)\2[ \t]*$")


def is_env_file(path: str | None) -> bool:
    if not path:
        return False
    name = PurePath(str(path)).name
    return name == ".env" or name.startswith(".env.")


def text(s: str, env_file: bool = False) -> tuple[str, int]:
    """s with every secret replaced, and how many were replaced."""
    n = 0

    def sub(kind: str, group: int):
        def repl(m: re.Match) -> str:
            nonlocal n
            if m.group(group).startswith("[redacted"):
                return m.group(0)
            n += 1
            if group == 0:
                return f"[redacted {kind}]"
            start, end = m.start(group) - m.start(0), m.end(group) - m.start(0)
            whole = m.group(0)
            return whole[:start] + f"[redacted {kind}]" + whole[end:]
        return repl

    def env_repl(m: re.Match) -> str:
        nonlocal n
        if m.group(3).startswith("[redacted"):
            return m.group(0)
        n += 1
        return f"{m.group(1)}{m.group(2)}[redacted env value]{m.group(2)}"

    for i, (kind, pat, group) in enumerate(_PATTERNS):
        s = pat.sub(sub(kind, group), s)
        if i == 0 and env_file:
            # after private keys (a quoted key spans lines), before the rest: in a .env file every value
            # reads the same, so a changed key does not show as two different placeholders
            s = _ENV_LINE.sub(env_repl, s)
    return s, n


def data(b: bytes | None, env_file: bool = False) -> tuple[bytes | None, int]:
    """File bytes with secrets replaced; bytes that are not UTF-8 come back unchanged."""
    if b is None:
        return None, 0
    try:
        s = b.decode("utf-8")
    except UnicodeDecodeError:
        return b, 0
    out, n = text(s, env_file)
    return (out.encode("utf-8") if n else b), n


# What could follow the end of a cut head: key characters then a space (an AWS key id is exactly 16 after
# its prefix, every other pattern takes any length from its minimum up), or a PEM block's END line.
_FILLERS = ["A" * n + " " for n in range(17)] + ["A" * 64 + " "]
_PEM_END = "\n-----END PRIVATE KEY-----"
# A secret that shows at least its pattern's minimum before the cut is matched by text() already; every
# minimum is under 40 characters, so only the head's last _TAIL characters can hold a cut one.
_TAIL = 256


def is_clip(obj: Any) -> bool:
    """The shape the hook records for a long input or result: its first characters and its length."""
    return (isinstance(obj, dict) and set(obj) == {"truncated", "chars", "head"} and obj["truncated"] is True
            and isinstance(obj["head"], str) and isinstance(obj["chars"], int) and obj["chars"] > len(obj["head"]))


def cut_start(head: str) -> tuple[int, str] | None:
    """Where a secret cut off by the end of `head` begins, and its kind; None if the end cuts none.

    The hook keeps only the first characters of a long value, so a token can end with the head and be too
    short for its pattern (sk-ant- needs 20 characters, a PEM block its END line). Each pattern is tried on
    the head followed by what could have come next; a match that runs past the end means the cut is
    inside a secret."""
    best: tuple[int, str] | None = None
    for kind, pat, group in _PATTERNS:
        # a PEM block is cut anywhere after its BEGIN line; the rest only near the end
        off = 0 if kind == "private key" else max(0, len(head) - _TAIL)
        for filler in ([_PEM_END] if kind == "private key" else _FILLERS):
            for m in pat.finditer(head[off:] + filler):
                start = off + m.start(group)
                if off + m.end(group) > len(head) and start < len(head) and (best is None or start < best[0]):
                    best = (start, kind)
    return best


def _clip_value(obj: dict, env_file: bool = False) -> tuple[dict, int]:
    head, n = obj["head"], 0
    cut = cut_start(head)
    if cut and not head[cut[0]:].startswith("[redacted"):
        head, n = head[:cut[0]] + f"[redacted {cut[1]}]", 1
    head, k = text(head, env_file)
    return {**obj, "head": head}, n + k


def value(obj: Any) -> tuple[Any, int]:
    """A JSON-shaped value (a recorded input or result) with secrets replaced in every string. A dict that
    names a .env file (file_path / path / notebook_path) gets every NAME=value line in it replaced too.
    A clipped value (is_clip) also loses a secret its cut ends inside (cut_start)."""
    if isinstance(obj, str):
        return text(obj)
    if is_clip(obj):
        return _clip_value(obj)
    if isinstance(obj, list):
        out, total = [], 0
        for v in obj:
            v2, k = value(v)
            out.append(v2)
            total += k
        return out, total
    if isinstance(obj, dict):
        env = any(is_env_file(obj.get(key)) for key in ("file_path", "path", "notebook_path")
                  if isinstance(obj.get(key), str))
        out_d, total = {}, 0
        for key, v in obj.items():
            if isinstance(v, str) and v and _SECRET_KEY.match(str(key)) and not v.startswith("[redacted"):
                v2, k = "[redacted secret value]", 1
            elif env and isinstance(v, str) and key not in ("file_path", "path", "notebook_path"):
                v2, k = text(v, env_file=True)
            elif env and is_clip(v):
                v2, k = _clip_value(v, env_file=True)
            else:
                v2, k = value(v)
            out_d[key] = v2
            total += k
        return out_d, total
    return obj, 0
