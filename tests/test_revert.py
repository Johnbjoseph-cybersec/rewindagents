"""`rewindagents revert K`: take back step K alone and keep every later step and hand edit.

takeback-bench S09 (a bad Edit, then a hand edit to the same file): `rewind` refuses safely and leaves the user to
merge by hand; git per step destroys the hand edit. S10 (undo one step, keep the agent's later work) needed
`rewind K-1 --only <each file step K changed>`. revert does both with one command, three-way merging each file
(base = after step K, theirs = before step K, ours = now), and on a conflict changes nothing and exits 1.

Every test here drives the real hook (test_rewind.Agent) and the real CLI. On the code before revert existed, the
CLI tests exit 2 (argparse: invalid choice 'revert') and `rewindagents.revert` / `rewindagents.merge` do not
import, so every test in this file fails there.
"""
import hashlib
import io
import os
import random
import shutil
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_rewind import Agent  # noqa: E402

from rewindagents import gc, hook, log, rewind  # noqa: E402
from rewindagents.cli import main  # noqa: E402

CONFIG = "debug: false\nport: 8080\nretries: 3\n"
BAD = "debug: true\nport: 8080\nretries: 3\n"


def cli(*args):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(list(args))
    return code, out.getvalue(), err.getvalue()


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.old = os.getcwd()
        os.chdir(self.root)
        self.a = Agent(self.root)

    def tearDown(self):
        os.chdir(self.old)
        self.tmp.cleanup()

    def f(self, name):
        p = self.root / name
        return p.read_text() if p.exists() else None

    def put(self, name, text):
        (self.root / name).parent.mkdir(parents=True, exist_ok=True)
        (self.root / name).write_text(text)

    def edit(self, name, old, new):
        """An Edit tool call through the real hook."""
        inp = {"file_path": str(self.root / name), "old_string": old, "new_string": new}
        hook.handle(self.a._p("PreToolUse", "Edit", inp))
        self.put(name, self.f(name).replace(old, new, 1))
        hook.handle(self.a._p("PostToolUse", "Edit", inp, {"ok": True}))

    def snapshot(self):
        out = {}
        for p in sorted(self.root.rglob("*")):
            if ".rewindagents" in p.parts or not p.is_file():
                continue
            out[str(p.relative_to(self.root))] = (p.read_bytes(), p.stat().st_mode & 0o777)
        return out


