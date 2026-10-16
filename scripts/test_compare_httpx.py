"""Offline fixtures for comparison integrity; no network requests."""

import argparse
import importlib.util
import json
import contextlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


SPEC = importlib.util.spec_from_file_location("compare_httpx", Path(__file__).with_name("compare_httpx.py"))
compare = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(compare)


def target(number, url=None):
    return {"id": str(number), "group": "test", "url": url or f"https://site{number}.example/",
            "category": "fixture", "source": "offline"}


def record(t, status=200, **kwargs):
    return {"input": t["url"], "url": t["url"], "status_code": status, "failed": False,
            "time": "200ms", "content_type": "text/html", **kwargs}


class CompareTests(unittest.TestCase):
    def test_go_duration_units_and_invalid_values(self):
        for value, expected in (("1.25s", 1.25), ("300ms", .3), ("2m3.5s", 123.5),
                                ("50µs", .00005), ("1h2m3s", 3723), ("0", 0), (0.2, .2)):
            self.assertAlmostEqual(compare.parse_duration(value), expected)
        for value in (None, "", "NaN", "-1s", "1foo", "hello200ms", True, float("nan")):
            self.assertIsNone(compare.parse_duration(value))

    def test_canonical_matching_preserves_scheme_path_query(self):
        self.assertEqual(compare.canonical_url("HTTPS://Example.COM:443"), "https://example.com/")
        self.assertNotEqual(compare.canonical_url("http://example.com/"), compare.canonical_url("https://example.com/"))
        self.assertNotEqual(compare.canonical_url("https://example.com/a?x=1"), compare.canonical_url("https://example.com/a?x=2"))
        self.assertEqual(compare.canonical_url("https://user:secret@example.com"), "")

    def test_missing_request_failure_and_process_failure_separate(self):
        targets = [target(1), target(2), target(3)]
        rows, unmatched = compare.normalize(targets, [record(targets[0], 403), record(targets[1], 0, failed=True, error="timeout")], {"exit_code": 2})
        self.assertEqual([r["state"] for r in rows], ["http_response", "request_failure", "missing"])
        self.assertTrue(all(r["process_failed"] for r in rows))
        self.assertFalse(any(r["challenge_heuristic"] for r in rows))
        self.assertEqual(unmatched, [])

    def test_duplicate_records_do_not_select_a_winner(self):
        t = target(1)
        rows, _ = compare.normalize([t], [record(t, 200), record(t, 403)], {"exit_code": 0})
        self.assertEqual(rows[0]["state"], "ambiguous")
        self.assertIsNone(rows[0]["status"])
        self.assertEqual(rows[0]["record_count"], 2)

    def test_redirect_matches_original_input_not_other_final_target(self):
        original, final = target(1), target(2)
        rows, unmatched = compare.normalize([original, final], [record(original, final_url=final["url"])], {"exit_code": 0})
        self.assertEqual([r["state"] for r in rows], ["http_response", "missing"])
        self.assertEqual(rows[0]["final_url"], final["url"])
        self.assertEqual(unmatched, [])

    def test_unknown_input_does_not_fall_back_to_another_targets_url(self):
        t = target(1)
        rows, unmatched = compare.normalize([t], [record(t, input="https://other.example/")], {"exit_code": 0})
        self.assertEqual(rows[0]["state"], "missing")
        self.assertEqual(len(unmatched), 1)

    def test_challenge_requires_header_or_title_evidence(self):
        self.assertEqual(compare.challenge_evidence({"status_code": 403, "title": "Forbidden"}), [])
        self.assertEqual(compare.challenge_evidence({"status_code": 200, "body_preview": "captcha"}), [])
        self.assertEqual(compare.challenge_evidence({"header": {"cf_mitigated": ["challenge"]}}), ["header:cf-mitigated=challenge"])
        self.assertEqual(compare.challenge_evidence({"title": "Just a moment..."}), ["title:just a moment"])
        self.assertEqual(compare.challenge_evidence({"raw_header": "HTTP/2 403\r\nCF-Mitigated: challenge\r\n"}), ["header:cf-mitigated=challenge"])

    def test_200_challenge_and_block_titles_are_not_classified_as_clean_content(self):
        for title, marker in (("Client Challenge", "client challenge"),
                              ("Reddit - Prove your humanity", "prove your humanity"),
                              ("Verifying your connection...", "verifying your connection"),
                              ("Your request has been blocked", "your request has been blocked")):
            t = target(1)
            row = compare.normalize_record(t, [record(t, 200, title=title)], {"exit_code": 0})
            self.assertEqual(row["state"], "http_response")
            self.assertTrue(compare.is_2xx(row))
            self.assertTrue(row["challenge_heuristic"])
            self.assertEqual(row["challenge_evidence"], ["title:" + marker])

    def test_transitions_exclude_missing_and_latency_uses_comparable_pairs(self):
        targets = [target(i) for i in range(1, 9)]
        upstream = [record(targets[0], 403), record(targets[1]), record(targets[2], time="1s"),
                    record(targets[3], time="9s"), record(targets[4], time="20ms"),
                    record(targets[6], title="Reddit - Prove your humanity"), record(targets[7])]
        fork = [record(targets[0]), record(targets[1], 403), record(targets[2], time="400ms"),
                record(targets[3], final_url="https://other.example/", time="1ms"), record(targets[5]),
                record(targets[6]), record(targets[7], title="Client Challenge")]
        normalized = {arm: compare.normalize(targets, records, {"exit_code": 0})[0]
                      for arm, records in (("upstream", upstream), ("fork", fork))}
        summary = compare.summarize(targets, normalized, {"mode": "defaults", "round": 1}, {})
        self.assertEqual(summary["transitions"]["non_2xx_to_2xx"], 1)
        self.assertEqual(summary["transitions"]["2xx_to_non_2xx"], 1)
        self.assertEqual(summary["transitions"]["paired_http_responses"], 6)
        self.assertEqual(summary["latency"]["pair_count"], 1)
        self.assertAlmostEqual(summary["latency"]["paired_delta_fork_minus_upstream_median_seconds"], -.6)
        self.assertEqual(summary["status_pairs"]["missing -> 200"], 1)
        self.assertEqual(summary["status_pairs"]["200 -> missing"], 1)

    def test_malformed_lines_record_diagnostics(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "output.jsonl"
            path.write_text('{"status_code":200}\nnot-json\n[]\n\n', encoding="utf-8")
            records, invalid = compare.read_jsonl(path)
        self.assertEqual(len(records), 1)
        self.assertEqual([r["line"] for r in invalid], [2, 3])

    def test_commands_cap_reads_and_native_matches_ua(self):
        args = argparse.Namespace(mode="native", threads=3, rate=3, timeout=12, user_agent="test-UA")
        for arm in compare.ARMS:
            command = compare.command_for(Path("/bin/test"), arm, args, Path("input"), Path("config"))
            self.assertIn("User-Agent: test-UA", command)
            self.assertIn("-bp=300", command)
            self.assertNotIn("-bp", command)
            self.assertIn("-random-agent=false", command)
            self.assertEqual(command[command.index("-rstr") + 1], "2097152")
            self.assertEqual("-native-http" in command, arm == "fork")
        args.mode = "redirects"
        command = compare.command_for(Path("/bin/test"), "fork", args, Path("input"), Path("config"))
        self.assertIn("-fr", command)
        self.assertEqual(command[command.index("-maxr") + 1], "3")

    def test_historical_separate_preview_argument_invalidates_comparison(self):
        commands = {a: {"command": ["httpx", "-bp", "300", "-rate-limit", "3", "-fr"]} for a in compare.ARMS}
        validity = compare.capture_validity({"arms": commands})
        self.assertFalse(validity["controlled_comparison_valid"])
        self.assertEqual(validity["status"], "invalid")
        self.assertEqual(len(validity["reasons"]), 2)
        commands = {a: {"command": ["httpx", "-bp=300", "-rate-limit", "3", "-fr"]} for a in compare.ARMS}
        self.assertEqual(compare.capture_validity({"arms": commands})["status"], "no_known_cli_error")

    def test_invalid_capture_report_labels_observations_as_excluded(self):
        t = target(1)
        metadata = {"mode": "redirects", "round": 1,
                    "arms": {a: {"exit_code": 0, "command": ["httpx", "-bp", "300", "-fr"]} for a in compare.ARMS}}
        normalized = {a: compare.normalize([t], [record(t, 302)], {"exit_code": 0})[0] for a in compare.ARMS}
        diagnostics = {a: {"invalid_json_lines": [], "unmatched_records": []} for a in compare.ARMS}
        summary = compare.summarize([t], normalized, metadata, diagnostics)
        report = compare.markdown_report(summary, normalized, metadata)
        self.assertIn("INVALID CONTROLLED COMPARISON", report)
        self.assertFalse(summary["validity"]["controlled_comparison_valid"])

    def test_markdown_escapes_site_titles(self):
        self.assertEqual(compare.markdown_cell("a|b\n<script>`&"), "a&#124;b<br>&lt;script&gt;&#96;&amp;")
        self.assertEqual(compare.markdown_cell("[click](https://example.com)"), "&#91;click&#93;(https://example.com)")

    def test_full_run_captures_isolated_processes_and_reanalysis_needs_no_binaries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            targets = root / "input.csv"
            targets.write_text("id,group,url,category,source\n1,test,https://site1.example/,fixture,offline\n", encoding="utf-8")
            binary = root / "fake-httpx"
            binary.write_text("#!" + sys.executable + "\n" +
                              "import json, os, sys\n" +
                              "if '-version' in sys.argv:\n print('offline-fixture 1.0'); sys.exit(0)\n" +
                              "assert 'HTTPS_PROXY' not in os.environ\n" +
                              "assert 'PDCP_API_KEY' not in os.environ\n" +
                              "assert os.environ['HOME'].endswith('/home')\n" +
                              "for url in open(sys.argv[sys.argv.index('-l')+1]):\n" +
                              " print(json.dumps({'input':url.strip(),'url':url.strip(),'status_code':200,'failed':False,'time':'25ms'}))\n",
                              encoding="utf-8")
            binary.chmod(0o755)
            capture = root / "capture"
            args = ["run", "--targets", str(targets), "--upstream", str(binary), "--fork", str(binary),
                    "--output", str(capture), "--mode", "native", "--user-agent", "fixture-UA", "--reverse"]
            with mock.patch.dict(os.environ, {"HTTPS_PROXY": "https://secret@example.com", "PDCP_API_KEY": "secret"}):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(compare.main(args), 0)
            metadata = json.loads((capture / "metadata.json").read_text())
            self.assertEqual(metadata["order"], ["fork", "upstream"])
            self.assertNotIn("secret", json.dumps(metadata))
            for arm in compare.ARMS:
                self.assertEqual(metadata["arms"][arm]["exit_code"], 0)
                self.assertEqual(metadata["arms"][arm]["stdout_sha256"], compare.sha256(capture / (arm + ".jsonl")))
            binary.unlink()
            derived = root / "derived"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(compare.main(["analyze", "--run", str(capture), "--output", str(derived)]), 0)
            self.assertEqual(json.loads((derived / "summary.json").read_text())["transitions"]["both_2xx"], 1)
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(compare.main(["analyze", "--run", str(capture), "--output", str(derived)]), 1)

    def test_analyze_capture_is_offline_and_checks_target_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            targets_path = root / "targets.csv"
            targets_path.write_text("id,group,url,category,source\n1,test,https://site1.example/,fixture,offline\n", encoding="utf-8")
            t = target(1)
            metadata = {"mode": "matched", "round": 1, "targets_sha256": compare.sha256(targets_path),
                        "arms": {a: {"exit_code": 0} for a in compare.ARMS}}
            compare.write_json(root / "metadata.json", metadata)
            for arm in compare.ARMS:
                (root / (arm + ".jsonl")).write_text(json.dumps(record(t)) + "\n", encoding="utf-8")
            summary = compare.analyze_capture(root, root)
            self.assertEqual(summary["transitions"]["both_2xx"], 1)
            self.assertEqual(summary["analysis"]["script_sha256"], compare.sha256(Path(compare.__file__)))
            self.assertTrue(summary["analysis"]["analyzed_at"].endswith("+00:00"))
            self.assertEqual(summary["analysis"]["revision"], 3)
            self.assertTrue((root / "normalized.csv").exists())
            self.assertIn("https://site1.example/", (root / "report.md").read_text())
            targets_path.write_text(targets_path.read_text() + "2,test,https://site2.example/,fixture,offline\n")
            with self.assertRaisesRegex(ValueError, "checksum"):
                compare.analyze_capture(root, root)

    def test_reject_duplicate_urls(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "targets.csv"
            path.write_text("id,group,url,category,source\n1,t,https://example.com,f,s\n2,t,https://EXAMPLE.com/,f,s\n")
            with self.assertRaisesRegex(ValueError, "unique"):
                compare.load_targets(path)


if __name__ == "__main__":
    unittest.main()
