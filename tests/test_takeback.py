"""takeback-bench (bench/takeback/takeback.py): the oracle, the judge, and that each tool really runs.

The oracle is the part a reader has to trust, so it is tested on hand-made snapshots here; the judge must call
a miss a miss and a clobbered later edit "destroyed"; and one real scenario per tool runs end to end (rewindagents
through its real hook process)."""
import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("takeback", ROOT / "bench" / "takeback" / "takeback.py")
tb = importlib.util.module_from_spec(_spec)
sys.modules["takeback"] = tb          # dataclasses look the module up by name
_spec.loader.exec_module(tb)


def scn(steps, goal, **kw):
    return tb.Scenario("T", "t", steps, goal, **kw)


A, H = tb.Step("Edit", "a"), tb.Step("hand", "a")


class OracleTest(unittest.TestCase):
    def test_to_step_takes_agent_changes_back_and_keeps_hand_ones(self):
        snaps = [{"a": "1", "b": "1"}, {"a": "2", "b": "1"}, {"a": "3", "b": "1", "c": "new"},
                 {"a": "3", "b": "h", "c": "new"}]
        steps = [A, tb.Step("Bash"), tb.Step("hand", "b")]
        want = tb.expected(scn(steps, ("to", 1)), snaps, [0, 1, 2])
        # a back to step 1's bytes, c (created by agent step 2) gone, b keeps the hand edit
        self.assertEqual(want, {"a": "2", "b": "h"})

    def test_to_zero_is_the_state_before_the_session(self):
        snaps = [{"a": "1"}, {"a": "2", "n": "x"}]
        self.assertEqual(tb.expected(scn([A], ("to", 0)), snaps, [0, 1]), {"a": "1"})

    def test_only_undoes_one_step_and_keeps_later_agent_work(self):
        snaps = [{"a": "1", "t": "t"}, {"a": "2", "t": "t"}, {"a": "2"}, {"a": "2", "c": "c"}]
        steps = [A, tb.Step("Bash"), tb.Step("Write", "c")]
        self.assertEqual(tb.expected(scn(steps, ("only", 2)), snaps, [0, 1, 2, 3]), {"a": "2", "t": "t", "c": "c"})

    def test_a_path_changed_by_agent_and_by_hand_needs_stated_merge(self):
        snaps = [{"a": "1"}, {"a": "2"}, {"a": "3"}, {"a": "4"}]
        with self.assertRaises(ValueError):
            tb.expected(scn([A, A, H], ("to", 1)), snaps, [0, 1, 2])
        want = tb.expected(scn([A, A, H], ("to", 1), merge={"a": "m"}), snaps, [0, 1, 2])
        self.assertEqual(want, {"a": tb.text_state("m")})


class JudgeTest(unittest.TestCase):
    def j(self, want, pre, post):
        return tb.judge(want, pre, post, scn([], ("to", 0)), ROOT)

    def test_exact(self):
        r = self.j({"a": "1"}, {"a": "2"}, {"a": "1"})
        self.assertTrue(r["exact"])
        self.assertEqual((r["missed"], r["destroyed"]), ([], []))

    def test_missed_and_destroyed_are_told_apart(self):
        r = self.j({"a": "1", "keep": "k"}, {"a": "2", "keep": "k"}, {"a": "2"})
        self.assertFalse(r["exact"])
        self.assertEqual(r["missed"], ["a"])
        self.assertEqual(r["destroyed"], ["keep"])

    def test_executable_bit_counts(self):
        r = self.j({"s": "sha256:x +x"}, {}, {"s": "sha256:x"})
        self.assertFalse(r["exact"])
        self.assertEqual(r["mode_only"], ["s"])
        self.assertIn("+x lost", tb.outcome(dict(r, applies=True, exit=0)))

    def test_a_miss_with_exit_0_is_called_silent(self):
        r = self.j({"a": "1"}, {"a": "2"}, {"a": "2"})
        self.assertIn("silent", tb.outcome(dict(r, applies=True, exit=0)))
        self.assertNotIn("silent", tb.outcome(dict(r, applies=True, exit=1)))


class RealRunTest(unittest.TestCase):
    def test_every_tool_runs_a_real_scenario(self):
        s01 = next(s for s in tb.SCENARIOS if s.id == "S01")
        for name, cls in tb.TOOLS.items():
            r = tb.run_one(s01, cls())
            self.assertTrue(r["applies"], name)
            self.assertIn("undo_ms", r)
        self.assertTrue(tb.run_one(s01, tb.RewindAgents())["exact"])
        self.assertTrue(tb.run_one(s01, tb.GitPerStep())["exact"])
        # the stash snapshot goes back to the session start: it takes step 1's good edit too
        self.assertEqual(tb.run_one(s01, tb.GitStash())["destroyed"], ["app.py"])

    def test_temp_dirs_are_removed(self):
        import tempfile
        before = set(Path(tempfile.gettempdir()).glob("takeback-*"))
        tb.run_one(tb.SCENARIOS[0], tb.GitPerStep())
        self.assertEqual(set(Path(tempfile.gettempdir()).glob("takeback-*")), before)


class ResultsFileTest(unittest.TestCase):
    def test_published_results_say_where_and_when_and_cover_every_scenario(self):
        for name in ("results.json", "results-baseline.json"):
            r = json.loads((ROOT / "bench" / "takeback" / name).read_text(encoding="utf-8"))
            self.assertRegex(r["date"], r"^\d{4}-\d{2}-\d{2}$")
            self.assertRegex(r["commit"], r"^[0-9a-f]{7,}$")
            for k in ("os", "arch", "python", "git"):
                self.assertTrue(r["machine"].get(k), k)
            self.assertEqual({s["id"] for s in r["scenarios"]}, {s.id for s in tb.SCENARIOS})
            self.assertEqual(len(r["results"]), len(r["scenarios"]) * len(r["tools"]))

    def test_results_md_tables_are_the_scripts_rendering(self):
        md = (ROOT / "bench" / "RESULTS.md").read_text(encoding="utf-8")
        for name in ("results.json", "results-baseline.json"):
            r = json.loads((ROOT / "bench" / "takeback" / name).read_text(encoding="utf-8"))
            self.assertIn(tb.table(r), md, name + ": run python3 bench/takeback/takeback.py --markdown")


if __name__ == "__main__":
    unittest.main()