class TestRevertKeepsLaterWork(Case):
    def test_s09_bad_edit_then_hand_edit_to_the_same_file(self):
        self.put("config.yaml", CONFIG)
        self.a.write("app.py", "v1\n")                                   # step 1
        self.edit("config.yaml", "debug: false\n", "debug: true\n")      # step 2: the bad one
        self.put("config.yaml", BAD + "# keep: staging uses 8081\n")     # by hand, no hook sees it
        code, out, err = cli("revert", "2")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.f("config.yaml"), CONFIG + "# keep: staging uses 8081\n")
        self.assertEqual(self.f("app.py"), "v1\n")                       # step 1 stays
        self.assertIn("revert step 2 of 2", out)
        self.assertIn("merge    config.yaml: step 2's change taken out, later changes kept", out)
        self.assertIn("undo it with:", out)

    def test_s10_undo_one_bash_step_keep_the_later_agent_step(self):
        self.put("tests/test_a.py", "def test_a(): pass\n")
        self.put("tests/test_b.py", "def test_b(): pass\n")
        self.a.write("app.py", "v2\n")                                                 # step 1
        self.a.bash("rm -rf tests", lambda cwd: shutil.rmtree(cwd / "tests"))         # step 2
        self.a.write("CHANGELOG.md", "## 0.2\n")                                       # step 3
        code, out, err = cli("revert", "2")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.f("tests/test_a.py"), "def test_a(): pass\n")
        self.assertEqual(self.f("tests/test_b.py"), "def test_b(): pass\n")
        self.assertIn("restore  tests/test_a.py", out)       # exactly the bytes from before step 2
        self.assertEqual(self.f("app.py"), "v2\n")
        self.assertEqual(self.f("CHANGELOG.md"), "## 0.2\n")

    def test_a_later_agent_edit_to_another_line_of_the_same_file_stays(self):
        self.put("config.yaml", CONFIG)
        self.a.bash("sed debug", lambda cwd: (cwd / "config.yaml").write_text(BAD))               # step 1
        self.edit("config.yaml", "retries: 3\n", "retries: 5\n")                                    # step 2
        code, out, err = cli("revert", "1")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.f("config.yaml"), "debug: false\nport: 8080\nretries: 5\n")

    def test_a_file_the_step_created_goes_only_if_unchanged_since(self):
        self.a.write("helper.py", "def h(): pass\n")      # step 1 creates it
        self.a.write("other.py", "x\n")                   # step 2
        code, out, err = cli("revert", "1")
        self.assertEqual(code, 0, out + err)
        self.assertIsNone(self.f("helper.py"))
        self.assertIn("delete   helper.py", out)
        self.assertEqual(self.f("other.py"), "x\n")

    def test_a_file_the_step_deleted_comes_back_with_its_mode(self):
        self.put("run.sh", "#!/bin/sh\necho hi\n")
        os.chmod(self.root / "run.sh", 0o755)
        self.a.bash("rm run.sh", lambda cwd: (cwd / "run.sh").unlink())    # step 1
        self.a.write("later.txt", "l\n")                                    # step 2
        code, out, err = cli("revert", "1")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.f("run.sh"), "#!/bin/sh\necho hi\n")
        self.assertEqual((self.root / "run.sh").stat().st_mode & 0o777, 0o755)
        self.assertEqual(self.f("later.txt"), "l\n")

    def test_the_revert_is_a_step_and_can_be_rewound_and_reverted(self):
        self.put("config.yaml", CONFIG)
        self.edit("config.yaml", "debug: false\n", "debug: true\n")       # step 1
        self.put("config.yaml", BAD + "# hand\n")
        before = self.f("config.yaml")
        self.assertEqual(cli("revert", "1")[0], 0)
        st = rewind.steps(self.a.log)
        self.assertEqual(st[-1]["event"], "revert")
        self.assertEqual(rewind.summary(st[-1]), "reverted step 1, keeping the steps after it")
        # rewind to just before the revert brings the exact pre-revert bytes back
        code, out, err = cli("rewind", "1")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.f("config.yaml"), before)
        # and a revert of the revert does the same (base: the revert's own stored result)
        cli("rewind", "2")                       # back to the reverted file
        self.assertEqual(self.f("config.yaml"), CONFIG + "# hand\n")
        code, out, err = cli("revert", "2")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.f("config.yaml"), before)
        self.assertTrue(log.verify(self.a.log)[0])

    def test_an_already_reverted_file_is_same_and_nothing_is_recorded(self):
        self.put("config.yaml", CONFIG)
        self.edit("config.yaml", "debug: false\n", "debug: true\n")
        self.put("config.yaml", CONFIG)                   # the user undid it by hand
        n = len(log.read(self.a.log))
        code, out, err = cli("revert", "1")
        self.assertEqual(code, 0, out + err)
        self.assertIn("same     config.yaml", out)
        self.assertEqual(len(log.read(self.a.log)), n)


class TestConflict(Case):
    def conflicted(self):
        self.put("config.yaml", CONFIG)
        self.a.write("app.py", "v1\n")
        self.edit("config.yaml", "debug: false\n", "debug: true\n")          # step 2
        self.put("config.yaml", "debug: maybe\nport: 8080\nretries: 3\n")    # by hand: the same line
        self.a.write("app.py", "v2\n")                                       # step 3

    def test_a_conflict_changes_nothing_and_exits_1(self):
        self.conflicted()
        files, log_bytes = self.snapshot(), self.a.log.read_bytes()
        objs = sorted(os.listdir(self.root / ".rewindagents" / "objects"))
        code, out, err = cli("revert", "2")
        self.assertEqual(code, 1, out + err)
        self.assertEqual(self.snapshot(), files)                      # no file
        self.assertEqual(self.a.log.read_bytes(), log_bytes)          # no record
        self.assertEqual(sorted(os.listdir(self.root / ".rewindagents" / "objects")), objs)
        self.assertIn("revert 2 refused, nothing changed", err)
        self.assertIn("CONFLICT config.yaml: step 2 and a later change both changed line 1", err)
        self.assertIn("replay --step 2 --diff", err)                  # what to do next
        self.assertIn("rewind 1 --only config.yaml --force", err)

    def test_one_conflicting_file_blocks_the_clean_ones_too(self):
        self.put("config.yaml", CONFIG)
        self.put("b.txt", "b\n")
        self.a.bash("both", lambda cwd: (cwd.joinpath("config.yaml").write_text(BAD),
                                         cwd.joinpath("b.txt").write_text("B\n")))
        self.put("config.yaml", "debug: maybe\nport: 8080\nretries: 3\n")
        code, out, err = cli("revert", "1")
        self.assertEqual(code, 1)
        self.assertEqual(self.f("b.txt"), "B\n")                       # not reverted either

    def test_dry_run_shows_the_conflict_and_the_plan_changes_nothing(self):
        self.conflicted()
        files = self.snapshot()
        code, out, err = cli("revert", "2", "--dry-run")
        self.assertEqual(code, 1)
        self.assertIn("would conflict", out)
        self.assertEqual(self.snapshot(), files)

    def test_dry_run_of_a_clean_revert_lists_and_changes_nothing(self):
        self.put("config.yaml", CONFIG)
        self.edit("config.yaml", "debug: false\n", "debug: true\n")
        self.put("config.yaml", BAD + "# hand\n")
        files, n = self.snapshot(), len(log.read(self.a.log))
        code, out, err = cli("revert", "1", "--dry-run")
        self.assertEqual(code, 0, out + err)
        self.assertIn("would change 1 file", out)
        self.assertIn("merge    config.yaml", out)
        self.assertEqual(self.snapshot(), files)
        self.assertEqual(len(log.read(self.a.log)), n)

    def test_a_created_file_changed_since_is_a_conflict(self):
        self.a.write("helper.py", "v1\n")
        self.put("helper.py", "v1 by hand\n")
        code, out, err = cli("revert", "1")
        self.assertEqual(code, 1)
        self.assertIn("step 1 created it, and it changed after step 1", err)
        self.assertEqual(self.f("helper.py"), "v1 by hand\n")

    def test_a_deleted_file_created_again_is_a_conflict(self):
        self.put("notes.txt", "old\n")
        self.a.bash("rm notes.txt", lambda cwd: (cwd / "notes.txt").unlink())
        self.put("notes.txt", "new\n")
        code, out, err = cli("revert", "1")
        self.assertEqual(code, 1)
        self.assertIn("step 1 deleted it, and it was created again", err)
        self.assertEqual(self.f("notes.txt"), "new\n")


