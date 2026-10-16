#!/usr/bin/env python3
"""Reproducible, low-rate comparison of two httpx binaries (stdlib only).

run creates an immutable capture directory. analyze reads a capture without
network requests and writes a new set of derived CSV/JSON/Markdown files.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import statistics
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit


ARMS = ("upstream", "fork")
TARGET_FIELDS = ("id", "group", "url", "category", "source")
MODES = ("defaults", "matched", "redirects", "native")
DURATION_PART = re.compile(r"(\d+(?:\.\d+)?)(ns|us|µs|μs|ms|s|m|h)")
DURATION_SCALE = {"ns": 1e-9, "us": 1e-6, "µs": 1e-6, "μs": 1e-6,
                  "ms": 1e-3, "s": 1, "m": 60, "h": 3600}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_url(value):
    """Match scheme/host case and an absent root slash; retain path and query."""
    try:
        parsed = urlsplit(str(value))
        if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname:
            return ""
        if parsed.username is not None or parsed.password is not None:
            return ""
        hostname = parsed.hostname.lower()
        if ":" in hostname:
            hostname = "[" + hostname + "]"
        port = parsed.port
        if port and (parsed.scheme.lower(), port) not in (("http", 80), ("https", 443)):
            hostname += ":" + str(port)
        return urlunsplit((parsed.scheme.lower(), hostname, parsed.path or "/", parsed.query, ""))
    except (TypeError, ValueError):
        return ""


def load_targets(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = set(TARGET_FIELDS) - set(reader.fieldnames or [])
        if missing:
            raise ValueError("Target CSV lacks columns: " + ", ".join(sorted(missing)))
        targets = [{field: (row.get(field) or "").strip() for field in TARGET_FIELDS}
                   for row in reader]
    if not targets:
        raise ValueError("Target CSV is empty")
    ids, urls = set(), set()
    for target in targets:
        key = canonical_url(target["url"])
        if not target["id"] or target["id"] in ids:
            raise ValueError("Target IDs must be present and unique: " + target["id"])
        if not key or key in urls:
            raise ValueError("Target URLs must be valid, unique HTTP(S) URLs without credentials: " + target["id"])
        if any(c in target["url"] for c in "\r\n\t") or urlsplit(target["url"]).fragment:
            raise ValueError("Target URLs must not contain line breaks, tabs, or fragments: " + target["id"])
        ids.add(target["id"])
        urls.add(key)
    return targets


def parse_duration(value):
    """Return seconds from Go duration strings, or None for absent/invalid data."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(value) and value >= 0 else None
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    if value == "0":
        return 0.0
    parts = list(DURATION_PART.finditer(value))
    if not parts or "".join(part.group(0) for part in parts) != value:
        return None
    seconds = sum(float(part.group(1)) * DURATION_SCALE[part.group(2)] for part in parts)
    return seconds if math.isfinite(seconds) else None


def response_headers(record):
    headers = record.get("header") or record.get("headers") or {}
    normalized = {}
    if isinstance(headers, dict):
        for key, value in headers.items():
            values = value if isinstance(value, list) else [value]
            normalized[str(key).lower().replace("_", "-")] = ", ".join(str(v) for v in values)
    raw = record.get("raw_header")
    if isinstance(raw, str):
        for line in raw.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                normalized.setdefault(key.lower().strip(), value.strip())
    return normalized


def challenge_evidence(record):
    """Challenge-like heuristic from explicit headers/titles, including block pages."""
    headers = response_headers(record)
    evidence = []
    if headers.get("cf-mitigated", "").strip().lower() == "challenge":
        evidence.append("header:cf-mitigated=challenge")
    title = " ".join(str(record.get("title") or "").lower().split())
    markers = ("just a moment", "checking your browser", "verify you are human",
               "verify you are a human", "attention required! | cloudflare",
               "pardon our interruption", "captcha", "security verification",
               "client challenge", "verifying your connection", "your request has been blocked",
               "prove your humanity")
    for marker in markers:
        if marker in title:
            evidence.append("title:" + marker)
    return evidence


def read_jsonl(path):
    records, invalid = [], []
    with Path(path).open(encoding="utf-8", errors="replace") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise ValueError("expected JSON object")
                records.append(record)
            except (ValueError, json.JSONDecodeError) as error:
                invalid.append({"line": line_number, "error": str(error)})
    return records, invalid


