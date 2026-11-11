"""Print a launch-kit file (task RB5) with its address placeholders filled in, ready to paste.

  python3 brand/launch/fill.py show-hn.md        -> the file, with {site_url}, {repo_url} and {waitlist_url}
                                                    replaced from brand/site/config.json

The launch copy keeps the placeholders: the product's address lives in brand/site/config.json only
(tests/test_site.py), so a bought domain is a one-line change there, never a rewrite of the posts. Exit 1 if a
placeholder is unknown or its value is empty in the config. Stdlib only. tests/test_launch.py runs this on every
file of the kit and checks every command in the filled text against README.md.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BRAND = os.path.dirname(HERE)
CONFIG = os.path.join(BRAND, "site", "config.json")
KEYS = ("site_url", "repo_url", "waitlist_url")
PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")


def config():
    with open(CONFIG, encoding="utf-8") as f:
        return json.load(f)


def fill(text, cfg=None):
    """text with every {key} replaced from the config; ValueError on an unknown key or an empty value."""
    cfg = config() if cfg is None else cfg

    def sub(m):
        key = m.group(1)
        if key not in KEYS:
            raise ValueError("unknown placeholder {%s}" % key)
        if not cfg.get(key):
            raise ValueError("{%s} has no value in brand/site/config.json" % key)
        return cfg[key]

    return PLACEHOLDER.sub(sub, text)


def main(argv):
    if len(argv) != 1:
        print("usage: python3 brand/launch/fill.py <file in brand/launch>", file=sys.stderr)
        return 2
    path = argv[0] if os.path.isabs(argv[0]) or os.path.exists(argv[0]) else os.path.join(HERE, argv[0])
    with open(path, encoding="utf-8") as f:
        text = f.read()
    try:
        sys.stdout.write(fill(text))
    except ValueError as e:
        print("fill.py: %s" % e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
