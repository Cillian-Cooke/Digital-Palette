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
import os
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
_JOB = Path(os.environ["LOCKUP_JOB"]) if os.environ.get("LOCKUP_JOB") else ROOT / "source"
FRAMES = _JOB / "frames_rgba"
EXPORT = Path(os.environ["LOCKUP_EXPORT"]) if os.environ.get("LOCKUP_EXPORT") else ROOT / "lottie" / "export"
QC = ROOT / "lottie" / "qc"
if os.environ.get("LOCKUP_JOB"):
    QC = ROOT / "lottie" / "qc" / Path(os.environ["LOCKUP_JOB"]).name

W = int(os.environ.get("LOCKUP_W", "960"))
H = int(os.environ.get("LOCKUP_H", "960"))
FPS = float(os.environ.get("LOCKUP_FPS", "24"))
SMALL_HOLE = int(os.environ.get("LOCKUP_SMALL_HOLE", str(int(7000 * (W / 960) * (H / 960)))))
MIN_AREA = 12

# Fixed resample budgets (player-safe morph/hold) — higher = tighter plate match
CREAM_N = 320
HOLE_N = 160
INK_N = 256
MOUTH_N = 128
MAX_INK = 10
MAX_MOUTH = 4
MAX_HOLES = 6
MAX_INK_HOLES = 6  # body outline can enclose several interior loops

if os.environ.get("LOCKUP_SEGMENTS"):
    _raw = json.loads(os.environ["LOCKUP_SEGMENTS"])
    SEGMENTS = {k: (int(v[0]), int(v[1])) for k, v in _raw.items()}
else:
    # 169 frames @ 24fps (~7.04s): idle → thumbs-up → idle  (job thumbs_5829 defaults)
    SEGMENTS = {
        "idle": (1, 56),
        "thumbs": (57, 140),
        "full": (1, 169),
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
        return np.full((n, 2), -10.0, dtype=np.float64)
    # Canonical start (top-most, then left) + CCW winding for first sample only;
    # temporal align_to_prev() re-phases later frames.
    i0 = int(np.lexsort((pts[:, 0], pts[:, 1]))[0])
    pts = np.vstack([pts[i0:], pts[:i0]])
    if _shoelace(pts) < 0:
        pts = pts[::-1]
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


def _shoelace(pts: np.ndarray) -> float:
    x, y = pts[:, 0], pts[:, 1]
    return float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y) * 0.5)


def align_to_prev(prev: np.ndarray | None, curr: np.ndarray, max_mean: float = 55.0) -> np.ndarray:
    """Cyclic-shift (+ optional reverse) so vertex i tracks the same feature."""
    if prev is None or len(prev) != len(curr):
        return curr
    n = len(curr)
    best, best_cost = curr, 1e99
    for rev in (False, True):
        base = curr[::-1] if rev else curr
        for s in range(n):
            rolled = np.roll(base, s, axis=0)
            cost = float(np.linalg.norm(rolled - prev, axis=1).mean())
            if cost < best_cost:
                best_cost = cost
                best = rolled
    # Refuse align when correspondence is nonsense (wrong slot match)
    if best_cost > max_mean:
        return curr
    return best


def _centroid(pts: np.ndarray) -> np.ndarray:
    return pts.mean(axis=0)


def _match_indices(
    prev_cents: list[np.ndarray | None],
    curr_cents: list[np.ndarray],
    max_dist: float,
    prev_areas: list[float | None] | None = None,
    curr_areas: list[float] | None = None,
) -> list[int | None]:
    """Greedy match by centroid (+ area) so big outlines don't steal tiny creases."""
    used = set()
    out: list[int | None] = [None] * len(prev_cents)
    pairs = []
    for pi, pc in enumerate(prev_cents):
        if pc is None:
            continue
        pa = (prev_areas[pi] if prev_areas else None) or 1.0
        for ci, cc in enumerate(curr_cents):
            dist = float(np.linalg.norm(pc - cc))
            ca = (curr_areas[ci] if curr_areas else None) or 1.0
            area_pen = abs(np.log(max(pa, 1.0)) - np.log(max(ca, 1.0))) * 50.0
            pairs.append((dist + area_pen, dist, area_pen, pi, ci))
    pairs.sort()
    for _score, dist, area_pen, pi, ci in pairs:
        if out[pi] is not None or ci in used:
            continue
        if dist > max_dist or area_pen > 90.0:
            continue
        out[pi] = ci
        used.add(ci)
    return out


