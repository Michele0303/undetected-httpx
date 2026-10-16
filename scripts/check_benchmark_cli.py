#!/usr/bin/env python3
"""Check benchmark CLI arguments against a loopback HTTP server, without public probes."""

from __future__ import annotations

import argparse
import hashlib
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
import tempfile
import threading
import time
from types import SimpleNamespace

from compare_httpx import command_for, isolated_environment, sha256


USER_AGENT = "httpx-cli-preflight/1.0"
REDIRECT_BODY = b"redirect"
FINAL_BODY = b"<title>Final</title>ok"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", required=True, type=Path)
    parser.add_argument("--fork", required=True, type=Path)
    args = parser.parse_args(argv)
    binaries = {arm: getattr(args, arm).expanduser().resolve() for arm in ("upstream", "fork")}
    hits = []
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_):
            pass

        def do_GET(self):
            with lock:
                hits.append({"path": self.path, "user_agent": self.headers.get("User-Agent"),
                             "time": time.monotonic()})
            redirect = self.path == "/start"
            body = REDIRECT_BODY if redirect else FINAL_BODY
            self.send_response(302 if redirect else 200)
            if redirect:
                self.send_header("Location", "/final")
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    results = []
    try:
        with tempfile.TemporaryDirectory(prefix="httpx-cli-preflight-") as temporary:
            directory = Path(temporary)
            env = isolated_environment(directory)
            config = directory / "empty-config.yaml"
            config.write_text("{}\n", encoding="utf-8")
            targets = directory / "targets.txt"

            def capture(arm, mode, urls):
                targets.write_text("\n".join(urls) + "\n", encoding="utf-8")
                options = SimpleNamespace(mode=mode, threads=3, rate=3, timeout=3,
                                          user_agent=USER_AGENT)
                command = command_for(binaries[arm], arm, options, targets, config)
                with lock:
                    hits.clear()
                started = time.monotonic()
                completed = subprocess.run(command, env=env, stdin=subprocess.DEVNULL,
                                           capture_output=True, text=True, timeout=30)
                elapsed = time.monotonic() - started
                if completed.returncode:
                    raise AssertionError(f"{arm}/{mode}: exit {completed.returncode}: {completed.stderr[-1000:]}")
                rows = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
                with lock:
                    observed = list(hits)
                return rows, observed, elapsed

            for mode in ("defaults", "matched", "redirects", "native"):
                for arm in binaries:
                    rows, observed, elapsed = capture(arm, mode, [base + "/start"])
                    assert len(rows) == 1, (arm, mode, "JSON row count", len(rows))
                    row = rows[0]
                    expected_status = 200 if mode == "redirects" else 302
                    expected_body = FINAL_BODY if mode == "redirects" else REDIRECT_BODY
                    expected_paths = ["/start", "/final"] if mode == "redirects" else ["/start"]
                    assert row.get("status_code") == expected_status, (arm, mode, "status", row)
                    assert row.get("hash", {}).get("body_sha256") == hashlib.sha256(expected_body).hexdigest(), (arm, mode, "missing or incorrect hash")
                    assert [hit["path"] for hit in observed] == expected_paths, (arm, mode, "paths", observed)
                    if mode == "redirects":
                        assert row.get("final_url") == base + "/final", (arm, mode, "final_url", row)
                        assert row.get("chain_status_codes") == [302, 200], (arm, mode, "chain", row)
                    if mode in ("matched", "native"):
                        assert all(hit["user_agent"] == USER_AGENT for hit in observed), (arm, mode, "UA", observed)
                    elif arm == "upstream":
                        assert all("httpx" in (hit["user_agent"] or "").lower() for hit in observed), (arm, mode, "non-deterministic UA", observed)
                    else:
                        assert all("Chrome/" in (hit["user_agent"] or "") for hit in observed), (arm, mode, "browser UA", observed)
                    results.append({"arm": arm, "mode": mode, "status": expected_status,
                                    "paths": expected_paths, "user_agent": observed[0]["user_agent"],
                                    "body_sha256": row["hash"]["body_sha256"],
                                    "duration_seconds": round(elapsed, 3)})

            for arm in binaries:
                rows, observed, elapsed = capture(arm, "defaults", [base + f"/rate/{i}" for i in range(12)])
                assert len(rows) == len(observed) == 12, (arm, "rate", len(rows), len(observed))
                span = observed[-1]["time"] - observed[0]["time"]
                assert span >= 2.5, (arm, "rate limit ignored", span)
                assert all(row.get("status_code") == 200 for row in rows), (arm, "rate statuses")
                results.append({"arm": arm, "mode": "rate", "requests": 12,
                                "request_span_seconds": round(span, 3),
                                "duration_seconds": round(elapsed, 3)})
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    print(json.dumps({"status": "pass", "network": "127.0.0.1 only",
                      "binaries": {arm: {"path": str(path), "sha256": sha256(path)}
                                   for arm, path in binaries.items()},
                      "checks": results}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
