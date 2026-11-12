"""The two steps of the `attach` GitHub Action that are not the artifact upload.

  prepare  import a committed bundle (optional), verify the log (optionally against a pinned head),
           and write one session's export page (secrets redacted, always). Writes the results to
           $GITHUB_OUTPUT for the upload and comment steps.
  comment  post one comment on the pull request linking the uploaded page, or update the one this
           action posted before (found by a hidden marker), so a PR carries one comment, not one per push.

Not part of the `rewindagents` package and never installed with it: the CLI stays network-free. Only
`comment` talks to a network, to GitHub's REST API at $GITHUB_API_URL, with the token from $GH_TOKEN
(never an argument; error messages replace it with [token]).

Endpoints (docs.github.com/en/rest/issues/comments, read 2026-11-13; "Every pull request is an issue"):
  GET   /repos/{owner}/{repo}/issues/{issue_number}/comments
  POST  /repos/{owner}/{repo}/issues/{issue_number}/comments
  PATCH /repos/{owner}/{repo}/issues/comments/{comment_id}
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

MARKER = "<!-- rewindagents-attach -->"
EXIT_FAIL = 1


def _outputs(pairs: dict) -> None:
    """Append key=value lines to $GITHUB_OUTPUT (values here never hold a newline)."""
    target = os.environ.get("GITHUB_OUTPUT")
    lines = "".join(f"{k}={str(v).replace(chr(10), ' ')}\n" for k, v in pairs.items())
    if target:
        with open(target, "a", encoding="utf-8") as f:
            f.write(lines)
    else:
        sys.stdout.write(lines)


def prepare(project: str, out_dir: str, bundle_file: str | None = None, session: str | None = None,
            head: str | None = None) -> dict:
    from rewindagents import bundle, export, log, rewind  # the copy installed from this action's own commit

    root = Path(project).resolve()
    log_path = root / ".rewindagents" / "log.jsonl"
    imported = None
    if bundle_file:
        d = bundle.import_bundle(root / bundle_file, log_path)
        imported = d["session"]
    if not log_path.exists():
        raise SystemExit("rewindagents attach: no log at .rewindagents/log.jsonl in the checkout. The store "
                         "is git-ignored, so commit a bundle (`rewindagents bundle --out <file>`) and pass "
                         "it as the `bundle` input.")
    ok, n, msg = log.verify(log_path, head or None)
    sess = session or imported or rewind.latest_session(log_path)
    page = Path(out_dir) / f"rewindagents-replay-{safe(sess)}.html"
    data = export.export(log_path, sess, page)  # redact=True: there is no input to turn it off
    chain_ok = ok and data["chain_ok"]
    return {
        "page": str(page),
        "session": data["session"],
        "steps": len(data["steps"]),
        "records": n,
        "chain_ok": "true" if chain_ok else "false",
        "chain_msg": msg if not ok else data["chain_msg"],
        "head_pinned": "true" if head else "false",
        "redacted": data["redacted"],
    }


def safe(text: str) -> str:
    """A session id as it may appear in a file name or a Markdown code span."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", str(text))[:80] or "session"


def body(session: str, steps: int, chain_ok: bool, chain_msg: str, head_pinned: bool, redacted: int,
         url: str) -> str:
    chain = ("intact" + (", matches the pinned head" if head_pinned else "")) if chain_ok \
        else f"**does not verify** ({safe_text(chain_msg)})"
    link = f"[Download the replay page]({url})" if url.startswith("https://") else "The page upload failed."
    return "\n".join([
        MARKER,
        f"**rewindagents replay** for session `{safe(session)}`: {steps} steps.",
        "",
        f"- Log hash chain: {chain}.",
        f"- Secrets replaced in the page: {redacted}.",
        f"- {link} (one HTML file, no scripts; downloading needs a GitHub login).",
    ])


def safe_text(text: str) -> str:
    return re.sub(r"[^\w .,:;()#/-]", "", str(text))[:200]


class ApiError(Exception):
    pass


def _call(method: str, url: str, token: str, payload: dict | None = None):
    req = urllib.request.Request(url, method=method, data=None if payload is None else
                                 json.dumps(payload).encode("utf-8"))
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if payload is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        raise ApiError(f"{method} {url.split('?')[0]}: HTTP {e.code}") from None
    except (urllib.error.URLError, OSError) as e:
        raise ApiError(f"{method} {url.split('?')[0]}: {e}".replace(token, "[token]")) from None
    return json.loads(raw) if raw else None


def comment(api: str, repo: str, pr: int, text: str, token: str) -> tuple[str, int]:
    """Update this action's earlier comment on the PR, or post a new one. Returns (action, comment id)."""
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
        raise ApiError(f"not an owner/repo: {repo!r}")
    base = f"{api.rstrip('/')}/repos/{repo}/issues"
    page = 1
    while True:
        found = _call("GET", f"{base}/{pr}/comments?per_page=100&page={page}", token) or []
        for c in found:
            if MARKER in (c.get("body") or ""):
                _call("PATCH", f"{base}/comments/{c['id']}", token, {"body": text})
                return "updated", c["id"]
        if len(found) < 100:
            break
        page += 1
    made = _call("POST", f"{base}/{pr}/comments", token, {"body": text})
    return "posted", made["id"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="attach.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--project", default=".")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--bundle", default="")
    p.add_argument("--session", default="")
    p.add_argument("--head", default="")
    c = sub.add_parser("comment")
    c.add_argument("--repo", required=True)
    c.add_argument("--pr", type=int, required=True)
    c.add_argument("--url", default="")
    c.add_argument("--session", required=True)
    c.add_argument("--steps", type=int, required=True)
    c.add_argument("--chain-ok", choices=("true", "false"), required=True)
    c.add_argument("--chain-msg", default="")
    c.add_argument("--head-pinned", choices=("true", "false"), default="false")
    c.add_argument("--redacted", type=int, required=True)
    a = ap.parse_args(argv)

    if a.cmd == "prepare":
        from rewindagents import bundle, export
        try:
            res = prepare(a.project, a.out_dir, a.bundle or None, a.session or None, a.head or None)
        except (bundle.BundleError, export.ExportError) as e:
            print(f"rewindagents attach: {e}", file=sys.stderr)
            return EXIT_FAIL
        _outputs(res)
        state = "intact" if res["chain_ok"] == "true" else f"DOES NOT VERIFY ({res['chain_msg']})"
        print(f"session {res['session']}: {res['steps']} steps, chain {state}, "
              f"{res['redacted']} secrets replaced; page {res['page']}")
        return 0

    token = os.environ.get("GH_TOKEN", "")
    if not token:
        print("::warning::rewindagents attach: no GH_TOKEN, so no comment was posted")
        return 0
    text = body(a.session, a.steps, a.chain_ok == "true", a.chain_msg, a.head_pinned == "true",
                a.redacted, a.url)
    try:
        done, cid = comment(os.environ.get("GITHUB_API_URL", "https://api.github.com"), a.repo, a.pr, text, token)
    except ApiError as e:
        # a pull request from a fork gets a read-only token: the page is still uploaded, so warn, do not fail
        print(f"::warning::rewindagents attach: comment not posted: {str(e).replace(token, '[token]')}")
        return 0
    print(f"{done} comment {cid} on #{a.pr}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