def normalize_record(target, records, process):
    row = dict(target)
    row.update({"state": "missing", "record_count": len(records), "status": None,
                "title": "", "url_reported": "", "final_url": "", "location": "",
                "server": "", "content_type": "", "content_length": None,
                "body_sha256": "", "time_seconds": None, "chain_status_codes": [],
                "challenge_heuristic": False, "challenge_evidence": [], "error": "",
                "process_exit_code": process.get("exit_code"),
                "process_timed_out": bool(process.get("timed_out")),
                "process_failed": process.get("exit_code") != 0 or bool(process.get("timed_out"))})
    if not records:
        return row
    if len(records) != 1:
        row["state"] = "ambiguous"
        row["error"] = "Multiple records matched this input; none selected"
        return row
    record = records[0]
    status = record.get("status_code")
    if isinstance(status, bool) or not isinstance(status, int) or not 100 <= status <= 599:
        status = None
    failed = record.get("failed") is True or bool(record.get("error"))
    row["state"] = "request_failure" if failed else "http_response" if status else "invalid_result"
    row["status"] = status
    for dest, source in (("title", "title"), ("url_reported", "url"), ("location", "location"),
                         ("server", "webserver"), ("content_type", "content_type"), ("error", "error")):
        row[dest] = str(record.get(source) or "")
    # httpx's url identifies the original endpoint; final_url carries redirect results.
    row["final_url"] = str(record.get("final_url") or record.get("url") or target["url"])
    length = record.get("content_length")
    row["content_length"] = length if isinstance(length, int) and not isinstance(length, bool) else None
    hashes = record.get("hash") or {}
    if isinstance(hashes, dict):
        row["body_sha256"] = str(hashes.get("body_sha256") or hashes.get("sha256") or "")
    row["time_seconds"] = parse_duration(record.get("time"))
    chain = record.get("chain_status_codes")
    if isinstance(chain, list):
        row["chain_status_codes"] = [x for x in chain if isinstance(x, int) and not isinstance(x, bool)]
    row["challenge_evidence"] = challenge_evidence(record)
    row["challenge_heuristic"] = bool(row["challenge_evidence"])
    return row


def normalize(targets, records, process):
    buckets = {canonical_url(t["url"]): [] for t in targets}
    unmatched = []
    for index, record in enumerate(records, 1):
        # Do not match a redirect's final URL to a different original target.
        raw_input = record.get("input")
        key = canonical_url(raw_input) if raw_input else canonical_url(record.get("url"))
        if key in buckets:
            buckets[key].append(record)
        else:
            unmatched.append({"record": index, "input": str(raw_input or ""), "url": str(record.get("url") or "")})
    return [normalize_record(t, buckets[canonical_url(t["url"])], process) for t in targets], unmatched


def is_response(row):
    return row["state"] == "http_response"


def is_2xx(row):
    return is_response(row) and 200 <= row["status"] < 300


def status_label(row):
    return str(row["status"]) if is_response(row) else row["state"]


def median(values):
    return statistics.median(values) if values else None


def capture_validity(metadata):
    """Detect the historical optional-flag mistake without altering raw captures."""
    reasons = []
    commands_present = 0
    for arm in ARMS:
        command = metadata.get("arms", {}).get(arm, {}).get("command") or []
        if command:
            commands_present += 1
        for index, argument in enumerate(command):
            if argument in ("-bp", "--bp", "-body-preview", "--body-preview"):
                if index + 1 < len(command) and not command[index + 1].startswith("-"):
                    reasons.append(arm + ": body-preview used a separate optional value. "
                                   "Go flag parsing stopped at that positional value and ignored subsequent flags, "
                                   "including rate, timeout, User-Agent, redirect and native controls when present.")
    return {"controlled_comparison_valid": not reasons and commands_present == len(ARMS),
            "status": "invalid" if reasons else "no_known_cli_error" if commands_present == len(ARMS) else "unverified",
            "reasons": reasons,
            "scope": "Static checks for known CLI errors; use a localhost control to verify effective runtime options"}


