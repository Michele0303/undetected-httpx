#!/usr/bin/env python3
"""Record live CLI executions with VHS; preserve unedited results and responses."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from compare_httpx import isolated_environment


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/demos/v2-live"
TOOLS = {"upstream": ("httpx", ROOT / "bin/httpx-upstream-v1.12.0"),
         "fork": ("undetected-httpx", ROOT / "bin/undetected-httpx")}
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36"


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def config_preflight():
    hits = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            hits.append((time.monotonic(), self.headers.get("User-Agent")))
            body = b"<title>Local control</title>ok"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    checks = {}
    try:
        for arm, (name, binary) in TOOLS.items():
            with tempfile.TemporaryDirectory(prefix="httpx-live-preflight-") as tmp:
                work = Path(tmp)
                shutil.copy2(SOURCE / "demo.yml", work / "demo.yml")
                (work / "list.txt").write_text("".join(f"http://127.0.0.1:{server.server_port}/{i}\n" for i in range(6)))
                hits.clear()
                result = subprocess.run([str(binary), "-l", "list.txt", "-sc", "-silent", "-config", "demo.yml"],
                                        cwd=work, env=isolated_environment(work), capture_output=True, text=True, timeout=30)
                rows = (work / "results.txt").read_text().splitlines() if (work / "results.txt").exists() else []
                if result.returncode or len(rows) != 6 or len(hits) != 6 or any(ua != UA for _, ua in hits):
                    raise RuntimeError(f"{arm}: config preflight failed: {result.stderr[-1000:]}")
                elapsed = hits[-1][0] - hits[0][0]
                if elapsed < 0.8 or not list((work / "responses").rglob("*.txt")):
                    raise RuntimeError(f"{arm}: rate limit or response storage not effective")
                checks[arm] = {"same_user_agent": True, "responses": len(rows), "first_to_last_request_seconds": elapsed}
    finally:
        server.shutdown()
        server.server_close()
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=SOURCE / "capture")
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    for name in ("vhs", "ffmpeg", "ttyd"):
        if not shutil.which(name):
            raise RuntimeError(f"Missing dependency: {name}")
    for tape in SOURCE.glob("*.tape"):
        subprocess.run(["vhs", "validate", str(tape)], cwd=SOURCE, check=True, capture_output=True, text=True)
    checks = config_preflight()
    print("Local config controls passed for both binaries", flush=True)
    if args.preflight_only:
        print(json.dumps(checks, indent=2))
        return
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    metadata = {"kind": "live-terminal-recording", "recorder": subprocess.check_output(["vhs", "--version"], text=True).strip(),
                "started_at": now(), "preflight": checks, "order": list(TOOLS), "arms": {},
                "script_sha256": sha(Path(__file__)), "config_sha256": sha(SOURCE / "demo.yml"),
                "input_sha256": sha(SOURCE / "list.txt"), "playback_speed": 1,
                "source_files": {f.name: sha(f) for f in SOURCE.glob("*.tape")},
                "environment": "Fresh HOME/XDG and allowlisted environment, no inherited proxies/accounts/cookies"}
    for arm, (name, binary) in TOOLS.items():
        destination = output / arm
        destination.mkdir()
        print(f"Recording real {name} requests", flush=True)
        with tempfile.TemporaryDirectory(prefix=f"httpx-live-{arm}-") as tmp:
            work = Path(tmp)
            env = isolated_environment(work)
            bin_dir = work / "bin"
            bin_dir.mkdir()
            (bin_dir / name).symlink_to(binary)
            dependency_dirs = dict.fromkeys(str(Path(shutil.which(tool)).parent) for tool in ("vhs", "ffmpeg", "ttyd", "bash"))
            env["PATH"] = ":".join([str(bin_dir), *dependency_dirs, env["PATH"]])
            env.pop("NO_COLOR", None)
            env["TERM"] = "xterm-256color"
            for filename in ("list.txt", "demo.yml", "style.tape", name + ".tape"):
                shutil.copy2(SOURCE / filename, work / filename)
            record = {"binary_sha256": sha(binary), "command": [name, "-l", "list.txt", "-sc", "-silent", "-config", "demo.yml"],
                      "started_at": now()}
            with (destination / "recorder.txt").open("w") as log:
                process = subprocess.run([shutil.which("vhs"), name + ".tape"], cwd=work, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=240)
            record.update({"finished_at": now(), "recorder_exit_code": process.returncode})
            for filename in (name + ".gif", name + ".mp4", "terminal.ascii", "final.png", "exit-code.txt", "results.txt", "demo.yml", "list.txt", "style.tape", name + ".tape"):
                if (work / filename).exists():
                    shutil.copy2(work / filename, destination / filename)
            if (work / "responses").exists():
                shutil.copytree(work / "responses", destination / "responses")
            exit_path = destination / "exit-code.txt"
            record["tool_exit_code"] = int(exit_path.read_text().strip()) if exit_path.exists() else None
            result_path = destination / "results.txt"
            lines = result_path.read_text().splitlines() if result_path.exists() else []
            plain = [re.sub(r"\x1b\[[0-9;]*m", "", line) for line in lines]
            record["results"] = plain
            record["files_sha256"] = {str(f.relative_to(destination)): sha(f) for f in destination.rglob("*") if f.is_file()}
            metadata["arms"][arm] = record
            (output / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
            if process.returncode or record["tool_exit_code"] != 0 or len(plain) != 5:
                raise RuntimeError(f"Incomplete capture for {name}; preserved evidence at {destination}")
    metadata["finished_at"] = now()
    (output / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(output, flush=True)


if __name__ == "__main__":
    main()
