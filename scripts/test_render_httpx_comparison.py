"""Offline checks for HTML escaping and cross-run comparison integrity."""

import csv
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location("render_httpx_comparison", Path(__file__).with_name("render_httpx_comparison.py"))
report = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(report)


def target(number):
    return {"id": str(number), "group": "example", "url": f"https://site{number}.example/"}


def row(number, status=200, **extra):
    return {**target(number), "state": "http_response", "status": status,
            "title": "Example", "content_length": 12, "time_seconds": .2,
            "challenge_heuristic": False, "process_failed": False,
            "process_timed_out": False, "chain_status_codes": [],
            "challenge_evidence": [], **extra}


def run(name, upstream, fork, reverse=False, mode="defaults"):
    rows = {"upstream": {r["id"]: r for r in upstream}, "fork": {r["id"]: r for r in fork}}
    arms = {}
    for arm, entries in rows.items():
        states = {}
        for entry in entries.values():
            states[entry["state"]] = states.get(entry["state"], 0) + 1
        arms[arm] = {"http_responses": sum(report.is_http(r) for r in entries.values()),
                     "http_2xx": sum(report.is_2xx(r) for r in entries.values()),
                     "challenge_heuristic": 0, "states": states}
    return {"path": Path("/tmp/capture") / name, "name": name, "rows": rows,
            "summary": {"mode": mode, "target_count": len(upstream), "arms": arms,
                        "transitions": {"different_status": sum(a["status"] != b["status"] for a, b in zip(upstream, fork))},
                        "latency": {"pair_count": 0, "upstream_median_seconds": None,
                                    "fork_median_seconds": None, "paired_delta_fork_minus_upstream_median_seconds": None}},
            "metadata": {"started_at": "2026-10-16T09:00:00+00:00", "finished_at": "2026-10-16T09:05:00+00:00",
                         "order": ["fork", "upstream"] if reverse else ["upstream", "fork"]}}


