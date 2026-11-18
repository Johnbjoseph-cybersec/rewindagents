"""What the live-agent evidence says, and a check that a page's live-status sentences say the same.

harness/live/evidence/<agent>.json is the only source of truth for whether an agent's hook has run in a live
session (harness/live/run.py writes it, harness/live/validate.py schema-checks it). A user-facing page must
follow it in both directions: an agent whose evidence is VERIFIED_LIVE is said to be verified in a live session
and never said to be not yet live; every other agent is said to be not yet in a live session and never said to
have run live. Standard library only.
"""
import json
import re
from pathlib import Path

from rewindagents import agents

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "harness" / "live" / "evidence"

# How each agent is named in prose. A clause names an agent when it contains this word.
NAMES = {"claude": "Claude Code", "codex": "Codex", "cursor": "Cursor", "gemini": "Gemini",
         "copilot": "Copilot", "droid": "Droid", "qwen": "Qwen"}

NOT_LIVE = re.compile(r"not yet (?:in|run in(?:side)?) a live session|not in a live session|has not run in a live", re.I)
LIVE = re.compile(r"verified in (?:a )?live sessions?|ha(?:s|ve) run in (?:a )?(?:live|real) sessions?|"
                  r"ran in (?:a )?live sessions?", re.I)


def load():
    """{agent: evidence dict} for every agent rewindagents has a hook for; a missing file is an error."""
    out = {}
    for key in agents.AGENTS:
        out[key] = json.loads((EVIDENCE / ("%s.json" % key)).read_text(encoding="utf-8"))
    return out


def verified(ev):
    return ev["status"] == "VERIFIED_LIVE"


def version_of(ev):
    """The version number in the agent's own --version line ('codex-cli 0.170.0' -> '0.170.0')."""
    m = re.search(r"\d+(?:\.\d+)+(?:-[0-9a-f]+)?", ev["agent_version"] or "")
    return m.group(0) if m else None


def clauses(text):
    """Sentences, split again at semicolons, whitespace collapsed (a README sentence spans lines)."""
    text = re.sub(r"\s+", " ", text)
    return [c for c in re.split(r"(?<=[.;!?])\s+", text) if c]


def mismatches(text, evidence):
    """Every way `text` disagrees with the evidence, as readable strings (empty list = it agrees)."""
    problems = []
    said_live, said_not = set(), set()
    for c in clauses(text):
        named = [k for k, n in NAMES.items() if n.lower() in c.lower()]
        if NOT_LIVE.search(c):
            for k in named:
                said_not.add(k)
                if verified(evidence[k]):
                    problems.append("%s is VERIFIED_LIVE but this says it is not yet live: %r" % (k, c))
        elif LIVE.search(c):
            for k in named:
                said_live.add(k)
                if not verified(evidence[k]):
                    problems.append("%s is %s but this says it ran live: %r" % (k, evidence[k]["status"], c))
                elif evidence[k]["ran_at"][:10] not in c:
                    problems.append("%s: a live claim without the date of the run (%s): %r"
                                    % (k, evidence[k]["ran_at"][:10], c))
    for k, ev in evidence.items():
        if verified(ev) and k not in said_live:
            problems.append("%s is VERIFIED_LIVE but no sentence says it was verified in a live session" % k)
        if not verified(ev) and k not in said_not:
            problems.append("%s is %s but no sentence says it is not yet in a live session" % (k, ev["status"]))
    return problems


def versions_missing(text, evidence):
    """Every VERIFIED_LIVE agent whose CLI version from the evidence is not in `text`."""
    return ["%s %s" % (k, version_of(ev)) for k, ev in evidence.items()
            if verified(ev) and (not version_of(ev) or version_of(ev) not in text)]
