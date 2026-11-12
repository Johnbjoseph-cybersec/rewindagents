"""Polar checkout and webhook code for the planned Cloud tier (R8). Not part of the rewindagents package: the CLI
makes no network connections (tests/test_site.py checks src/), and this file is never installed with it.

Built from Polar's documentation, read 2026-11-11 (API version 2026-10):
  https://polar.sh/docs/api-reference/introduction        base URLs, "Authorization: Bearer polar_oat_..."
  https://polar.sh/docs/integrate/sandbox                 sandbox base URL; production tokens do not work there
  https://polar.sh/docs/api-reference/checkouts/create-session   POST /v1/checkouts/, body `products` (UUIDs),
      response `url`; "You can add the `checkout_id={CHECKOUT_ID}` query parameter" to success_url
  https://polar.sh/docs/api-reference/checkout-links/create      POST /v1/checkout-links/, body
      `payment_processor` "stripe" + `products`, response `url`
  https://polar.sh/docs/integrate/webhooks/delivery       headers webhook-id / webhook-timestamp / webhook-signature;
      secrets made before 8 September 2026 00:00 UTC use the UTF-8 bytes of the whole `whsec_...` string as the
      HMAC key, later ones are Standard Webhooks secrets; Polar's SDKs try both keys, and so does verify()
  https://github.com/standard-webhooks/standard-webhooks/blob/main/spec/standard-webhooks.md (v1.0.0)
      signed content `id.timestamp.body`, HMAC-SHA256, header `v1,<base64>`, space-separated list

Not documented on the pages above, so not assumed here: the JSON shape of a webhook body. verify() returns the
parsed body and the CLI prints its `type` field only if there is one. The 5-minute timestamp tolerance is our
choice; neither source gives a number.

Nothing here creates a product. Tokens and secrets are read from the environment (POLAR_ACCESS_TOKEN,
POLAR_WEBHOOK_SECRET), never from an argument or a file, and never printed.

    python3 billing/polar.py checkout --product <uuid> [--email E] [--production]
    python3 billing/polar.py link --product <uuid> [--label L] [--production] [--write-config]
    python3 billing/polar.py verify --headers headers.json --body body.json
"""
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "brand" / "site" / "config.json"
API = {"sandbox": "https://sandbox-api.polar.sh/v1", "production": "https://api.polar.sh/v1"}
TOKEN_ENV = "POLAR_ACCESS_TOKEN"
SECRET_ENV = "POLAR_WEBHOOK_SECRET"
TOLERANCE = 300           # seconds either side of now; our choice (see the docstring)
TIMEOUT = 30
MAX_METADATA = 50         # pairs; keys up to 40 characters, string values up to 500 (create-session schema)


class PolarError(Exception):
    pass


class WebhookError(Exception):
    pass


def load_config(path: Path | None = None) -> dict:
    with open(path or CONFIG, encoding="utf-8") as f:
        return json.load(f)


def success_url(cfg: dict) -> str:
    """Back to the site's pricing page; Polar fills {CHECKOUT_ID} in."""
    return cfg["site_url"] + "pricing.html?checkout_id={CHECKOUT_ID}"


def _products(products) -> list[str]:
    if not products:
        raise PolarError("at least one product id is needed")
    out = []
    for p in products:
        try:
            out.append(str(uuid.UUID(str(p))))
        except ValueError:
            raise PolarError(f"not a product id (UUID): {p!r}") from None
    return out


def _metadata(md: dict | None) -> dict:
    md = dict(md or {})
    if len(md) > MAX_METADATA:
        raise PolarError(f"metadata has {len(md)} pairs, Polar takes up to {MAX_METADATA}")
    for k, v in md.items():
        if not isinstance(k, str) or not 1 <= len(k) <= 40:
            raise PolarError(f"metadata key must be 1-40 characters: {k!r}")
        if isinstance(v, str):
            if len(v) > 500:
                raise PolarError(f"metadata value for {k!r} is over 500 characters")
        elif not isinstance(v, (int, float, bool)):
            raise PolarError(f"metadata value for {k!r} must be a string, number or boolean")
    return md


def _base(env: str) -> str:
    if env not in API:
        raise PolarError(f"environment must be one of {sorted(API)}")
    return API[env]


def checkout_request(products, cfg: dict, env: str = "sandbox", customer_email: str | None = None,
                     metadata: dict | None = None) -> tuple[str, dict]:
    """A single-use checkout session (POST /v1/checkouts/)."""
    body = {"products": _products(products), "success_url": success_url(cfg)}
    if customer_email:
        body["customer_email"] = customer_email
    if metadata:
        body["metadata"] = _metadata(metadata)
    return _base(env) + "/checkouts/", body


def link_request(products, cfg: dict, env: str = "sandbox", label: str | None = None,
                 metadata: dict | None = None) -> tuple[str, dict]:
    """A reusable checkout link (POST /v1/checkout-links/): the URL a static pricing page can carry."""
    body = {"payment_processor": "stripe", "products": _products(products), "success_url": success_url(cfg)}
    if label:
        body["label"] = label
    if metadata:
        body["metadata"] = _metadata(metadata)
    return _base(env) + "/checkout-links/", body


def _urlopen(req: urllib.request.Request) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


SEND = _urlopen           # the one network call; tests swap it


