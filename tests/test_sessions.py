"""`rewindagent sessions [--grep TEXT]`: list the sessions in a log and find the ones that mention a text."""
import os
import re
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rewindagent import hook, read, rewind, sessions  # noqa: E402
from test_rewind import Agent, cli  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def two_sessions(d):
    """Session "one" writes two files and runs a command; session "two" (later) edits one file and reads one."""
    one = Agent(d, "one")
    one.write("app/config.py", "PORT = 1\n")                        # one: step 1
    one.write("README.md", "hello\n")                               # one: step 2
    one.bash("pytest -q tests/")                                    # one: step 3 (nothing changed)
    two = Agent(d, "two")
    two.write("app/config.py", "PORT = 2\n")                        # two: step 1
    inp = {"file_path": str(Path(d) / "README.md")}        # a Read is recorded like any call
    hook.handle(two._p("PreToolUse", "Read", inp))
    hook.handle(two._p("PostToolUse", "Read", inp, {"content": "hello\n"}))   # two: step 2
    return one, two


class TestSessions(unittest.TestCase):
    def test_every_session_is_listed_once_in_first_write_order_with_steps_and_files(self):
        with TemporaryDirectory() as d:
            one, two = two_sessions(d)
            got = sessions.sessions(one.log)
            self.assertEqual([e["session"] for e in got], ["one", "two"])
            self.assertEqual([e["steps"] for e in got], [3, 2])
            self.assertEqual(got[0]["files"], ["app/config.py", "README.md"])   # paths relative to the project
            self.assertEqual(got[1]["files"], ["app/config.py"])                # a Read touches nothing
            self.assertEqual([e["latest"] for e in got], [False, True])
            self.assertEqual([e["rewinds"] for e in got], [0, 0])

    def test_first_and_last_are_the_times_of_the_sessions_own_records(self):
        with TemporaryDirectory() as d:
            one, _ = two_sessions(d)
            recs = read(one.log)
            ones = [r for r in recs if r["session"] == "one"]
            e = sessions.sessions(one.log)[0]
            self.assertEqual((e["first"], e["last"]), (ones[0]["ts"], ones[-1]["ts"]))
            self.assertLessEqual(e["first"], e["last"])

    def test_a_rewind_counts_as_a_step_and_its_files_as_touched(self):
        with TemporaryDirectory() as d:
            a = Agent(d, "s")
            a.write("x.txt", "1")
            a.write("y.txt", "2")
            rewind.rewind(a.log, 1)             # deletes y.txt, checkpointing it first: step 3
            e = sessions.sessions(a.log)[0]
            self.assertEqual((e["steps"], e["rewinds"]), (3, 1))
            self.assertEqual(e["files"], ["x.txt", "y.txt"])
            _, out, _ = cli("--log", str(a.log), "sessions")
            self.assertIn("  3 steps (1 rewind)  2 files  (latest)", out.splitlines()[0])
            rewind.rewind(a.log, 2)             # undo the rewind: step 4, a second rewind
            _, out, _ = cli("--log", str(a.log), "sessions")
            self.assertIn("  4 steps (2 rewinds)  2 files", out.splitlines()[0])

    def test_the_latest_mark_follows_the_last_record_not_the_list_order(self):
        with TemporaryDirectory() as d:
            Agent(d, "first").write("a.txt", "1")
            Agent(d, "second").write("b.txt", "1")
            Agent(d, "first").write("a.txt", "2")    # "first" writes the last record
            got = sessions.sessions(Agent(d).log)
            self.assertEqual([(e["session"], e["latest"]) for e in got], [("first", True), ("second", False)])
            self.assertEqual(rewind.latest_session(Agent(d).log), "first")   # the same session replay defaults to


