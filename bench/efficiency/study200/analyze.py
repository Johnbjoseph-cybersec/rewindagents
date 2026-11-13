"""Analysis of the 200-run efficiency study, exactly as pre-registered in bench/EFFICIENCY_STUDY_PLAN.md.

Reads bench/efficiency/runs-200.jsonl (or --log PATH), runs no agent, prints Markdown.

    python3 bench/efficiency/study200/analyze.py [--log PATH]
"""
from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import study  # noqa: E402

B = 10000          # bootstrap sequences per task and policy
MAX_SOLO = 6       # sequential retries: at most 6 attempts
MAX_RACES = 2      # race retries: at most 2 races of 3 = the same 6 attempts
INF = float("inf")


def load(path: Path):
    recs = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    done = study.complete_execs(recs)
    kept = [r for r in recs if done.get(r["unit"]) == r["exec"]]
    dropped = [r for r in recs if done.get(r["unit"]) != r["exec"]]
    return recs, kept, dropped


def med(xs):
    xs = list(xs)
    return statistics.median(xs) if xs else None


def fmt(x, nd=1):
    if x is None:
        return "-"
    if x == INF:
        return "not reached"
    return ("%%.%df" % nd) % x


def races_of(rs):
    by = {}
    for r in rs:
        by.setdefault(r["exec"], []).append(r)
    out = []
    for ex, xs in by.items():
        xs.sort(key=lambda r: r["done_after_race_start_s"])
        last = max(r["done_after_race_start_s"] for r in xs)
        vis = [r for r in xs if r["visible_pass"]]
        hid = [r for r in xs if r["hidden_pass"]]
        out.append({
            "cost": sum(r.get("cost_usd") or 0 for r in xs),
            "kept_t": vis[0]["done_after_race_start_s"] if vis else None,
            "kept_hidden": vis[0]["hidden_pass"] if vis else False,
            "oracle_t": hid[0]["done_after_race_start_s"] if hid else None,
            "last_t": last,
            "walls": [r["wall_s"] for r in xs],
        })
    return out


def boot_seq(solos, rng, oracle=False):
    """Sequential retries drawn from the solo attempts: stop at the first visible pass (or hidden, oracle)."""
    ts, ok, cs = [], 0, []
    for _ in range(B):
        t = c = 0.0
        res = None
        for _ in range(MAX_SOLO):
            a = rng.choice(solos)
            t += a["wall_s"]
            c += a.get("cost_usd") or 0
            if (a["hidden_pass"] if oracle else a["visible_pass"]):
                res = a["hidden_pass"]
                break
        ts.append(t if res is not None else INF)
        ok += bool(res)
        cs.append(c)
    return med(ts), ok / B, med(cs)


def boot_race(races, rng, oracle=False):
    """Race retries drawn from the measured races: stop at the first race with a visible pass (or hidden).
    A race in which nothing passes costs the time until its last attempt finished."""
    ts, ok, cs = [], 0, []
    for _ in range(B):
        t = c = 0.0
        res = None
        for _ in range(MAX_RACES):
            r = rng.choice(races)
            c += r["cost"]
            hit = r["oracle_t"] if oracle else r["kept_t"]
            if hit is not None:
                t += hit
                res = True if oracle else r["kept_hidden"]
                break
            t += r["last_t"]
        ts.append(t if res is not None else INF)
        ok += bool(res)
        cs.append(c)
    return med(ts), ok / B, med(cs)


def sign_test(wins, losses):
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    p = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * p)