def post(url: str, body: dict, token: str, send=None) -> dict:
    """POST JSON with the bearer token; return the decoded reply. Errors never carry the token."""
    send = send or SEND
    if not token:
        raise PolarError(f"no token: set {TOKEN_ENV}")
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST", headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json"})
    try:
        status, raw = send(req)
    except (urllib.error.URLError, OSError) as e:
        raise PolarError(f"POST {url} failed: {str(e).replace(token, '[token]')}") from None
    text = raw.decode("utf-8", "replace").replace(token, "[token]")
    if status not in (200, 201):
        raise PolarError(f"POST {url} returned {status}: {text[:300]}")
    try:
        return json.loads(text)
    except ValueError:
        raise PolarError(f"POST {url} returned {status} but not JSON") from None


def created_url(reply: dict) -> str:
    url = reply.get("url") if isinstance(reply, dict) else None
    if not isinstance(url, str) or not url.startswith("https://"):
        raise PolarError("Polar's reply has no https url")
    return url


def write_checkout_url(url: str, path: Path | None = None) -> None:
    """The site's one place for the address (brand/site/config.json); build.py turns it into the buy button."""
    cfg = load_config(path)
    cfg["checkout_url"] = url
    with open(path or CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=1, ensure_ascii=False)
        f.write("\n")


def hmac_keys(secret: str) -> list[bytes]:
    """Both keys Polar's delivery page describes: the Standard Webhooks key (base64 after `whsec_`), and the
    UTF-8 bytes of the whole secret string (secrets made before 8 September 2026)."""
    if not secret:
        raise WebhookError(f"no webhook secret: set {SECRET_ENV}")
    keys = []
    if secret.startswith("whsec_"):
        try:
            keys.append(base64.b64decode(secret[len("whsec_"):], validate=True))
        except (binascii.Error, ValueError):
            pass
    keys.append(secret.encode("utf-8"))
    return keys


def sign(key: bytes, msg_id: str, timestamp: str, body: bytes) -> str:
    mac = hmac.new(key, msg_id.encode() + b"." + timestamp.encode() + b"." + body, hashlib.sha256).digest()
    return "v1," + base64.b64encode(mac).decode()


def verify(secret: str, headers: dict, body: bytes, now: float | None = None, tolerance: int = TOLERANCE) -> dict:
    """Check a delivery's signature and timestamp; return the parsed JSON body. Raises WebhookError."""
    h = {str(k).lower(): str(v) for k, v in headers.items()}
    msg_id, ts, sigs = h.get("webhook-id"), h.get("webhook-timestamp"), h.get("webhook-signature")
    if not (msg_id and ts and sigs):
        raise WebhookError("missing webhook-id, webhook-timestamp or webhook-signature")
    try:
        t = int(ts)
    except ValueError:
        raise WebhookError("webhook-timestamp is not an integer") from None
    now = time.time() if now is None else now
    if abs(now - t) > tolerance:
        raise WebhookError(f"webhook-timestamp is more than {tolerance} s from now")
    given = [s for s in sigs.split(" ") if s.startswith("v1,")]
    for key in hmac_keys(secret):
        expected = sign(key, msg_id, ts, body)
        if any(hmac.compare_digest(expected, g) for g in given):
            break
    else:
        raise WebhookError("no signature matches")
    try:
        return json.loads(body)
    except ValueError:
        raise WebhookError("signed body is not JSON") from None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="billing/polar.py", description="Polar checkout and webhook helper "
                                 f"(token from {TOKEN_ENV}, webhook secret from {SECRET_ENV}; sandbox by default)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, text in (("checkout", "create a single-use checkout session, print its URL"),
                       ("link", "create a reusable checkout link, print its URL")):
        p = sub.add_parser(name, help=text)
        p.add_argument("--product", action="append", required=True, help="Polar product id (repeatable)")
        p.add_argument("--production", action="store_true", help="use api.polar.sh instead of the sandbox")
        if name == "checkout":
            p.add_argument("--email", help="prefill the customer's email")
        else:
            p.add_argument("--label")
            p.add_argument("--write-config", action="store_true",
                           help="also set checkout_url in brand/site/config.json")
    v = sub.add_parser("verify", help="check a saved delivery: headers JSON file + raw body file")
    v.add_argument("--headers", required=True)
    v.add_argument("--body", required=True)
    a = ap.parse_args(argv)

    if a.cmd == "verify":
        with open(a.headers, encoding="utf-8") as f:
            headers = json.load(f)
        body = Path(a.body).read_bytes()
        try:
            event = verify(os.environ.get(SECRET_ENV, ""), headers, body)
        except WebhookError as e:
            print(f"rejected: {e}", file=sys.stderr)
            return 1
        kind = event.get("type") if isinstance(event, dict) else None
        msg_id = {str(k).lower(): v for k, v in headers.items()}["webhook-id"]
        print(f"ok {msg_id}" + (f" {kind}" if kind else ""))
        return 0

    env = "production" if a.production else "sandbox"
    cfg = load_config()
    try:
        if a.cmd == "checkout":
            url, body = checkout_request(a.product, cfg, env, customer_email=a.email)
        else:
            url, body = link_request(a.product, cfg, env, label=a.label)
        result = created_url(post(url, body, os.environ.get(TOKEN_ENV, "")))
    except PolarError as e:
        print(f"polar: {e}", file=sys.stderr)
        return 2
    print(result)
    if a.cmd == "link" and a.write_config:
        write_checkout_url(result)
        print(f"checkout_url set in {CONFIG}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
