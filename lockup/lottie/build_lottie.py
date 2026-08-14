#!/usr/bin/env python3
"""
1:1 RGBA → Lottie (player-safe).

Layer model (fixes transparent mouth/neck + broken playback):
  1. cream  — FULL character matte minus shackle hole only
              (eyes/mouth sit on cream; ink/mouth paint on top)
  2. mouth  — red cavity ∪ tongue (when open)
  3. ink    — black linework / eyes / outline / closed-mouth / creases

Paths resampled to a FIXED vertex count per slot (lottie-web requires this
even with hold keys). Hold keys @ source fps.
"""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
FRAMES = ROOT / "source" / "frames_rgba"
EXPORT = ROOT / "lottie" / "export"
QC = ROOT / "lottie" / "qc"

W = H = 1440
FPS = 24
SMALL_HOLE = 15000  # eyes/mouth-sized; larger = shackle
MIN_AREA = 20

# Fixed resample budgets (player-safe morph/hold)
CREAM_N = 256
HOLE_N = 128
INK_N = 192
MOUTH_N = 96
MAX_INK = 10
MAX_MOUTH = 4
MAX_HOLES = 6

SEGMENTS = {
    "intro": (1, 144),
    "wave": (145, 288),
    "sit": (289, 361),
    "full": (1, 361),
}

CREAM_RGB = [251, 244, 236]
INK_RGB = [5, 5, 5]
MOUTH_DARK = [140, 28, 28]
MOUTH_TONGUE = [220, 120, 120]


def load_rgba(n: int) -> np.ndarray:
    return np.array(Image.open(FRAMES / f"frame_{n:04d}.png").convert("RGBA"))


def shackle_hole(matte: np.ndarray) -> np.ndarray:
    """Large interior hole(s) in the opaque matte (= padlock shackle opening)."""
    inv = (~matte).astype(np.uint8) * 255
    ff = inv.copy()
    ffmask = np.zeros((ff.shape[0] + 2, ff.shape[1] + 2), np.uint8)
    cv2.floodFill(ff, ffmask, (0, 0), 64)
    holes = ff == 255
    num, labels, stats, _ = cv2.connectedComponentsWithStats(holes.astype(np.uint8), 8)
    out = np.zeros_like(matte)
    for i in range(1, num):
        if int(stats[i, cv2.CC_STAT_AREA]) > SMALL_HOLE:
            out[labels == i] = True
    return out


def classify(rgba: np.ndarray):
    rgb = rgba[:, :, :3].astype(np.float32)
    a = rgba[:, :, 3]
    lum = rgb.mean(axis=2)
    r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
    matte = a > 100
    mouth = matte & (r > 80) & (r > g * 1.25) & (r > b * 1.25) & (lum < 210)
    tongue = mouth & (lum >= 110)
    cavity = mouth & ~tongue
    ink = matte & (lum < 70) & ~mouth
    hole = shackle_hole(matte)
    # Cream underlay: everything opaque except shackle hole (no mouth/eye punch-outs)
    cream = matte & ~hole
    return cream, ink, cavity, tongue, hole


def resample_closed(pts: np.ndarray, n: int) -> np.ndarray:
    if len(pts) < 3:
        out = np.zeros((n, 2), dtype=np.float64)
        out[:, 0] = W / 2
        out[:, 1] = H / 2
        return out
    i0 = int(np.lexsort((pts[:, 0], pts[:, 1]))[0])
    pts = np.vstack([pts[i0:], pts[:i0]])
    closed = np.vstack([pts, pts[0]])
    d = np.sqrt(((closed[1:] - closed[:-1]) ** 2).sum(axis=1))
    s = np.concatenate([[0], np.cumsum(d)])
    total = float(s[-1])
    if total < 1e-6:
        return np.repeat(pts[:1], n, axis=0)
    targets = np.linspace(0, total, n, endpoint=False)
    out = np.zeros((n, 2), dtype=np.float64)
    j = 0
    for i, t in enumerate(targets):
        while j + 1 < len(s) and s[j + 1] < t:
            j += 1
        span = s[j + 1] - s[j]
        u = 0.0 if span < 1e-9 else (t - s[j]) / span
        out[i] = closed[j] * (1 - u) + closed[j + 1] * u
    return out