def summarize(targets, normalized, metadata, diagnostics):
    summary = {"schema_version": 1, "mode": metadata.get("mode"), "round": metadata.get("round"),
               "target_count": len(targets), "groups": len({t["group"] for t in targets}),
               "arms": {}, "status_pairs": {}, "transitions": {}, "differences": [],
               "diagnostics": diagnostics, "validity": capture_validity(metadata),
               "analysis": {"revision": 3, "analyzed_at": utc_now(),
                            "script_sha256": sha256(Path(__file__)),
                            "capture_script_sha256": metadata.get("script_sha256")}}
    for arm in ARMS:
        rows = normalized[arm]
        summary["arms"][arm] = {
            "states": dict(sorted(Counter(r["state"] for r in rows).items())),
            "http_statuses": dict(sorted(Counter(str(r["status"]) for r in rows if is_response(r)).items())),
            "http_responses": sum(is_response(r) for r in rows),
            "http_2xx": sum(is_2xx(r) for r in rows),
            "challenge_heuristic": sum(r["challenge_heuristic"] for r in rows),
            "process": metadata.get("arms", {}).get(arm, {}),
        }
    paired = list(zip(normalized["upstream"], normalized["fork"]))
    summary["status_pairs"] = dict(sorted(Counter(status_label(a) + " -> " + status_label(b) for a, b in paired).items()))
    observed = [(a, b) for a, b in paired if is_response(a) and is_response(b)]
    summary["transitions"] = {
        "paired_http_responses": len(observed),
        "both_2xx": sum(is_2xx(a) and is_2xx(b) for a, b in observed),
        "non_2xx_to_2xx": sum(not is_2xx(a) and is_2xx(b) for a, b in observed),
        "2xx_to_non_2xx": sum(is_2xx(a) and not is_2xx(b) for a, b in observed),
        "same_status": sum(a["status"] == b["status"] for a, b in observed),
        "different_status": sum(a["status"] != b["status"] for a, b in observed),
        "different_title": sum(a["title"] != b["title"] for a, b in observed),
        "different_redirect_chain": sum(a["chain_status_codes"] != b["chain_status_codes"] for a, b in observed),
        "different_location": sum(a["location"] != b["location"] for a, b in observed),
        "different_final_url": sum(canonical_url(a["final_url"]) != canonical_url(b["final_url"]) for a, b in observed),
        "challenge_to_2xx_without_evidence": sum(a["challenge_heuristic"] and is_2xx(b) and not b["challenge_heuristic"] for a, b in observed),
        "2xx_without_evidence_to_challenge": sum(is_2xx(a) and not a["challenge_heuristic"] and b["challenge_heuristic"] for a, b in observed),
    }
    latency = [(a, b) for a, b in observed if is_2xx(a) and is_2xx(b)
               and not a["challenge_heuristic"] and not b["challenge_heuristic"]
               and a["status"] == b["status"]
               and canonical_url(a["final_url"]) == canonical_url(b["final_url"])
               and a["content_type"].split(";")[0].strip().lower() == b["content_type"].split(";")[0].strip().lower()
               and a["time_seconds"] is not None and b["time_seconds"] is not None]
    summary["latency"] = {
        "selection": "Paired 2xx HTTP responses, same status/final URL/media type, both timings present, no challenge-like evidence on either side; dynamic bodies may differ",
        "pair_count": len(latency), "upstream_median_seconds": median([a["time_seconds"] for a, b in latency]),
        "fork_median_seconds": median([b["time_seconds"] for a, b in latency]),
        "paired_delta_fork_minus_upstream_median_seconds": median([b["time_seconds"] - a["time_seconds"] for a, b in latency]),
        "paired_ratio_fork_over_upstream_median": median([b["time_seconds"] / a["time_seconds"] for a, b in latency if a["time_seconds"] > 0]),
        "ids": [a["id"] for a, b in latency],
    }
    compare_fields = ("state", "status", "title", "location", "chain_status_codes", "content_type", "content_length", "body_sha256", "challenge_heuristic")
    for a, b in paired:
        changed = [field for field in compare_fields if a[field] != b[field]]
        if canonical_url(a["final_url"]) != canonical_url(b["final_url"]):
            changed.append("final_url")
        if changed:
            summary["differences"].append({"id": a["id"], "url": a["url"], "fields": changed,
                                           "upstream": status_label(a), "fork": status_label(b)})
    summary["interpretation"] = [
        "A missing output, failed process, request failure, and HTTP response are separate outcomes.",
        "A 403-to-200 transition alone does not establish anti-bot bypass or equivalent content.",
        "Challenge-like labels include challenge and block-page header/title heuristics. They can produce false positives or miss challenges; they do not prove a WAF, bypass, or usable content.",
        "The two arms run sequentially; time, CDN routing, cache, server load, and request order can affect differences.",
        "Body hashes can differ for timestamps, cookies, localization, and other dynamic content.",
        "The 2 MiB response-read cap can truncate bodies and affect content hashes, lengths, and timing.",
        "A matched User-Agent still permits differences in DNS, connection reuse, HTTP version, compression, and headers.",
        "The configured rate limits initial probes; redirects and internal transport requests can add traffic.",
        "Redirect mode uses -maxr 3; upstream's limit counts the initial request, allowing at most two followed redirects.",
        "Per-request times describe these requests; they do not measure maximum throughput.",
    ]
    return summary