class TestGrep(unittest.TestCase):
    def test_grep_matches_commands_and_paths_in_any_case_and_lists_the_steps(self):
        with TemporaryDirectory() as d:
            one, _ = two_sessions(d)
            by_cmd = sessions.sessions(one.log, "PYTEST")
            self.assertEqual([e["session"] for e in by_cmd], ["one"])
            self.assertEqual([(s["step"], s["tool"]) for s in by_cmd[0]["hits"]], [(3, "Bash")])
            by_path = sessions.sessions(one.log, "config")
            self.assertEqual([e["session"] for e in by_path], ["one", "two"])
            self.assertEqual([s["step"] for s in by_path[0]["hits"]], [1])
            self.assertEqual([s["step"] for s in by_path[1]["hits"]], [1])
            self.assertEqual(sessions.sessions(one.log, "nothing-like-this"), [])

    def test_grep_sees_a_read_files_path_and_a_bash_checkpointed_path(self):
        with TemporaryDirectory() as d:
            one, two = two_sessions(d)
            self.assertEqual([s["step"] for s in sessions.sessions(one.log, "readme")[1]["hits"]], [2])
            two.bash("mv README.md NOTES.md", action=lambda cwd: os.rename(cwd / "README.md", cwd / "NOTES.md"))
            hits = sessions.sessions(one.log, "notes.md")[0]["hits"]
            self.assertEqual([(s["step"], s["tool"]) for s in hits], [(3, "Bash")])   # matched by the checkpointed path

    def test_a_record_without_a_file_or_command_is_searched_by_its_input(self):
        with TemporaryDirectory() as d:
            a = Agent(d, "w")
            inp = {"query": "fcntl flock semantics"}
            hook.handle(a._p("PreToolUse", "WebSearch", inp))
            hook.handle(a._p("PostToolUse", "WebSearch", inp, {"results": []}))
            self.assertEqual(len(sessions.sessions(a.log, "FLOCK")), 1)


class TestCli(unittest.TestCase):
    def test_lists_sessions_without_the_projects_absolute_path(self):
        with TemporaryDirectory() as d:
            one, _ = two_sessions(d)
            code, out, err = cli("--log", str(one.log), "sessions")
            self.assertEqual((code, err), (0, ""))
            lines = out.splitlines()
            self.assertEqual(len(lines), 4, out)
            self.assertRegex(lines[0], r"^one  \d{4}-\d\d-\d\d \d\d:\d\d:\d\d to \d{4}-\d\d-\d\d \d\d:\d\d:\d\d  3 steps  2 files$")
            self.assertEqual(lines[1], "    files: app/config.py, README.md")
            self.assertTrue(lines[2].startswith("two  "), lines[2])
            self.assertTrue(lines[2].endswith("  2 steps  1 files  (latest)"), lines[2])
            self.assertEqual(lines[3], "    files: app/config.py")
            self.assertNotIn(str(Path(d).resolve()), out)

    def test_the_time_shown_is_the_records_local_time(self):
        with TemporaryDirectory() as d:
            one, _ = two_sessions(d)
            e = sessions.sessions(one.log)[0]
            _, out, _ = cli("--log", str(one.log), "sessions")
            self.assertIn(f"{sessions.when(e['first'])} to {sessions.when(e['last'])}", out.splitlines()[0])

    def test_grep_prints_matching_steps_and_exits_1_when_nothing_matches(self):
        with TemporaryDirectory() as d:
            one, _ = two_sessions(d)
            code, out, err = cli("--log", str(one.log), "sessions", "--grep", "pytest")
            self.assertEqual((code, err), (0, ""))
            self.assertEqual(out.splitlines()[0].split("  ")[0], "one")
            self.assertEqual(out.splitlines()[-1], "        3  Bash          pytest -q tests/")
            self.assertNotIn("two  ", out)
            code, out, err = cli("--log", str(one.log), "sessions", "--grep", "zebra")
            self.assertEqual((code, out), (1, ""))
            self.assertEqual(err.strip(), "rewindagent: no session mentions 'zebra'")

    def test_more_than_show_files_are_counted_not_listed(self):
        with TemporaryDirectory() as d:
            a = Agent(d, "many")
            for i in range(sessions.SHOW_FILES + 2):
                a.write(f"f{i}.txt", "x")
            _, out, _ = cli("--log", str(a.log), "sessions")
            self.assertIn(f"{sessions.SHOW_FILES + 2} files", out.splitlines()[0])
            self.assertTrue(out.splitlines()[1].endswith(" (+2 more)"), out)
            self.assertEqual(out.splitlines()[1].count(".txt"), sessions.SHOW_FILES)

    def test_no_log_is_exit_2(self):
        with TemporaryDirectory() as d:
            code, _, err = cli("--log", str(Path(d, "none.jsonl")), "sessions")
            self.assertEqual(code, 2)
            self.assertIn("no log at", err)


class TestReadme(unittest.TestCase):
    def test_readme_describes_sessions_as_the_code_does(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("rewindagent sessions --grep", readme)
        self.assertIn(f"first {sessions.SHOW_FILES} files", readme)
        # the status line lists the command among what is built
        status = re.search(r"\*\*Status:.*?\n\n", readme, re.S).group(0)
        self.assertIn("`sessions`", status)


if __name__ == "__main__":
    unittest.main()