def contour_pts(cnt, n: int, min_area: float | None = None) -> np.ndarray | None:
    floor = MIN_AREA if min_area is None else min_area
    if cnt is None or cv2.contourArea(cnt) < floor:
        return None
    peri = cv2.arcLength(cnt, True)
    approx = cv2.approxPolyDP(cnt, max(0.2, 0.0002 * peri), True)
    pts = approx.reshape(-1, 2).astype(np.float64)
    if len(pts) < 3:
        pts = cnt.reshape(-1, 2).astype(np.float64)
    return resample_closed(pts, n)


def ccomp_shapes(
    mask: np.ndarray,
    outer_n: int,
    hole_n: int,
    max_shapes: int,
    max_holes: int | None = None,
    min_area: float | None = None,
) -> list[dict]:
    hole_cap = MAX_HOLES if max_holes is None else max_holes
    area_floor = MIN_AREA if min_area is None else min_area
    u8 = mask.astype(np.uint8) * 255
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
        if area < area_floor:
            continue
        roots.append((area, i, c))
    roots.sort(reverse=True)
    shapes = []
    for area, i, c in roots[:max_shapes]:
        outer = contour_pts(c, outer_n, min_area=area_floor)
        if outer is None:
            continue
        holes = []
        child = hier[i][2]
        while child != -1 and len(holes) < hole_cap:
            hp = contour_pts(cnts[child], hole_n, min_area=area_floor)
            if hp is not None:
                holes.append(hp)
            child = hier[child][0]
        shapes.append({"outer": outer, "holes": holes, "area": float(area)})
    return shapes


def pts_to_path(pts: np.ndarray) -> dict:
    # 0.1px grid @ 960 — visually lossless, helps identical-frame sparsify
    v = [[float(round(x, 1)), float(round(y, 1))] for x, y in pts]
    z = [[0, 0]] * len(v)
    return {"i": z, "o": [h[:] for h in z], "v": v, "c": True}


def empty_pts(n: int) -> np.ndarray:
    """Collapsed path outside the artboard — zero area, no even-odd punch."""
    return np.full((n, 2), -10.0, dtype=np.float64)


def empty_path(n: int) -> dict:
    return pts_to_path(empty_pts(n))


def path_hold_keys(paths: list[dict], eps: float = 0.5) -> dict:
    """Hold keys only when path moves > eps px — drops contour jitter, same look."""
    if len(paths) == 1:
        return {"a": 0, "k": paths[0]}

    def close(a: dict, b: dict) -> bool:
        va, vb = a["v"], b["v"]
        if len(va) != len(vb):
            return False
        for (x0, y0), (x1, y1) in zip(va, vb):
            if abs(x0 - x1) > eps or abs(y0 - y1) > eps:
                return False
        return True

    if all(close(p, paths[0]) for p in paths):
        return {"a": 0, "k": paths[0]}
    keys = []
    prev = None
    for i, p in enumerate(paths):
        if prev is None or not close(p, prev):
            keys.append({"t": i, "s": [p], "h": 1})
            prev = p
    return {"a": 1, "k": keys}



def opacity_keys(values: list[int]) -> dict:
    if all(v == values[0] for v in values):
        return {"a": 0, "k": values[0]}
    keys = []
    prev = None
    for i, v in enumerate(values):
        if prev is None or v != prev:
            keys.append({"t": i, "s": [v], "h": 1})
            prev = v
    return {"a": 1, "k": keys}


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


def enrich_ink(ink: np.ndarray, rgba: np.ndarray, mouth: np.ndarray) -> np.ndarray:
    """Pull in antialias fringe around hard ink so outlines match the plate."""
    rgb = rgba[:, :, :3].astype(np.float32)
    a = rgba[:, :, 3] > 100
    lum = rgb.mean(axis=2)
    near = cv2.dilate(ink.astype(np.uint8) * 255, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))) > 0
    soft = ink | (a & near & (lum < 120) & ~mouth)
    soft = cv2.morphologyEx(soft.astype(np.uint8) * 255, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8)) > 0
    return soft