def contour_pts(cnt, n: int) -> np.ndarray | None:
    if cnt is None or cv2.contourArea(cnt) < MIN_AREA:
        return None
    # Light simplify then resample to fixed n (player-safe)
    peri = cv2.arcLength(cnt, True)
    approx = cv2.approxPolyDP(cnt, max(0.4, 0.0005 * peri), True)
    pts = approx.reshape(-1, 2).astype(np.float64)
    if len(pts) < 3:
        pts = cnt.reshape(-1, 2).astype(np.float64)
    return resample_closed(pts, n)


def ccomp_shapes(mask: np.ndarray, outer_n: int, hole_n: int, max_shapes: int) -> list[dict]:
    u8 = mask.astype(np.uint8) * 255
    # Bridge hairline gaps (neck crease must not split cream — cream is solid underlay)
    u8 = cv2.morphologyEx(u8, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    cnts, hier = cv2.findContours(u8, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    if not cnts or hier is None:
        return []
    hier = hier[0]
    roots = []
    for i, c in enumerate(cnts):
        if hier[i][3] != -1:
            continue
        area = cv2.contourArea(c)
        if area < MIN_AREA:
            continue
        roots.append((area, i, c))
    roots.sort(reverse=True)
    shapes = []
    for area, i, c in roots[:max_shapes]:
        outer = contour_pts(c, outer_n)
        if outer is None:
            continue
        holes = []
        child = hier[i][2]
        while child != -1 and len(holes) < MAX_HOLES:
            hp = contour_pts(cnts[child], hole_n)
            if hp is not None:
                holes.append(hp)
            child = hier[child][0]
        shapes.append({"outer": outer, "holes": holes, "area": area})
    return shapes


def pts_to_path(pts: np.ndarray) -> dict:
    v = [[float(round(x, 2)), float(round(y, 2))] for x, y in pts]
    z = [[0, 0]] * len(v)
    return {"i": z, "o": [h[:] for h in z], "v": v, "c": True}


def empty_path(n: int) -> dict:
    pts = np.zeros((n, 2))
    pts[:, 0] = W / 2
    pts[:, 1] = H / 2
    return pts_to_path(pts)


def path_hold_keys(paths: list[dict]) -> dict:
    if len(paths) == 1:
        return {"a": 0, "k": paths[0]}
    return {"a": 1, "k": [{"t": i, "s": [p], "h": 1} for i, p in enumerate(paths)]}


def opacity_keys(values: list[int]) -> dict:
    if all(v == values[0] for v in values):
        return {"a": 0, "k": values[0]}
    return {"a": 1, "k": [{"t": i, "s": [v], "h": 1} for i, v in enumerate(values)]}


def solid_fill(rgb, even_odd: bool = True) -> dict:
    return {
        "ty": "fl",
        "c": {"a": 0, "k": [rgb[0] / 255, rgb[1] / 255, rgb[2] / 255, 1]},
        "o": {"a": 0, "k": 100},
        "r": 2 if even_odd else 1,
    }


def tr(opacity=None) -> dict:
    return {
        "ty": "tr",
        "p": {"a": 0, "k": [0, 0]},
        "a": {"a": 0, "k": [0, 0]},
        "s": {"a": 0, "k": [100, 100]},
        "r": {"a": 0, "k": 0},
        "o": opacity if opacity is not None else {"a": 0, "k": 100},
        "sk": {"a": 0, "k": 0},
        "sa": {"a": 0, "k": 0},
    }


def extract_frame(rgba: np.ndarray) -> dict:
    cream, ink, cavity, tongue, hole = classify(rgba)
    mouth = cavity | tongue
    if mouth.any():
        mouth = cv2.morphologyEx(mouth.astype(np.uint8) * 255, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8)) > 0
        tongue = tongue & mouth

    # Cream underlay: EXTERNAL silhouette only + explicit shackle hole(s).
    # Never take CCOMP holes from cream (those punched mouth/eyes → transparent).
    u8 = cream.astype(np.uint8) * 255
    u8 = cv2.morphologyEx(u8, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    cnts, _ = cv2.findContours(u8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    cream_shapes = []
    if cnts:
        c = max(cnts, key=cv2.contourArea)
        outer = contour_pts(c, CREAM_N)
        if outer is not None:
            holes = []
            if hole.any():
                for hs in ccomp_shapes(hole, HOLE_N, HOLE_N, max_shapes=2):
                    holes.append(hs["outer"])
            cream_shapes.append({"outer": outer, "holes": holes, "area": float(cv2.contourArea(c))})

    return {
        "cream": cream_shapes,
        "ink": ccomp_shapes(ink, INK_N, HOLE_N, MAX_INK),
        "cavity": ccomp_shapes(mouth, MOUTH_N, MOUTH_N // 2, MAX_MOUTH),
        "tongue": ccomp_shapes(tongue, MOUTH_N, MOUTH_N // 2, MAX_MOUTH),
    }


def rasterize_shapes(shapes: list[dict]) -> np.ndarray:
    mask = np.zeros((H, W), np.uint8)
    for sh in shapes:
        polys = [sh["outer"].astype(np.int32).reshape(-1, 1, 2)]
        for h in sh["holes"]:
            polys.append(h.astype(np.int32).reshape(-1, 1, 2))
        cv2.fillPoly(mask, polys, 255)
    return mask > 0


def rasterize_classify(cream, ink, cavity, tongue) -> np.ndarray:
    out = np.zeros((H, W, 3), np.uint8)
    out[cream] = CREAM_RGB
    out[cavity] = MOUTH_DARK
    out[tongue] = MOUTH_TONGUE
    out[ink] = INK_RGB
    return out


def slots_from_frames(frames: list[dict], kind: str, max_shapes: int, outer_n: int, hole_n: int):
    max_holes = 0
    for fd in frames:
        for sh in fd[kind][:max_shapes]:
            max_holes = max(max_holes, len(sh["holes"]))
    max_holes = min(max_holes, MAX_HOLES)

    slots = []
    for s in range(max_shapes):
        outer, opacity = [], []
        holes = [[] for _ in range(max_holes)]
        any_on = False
        for fd in frames:
            shapes = fd[kind]
            if s < len(shapes):
                sh = shapes[s]
                # enforce fixed counts
                outer.append(pts_to_path(resample_closed(sh["outer"], outer_n)))
                opacity.append(100)
                any_on = True
                for hi in range(max_holes):
                    if hi < len(sh["holes"]):
                        holes[hi].append(pts_to_path(resample_closed(sh["holes"][hi], hole_n)))
                    else:
                        holes[hi].append(empty_path(hole_n))
            else:
                outer.append(empty_path(outer_n))
                opacity.append(0)
                for hi in range(max_holes):
                    holes[hi].append(empty_path(hole_n))
        if any_on:
            slots.append({"outer": outer, "holes": holes, "opacity": opacity})
    return slots


def groups_from_slots(slots: list[dict], rgb, prefix: str) -> list[dict]:
    groups = []
    for i, slot in enumerate(slots):
        items = [{"ty": "sh", "nm": f"{prefix}_{i}_o", "ks": path_hold_keys(slot["outer"])}]
        for hi, series in enumerate(slot["holes"]):
            items.append({"ty": "sh", "nm": f"{prefix}_{i}_h{hi}", "ks": path_hold_keys(series)})
        items.append(solid_fill(rgb, even_odd=True))
        items.append(tr(opacity_keys(slot["opacity"])))
        groups.append({"ty": "gr", "nm": f"{prefix}_{i}", "it": items})
    return groups


def make_layer(name: str, index: int, groups: list[dict], ip: int, op: int) -> dict:
    return {
        "ddd": 0,
        "ind": index,
        "ty": 4,
        "nm": name,
        "sr": 1,
        "ks": {
            "o": {"a": 0, "k": 100},
            "r": {"a": 0, "k": 0},
            "p": {"a": 0, "k": [0, 0, 0]},
            "a": {"a": 0, "k": [0, 0, 0]},
            "s": {"a": 0, "k": [100, 100, 100]},
        },
        "ao": 0,
        "shapes": groups,
        "ip": ip,
        "op": op,
        "st": 0,
        "bm": 0,
    }


def build_segment(seg_id: str, start: int, end: int) -> dict:
    print(f"tracing {seg_id} {start}-{end}…")
    frames = []
    for n in range(start, end + 1):
        frames.append(extract_frame(load_rgba(n)))
        if (n - start) % 40 == 0:
            print(f"  … {n}")

    cream = slots_from_frames(frames, "cream", 2, CREAM_N, HOLE_N)
    ink = slots_from_frames(frames, "ink", MAX_INK, INK_N, HOLE_N)
    cavity = slots_from_frames(frames, "cavity", MAX_MOUTH, MOUTH_N, MOUTH_N // 2)
    tongue = slots_from_frames(frames, "tongue", MAX_MOUTH, MOUTH_N, MOUTH_N // 2)

    ip, op = 0, end - start + 1
    layers = [
        make_layer("ink", 1, groups_from_slots(ink, INK_RGB, "ink"), ip, op),
        make_layer("tongue", 2, groups_from_slots(tongue, MOUTH_TONGUE, "tongue"), ip, op),
        make_layer("cavity", 3, groups_from_slots(cavity, MOUTH_DARK, "cavity"), ip, op),
        make_layer("cream", 4, groups_from_slots(cream, CREAM_RGB, "cream"), ip, op),
    ]
    return {
        "v": "5.7.4",
        "fr": FPS,
        "ip": ip,
        "op": op,
        "w": W,
        "h": H,
        "nm": f"mascot_{seg_id}",
        "ddd": 0,
        "assets": [],
        "layers": layers,
        "markers": [],
    }


def write_qc_pair(seg_id: str, mid: int):
    rgba = load_rgba(mid)
    cream, ink, cavity, tongue, _ = classify(rgba)
    data = extract_frame(rgba)
    pred = np.zeros((H, W, 3), np.uint8)
    pred[rasterize_shapes(data["cream"])] = CREAM_RGB
    pred[rasterize_shapes(data["cavity"])] = MOUTH_DARK
    pred[rasterize_shapes(data["tongue"])] = MOUTH_TONGUE
    pred[rasterize_shapes(data["ink"])] = INK_RGB
    a = rgba[:, :, 3:4].astype(np.float32) / 255
    yy, xx = np.mgrid[0:H, 0:W]
    checker = np.where(((xx // 32) + (yy // 32)) % 2 == 0, 220, 180).astype(np.uint8)
    checker = np.dstack([checker] * 3)
    plate = (rgba[:, :, :3] * a + checker * (1 - a)).astype(np.uint8)
    QC.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.concatenate([plate, pred], axis=1)).save(QC / f"{seg_id}_f{mid:04d}_trace.png")


def main():
    EXPORT.mkdir(parents=True, exist_ok=True)
    QC.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Mascot Lottie exports",
        "",
        "Player-safe 1:1: solid cream underlay (shackle hole only) + mouth + ink.",
        "Fixed vertex counts per slot; held keys @ 24fps.",
        "",
        "| File | Frames |",
        "|------|--------|",
    ]
    for seg_id, (a, b) in SEGMENTS.items():
        data = build_segment(seg_id, a, b)
        if seg_id == "full":
            data["markers"] = [
                {"tm": 0, "cm": "intro", "dr": 144},
                {"tm": 144, "cm": "wave", "dr": 144},
                {"tm": 288, "cm": "sit", "dr": 73},
            ]
        out = EXPORT / f"mascot_{seg_id}.json"
        out.write_text(json.dumps(data, separators=(",", ":")))
        print(f"wrote {out.name} ({out.stat().st_size/1024:.0f} KB)")
        lines.append(f"| `{out.name}` | {a}–{b} |")
        write_qc_pair(seg_id, (a + b) // 2)
    (EXPORT / "README.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