def report(path: Path) -> str:
    recs, kept, dropped = load(path)
    out = []
    w = out.append
    tasks = study.TASKS
    total_cost = sum(r.get("cost_usd") or 0 for r in recs)
    w("Log: `%s`, %d agent runs in all (%d in complete units, %d in units repeated after an infrastructure "
      "error or a crash), total cost reported by Claude Code %.2f USD." % (
          path.relative_to(study.ROOT) if path.is_relative_to(study.ROOT) else path, len(recs), len(kept),
          len(dropped), total_cost))
    models = sorted({str(r.get("model")) for r in recs})
    vers = sorted({str(r.get("claude")) for r in recs})
    w("Models reported: %s. Claude Code: %s. Commits: %s." % (", ".join(models), ", ".join(vers),
                                                           ", ".join(sorted({r["commit"] for r in recs}))))
    sched = {u["id"] for u in study.schedule()}
    done_units = {r["unit"] for r in kept}
    w("Units complete: %d of %d%s." % (len(done_units), len(sched),
                                        "" if done_units >= sched else " (PARTIAL: the schedule did not finish)"))
    w("")

    # ---------------------------------------------------------- raw per-task table
    w("### Every task, raw (median wall-clock in seconds, min-max in brackets)")
    w("")
    w("| task | solo n | solo visible | solo hidden | solo wall | race attempts n | race attempt hidden | "
      "race attempt wall | races | race kept hidden | race time to kept |")
    w("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    per = {}
    for t in tasks:
        solos = [r for r in kept if r["task"] == t and r["workflow"] == "solo"]
        ra = [r for r in kept if r["task"] == t and r["workflow"] == "race"]
        races = races_of(ra)
        per[t] = (solos, races, ra)
        sw = [r["wall_s"] for r in solos]
        aw = [r["wall_s"] for r in ra]
        kt = [x["kept_t"] if x["kept_t"] is not None else INF for x in races]
        w("| %s | %d | %d/%d | %d/%d | %s [%s-%s] | %d | %d/%d | %s [%s-%s] | %d | %d/%d | %s |" % (
            t, len(solos), sum(r["visible_pass"] for r in solos), len(solos), sum(r["hidden_pass"] for r in solos),
            len(solos), fmt(med(sw)), fmt(min(sw) if sw else None), fmt(max(sw) if sw else None), len(ra),
            sum(r["hidden_pass"] for r in ra), len(ra), fmt(med(aw)), fmt(min(aw) if aw else None),
            fmt(max(aw) if aw else None), len(races), sum(x["kept_hidden"] for x in races), len(races),
            fmt(med(kt))))
    w("")

    # ---------------------------------------------------------- primary comparison
    w("### Primary: time to a kept result, sequential retries vs racing 3 (pre-registered policy)")
    w("")
    w("Sequential: one attempt at a time, retry until the visible tests pass (at most %d attempts). Race: 3 at "
      "once, keep the first to pass the visible tests, race again if none does (at most %d races). Both are "
      "bootstrap medians over %d resampled sequences of the measured runs (seed 0). Hidden = share of "
      "sequences whose kept result passes the hidden tests (a sequence that never passes counts as a fail). "
      "Cost = median USD per sequence; a race counts all three attempts, run to the end." % (
          MAX_SOLO, MAX_RACES, B))
    w("")
    w("| task | seq time s | seq hidden | seq cost | race time s | race hidden | race cost | speed ratio "
      "(seq/race) | cost ratio (race/seq) |")
    w("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    rows = {}
    for i, t in enumerate(tasks):
        solos, races, _ = per[t]
        if not solos or not races:
            w("| %s | (no data) |||||||" % t)
            continue
        s = boot_seq(solos, random.Random(i))
        r = boot_race(races, random.Random(1000 + i))
        so = boot_seq(solos, random.Random(2000 + i), oracle=True)
        ro = boot_race(races, random.Random(3000 + i), oracle=True)
        ratio = (s[0] / r[0]) if r[0] not in (None, 0, INF) and s[0] != INF else None
        cratio = (r[2] / s[2]) if s[2] else None
        rows[t] = {"seq": s, "race": r, "seq_o": so, "race_o": ro, "ratio": ratio, "cratio": cratio,
                   "solo_hidden": sum(x["hidden_pass"] for x in solos) / len(solos)}
        w("| %s | %s | %.2f | %s | %s | %.2f | %s | %s | %s |" % (
            t, fmt(s[0]), s[1], fmt(s[2], 3), fmt(r[0]), r[1], fmt(r[2], 3), fmt(ratio, 2), fmt(cratio, 2)))
    w("")
    ratios = [v["ratio"] for v in rows.values() if v["ratio"] is not None]
    wins = sum(1 for v in rows.values() if v["ratio"] is not None and v["ratio"] > 1)
    losses = sum(1 for v in rows.values() if v["ratio"] is not None and v["ratio"] < 1)
    p = sign_test(wins, losses)
    seq_pass = statistics.mean(v["seq"][1] for v in rows.values()) if rows else 0
    race_pass = statistics.mean(v["race"][1] for v in rows.values()) if rows else 0
    cr = [v["cratio"] for v in rows.values() if v["cratio"] is not None]
    w("Pooled over %d tasks: median speed ratio %s (range %s to %s); race faster on %d, slower on %d "
      "(two-sided sign test p = %.3f); mean hidden pass of the kept result: sequential %.2f, race %.2f; "
      "median cost ratio %s." % (len(rows), fmt(med(ratios), 2), fmt(min(ratios) if ratios else None, 2),
                                 fmt(max(ratios) if ratios else None, 2), wins, losses, p, seq_pass, race_pass,
                                 fmt(med(cr), 2)))
    w("")
    crit = (med(ratios) or 0) >= 1.10 and wins >= 9 and race_pass >= seq_pass - 0.05
    w("Pre-registered decision rule (ratio >= 1.10 AND race faster on >= 9 of 10 tasks AND race hidden pass "
      ">= sequential - 0.05): **%s**." % ("MET" if crit else "NOT MET"))
    w("")

    # ---------------------------------------------------------- oracle + subgroup + concurrency
    w("### Secondary: time to the first attempt that passes the HIDDEN tests (oracle: needs knowledge a user "
      "does not have)")
    w("")
    w("| task | seq oracle time s | seq reaches hidden pass | race oracle time s | race reaches hidden pass |")
    w("|---|---:|---:|---:|---:|")
    for t, v in rows.items():
        w("| %s | %s | %.2f | %s | %.2f |" % (t, fmt(v["seq_o"][0]), v["seq_o"][1], fmt(v["race_o"][0]),
                                              v["race_o"][1]))
    w("")
    hard = [t for t, v in rows.items() if v["solo_hidden"] <= 0.6]
    w("Subgroup (exploratory, pre-registered): tasks where solo attempts passed the hidden tests 3 of 5 times "
      "or fewer: %s." % (", ".join(hard) if hard else "none"))
    if hard:
        hr = [rows[t]["ratio"] for t in hard if rows[t]["ratio"] is not None]
        w("On them: median speed ratio %s; mean hidden pass sequential %.2f, race %.2f." % (
            fmt(med(hr), 2), statistics.mean(rows[t]["seq"][1] for t in hard),
            statistics.mean(rows[t]["race"][1] for t in hard)))
    w("")
    sl = []
    for t in tasks:
        solos, _, ra = per[t]
        if solos and ra:
            sl.append(med(r["wall_s"] for r in ra) / med(r["wall_s"] for r in solos))
    w("Concurrency slowdown: per task, median wall of a race attempt / median wall of a solo attempt; median "
      "over tasks %s (range %s to %s)." % (fmt(med(sl), 2), fmt(min(sl) if sl else None, 2),
                                         fmt(max(sl) if sl else None, 2)))
    w("")

    # ---------------------------------------------------------- H1
    w("### H1: resume after a wreck (rewindagents rewind) vs restart from zero")
    w("")
    w("The wreck is fixed in advance: after part 1 (the issue fix, solo attempt 0), a recorded shell step "
      "deletes the tests and the module. Resume = `rewindagents rewind` + an agent doing part 2 only. Restart = "
      "a fresh copy and an agent doing parts 1 and 2. Hidden = the hidden fix tests AND the hidden part-2 "
      "tests. The ratio is set by how much work lies before the wreck, which the scenario fixes; it is not a "
      "property of the tool.")
    w("")
    w("| task | part 1 hidden | restored exactly | rewind s | resume s | resume hidden | resume cost | "
      "restart s | restart hidden | restart cost |")
    w("|---|---|---|---:|---:|---|---:|---:|---|---:|")
    res_t, rst_t, res_c, rst_c, res_ok, rst_ok = [], [], [], [], 0, 0
    for t in tasks:
        a = [r for r in kept if r["task"] == t and r["workflow"] == "h1-resume"]
        b = [r for r in kept if r["task"] == t and r["workflow"] == "h1-restart"]
        if not a or not b:
            continue
        a, b = a[0], b[0]
        rt = a["rewind_s"] + a["wall_s"]
        res_t.append(rt)
        rst_t.append(b["wall_s"])
        res_c.append(a.get("cost_usd") or 0)
        rst_c.append(b.get("cost_usd") or 0)
        res_ok += a["hidden_pass"]
        rst_ok += b["hidden_pass"]
        w("| %s | %s | %s | %.2f | %.1f | %s | %.3f | %.1f | %s | %.3f |" % (
            t, a["part1_hidden_pass"], a["restored"], a["rewind_s"], rt, a["hidden_pass"], a.get("cost_usd") or 0,
            b["wall_s"], b["hidden_pass"], b.get("cost_usd") or 0))
    if res_t:
        w("")
        w("n = %d: median resume %s s vs restart %s s (ratio %s); hidden pass resume %d/%d, restart %d/%d; "
          "median cost %.3f vs %.3f USD." % (
              len(res_t), fmt(med(res_t)), fmt(med(rst_t)), fmt(med(rst_t) / med(res_t), 2), res_ok, len(res_t),
              rst_ok, len(rst_t), med(res_c), med(rst_c)))
    w("")

    # ---------------------------------------------------------- every run that is not in the tables
    w("### Runs not in the tables above (repeated units)")
    w("")
    if not dropped:
        w("None.")
    for r in dropped:
        w("- %s %s %s: infra_error=%s, cost %s, %s" % (r["date"], r["unit"], r["workflow"], r.get("infra_error"),
                                                      r.get("cost_usd"), (r.get("error_text") or "")[:160]))
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", type=Path, default=study.RUNS)
    a = ap.parse_args(argv)
    print(report(a.log.resolve()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
