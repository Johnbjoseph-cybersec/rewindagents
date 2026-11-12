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


def value(obj: Any) -> tuple[Any, int]:
    """A JSON-shaped value (a recorded input or result) with secrets replaced in every string. A dict that
    names a .env file (file_path / path / notebook_path) gets every NAME=value line in it replaced too."""
    if isinstance(obj, str):
        return text(obj)
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
            else:
                v2, k = value(v)
            out_d[key] = v2
            total += k
        return out_d, total
    return obj, 0
