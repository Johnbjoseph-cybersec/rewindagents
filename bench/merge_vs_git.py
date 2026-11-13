"""Compare rewindagents' three-way merge (src/rewindagents/merge.py) with `git merge-file` on random inputs.

Each case: a base of 3-16 lines drawn from ALPHABET (with repeats), and two sides that each make 0-3 random
edits (replace, insert, delete). Both merges run; the outcome is counted as: same bytes, both conflict, conflict
only here (revert refuses), conflict only in git, or both clean with different bytes.

    python3 bench/merge_vs_git.py                  # 3 seeds x 1,000 cases, 3-line alphabet (repeats a lot)
    python3 bench/merge_vs_git.py --alphabet abcdefghijkl --seeds 8

Stdlib only; needs git on PATH. Writes three small files to a temporary directory, removed after.
"""
from __future__ import annotations

import argparse
import random
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from rewindagents.merge import Conflict, merge3  # noqa: E402


def mutate(rnd: random.Random, ls: list[str], alphabet: str) -> list[str]:
    ls = list(ls)
    for _ in range(rnd.randint(0, 3)):
        op, i = rnd.random(), rnd.randint(0, len(ls))
        if op < 0.4 and ls:
            ls[min(i, len(ls) - 1)] = rnd.choice(alphabet + "xy") + "\n"
        elif op < 0.7:
            ls.insert(i, rnd.choice(alphabet + "pq") + "\n")
        elif ls:
            del ls[min(i, len(ls) - 1)]
    return ls


def run(seed: int, n: int, alphabet: str, d: Path) -> dict[str, int]:
    rnd = random.Random(seed)
    res = dict.fromkeys(("same", "both_conflict", "conflict_only_here", "conflict_only_git", "different_bytes"), 0)
    o, a, b = d / "o", d / "a", d / "b"
    for _ in range(n):
        base = [rnd.choice(alphabet) + "\n" for _ in range(rnd.randint(3, 16))]
        ours, theirs = mutate(rnd, base, alphabet), mutate(rnd, base, alphabet)
        for p, ls in ((o, base), (a, ours), (b, theirs)):
            p.write_bytes("".join(ls).encode())
        g = subprocess.run(["git", "merge-file", "-p", str(a), str(o), str(b)], capture_output=True)
        try:
            mine = merge3(o.read_bytes(), a.read_bytes(), b.read_bytes())
        except Conflict:
            mine = None
        git = g.stdout if g.returncode == 0 else None
        if mine is None and git is None:
            res["both_conflict"] += 1
        elif mine is None:
            res["conflict_only_here"] += 1
        elif git is None:
            res["conflict_only_git"] += 1
        else:
            res["same" if mine == git else "different_bytes"] += 1
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--alphabet", default="abc")
    ap.add_argument("--seeds", type=int, nargs="+", default=[7, 8, 9])
    ap.add_argument("-n", type=int, default=1000)
    a = ap.parse_args()
    print(subprocess.run(["git", "--version"], capture_output=True, text=True).stdout.strip())
    with tempfile.TemporaryDirectory() as d:
        for seed in a.seeds:
            print(f"seed {seed}, {a.n} cases, alphabet {a.alphabet!r}: {run(seed, a.n, a.alphabet, Path(d))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