class ReportTests(unittest.TestCase):
    def test_repetition_requires_same_outcomes_in_both_orders(self):
        ab = run("ab", [row(1, 403), row(2, 403), row(3)], [row(1), row(2), row(3)])
        ba = run("ba", [row(1, 403), row(2), row(3)], [row(1), row(2), row(3)], reverse=True)
        base, repeated, changed = report.repeated_deltas([ab, ba], [target(i) for i in range(1, 4)])
        self.assertEqual(repeated, ["1"])
        self.assertEqual(changed, ["2"])
        self.assertEqual(base, (ab, ba))
        self.assertEqual(report.repeated_deltas([ab], [target(1)]), (None, [], []))

    def test_native_subset_is_outside_cohort_not_missing(self):
        native = run("native", [row(1)], [row(1)], mode="native")
        native["partial"] = True
        self.assertIsNone(report.pair(native, "2"))
        self.assertIn("Fuori campione", report.pair_cell(native, "2"))
        self.assertNotIn("output assente", report.pair_cell(native, "2"))
        self.assertIn("Campione selezionato", report.summary_section([native]))

    def test_untrusted_titles_errors_and_attributes_are_escaped(self):
        malicious = '</script><img src=x onerror="alert(1)"><script>alert(2)</script>'
        capture = run("<bad>", [row(1, title=malicious)],
                      [row(1, status=None, state="request_failure", error=malicious)])
        rendered = report.render([capture], [target(1)], Path("/tmp/index.html"), Path("/tmp/targets.csv"))
        self.assertNotIn('<img src=x', rendered)
        self.assertNotIn('<script>alert(2)', rendered)
        self.assertIn('&lt;img src=x onerror=&quot;alert(1)&quot;&gt;', rendered)
        self.assertEqual(rendered.count("<script>"), 1)
        self.assertIn('data-errors="1"', rendered)
        self.assertNotIn('href="javascript:', report.target_link("javascript:alert(1)"))

    def test_findings_derive_counts_and_flag_200_challenges_and_native_deltas(self):
        matched = run("matched", [row(1, 403), row(2)],
                      [row(1), row(2, title="Client Challenge", challenge_heuristic=True)], mode="matched")
        native = run("native", [row(1, 302)], [row(1, 403, title="Verifying your connection")], mode="native")
        section = report.findings_section([matched, native])
        self.assertIn("upstream riceve 1 risposte 2xx e il fork 2", section)
        self.assertIn("I 403 sono 1 e 0", section)
        self.assertIn("0 URL su 1", section)
        self.assertIn("Un HTTP 200 può contenere una challenge", section)
        self.assertIn("Client Challenge", section)
        self.assertIn("Differenze nel controllo native", section)
        self.assertIn("<th>403</th><th>406</th>", report.summary_section([matched]))

    def test_supporting_links_only_point_to_existing_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "validation.md").write_text("tests")
            (root / "fingerprints.json").write_text("{}")
            section = report.method_section([], root / "index.html", root / "targets.csv")
            self.assertIn('href="validation.md"', section)
            self.assertIn('href="fingerprints.json"', section)
            self.assertNotIn('href="README.md"', section)

    def test_challenge_examples_distinguish_native_from_browser(self):
        matched = run("matched-verified", [row(1)], [row(1)], mode="matched")
        native = run("native-control-verified", [row(1)],
                     [row(1, title="Your request has been blocked", challenge_heuristic=True)], mode="native")
        section = report.findings_section([matched, native])
        warning = section[section.index('<aside'):section.index('</aside>')]
        self.assertIn('<b>Fork native</b>', warning)
        self.assertIn('Esecuzioni: native-control-verified', warning)
        self.assertNotIn('Fork browser', warning)
        self.assertNotIn('matched-verified', warning)

    def test_run_target_must_match_canonical_dataset(self):
        capture = run("ab", [row(1)], [row(1)])
        capture["rows"]["fork"]["1"]["url"] = "https://wrong.example/"
        with self.assertRaisesRegex(ValueError, "canonical dataset"):
            report.render([capture], [target(1)], Path("/tmp/index.html"), Path("/tmp/targets.csv"))

    def test_load_rejects_incomplete_and_inconsistent_capture(self):
        capture = run("ab", [row(1)], [row(1)])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "summary.json").write_text(json.dumps(capture["summary"]))
            unfinished = {k: v for k, v in capture["metadata"].items() if k != "finished_at"}
            (path / "metadata.json").write_text(json.dumps(unfinished))
            with self.assertRaisesRegex(ValueError, "not finished"):
                report.load_run(path)
            (path / "metadata.json").write_text(json.dumps(capture["metadata"]))
            columns = ["arm"] + list(capture["rows"]["upstream"]["1"])
            with (path / "normalized.csv").open("w", newline="") as output:
                writer = csv.DictWriter(output, fieldnames=columns)
                writer.writeheader()
                for arm in report.ARMS:
                    values = {k: json.dumps(v) if isinstance(v, list) else v for k, v in capture["rows"][arm]["1"].items()}
                    writer.writerow({"arm": arm, **values})
            loaded = report.load_run(path)
            self.assertEqual(loaded["rows"]["fork"]["1"]["status"], 200)
            capture["summary"]["arms"]["fork"]["http_2xx"] = 0
            (path / "summary.json").write_text(json.dumps(capture["summary"]))
            with self.assertRaisesRegex(ValueError, "2xx totals"):
                report.load_run(path)

    def test_invalidated_and_historically_broken_cli_captures_are_rejected(self):
        capture = run("ab", [row(1)], [row(1)])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "INVALIDATED.md").write_text("invalid flags")
            with self.assertRaisesRegex(ValueError, "Invalidated"):
                report.load_run(path)
            (path / "INVALIDATED.md").unlink()
            (path / "summary.json").write_text(json.dumps(capture["summary"]))
            capture["metadata"]["arms"] = {"upstream": {"command": ["httpx", "-bp", "300", "-retries", "0"]}}
            (path / "metadata.json").write_text(json.dumps(capture["metadata"]))
            with self.assertRaisesRegex(ValueError, "stops CLI flag parsing"):
                report.load_run(path)
            capture["summary"]["validity"] = {"controlled_comparison_valid": False}
            (path / "summary.json").write_text(json.dumps(capture["summary"]))
            with self.assertRaisesRegex(ValueError, "Invalid controlled"):
                report.load_run(path)


if __name__ == "__main__":
    unittest.main()
