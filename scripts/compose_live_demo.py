#!/usr/bin/env python3
"""Place the two unchanged VHS recordings side by side, with labels."""

import argparse
import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def probe(path):
    return json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration:stream=width,height,r_frame_rate,codec_name",
        "-of", "json", str(path)], text=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, default=ROOT / "docs/demos/v2-live/capture")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/demos/v2-live")
    parser.add_argument("--font", type=Path, default=Path("/System/Library/Fonts/Menlo.ttc"))
    args = parser.parse_args()
    capture, output = args.capture.resolve(), args.output.resolve()
    metadata = json.loads((capture / "metadata.json").read_text())
    if not metadata.get("finished_at") or any(record["recorder_exit_code"] or record["tool_exit_code"]
                                              for record in metadata["arms"].values()):
        raise ValueError("Only complete, successful real recordings can be composed")
    inputs = [capture / "upstream/httpx.mp4", capture / "fork/undetected-httpx.mp4"]
    dimensions = [probe(path) for path in inputs]
    width, height = (dimensions[0]["streams"][0][key] for key in ("width", "height"))
    if any(item["streams"][0]["width"] != width or item["streams"][0]["height"] != height for item in dimensions):
        raise ValueError("Recording dimensions differ")
    durations = [float(item["format"]["duration"]) for item in dimensions]
    duration = max(durations)
    date = datetime.fromisoformat(metadata["started_at"]).strftime("%d %b %Y").upper()
    # Padding freezes only the already completed recording; output is never
    # retimed, reordered, replaced or selectively removed.
    output.mkdir(parents=True, exist_ok=True)
    labels = Image.new("RGBA", (width * 2, height + 112), (0, 0, 0, 0))
    draw = ImageDraw.Draw(labels)
    draw.rectangle((0, 0, width * 2, 67), fill="#11111b")
    draw.rectangle((0, height + 68, width * 2, height + 112), fill="#11111b")
    font = ImageFont.truetype(str(args.font), 30)
    draw.text((32, 20), "httpx v1.12.0", font=font, fill="#cdd6f4")
    draw.text((width + 32, 20), "undetected-httpx 2.0", font=font, fill="#a6e3a1")
    draw.text((32, height + 80), "LIVE REQUESTS  |  SAME USER-AGENT  |  SELECTED URLS  |  " + date,
              font=ImageFont.truetype(str(args.font), 20), fill="#a6adc8")
    labels_path = output / "labels.png"
    labels.save(labels_path)
    filters = (
        f"[0:v]setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration={duration-durations[0]:.3f}[u];"
        f"[1:v]setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration={duration-durations[1]:.3f}[f];"
        "[u][f]hstack=inputs=2:shortest=1,pad=iw:ih+112:0:68:color=0x11111b[pair];"
        "[pair][2:v]overlay=0:0:shortest=1[v]"
    )
    video = output / "comparison.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(inputs[0]), "-i", str(inputs[1]),
                    "-loop", "1", "-framerate", "25", "-i", str(labels_path),
                    "-filter_complex", filters, "-map", "[v]", "-t", str(duration), "-c:v", "libx264",
                    "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", str(video)], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(max(0, duration-1)), "-i", str(video),
                    "-frames:v", "1", str(output / "comparison-poster.png")], check=True)
    record = {"input_sha256": {str(path.relative_to(capture)): sha(path) for path in inputs},
              "capture_metadata_sha256": sha(capture / "metadata.json"), "durations_seconds": durations,
              "output": probe(video), "output_sha256": sha(video), "composer_sha256": sha(Path(__file__)),
              "edit": "Side-by-side labels; shorter completed clip held on its last frame. No execution-speed changes."}
    (output / "media.json").write_text(json.dumps(record, indent=2) + "\n")
    print(video)


if __name__ == "__main__":
    main()
