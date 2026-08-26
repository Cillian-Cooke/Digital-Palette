#!/usr/bin/env python3
"""
Kling MOV → Lottie job runner.

Usage:
  lockup/source/.venv/bin/python lockup/lottie/convert_mov.py \\
    --mov /path/to/file.mov --job my_clip

See lockup/LOTTIE_RUNBOOK.md.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "source"
LOTTIE = ROOT / "lottie"
VENV_PY = SOURCE / ".venv" / "bin" / "python"


def ffmpeg_exe() -> str:
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def probe(mov: Path) -> dict:
    ff = ffmpeg_exe()
    r = subprocess.run([ff, "-i", str(mov)], capture_output=True, text=True)
    err = r.stderr
    info = {"raw": err, "w": None, "h": None, "fps": 24.0, "duration": None}
    for line in err.splitlines():
        line = line.strip()
        if "Video:" in line and "fps" in line:
            # e.g. 960x960, 2296 kb/s, 24 fps
            import re

            m = re.search(r"(\d{3,5})x(\d{3,5})", line)
            if m:
                info["w"], info["h"] = int(m.group(1)), int(m.group(2))
            m = re.search(r"([\d.]+)\s*fps", line)
            if m:
                info["fps"] = float(m.group(1))
        if line.startswith("Duration:"):
            # Duration: 00:00:07.04
            import re

            m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", line)
            if m:
                h, mi, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
                info["duration"] = h * 3600 + mi * 60 + s
    return info


def extract_frames(mov: Path, out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    for p in out_dir.glob("frame_*.png"):
        p.unlink()
    ff = ffmpeg_exe()
    cmd = [ff, "-y", "-i", str(mov), "-vsync", "0", str(out_dir / "frame_%04d.png")]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-2000:], file=sys.stderr)
        raise SystemExit(f"ffmpeg extract failed ({r.returncode})")
    return len(list(out_dir.glob("frame_*.png")))


def contact_sheet(raw: Path, refs: Path, n: int = 12) -> None:
    from PIL import Image

    refs.mkdir(parents=True, exist_ok=True)
    files = sorted(raw.glob("frame_*.png"))
    if not files:
        return
    step = max(1, len(files) // n)
    idxs = list(range(0, len(files), step))[:n]
    thumbs = [Image.open(files[i]).convert("RGB").resize((160, 160)) for i in idxs]
    cols = 6
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (160 * cols, 160 * rows), (20, 20, 20))
    for i, t in enumerate(thumbs):
        sheet.paste(t, ((i % cols) * 160, (i // cols) * 160))
    sheet.save(refs / "poses.png")


def detect_plate(raw: Path) -> str:
    """Return 'light' or 'black' from corner luminance."""
    from PIL import Image
    import numpy as np

    files = sorted(raw.glob("frame_*.png"))
    rgb = np.array(Image.open(files[0]).convert("RGB"))
    h, w, _ = rgb.shape
    corners = np.concatenate(
        [
            rgb[4:24, 4:24].reshape(-1, 3),
            rgb[4:24, w - 24 : w - 4].reshape(-1, 3),
            rgb[h - 24 : h - 4, 4:24].reshape(-1, 3),
            rgb[h - 24 : h - 4, w - 24 : w - 4].reshape(-1, 3),
        ],
        axis=0,
    )
    mean = corners.mean()
    return "light" if mean > 120 else "black"


def default_segments(n_frames: int) -> dict:
    """Simple thirds if no custom cuts — always include full."""
    a = max(1, n_frames // 3)
    b = max(a + 1, (2 * n_frames) // 3)
    return {
        "a": (1, a),
        "b": (a + 1, b),
        "full": (1, n_frames),
    }


def write_segments_md(job_dir: Path, mov: Path, info: dict, n: int, plate: str, segs: dict) -> None:
    lines = [
        f"# Segment table — job `{job_dir.name}`",
        "",
        f"Source: `mascot.mov` @ **{info.get('fps')} fps**, **{info.get('w')}×{info.get('h')}**, "
        f"**{n} frames**, **{info.get('duration')} s**",
        f"Original: `{mov}`",
        f"Plate: **{plate}**",
        "",
        "| Segment id | Start | End |",
        "|------------|-------|-----|",
    ]
    for sid, (a, b) in segs.items():
        lines.append(f"| `{sid}` | {a} | {b} |")
    lines.append("")
    (job_dir / "segments.md").write_text("\n".join(lines) + "\n")


def run_rebuild(job_dir: Path, plate: str) -> None:
    env = os.environ.copy()
    env["LOCKUP_JOB"] = str(job_dir)
    env["LOCKUP_PLATE"] = plate
    # Pass size for wipe scaling
    from PIL import Image

    sample = next((job_dir / "frames_raw").glob("frame_*.png"))
    im = Image.open(sample)
    env["LOCKUP_W"] = str(im.size[0])
    env["LOCKUP_H"] = str(im.size[1])
    r = subprocess.run(
        [str(VENV_PY), str(SOURCE / "rebuild_rgba.py")],
        cwd=str(SOURCE),
        env=env,
    )
    if r.returncode != 0:
        raise SystemExit("rebuild_rgba failed")


def run_build(job_dir: Path, export_dir: Path, w: int, h: int, fps: float, segs: dict) -> None:
    env = os.environ.copy()
    env["LOCKUP_JOB"] = str(job_dir)
    env["LOCKUP_EXPORT"] = str(export_dir)
    env["LOCKUP_W"] = str(w)
    env["LOCKUP_H"] = str(h)
    env["LOCKUP_FPS"] = str(fps)
    env["LOCKUP_SEGMENTS"] = json.dumps(segs)
    r = subprocess.run(
        [str(VENV_PY), str(LOTTIE / "build_lottie.py")],
        cwd=str(LOTTIE),
        env=env,
    )
    if r.returncode != 0:
        raise SystemExit("build_lottie failed")


def main():
    ap = argparse.ArgumentParser(description="Kling MOV → Lottie")
    ap.add_argument("--mov", required=True, type=Path)
    ap.add_argument("--job", required=True, help="short slug, e.g. thumbs_5829")
    ap.add_argument(
        "--segments",
        default="",
        help='JSON object {"idle":[1,56],"full":[1,169]} — default auto thirds + full',
    )
    args = ap.parse_args()
    mov = args.mov.expanduser().resolve()
    if not mov.exists():
        raise SystemExit(f"missing mov: {mov}")
    if not VENV_PY.exists():
        raise SystemExit(f"missing venv python: {VENV_PY}")

    job_dir = SOURCE / "jobs" / args.job
    raw = job_dir / "frames_raw"
    rgba = job_dir / "frames_rgba"
    refs = job_dir / "refs"
    export_dir = LOTTIE / "export" / args.job
    qc_dir = LOTTIE / "qc" / args.job
    job_dir.mkdir(parents=True, exist_ok=True)
    export_dir.mkdir(parents=True, exist_ok=True)
    qc_dir.mkdir(parents=True, exist_ok=True)

    dest_mov = job_dir / "mascot.mov"
    if dest_mov.resolve() != mov.resolve():
        shutil.copy2(mov, dest_mov)
    print(f"job {args.job} ← {mov}")

    info = probe(dest_mov)
    print(f"probe: {info['w']}x{info['h']} @ {info['fps']}fps, duration={info['duration']}")
    if not info["w"] or not info["h"]:
        raise SystemExit("could not probe width/height")

    n = extract_frames(dest_mov, raw)
    print(f"extracted {n} frames")
    contact_sheet(raw, refs)
    plate = detect_plate(raw)
    print(f"plate detected: {plate}")
    os.environ["LOCKUP_PLATE"] = plate

    if args.segments:
        raw_segs = json.loads(args.segments)
        segs = {k: (int(v[0]), int(v[1])) for k, v in raw_segs.items()}
        if "full" not in segs:
            segs["full"] = (1, n)
    else:
        segs = default_segments(n)
    write_segments_md(job_dir, mov, info, n, plate, segs)

    # Point active source dirs used by rebuild/build via env + symlink convenience
    # Also keep legacy SOURCE/frames_* in sync for scripts that hardcode paths
    for name, src in (("frames_raw", raw), ("frames_rgba", rgba)):
        link = SOURCE / name
        if link.is_symlink() or link.exists():
            if link.is_symlink():
                link.unlink()
            elif link.is_dir() and not any(link.iterdir()):
                link.rmdir()
            else:
                # leave existing data; rebuild writes via LOCKUP_JOB
                pass
        rgba.mkdir(parents=True, exist_ok=True)

    run_rebuild(job_dir, plate)
    run_build(job_dir, export_dir, info["w"], info["h"], info["fps"], segs)

    # QC traces for midpoints
    env = os.environ.copy()
    env["LOCKUP_JOB"] = str(job_dir)
    env["LOCKUP_EXPORT"] = str(export_dir)
    env["LOCKUP_W"] = str(info["w"])
    env["LOCKUP_H"] = str(info["h"])
    env["LOCKUP_FPS"] = str(info["fps"])
    env["LOCKUP_SEGMENTS"] = json.dumps(segs)
    mid = max(1, n // 2)
    subprocess.run(
        [
            str(VENV_PY),
            "-c",
            f"from build_lottie import write_qc_pair; write_qc_pair('full', {mid})",
        ],
        cwd=str(LOTTIE),
        env=env,
    )
    print(f"done → {export_dir}")
    print(f"preview: serve lockup/lottie and open export/{args.job}/mascot_full.json")


if __name__ == "__main__":
    main()