class TestLimits(Case):
    def test_out_of_range_exits_2_and_no_log_exits_2(self):
        self.a.write("a.txt", "1\n")
        code, _, err = cli("revert", "5")
        self.assertEqual(code, 2)
        self.assertIn("step 5 is out of range", err)
        self.assertEqual(cli("revert", "0")[0], 2)
        with TemporaryDirectory() as d:
            self.assertEqual(cli("--log", str(Path(d, "none.jsonl")), "revert", "1")[0], 2)

    def test_a_step_that_changed_nothing_says_so(self):
        self.a.bash("ls")
        code, _, err = cli("revert", "1")
        self.assertEqual(code, 1)
        self.assertIn("changed no file", err)
        self.assertIn("a file outside it or a symlink it changed is not recorded", err)

    def test_a_broken_chain_changes_nothing(self):
        self.put("config.yaml", CONFIG)
        self.edit("config.yaml", "debug: false\n", "debug: true\n")
        lines = self.a.log.read_text().splitlines(True)
        lines[0] = lines[0].replace("Edit", "Edyt")
        self.a.log.write_text("".join(lines))
        code, _, err = cli("revert", "1")
        self.assertEqual(code, 1)
        self.assertIn("does not verify", err)
        self.assertEqual(self.f("config.yaml"), BAD)

    def test_a_file_outside_the_project_is_cannot(self):
        with TemporaryDirectory() as other:
            target = Path(other, "x.txt")
            target.write_text("1\n")
            inp = {"file_path": str(target), "content": "2\n"}
            hook.handle(self.a._p("PreToolUse", "Write", inp))
            target.write_text("2\n")
            hook.handle(self.a._p("PostToolUse", "Write", inp, {"ok": True}))
            code, out, _ = cli("revert", "1")
            self.assertEqual(code, 1)
            self.assertIn("outside the project", out)
            self.assertEqual(target.read_text(), "2\n")

    def test_a_tampered_stored_copy_is_cannot(self):
        self.put("config.yaml", CONFIG)
        self.edit("config.yaml", "debug: false\n", "debug: true\n")
        self.put("config.yaml", BAD + "# hand\n")
        obj = self.root / ".rewindagents" / "objects" / hashlib.sha256(CONFIG.encode()).hexdigest()
        obj.write_text("tampered")
        code, out, _ = cli("revert", "1")
        self.assertEqual(code, 1)
        self.assertIn("stored copy missing or altered", out)
        self.assertEqual(self.f("config.yaml"), BAD + "# hand\n")

    def test_an_old_log_without_the_after_copy_uses_the_file_when_it_still_has_the_hash(self):
        """Logs written before this version hold the after hash only. If the file is still as step K left it,
        the file now is that version; if a hand edit changed it, nothing says what step K left: cannot."""
        self.put("config.yaml", CONFIG)
        self.edit("config.yaml", "debug: false\n", "debug: true\n")
        (self.root / ".rewindagents" / "objects" / hashlib.sha256(BAD.encode()).hexdigest()).unlink()
        self.put("config.yaml", BAD + "# hand\n")
        code, out, _ = cli("revert", "1")
        self.assertEqual(code, 1)
        self.assertIn("was not kept", out)
        self.assertEqual(self.f("config.yaml"), BAD + "# hand\n")
        self.put("config.yaml", BAD)
        code, out, err = cli("revert", "1")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.f("config.yaml"), CONFIG)