def prepare_mouth(mouth: np.ndarray) -> np.ndarray:
    """Grow speck openings only (<40px) so they contour; leave normal mouths alone."""
    if not mouth.any():
        return mouth
    area = int(mouth.sum())
    if area >= 40:
        return (
            cv2.morphologyEx(mouth.astype(np.uint8) * 255, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8)) > 0
        )
    m = cv2.dilate(mouth.astype(np.uint8) * 255, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    return m > 0


def extract_frame(rgba: np.ndarray) -> dict:
    cream, ink, cavity, tongue, hole = classify(rgba)
    mouth = cavity | tongue
    mouth = prepare_mouth(mouth)
    if mouth.any():
        # re-split tongue after grow
        rgb = rgba[:, :, :3].astype(np.float32)
        lum = rgb.mean(axis=2)
        tongue = mouth & (lum >= 110)
        cavity = mouth & ~tongue
    else:
        cavity = mouth
        tongue = mouth

    ink = enrich_ink(ink, rgba, mouth)

    # Cream underlay: EXTERNAL silhouette only + explicit shackle hole(s).
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
                for hs in ccomp_shapes(hole, HOLE_N, HOLE_N, max_shapes=2, max_holes=1):
                    holes.append(hs["outer"])
            cream_shapes.append({"outer": outer, "holes": holes, "area": float(cv2.contourArea(c))})

    return {
        "cream": cream_shapes,
        "ink": ccomp_shapes(ink, INK_N, HOLE_N, MAX_INK, max_holes=MAX_INK_HOLES),
        "cavity": ccomp_shapes(cavity, MOUTH_N, MOUTH_N // 2, MAX_MOUTH, max_holes=1, min_area=4),
        "tongue": ccomp_shapes(tongue, MOUTH_N, MOUTH_N // 2, MAX_MOUTH, max_holes=1, min_area=4),
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


def slots_from_frames(
    frames: list[dict],
    kind: str,
    max_shapes: int,
    outer_n: int,
    hole_n: int,
    hole_cap: int | None = None,
):
    """Build temporally stable shape slots: centroid+area track + path phase-align."""
    cap = MAX_HOLES if hole_cap is None else hole_cap
    max_holes = 0
    for fd in frames:
        for sh in fd[kind][:max_shapes]:
            max_holes = max(max_holes, len(sh["holes"]))
    max_holes = min(max_holes, cap)

    outers: list[list[dict]] = [[] for _ in range(max_shapes)]
    opacities: list[list[int]] = [[] for _ in range(max_shapes)]
    holes_buf: list[list[list[dict]]] = [[[] for _ in range(max_holes)] for _ in range(max_shapes)]
    slot_used = [False] * max_shapes

    prev_outer: list[np.ndarray | None] = [None] * max_shapes
    prev_cent: list[np.ndarray | None] = [None] * max_shapes
    prev_area: list[float | None] = [None] * max_shapes
    prev_holes: list[list[np.ndarray | None]] = [[None] * max_holes for _ in range(max_shapes)]
    prev_hole_cent: list[list[np.ndarray | None]] = [[None] * max_holes for _ in range(max_shapes)]

    match_r = 0.35 * min(W, H)

    for fd in frames:
        shapes = list(fd[kind][:max_shapes])
        cents = [_centroid(sh["outer"]) for sh in shapes]
        areas = [float(sh.get("area") or 1.0) for sh in shapes]
        assign = _match_indices(prev_cent, cents, match_r, prev_area, areas)

        slot_to_shape: list[int | None] = [None] * max_shapes
        taken_shapes = set()
        for si, ci in enumerate(assign):
            if ci is not None:
                slot_to_shape[si] = ci
                taken_shapes.add(ci)

        free_slots = [i for i in range(max_shapes) if slot_to_shape[i] is None]
        for ci, sh in enumerate(shapes):
            if ci in taken_shapes:
                continue
            if not free_slots:
                break
            slot_to_shape[free_slots.pop(0)] = ci

        for si in range(max_shapes):
            ci = slot_to_shape[si]
            if ci is None:
                if prev_outer[si] is not None:
                    outers[si].append(pts_to_path(prev_outer[si]))
                else:
                    outers[si].append(empty_path(outer_n))
                opacities[si].append(0)
                for hi in range(max_holes):
                    if prev_holes[si][hi] is not None:
                        holes_buf[si][hi].append(pts_to_path(prev_holes[si][hi]))
                    else:
                        holes_buf[si][hi].append(empty_path(hole_n))
                continue

            sh = shapes[ci]
            outer = resample_closed(sh["outer"], outer_n)
            outer = align_to_prev(prev_outer[si], outer)
            outers[si].append(pts_to_path(outer))
            opacities[si].append(100)
            slot_used[si] = True
            prev_outer[si] = outer
            prev_cent[si] = _centroid(outer)
            prev_area[si] = float(sh.get("area") or 1.0)

            h_pts = [resample_closed(h, hole_n) for h in sh["holes"][:max_holes]]
            h_cents = [_centroid(h) for h in h_pts]
            h_areas = [float(max(1.0, abs(_shoelace(h)))) for h in h_pts]
            h_assign = _match_indices(prev_hole_cent[si], h_cents, match_r, None, h_areas)
            hole_to: list[int | None] = [None] * max_holes
            taken_h = set()
            for hi, hj in enumerate(h_assign):
                if hj is not None:
                    hole_to[hi] = hj
                    taken_h.add(hj)
            free_h = [i for i in range(max_holes) if hole_to[i] is None]
            for hj in range(len(h_pts)):
                if hj in taken_h:
                    continue
                if not free_h:
                    break
                hole_to[free_h.pop(0)] = hj

            for hi in range(max_holes):
                hj = hole_to[hi]
                if hj is None:
                    pts = empty_pts(hole_n)
                    holes_buf[si][hi].append(pts_to_path(pts))
                    prev_holes[si][hi] = pts
                else:
                    hp = align_to_prev(prev_holes[si][hi], h_pts[hj])
                    holes_buf[si][hi].append(pts_to_path(hp))
                    prev_holes[si][hi] = hp
                    prev_hole_cent[si][hi] = _centroid(hp)

    slots = []
    for si in range(max_shapes):
        if not slot_used[si]:
            continue
        slots.append(
            {
                "outer": outers[si],
                "holes": holes_buf[si],
                "opacity": opacities[si],
            }
        )
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

    cream = slots_from_frames(frames, "cream", 2, CREAM_N, HOLE_N, hole_cap=2)
    ink = slots_from_frames(frames, "ink", MAX_INK, INK_N, HOLE_N, hole_cap=MAX_INK_HOLES)
    cavity = slots_from_frames(frames, "cavity", MAX_MOUTH, MOUTH_N, MOUTH_N // 2, hole_cap=1)
    tongue = slots_from_frames(frames, "tongue", MAX_MOUTH, MOUTH_N, MOUTH_N // 2, hole_cap=1)

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
    import gzip
    import zipfile

    EXPORT.mkdir(parents=True, exist_ok=True)
    QC.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Mascot Lottie exports",
        "",
        "Player-safe 1:1: solid cream underlay (shackle hole only) + mouth + ink.",
        "Fixed vertex counts; hold keys sparsified (±0.5px) @ source fps.",
        "Paths phase-aligned + centroid-tracked across frames (reduces flicker).",
        "Also writes `.json.gz` and `.lottie` (zipped) — same pixels, smaller download.",
        "",
        "| File | Frames | JSON | gzip |",
        "|------|--------|------|------|",
    ]
    for seg_id, (a, b) in SEGMENTS.items():
        data = build_segment(seg_id, a, b)
        if seg_id == "full" and len(SEGMENTS) > 1:
            markers = []
            t = 0
            for mid, (aa, bb) in SEGMENTS.items():
                if mid == "full":
                    continue
                dr = bb - aa + 1
                markers.append({"tm": t, "cm": mid, "dr": dr})
                t += dr
            data["markers"] = markers
        raw = json.dumps(data, separators=(",", ":")).encode("utf-8")
        out = EXPORT / f"mascot_{seg_id}.json"
        out.write_bytes(raw)
        gz = EXPORT / f"mascot_{seg_id}.json.gz"
        with gzip.open(gz, "wb", compresslevel=9) as f:
            f.write(raw)
        lot = EXPORT / f"mascot_{seg_id}.lottie"
        with zipfile.ZipFile(lot, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            z.writestr(
                "manifest.json",
                json.dumps(
                    {
                        "version": "1",
                        "generator": "digital-palette-lockup",
                        "animations": [{"id": "main", "speed": 1}],
                    },
                    separators=(",", ":"),
                ),
            )
            z.writestr("animations/main.json", raw)
        print(
            f"wrote {out.name} ({out.stat().st_size/1024:.0f} KB)  "
            f"gz={gz.stat().st_size/1024:.0f} KB  lottie={lot.stat().st_size/1024:.0f} KB"
        )
        lines.append(
            f"| `mascot_{seg_id}.*` | {a}–{b} | {out.stat().st_size/1024:.0f} KB | {gz.stat().st_size/1024:.0f} KB |"
        )
        write_qc_pair(seg_id, (a + b) // 2)
    (EXPORT / "README.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
