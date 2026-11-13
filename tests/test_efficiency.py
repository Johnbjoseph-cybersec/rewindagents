"""The efficiency pilot (bench/efficiency/pilot.py) without running any agent: the task is a real task (its
seeded bugs fail both test sets), the recorded runs carry what the plan promises, and the budget guard holds."""
import importlib.util
import io
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("pilot", ROOT / "bench" / "efficiency" / "pilot.py")
pilot = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pilot)


class TaskTest(unittest.TestCase):
    def test_the_seeded_task_fails_visible_and_hidden_tests(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t, "repo")
            shutil.copytree(pilot.TASK / "repo", d)
            self.assertFalse(pilot.visible_ok(d))
            self.assertFalse(pilot.hidden_ok(d, ["test_hidden_cart.py"]))

    def test_hidden_tests_are_not_in_the_agents_copy(self):
        names = {p.name for p in (pilot.TASK / "repo").rglob("*")}
        self.assertFalse(names & {p.name for p in (pilot.TASK / "hidden").glob("*.py")})


class RunsTest(unittest.TestCase):
    def test_every_recorded_run_has_the_fields_the_plan_names(self):
        runs = pilot.runs_so_far()
        self.assertLessEqual(len(runs), pilot.PILOT_RUNS)
        for r in runs:
            for k in ("task", "task_sha", "commit", "workflow", "wall_s", "num_turns", "cost_usd", "tokens",
                      "visible_pass", "hidden_pass", "model", "claude"):
                self.assertIn(k, r)

    def test_budget_guard_refuses_past_the_pilot(self):
        with self.assertRaises(SystemExit):
            pilot.budget_ok(pilot.PILOT_RUNS - len(pilot.runs_so_far()) + 1, None)

    def test_report_runs_without_agents(self):
        out = io.StringIO()
        with redirect_stdout(out):
            pilot.report()
        self.assertIn("| workflow | n |", out.getvalue())


if __name__ == "__main__":
    unittest.main()