def markdown_cell(value):
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        value = json.dumps(value, ensure_ascii=False)
    value = str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    for character, replacement in (("\\", "&#92;"), ("|", "&#124;"), ("`", "&#96;"),
                                   ("[", "&#91;"), ("]", "&#93;"), ("*", "&#42;"), ("_", "&#95;")):
        value = value.replace(character, replacement)
    return value.replace("\r", " ").replace("\n", "<br>")


def markdown_report(summary, normalized, metadata):
    t = summary["transitions"]
    lines = ["# httpx comparison", "", f"Mode: **{summary['mode']}**. Round: **{summary['round']}**. "
             f"Targets: **{summary['target_count']}** across **{summary['groups']}** groups.", "",
             "The capture includes exact commands, binary hashes, version output, timings, raw JSONL, and stderr in the run directory.", "",
             "| Outcome | Upstream | Fork |", "| --- | ---: | ---: |"]
    if summary["validity"]["status"] == "invalid":
        warning = ["**INVALID CONTROLLED COMPARISON. The CLI did not apply the requested controls. "
                   "Keep this capture as diagnostic evidence and exclude it from benchmark conclusions.**", ""]
        warning += ["- " + reason for reason in summary["validity"]["reasons"]]
        lines[2:2] = warning + [""]
    for label, field in (("HTTP responses", "http_responses"), ("HTTP 2xx", "http_2xx"), ("Challenge-like heuristic", "challenge_heuristic")):
        lines.append(f"| {label} | {summary['arms']['upstream'][field]} | {summary['arms']['fork'][field]} |")
    for state in ("request_failure", "missing", "ambiguous", "invalid_result"):
        lines.append(f"| {state} | {summary['arms']['upstream']['states'].get(state, 0)} | {summary['arms']['fork']['states'].get(state, 0)} |")
    lines += ["", f"Among {t['paired_http_responses']} pairs with HTTP responses: "
              f"{t['non_2xx_to_2xx']} changed from non-2xx to 2xx; {t['2xx_to_non_2xx']} changed from 2xx to non-2xx. "
              f"{t['different_status']} pairs changed status, {t['different_title']} changed title, "
              f"and {t['different_redirect_chain']} changed redirect status chain.", "",
              "| Upstream → fork | Count |", "| --- | ---: |"]
    for pair, count in summary["status_pairs"].items():
        lines.append(f"| {markdown_cell(pair)} | {count} |")
    latency = summary["latency"]
    lines += ["", "Latency: " + latency["selection"] + ".", "",
              f"Comparable pairs: {latency['pair_count']}. "
              f"Upstream median: {latency['upstream_median_seconds']} s. "
              f"Fork median: {latency['fork_median_seconds']} s. "
              f"Median paired delta (fork − upstream): {latency['paired_delta_fork_minus_upstream_median_seconds']} s.", "",
              "| Target | Upstream | Fork | Upstream title | Fork title | Changed fields |",
              "| --- | --- | --- | --- | --- | --- |"]
    differences = {x["id"]: x["fields"] for x in summary["differences"]}
    for a, b in zip(normalized["upstream"], normalized["fork"]):
        values = [a["url"], status_label(a), status_label(b), a["title"], b["title"], ", ".join(differences.get(a["id"], []))]
        lines.append("| " + " | ".join(markdown_cell(v) for v in values) + " |")
    lines += ["", "Interpretation:", ""] + ["- " + item for item in summary["interpretation"]]
    for arm in ARMS:
        process = metadata.get("arms", {}).get(arm, {})
        if process.get("exit_code") != 0 or process.get("timed_out"):
            lines += ["", f"**{arm}: process failure** (exit code {process.get('exit_code')}; "
                      f"timeout {process.get('timed_out', False)}). Check {arm}.stderr.log before interpreting missing targets."]
        diagnostic = summary["diagnostics"][arm]
        if diagnostic["invalid_json_lines"] or diagnostic["unmatched_records"]:
            lines += ["", f"**{arm}: parsing/matching diagnostics**: "
                      f"{len(diagnostic['invalid_json_lines'])} invalid JSON lines, "
                      f"{len(diagnostic['unmatched_records'])} unmatched records. See summary.json."]
    return "\n".join(lines) + "\n"


