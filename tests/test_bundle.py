"""`rewindagents bundle` / `rewindagents import`: carry a session to another clone, replay and rewind it there."""
import base64
import hashlib
import json
import os
import re
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rewindagents import bundle, read, rewind, sessions, verify  # noqa: E402
from test_rewind import Agent, cli  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def recorded(d, session="s1"):
    """Step 1 writes a.txt v1, step 2 overwrites it (v2), step 3 creates b.txt, step 4 a Bash rm of a.txt."""
    a = Agent(d, session)
    a.write("a.txt", "v1\n")
    a.write("a.txt", "v2\n")
    a.write("sub/b.txt", "b\n")
    a.bash("rm a.txt", action=lambda cwd: (cwd / "a.txt").unlink())
    return a


def tree(root):
    """{relative path: text} for the project's files outside .rewindagents/."""
    root = Path(root)
    return {p.relative_to(root).as_posix(): p.read_text() for p in sorted(root.rglob("*"))
            if p.is_file() and ".rewindagents" not in p.relative_to(root).parts}


def rewrite(path, change):
    """Load a bundle, let change() edit it, write it back with its digest recomputed (a careful tamperer)."""
    b = json.loads(Path(path).read_text())
    change(b)
    b["digest"] = bundle.digest(b)
    Path(path).write_text(json.dumps(b))


