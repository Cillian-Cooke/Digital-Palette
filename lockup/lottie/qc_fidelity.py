#!/usr/bin/env python3
"""QC + headless player screenshots for Lottie vs plate."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

from build_lottie import (
    QC,
    EXPORT,
    classify,
    extract_frame,
    load_rgba,
    rasterize_shapes,
    CREAM_RGB,
    INK_RGB,
    MOUTH_DARK,
    MOUTH_TONGUE,
    build_segment,
)

MIN_IOU = {"cream": 0.97, "ink": 0.97, "alpha": 0.98}


def iou(a, b):
    u = np.logical_or(a, b).sum()
    return float(np.logical_and(a, b).sum()) / u if u else 1.0


def evaluate_extractors(frames: list[int]) -> dict:
    rows = []
    failed = []
    for n in frames:
        rgba = load_rgba(n)
        gt_cream, gt_ink, gt_cav, gt_tong, hole = classify(rgba)
        data = extract_frame(rgba)
        pr_cream = rasterize_shapes(data["cream"])
        pr_ink = rasterize_shapes(data["ink"])
        pr_mouth = rasterize_shapes(data["cavity"])
        pr_tong = rasterize_shapes(data["tongue"])
        gt_alpha = rgba[:, :, 3] > 100
        # cream underlay covers matte minus hole; predicted cream should cover that
        scores = {
            "cream": iou(gt_cream, pr_cream),
            "ink": iou(gt_ink, pr_ink),
            "alpha": iou(gt_alpha, pr_cream | pr_ink | pr_mouth | pr_tong),
        }
        # neck must not be a transparent band: cream should be single connected-ish underlay
        row = {"frame": n, **scores}
        rows.append(row)
        if any(scores[k] < MIN_IOU[k] for k in MIN_IOU):
            failed.append(row)
        # save pred
        pred = np.zeros((*gt_alpha.shape, 3), np.uint8)
        pred[pr_cream] = CREAM_RGB
        pred[pr_mouth] = MOUTH_DARK
        pred[pr_tong] = MOUTH_TONGUE
        pred[pr_ink] = INK_RGB
        if n in frames[:: max(1, len(frames)//6)] or n in (1, 121, 217, 340):
            Image.fromarray(pred).save(QC / f"pred_f{n:04d}.png")
    summary = {k: {"min": min(r[k] for r in rows), "mean": sum(r[k] for r in rows)/len(rows)} for k in MIN_IOU}
    return {"summary": summary, "failures": failed, "pass": not failed}


def export_stills(source_frames: list[int]):
    """One-frame Lotties for headless player screenshots."""
    EXPORT.mkdir(parents=True, exist_ok=True)
    paths = []
    for n in source_frames:
        data = build_segment(f"f{n:04d}", n, n)
        out = EXPORT / f"mascot_f{n:04d}_still.json"
        out.write_text(json.dumps(data, separators=(",", ":")))
        paths.append(out)
        print("still", out.name, f"{out.stat().st_size/1024:.0f}KB")
    return paths


def chrome_shot(url: str, out: Path, port: int = 8768):
    subprocess.run(
        [
            "google-chrome",
            "--headless=new",
            "--no-sandbox",
            "--disable-gpu",
            f"--window-size=1440,1440",
            "--virtual-time-budget=25000",
            f"--screenshot={out}",
            url,
        ],
        check=False,
        capture_output=True,
    )


def player_screenshots(source_frames: list[int], port: int = 8768):
    QC.mkdir(parents=True, exist_ok=True)
    here = Path(__file__).resolve().parent
    # ensure render_still.html exists
    html = here / "render_still.html"
    if not html.exists():
        html.write_text(
            """<!DOCTYPE html><html><body style="margin:0;background:#ff00ff">
<div id="c" style="width:1440px;height:1440px"></div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/lottie-web/5.12.2/lottie.min.js"></script>
<script>
(async()=>{
  const src=new URLSearchParams(location.search).get('src');
  const data=await (await fetch(src)).json();
  const anim=lottie.loadAnimation({container:document.getElementById('c'),renderer:'svg',loop:false,autoplay:false,animationData:data});
  await new Promise(r=>anim.addEventListener('DOMLoaded',r));
  anim.goToAndStop(0,true);
  await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
  document.title='READY';
})();
</script></body></html>"""
        )
    srv = subprocess.Popen(
        ["python3", "-m", "http.server", str(port), "--bind", "127.0.0.1"],
        cwd=str(here),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(0.5)
    try:
        export_stills(source_frames)
        for n in source_frames:
            url = f"http://127.0.0.1:{port}/render_still.html?src=export/mascot_f{n:04d}_still.json"
            out = QC / f"player_f{n:04d}.png"
            chrome_shot(url, out)
            print("shot", out.name, out.stat().st_size if out.exists() else 0)
            # compare vs plate magenta composite
            if out.exists() and out.stat().st_size > 20000:
                player = np.array(Image.open(out).convert("RGB"))[:1440, :1440]
                rgba = load_rgba(n)
                a = rgba[:, :, 3:4].astype(np.float32) / 255
                plate = (rgba[:, :, :3] * a + np.array([255, 0, 255]) * (1 - a)).astype(np.uint8)
                # transparent in player ≈ magenta
                pchar = ~((player[:, :, 0] > 240) & (player[:, :, 1] < 40) & (player[:, :, 2] > 240))
                gt = rgba[:, :, 3] > 100
                # mouth region check: plate has red, player should too when open
                mouth_gt = gt & (rgba[:, :, 0] > 100) & (rgba[:, :, 0] > rgba[:, :, 1] * 1.2)
                if mouth_gt.sum() > 200:
                    mouth_ok = (player[mouth_gt, 0] > player[mouth_gt, 1]).mean()
                else:
                    mouth_ok = 1.0
                # neck band: mid torso horizontal strip should be mostly opaque in player if opaque in gt
                neck = np.zeros_like(gt)
                neck[820:900, 600:840] = True
                neck_gt = gt & neck
                if neck_gt.sum() > 100:
                    neck_ok = pchar[neck_gt].mean()
                else:
                    neck_ok = 1.0
                pair = np.concatenate([plate, player], axis=1)
                Image.fromarray(pair).save(QC / f"compare_f{n:04d}.png")
                print(f"  f{n}: mouth_red_frac={mouth_ok:.3f} neck_opaque_frac={neck_ok:.3f} char={pchar.sum()}")
    finally:
        srv.terminate()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shots", action="store_true")
    ap.add_argument("--every", type=int, default=8)
    args = ap.parse_args()
    QC.mkdir(parents=True, exist_ok=True)

    heroes = [1, 49, 121, 145, 217, 288, 340, 361]
    frames = sorted(set(range(1, 362, args.every)) | set(heroes))
    rep = evaluate_extractors(frames)
    print(json.dumps(rep["summary"], indent=2))
    (QC / "fidelity_report.json").write_text(json.dumps(rep, indent=2))
    if not rep["pass"]:
        print("EXTRACTOR FAIL", rep["failures"][:10])
        sys.exit(1)
    print("EXTRACTOR PASS")

    if args.shots:
        player_screenshots(heroes)
    print("done")


if __name__ == "__main__":
    main()