class TestHookKeepsTheAfterCopy(Case):
    def test_edit_and_bash_post_records_name_a_stored_copy_that_gc_keeps(self):
        self.put("config.yaml", CONFIG)
        self.edit("config.yaml", "debug: false\n", "debug: true\n")
        self.a.bash("sed", lambda cwd: (cwd / "config.yaml").write_text(BAD + "# 2\n"))
        posts = [r for r in log.read(self.a.log) if r["event"] == "post"]
        for rec, text in zip(posts, (BAD, BAD + "# 2\n")):
            (entry,) = rec["args"]["after"]
            sha = hashlib.sha256(text.encode()).hexdigest()
            self.assertEqual((entry["after"], entry["sha256"]), (sha, sha))
            self.assertIn("mode", entry)
        gc.gc(self.a.log)
        objs = set(os.listdir(self.root / ".rewindagents" / "objects"))
        self.assertIn(hashlib.sha256((BAD + "# 2\n").encode()).hexdigest(), objs)


class TestMergeRepeatedLines(unittest.TestCase):
    """A longest-block diff (difflib, the first version here) pairs a repeated line with the wrong copy of itself:
    it dropped a deletion in the first case and called the second a conflict. merge3 uses a shortest diff
    (Myers, git's default) after trimming the common start and end, as git does."""

    def test_a_deletion_among_identical_lines_is_kept(self):
        from rewindagents.merge import merge3
        self.assertEqual(merge3(b"c\nc\nc\n", b"c\np\nc\nc\n", b"c\nc\n"), b"c\np\nc\n")

    def test_far_apart_changes_in_a_file_of_identical_lines_merge(self):
        from rewindagents.merge import merge3
        base = [b"x\n"] * 20000
        ours, theirs = list(base), list(base)
        ours[15000], theirs[10] = b"ours\n", b"theirs\n"
        got = merge3(b"".join(base), b"".join(ours), b"".join(theirs))
        want = list(base)
        want[15000], want[10] = b"ours\n", b"theirs\n"
        self.assertEqual(got, b"".join(want))

    def test_too_many_changed_lines_is_a_conflict_and_revert_changes_nothing(self):
        from rewindagents import merge
        base = b"".join(b"line %d\n" % i for i in range(merge.MAX_EDITS + 10))
        theirs = base.replace(b"line", b"LINE")           # every line differs
        with self.assertRaises(merge.TooBig):
            merge.merge3(base, base + b"tail\n", theirs)


class TestTooBigRevert(Case):
    def test_revert_reports_it_and_changes_nothing(self):
        from rewindagents import merge
        before = "".join("line %d\n" % i for i in range(merge.MAX_EDITS + 10))
        self.put("big.txt", before)
        self.a.write("big.txt", before.replace("line", "LINE"))           # step 1 rewrites every line
        self.put("big.txt", self.f("big.txt") + "by hand\n")
        now = self.f("big.txt")
        code, out, err = cli("revert", "1")
        self.assertEqual(code, 1)
        self.assertIn("too many to merge safely", err)
        self.assertEqual(self.f("big.txt"), now)


@unittest.skipUnless(shutil.which("git"), "git is not installed")
class TestMergeAgreesWithGit(unittest.TestCase):
    """merge.merge3 is our own (stdlib only, no git needed). On 300 seeded random three-way inputs it gives the
    same answer as `git merge-file`: the same bytes when both merge cleanly, and a conflict when git has one."""

    def test_seeded_inputs(self):
        from rewindagents.merge import Conflict, merge3
        rnd = random.Random(20261114)

        def mutate(ls):
            ls = list(ls)
            for _ in range(rnd.randint(0, 2)):
                op, i = rnd.random(), rnd.randint(0, len(ls))
                if op < 0.4 and ls:
                    ls[min(i, len(ls) - 1)] = rnd.choice("xyzw") + "\n"
                elif op < 0.7:
                    ls.insert(i, rnd.choice("pqrs") + "\n")
                elif ls:
                    del ls[min(i, len(ls) - 1)]
            return ls
        with TemporaryDirectory() as d:
            o, a, b = (Path(d, n) for n in "oab")
            for _ in range(300):
                base = [c + "\n" for c in rnd.sample("abcdefghijkl", rnd.randint(3, 10))]
                ours, theirs = mutate(base), mutate(base)
                for p, ls in ((o, base), (a, ours), (b, theirs)):
                    p.write_bytes("".join(ls).encode())
                g = subprocess.run(["git", "merge-file", "-p", str(a), str(o), str(b)], capture_output=True)
                try:
                    got = merge3(o.read_bytes(), a.read_bytes(), b.read_bytes())
                except Conflict:
                    got = None
                self.assertEqual(got, g.stdout if g.returncode == 0 else None, (base, ours, theirs))


if __name__ == "__main__":
    unittest.main()