class TestRoundTrip(unittest.TestCase):
    def test_a_session_moved_to_another_project_replays_and_rewinds_there(self):
        with TemporaryDirectory() as src, TemporaryDirectory() as dst:
            a = recorded(src)
            out = Path(src, ".rewindagents", "s1.bundle")
            d = bundle.bundle(a.log, out)
            self.assertEqual((d["session"], d["steps"], d["records"]), ("s1", 4, 8))
            # a.txt v1 (before step 2's Write), v2 (before step 4's rm), and sub/b.txt as step 3 left it (the copy
            # each post record keeps for `revert`; v1 and v2 are also what steps 1 and 2 left)
            self.assertEqual(d["objects"], 3)
            dest_log = Path(dst, ".rewindagents", "log.jsonl")
            got = bundle.import_bundle(out, dest_log)
            self.assertEqual((got["session"], got["steps"], got["records"], got["already_here"]), ("s1", 4, 8, 0))
            self.assertEqual(verify(dest_log)[:2], (True, 8))
            # the same steps, the same lines replay prints (paths relative to each project)
            src_steps, dst_steps = rewind.steps(a.log), rewind.steps(dest_log)
            self.assertEqual([s["tool"] for s in dst_steps], [s["tool"] for s in src_steps])
            self.assertEqual([rewind.summary(s, root=Path(dst).resolve()) for s in dst_steps],
                             [rewind.summary(s, root=Path(src).resolve()) for s in src_steps])
            # every path the records name now lives under the destination, none under the source
            text = dest_log.read_text()
            for spelled in (src, str(Path(src).resolve())):
                self.assertNotIn(spelled, text)
                self.assertNotIn(json.dumps(spelled)[1:-1], text)   # as a JSON log spells it (Windows: \\)
            # rewinding in the destination rebuilds the files there as they were after each step
            self.assertEqual(tree(dst), {})
            rewind.rewind(dest_log, 2, "s1")
            self.assertEqual(tree(dst), {"a.txt": "v2\n"})
            rewind.rewind(dest_log, 1, "s1")
            self.assertEqual(tree(dst), {"a.txt": "v1\n"})
            self.assertEqual(tree(src), {"sub/b.txt": "b\n"})     # the source project is untouched

    def test_times_are_kept_so_sessions_shows_the_original_span(self):
        with TemporaryDirectory() as src, TemporaryDirectory() as dst:
            a = recorded(src)
            bundle.bundle(a.log, Path(src, "x.bundle"))
            dest_log = Path(dst, ".rewindagents", "log.jsonl")
            bundle.import_bundle(Path(src, "x.bundle"), dest_log)
            e_src, e_dst = sessions.sessions(a.log)[0], sessions.sessions(dest_log)[0]
            self.assertEqual((e_dst["first"], e_dst["last"]), (e_src["first"], e_src["last"]))
            self.assertEqual(e_dst["files"], e_src["files"])
            self.assertEqual([r["ts"] for r in read(dest_log)], [r["ts"] for r in read(a.log)])

    def test_only_the_named_session_goes_and_it_joins_an_existing_log(self):
        with TemporaryDirectory() as src, TemporaryDirectory() as dst:
            recorded(src, "one")
            two = Agent(src, "two")
            two.write("c.txt", "c1\n")
            two.write("c.txt", "c2\n")
            out = Path(src, "one.bundle")
            d = bundle.bundle(two.log, out, "one")
            self.assertEqual(d["records"], 8)
            here = Agent(dst, "mine")
            here.write("mine.txt", "m\n")
            got = bundle.import_bundle(out, here.log)
            self.assertEqual(got["session"], "one")
            self.assertEqual(verify(here.log)[:2], (True, 2 + 8))
            self.assertEqual([e["session"] for e in sessions.sessions(here.log)], ["mine", "one"])
            self.assertNotIn("two", {r["session"] for r in read(here.log)})

    def test_default_session_is_the_latest_writer(self):
        with TemporaryDirectory() as src:
            recorded(src, "one")
            two = Agent(src, "two")
            two.write("c.txt", "c\n")
            self.assertEqual(bundle.bundle(two.log, Path(src, "b"))["session"], "two")

    def test_root_spellings_cover_the_unresolved_temp_path(self):
        with TemporaryDirectory() as src:
            a = recorded(src)
            bundle.bundle(a.log, Path(src, "b"))
            b = json.loads(Path(src, "b").read_text())
            self.assertIn(str(Path(src).resolve()), b["root_spellings"])
            self.assertIn(src.rstrip("/"), b["root_spellings"])     # the hook saw the unresolved cwd
            self.assertEqual(b["root_spellings"], sorted(b["root_spellings"], key=len, reverse=True))

    def test_importing_the_same_bundle_twice_is_refused_and_changes_nothing(self):
        with TemporaryDirectory() as src, TemporaryDirectory() as dst:
            a = recorded(src)
            out = Path(src, "b")
            bundle.bundle(a.log, out)
            dest_log = Path(dst, ".rewindagents", "log.jsonl")
            bundle.import_bundle(out, dest_log)
            before = dest_log.read_bytes()
            with self.assertRaisesRegex(bundle.BundleError, "already holds session 's1'"):
                bundle.import_bundle(out, dest_log)
            self.assertEqual(dest_log.read_bytes(), before)

    def test_stored_copies_already_present_are_counted_not_rewritten(self):
        with TemporaryDirectory() as src:
            a = recorded(src)
            out = Path(src, "b")
            bundle.bundle(a.log, out, "s1")
            b = json.loads(out.read_text())
            b["session"] = "s1-copy"
            for r in b["records"]:
                r["session"] = "s1-copy"
                r["hash"] = hashlib.sha256(json.dumps({k: v for k, v in r.items() if k != "hash"}, sort_keys=True,
                                                      separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
            b["digest"] = bundle.digest(b)
            out.write_text(json.dumps(b))
            got = bundle.import_bundle(out, a.log)            # back into its own project, under a new id
            self.assertEqual(got["already_here"], got["objects"])
            self.assertTrue(verify(a.log)[0])


class TestRefusals(unittest.TestCase):
    def setUp(self):
        self._src, self._dst = TemporaryDirectory(), TemporaryDirectory()
        self.src, self.dst = self._src.name, self._dst.name
        self.agent = recorded(self.src)
        self.out = Path(self.src, "s1.bundle")
        bundle.bundle(self.agent.log, self.out)
        self.dest_log = Path(self.dst, ".rewindagents", "log.jsonl")

    def tearDown(self):
        self._src.cleanup()
        self._dst.cleanup()

    def refused(self, pattern):
        with self.assertRaisesRegex(bundle.BundleError, pattern):
            bundle.import_bundle(self.out, self.dest_log)
        self.assertEqual(os.listdir(self.dst), [], "a refused import must write nothing")

    def test_an_edited_bundle_fails_its_own_digest(self):
        b = json.loads(self.out.read_text())
        b["records"][0]["tool"] = "Read"
        self.out.write_text(json.dumps(b))
        self.refused("bundle altered")

    def test_an_edited_record_with_a_recomputed_digest_fails_the_record_hash(self):
        rewrite(self.out, lambda b: b["records"][1]["args"].update(input={"file_path": "/etc/passwd"}))
        self.refused("record 2: contents altered")

    def test_an_altered_stored_copy_is_refused(self):
        def change(b):
            sha = next(iter(b["objects"]))
            b["objects"][sha] = base64.b64encode(b"not what was saved\n").decode()
        rewrite(self.out, change)
        self.refused("altered: its bytes do not match")

    def test_a_missing_stored_copy_is_refused(self):
        rewrite(self.out, lambda b: b["objects"].clear())
        self.refused("which the bundle does not carry")

    def test_a_stored_copy_not_named_by_a_hash_is_refused(self):
        rewrite(self.out, lambda b: b["objects"].update({"../../escape": base64.b64encode(b"x").decode()}))
        self.refused("is not named by a SHA-256")
        self.assertFalse(Path(self.dst).parent.joinpath("escape").exists())

    def test_reordered_records_are_refused(self):
        rewrite(self.out, lambda b: b["records"].reverse())
        self.refused("out of log order")

    def test_a_record_from_another_session_is_refused(self):
        other = Agent(self.src, "other")
        other.write("o.txt", "o\n")
        stranger = [r for r in read(other.log) if r["session"] == "other"][0]
        rewrite(self.out, lambda b: b["records"].append(stranger))
        self.refused("belongs to session 'other'")

    def test_not_a_bundle(self):
        self.out.write_text('{"hello": 1}')
        self.refused("not a rewindagents bundle")
        self.out.write_text("not json")
        self.refused("cannot read")

    def test_a_destination_log_that_does_not_verify_is_refused(self):
        here = Agent(self.dst, "mine")
        here.write("m.txt", "m\n")
        here.write("m.txt", "m2\n")                    # the second write stores a copy, so objects/ exists
        lines = here.log.read_text().splitlines()
        lines[0] = lines[0].replace('"Write"', '"Edit"')
        here.log.write_text("\n".join(lines) + "\n")
        before = sorted(p.name for p in (Path(self.dst, ".rewindagents", "objects")).iterdir())
        with self.assertRaisesRegex(bundle.BundleError, "this log does not verify"):
            bundle.import_bundle(self.out, here.log)
        self.assertEqual(sorted(p.name for p in Path(self.dst, ".rewindagents", "objects").iterdir()), before)

    def test_a_tampered_source_log_is_not_bundled(self):
        lines = self.agent.log.read_text().splitlines()
        lines[2] = lines[2].replace("v2", "v3")
        self.agent.log.write_text("\n".join(lines) + "\n")
        with self.assertRaisesRegex(bundle.BundleError, "log does not verify"):
            bundle.bundle(self.agent.log, Path(self.src, "again.bundle"))
        self.assertFalse(Path(self.src, "again.bundle").exists())

    def test_a_session_whose_stored_copy_is_gone_is_not_bundled(self):
        for obj in Path(self.src, ".rewindagents", "objects").iterdir():
            obj.unlink()
        with self.assertRaisesRegex(bundle.BundleError, "missing or altered"):
            bundle.bundle(self.agent.log, Path(self.src, "again.bundle"))

    def test_an_unknown_session_is_not_bundled(self):
        with self.assertRaisesRegex(bundle.BundleError, "no session 'nope'"):
            bundle.bundle(self.agent.log, Path(self.src, "again.bundle"), "nope")


class TestCli(unittest.TestCase):
    def test_bundle_then_import_through_the_cli(self):
        with TemporaryDirectory() as src, TemporaryDirectory() as dst:
            a = recorded(src)
            out = Path(src, "s1.bundle")
            code, text, err = cli("--log", str(a.log), "bundle", "--out", str(out))
            self.assertEqual((code, err), (0, ""))
            self.assertRegex(text.strip(), r"^wrote s1\.bundle: session s1, 4 steps, 8 records, \d+ stored files, "
                                           r"[\d,]+ bytes\n  0 secret values replaced with \[redacted \.\.\.\]; "
                                           r"--no-redact keeps them$")
            dest_log = Path(dst, ".rewindagents", "log.jsonl")
            code, text, err = cli("--log", str(dest_log), "import", str(out))
            self.assertEqual((code, err), (0, ""))
            lines = text.splitlines()
            self.assertRegex(lines[0], r"^imported session s1: 4 steps, 8 records, \d+ stored files \(0 already here\)$")
            self.assertEqual(lines[1], f"  file paths moved from {Path(src).resolve()} to {Path(dst).resolve()}")
            self.assertTrue(lines[2].endswith(" replay --session s1"), lines[2])
            code, text, _ = cli("--log", str(dest_log), "replay")
            self.assertEqual(code, 0)
            self.assertIn("sub/b.txt", text)

    def test_cli_refusals_exit_1_and_bundle_needs_out_and_a_log(self):
        with TemporaryDirectory() as d:
            junk = Path(d, "junk")
            junk.write_text("[]")
            code, _, err = cli("--log", str(Path(d, ".rewindagents", "log.jsonl")), "import", str(junk))
            self.assertEqual((code, err.strip()), (1, "rewindagents: not a rewindagents bundle"))
            code, _, err = cli("--log", str(Path(d, "none.jsonl")), "bundle", "--out", str(Path(d, "x")))
            self.assertEqual(code, 2)
            self.assertIn("no log at", err)
            with self.assertRaises(SystemExit):
                cli("--log", str(Path(d, "none.jsonl")), "bundle")


class TestReadme(unittest.TestCase):
    def test_readme_documents_bundle_and_import(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        section = re.search(r"^## Move a session to another machine\n(.*?)^## ", readme, re.S | re.M).group(1)
        self.assertIn("rewindagents bundle --out", section)
        self.assertIn("rewindagents import ", section)
        status = re.search(r"\*\*Status:.*?\n\n", readme, re.S).group(0)
        self.assertIn("`bundle`", status)
        self.assertIn("`import`", status)


if __name__ == "__main__":
    unittest.main()