def write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def analyze_capture(capture, output):
    capture, output = Path(capture), Path(output)
    metadata = json.loads((capture / "metadata.json").read_text(encoding="utf-8"))
    expected = metadata.get("targets_sha256")
    if expected and sha256(capture / "targets.csv") != expected:
        raise ValueError("Target checksum differs from the capture metadata")
    targets = load_targets(capture / "targets.csv")
    normalized, diagnostics = {}, {}
    for arm in ARMS:
        expected_stdout = metadata.get("arms", {}).get(arm, {}).get("stdout_sha256")
        if expected_stdout and sha256(capture / (arm + ".jsonl")) != expected_stdout:
            raise ValueError(arm + " stdout checksum differs from the capture metadata")
        records, invalid = read_jsonl(capture / (arm + ".jsonl"))
        normalized[arm], unmatched = normalize(targets, records, metadata.get("arms", {}).get(arm, {}))
        diagnostics[arm] = {"invalid_json_lines": invalid, "unmatched_records": unmatched,
                            "raw_record_count": len(records)}
    summary = summarize(targets, normalized, metadata, diagnostics)
    columns = list(normalized["upstream"][0])
    with (output / "normalized.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["arm"] + columns)
        writer.writeheader()
        for arm in ARMS:
            for row in normalized[arm]:
                writer.writerow({"arm": arm, **{key: json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value for key, value in row.items()}})
    write_json(output / "summary.json", summary)
    (output / "report.md").write_text(markdown_report(summary, normalized, metadata), encoding="utf-8")
    return summary


def isolated_environment(output):
    home = output / "home"
    home.mkdir()
    temp = output / "tmp"
    temp.mkdir()
    # Allowlisted environment excludes proxies, tokens, PDCP credentials and user configs.
    env = {"PATH": os.defpath, "HOME": str(home), "USERPROFILE": str(home),
           "XDG_CONFIG_HOME": str(home / ".config"), "XDG_CACHE_HOME": str(home / ".cache"),
           "TMPDIR": str(temp), "TMP": str(temp), "TEMP": str(temp),
           "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "TZ": "UTC", "NO_COLOR": "1"}
    if "SYSTEMROOT" in os.environ:
        env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
    return env


def command_for(binary, arm, args, input_path, config_path):
    command = [str(binary), "-l", str(input_path), "-config", str(config_path),
               "-json", "-silent", "-duc", "-nfs", "-probe", "-sc", "-title", "-server",
               "-location", "-cl", "-ct", "-rt", "-irh", "-bp=300", "-hash", "sha256",
               "-rstr", "2097152", "-threads", str(args.threads), "-rate-limit", str(args.rate),
               "-timeout", str(args.timeout), "-retries", "0", "-random-agent=false"]
    if args.mode in ("matched", "native"):
        command += ["-H", "User-Agent: " + args.user_agent]
    if args.mode == "redirects":
        command += ["-fr", "-maxr", "3"]
    if args.mode == "native" and arm == "fork":
        command += ["-native-http"]
    return command


def capture_process(command, env, output, arm, timeout):
    started = utc_now()
    tick = time.monotonic()
    result = {"command": command, "started_at": started, "timed_out": False, "exit_code": None}
    with (output / (arm + ".jsonl")).open("wb") as stdout, (output / (arm + ".stderr.log")).open("wb") as stderr:
        try:
            child = subprocess.Popen(command, stdout=stdout, stderr=stderr, env=env, stdin=subprocess.DEVNULL)
            try:
                result["exit_code"] = child.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                result["timed_out"] = True
                child.kill()
                result["exit_code"] = child.wait()
            except KeyboardInterrupt:
                child.kill()
                child.wait()
                raise
        except OSError as error:
            result["launch_error"] = str(error)
    result["finished_at"] = utc_now()
    result["duration_seconds"] = time.monotonic() - tick
    result["stdout_sha256"] = sha256(output / (arm + ".jsonl"))
    result["stderr_sha256"] = sha256(output / (arm + ".stderr.log"))
    return result


def resolve_binary(value):
    path = Path(value).expanduser().resolve()
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError("Binary must be an executable file: " + str(path))
    return path


def run_benchmark(args):
    targets_path = Path(args.targets).expanduser().resolve()
    targets = load_targets(targets_path)
    binaries = {arm: resolve_binary(getattr(args, arm)) for arm in ARMS}
    output = Path(args.output).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(targets_path, output / "targets.csv")
    (output / "targets.txt").write_text("\n".join(t["url"] for t in targets) + "\n", encoding="utf-8")
    (output / "empty-config.yaml").write_text("{}\n", encoding="utf-8")
    env = isolated_environment(output)
    metadata = {"schema_version": 1, "started_at": utc_now(), "mode": args.mode, "round": args.round,
                "mode_description": {"defaults": "Deterministic baseline: upstream UA vs fork browser profile",
                                     "matched": "Same explicit User-Agent; transport/header behavior can still differ",
                                     "redirects": "Deterministic baseline with -maxr 3 (up to two followed redirects)",
                                     "native": "Both native transports with the same explicit User-Agent"}[args.mode],
                "targets_sha256": sha256(output / "targets.csv"), "target_count": len(targets),
                "script_sha256": sha256(Path(__file__)), "environment": env,
                "runtime": {"python": platform.python_version(), "platform": sys.platform,
                            "machine": platform.machine()},
                "environment_policy": "Allowlisted clean environment, isolated HOME/XDG, no inherited proxy or cloud credentials",
                "body_read_limit_bytes": 2097152, "initial_probe_rate_limit_per_second": args.rate,
                "threads": args.threads, "timeout_seconds": args.timeout, "retries": 0,
                "order": list(reversed(ARMS)) if args.reverse else list(ARMS), "binaries": {}, "arms": {}}
    for arm, binary in binaries.items():
        version = subprocess.run([str(binary), "-version"], capture_output=True, env=env, timeout=30, check=False)
        metadata["binaries"][arm] = {"path": str(binary), "sha256": sha256(binary),
                                     "version_command": [str(binary), "-version"], "version_exit_code": version.returncode,
                                     "version_stdout": version.stdout.decode("utf-8", errors="replace"),
                                     "version_stderr": version.stderr.decode("utf-8", errors="replace")}
    write_json(output / "metadata.json", metadata)
    multiplier = 4 if args.mode == "redirects" else 1
    process_timeout = args.process_timeout or max(120, len(targets) * (args.timeout * multiplier / args.threads + 1 / args.rate) + 60)
    metadata["process_timeout_seconds"] = process_timeout
    for arm in metadata["order"]:
        command = command_for(binaries[arm], arm, args, output / "targets.txt", output / "empty-config.yaml")
        metadata["arms"][arm] = capture_process(command, env, output, arm, process_timeout)
        write_json(output / "metadata.json", metadata)
    metadata["finished_at"] = utc_now()
    write_json(output / "metadata.json", metadata)
    summary = analyze_capture(output, output)
    print(str(output / "report.md"))
    return 2 if any(p["process"].get("exit_code") != 0 or p["process"].get("timed_out") for p in summary["arms"].values()) else 0


def positive_int(value):
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    run = commands.add_parser("run", help="Capture two low-rate HTTP probe runs and compare their outputs")
    for field in ("targets", "upstream", "fork", "output"):
        run.add_argument("--" + field, required=True)
    run.add_argument("--mode", choices=MODES, default="defaults")
    run.add_argument("--round", type=positive_int, default=1)
    run.add_argument("--rate", type=positive_int, default=3)
    run.add_argument("--threads", type=positive_int, default=3)
    run.add_argument("--timeout", type=positive_int, default=12)
    run.add_argument("--process-timeout", type=positive_int)
    run.add_argument("--reverse", action="store_true", help="Run fork first, then upstream (BA order)")
    run.add_argument("--user-agent", help="Required explicit common UA for matched/native modes")
    analyze = commands.add_parser("analyze", help="Analyze captured raw output without network requests")
    analyze.add_argument("--run", required=True, dest="capture")
    analyze.add_argument("--output", required=True, help="New directory; existing paths are rejected")
    args = parser.parse_args(argv)
    if args.action == "run" and args.mode in ("matched", "native") and not args.user_agent:
        parser.error("--user-agent is required for matched/native mode")
    if args.action == "run" and args.user_agent and any(c in args.user_agent for c in "\r\n"):
        parser.error("--user-agent must not contain line breaks")
    try:
        if args.action == "run":
            return run_benchmark(args)
        output = Path(args.output).expanduser().resolve()
        output.mkdir(parents=True, exist_ok=False)
        summary = analyze_capture(Path(args.capture).expanduser().resolve(), output)
        write_json(output / "analysis-source.json", {"capture": str(Path(args.capture).resolve()), "analyzed_at": utc_now(), "script_sha256": sha256(Path(__file__))})
        print(str(output / "report.md"))
        return 0
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        print("compare_httpx: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
