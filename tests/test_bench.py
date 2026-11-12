"""R17: the overhead numbers in the README and on the docs page are the ones bench/hook_overhead.py wrote to
bench/results.json, with the machine and date it ran on, and no other timing number is typed anywhere."""
import importlib.util
import io
import json
import os
import re
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_bench():
    spec = importlib.util.spec_from_file_location("hook_overhead", os.path.join(ROOT, "bench", "hook_overhead.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


MS = re.compile(r"\d[\d,.]* ?ms\b")


class BenchTest(unittest.TestCase):
    def setUp(self):
        self.bench = load_bench()
        self.results = json.loads(read("bench", "results.json"))

    def test_results_say_where_and_when(self):
        r = self.results
        self.assertRegex(r["date"], r"^\d{4}-\d{2}-\d{2}$")
        for k in ("os", "arch", "cpus", "python"):
            self.assertTrue(r["machine"].get(k), k)
        self.assertRegex(r["commit"], r"^[0-9a-f]{7,}$")
        self.assertEqual([x["files"] for x in r["results"]], [100, 1000, 10000])
        for x in r["results"]:
            self.assertEqual(sorted(x["tools"]), sorted(self.bench.TOOLS))
            for s in x["tools"].values():
                self.assertLessEqual(s["min_ms"], s["median_ms"])
                self.assertLessEqual(s["median_ms"], s["p90_ms"])
                self.assertLessEqual(s["p90_ms"], s["max_ms"])

    def test_readme_block_is_the_scripts_rendering_of_results(self):
        readme = read("README.md")
        a = readme.index(self.bench.START)
        b = readme.index(self.bench.END) + len(self.bench.END)
        self.assertEqual(readme[a:b], self.bench.readme_block(self.results),
                         "README drifted from bench/results.json: run python3 bench/hook_overhead.py --readme-only")

    def test_no_timing_number_is_typed_outside_the_generated_block(self):
        readme = read("README.md")
        a, b = readme.index(self.bench.START), readme.index(self.bench.END)
        self.assertEqual(MS.findall(readme[:a] + readme[b:]), [])
        docs = read("brand", "site", "docs", "index.html")
        sec = re.search(r'<h2 id="overhead">.*?(?=<h2 )', docs, re.S).group(0)
        self.assertEqual(MS.findall(docs.replace(sec, "")), [])
        for page in ("index.html", "pricing.html"):
            self.assertEqual(MS.findall(read("brand", "site", page)), [], page)
        allowed = set()
        for x in self.results["results"]:
            allowed.add(self.bench._ms(x["first_bash_ms"]))
            for s in x["tools"].values():
                allowed |= {self.bench._ms(s["median_ms"]), self.bench._ms(s["p90_ms"])}
        allowed.add(self.bench._ms(self.results["startup"]["median_ms"]))
        for n in MS.findall(sec):
            self.assertIn(n, allowed, n)
        self.assertIn(self.bench.where(self.results).replace("&", "&amp;"), sec)

    def test_the_script_measures_through_the_real_hook(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "r.json")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(self.bench.main(["--files", "12", "--runs", "2", "--out", out]), 0)
            with open(out, encoding="utf-8") as f:
                r = json.load(f)
        x = r["results"][0]
        self.assertEqual(x["files"], 12)
        self.assertEqual({t: s["runs"] for t, s in x["tools"].items()}, {"Read": 2, "Edit": 2, "Bash": 2})
        self.assertGreater(x["first_bash_ms"], 0)
        self.assertGreater(r["startup"]["median_ms"], 0)

    def test_readme_only_rewrites_from_saved_results(self):
        with tempfile.TemporaryDirectory() as d:
            readme = os.path.join(d, "README.md")
            with open(readme, "w", encoding="utf-8") as f:
                f.write("x\n%s\nold\n%s\ny\n" % (self.bench.START, self.bench.END))
            self.bench.write_readme(self.results, path=Path(readme))
            with open(readme, encoding="utf-8") as f:
                self.assertEqual(f.read(), "x\n%s\ny\n" % self.bench.readme_block(self.results))


if __name__ == "__main__":
    unittest.main()
