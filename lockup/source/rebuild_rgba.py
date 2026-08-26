#!/usr/bin/env python3
"""Rebuild frames_rgba from Kling plates.

Supports two plate types (set LOCKUP_PLATE=light|black, or auto from corners):

- **light** — ~#F0 gray BG (2026-08-26 thumbs 5829). Warm cream vs cool BG.
- **black** — studio black BG (2026-08-15 wave/sit; 2026-08-26 clip 5896).

See lockup/LOTTIE_RUNBOOK.md.
"""
from __future__ import annotations

import os
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

_JOB = Path(os.environ["LOCKUP_JOB"]) if os.environ.get("LOCKUP_JOB") else Path(__file__).resolve().parent
RAW = _JOB / "frames_raw"
RGBA = _JOB / "frames_rgba"
REFS = _JOB / "refs"

_W = int(os.environ.get("LOCKUP_W", "960"))
_H = int(os.environ.get("LOCKUP_H", "960"))
_sx, _sy = _W / 960.0, _H / 960.0

# Watermark wipe — scaled from 960 defaults; override with LOCKUP_WX0/WY0
WX0 = int(os.environ.get("LOCKUP_WX0", str(int(640 * _sx))))
WY0 = int(os.environ.get("LOCKUP_WY0", str(int(890 * _sy))))
WX1, WY1 = _W, _H

SMALL_HOLE = int(os.environ.get("LOCKUP_SMALL_HOLE", str(max(2000, int(7000 * _sx * _sy)))))
MIN_BODY = 200
CREASE_CLOSE = max(5, int(round(15 * _sx)) | 1)
# Unified outer stroke for both plate types (~8px visual @ 960 → kernel 11)
OUTER_EDGE = max(5, int(round(11 * _sx)) | 1)
INK = (5, 5, 5)
CREAM = (251, 244, 236)

# Light-plate
BG_DIST = 10
WALK_DIST = 16
CREAM_WARM = 4

# Black-plate (lum 0–255)
CREAM_LUM = 100
DARK_LUM = 60


def detect_plate(rgb: np.ndarray) -> str:
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
    return "light" if float(corners.mean()) > 120 else "black"


def clean_components(mask: np.ndarray, min_area: int) -> np.ndarray:
    u8 = mask.astype(np.uint8) * 255
    u8 = cv2.morphologyEx(u8, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    u8 = cv2.morphologyEx(u8, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    num, labels, stats, _ = cv2.connectedComponentsWithStats((u8 > 0).astype(np.uint8), 8)
    out = np.zeros(mask.shape, bool)
    for i in range(1, num):
        if int(stats[i, cv2.CC_STAT_AREA]) >= min_area:
            out[labels == i] = True
    return out


def labeled_interior_holes(body: np.ndarray):
    inv = (~body).astype(np.uint8) * 255
    ff = inv.copy()
    ffmask = np.zeros((ff.shape[0] + 2, ff.shape[1] + 2), np.uint8)
    cv2.floodFill(ff, ffmask, (0, 0), 64)
    hole_bin = ff == 255
    num, labels, stats, _ = cv2.connectedComponentsWithStats(hole_bin.astype(np.uint8), 8)
    small = np.zeros(body.shape, bool)
    large = np.zeros(body.shape, bool)
    for i in range(1, num):
        if int(stats[i, cv2.CC_STAT_AREA]) <= SMALL_HOLE:
            small[labels == i] = True
        else:
            large[labels == i] = True
    return small, large


def paint_finish(rgb_u8, body, ink, mouth, shackle):
    keep = (body | ink | mouth) & ~shackle
    out = rgb_u8.copy()
    cream_mask = body & ~ink & ~mouth
    out[cream_mask] = CREAM
    out[ink] = INK
    alpha = np.where(keep, 255, 0).astype(np.uint8)
    alpha[WY0:WY1, WX0:WX1] = 0
    out[WY0:WY1, WX0:WX1] = 0
    out[alpha == 0] = 0
    return np.dstack([out, alpha])


def ink_and_creases(body, shackle, dark):
    face_ink = dark & body & ~shackle
    k_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (CREASE_CLOSE, CREASE_CLOSE))
    bridged = cv2.morphologyEx(body.astype(np.uint8) * 255, cv2.MORPH_CLOSE, k_close) > 0
    creases = bridged & ~body & ~shackle
    creases |= dark & bridged & ~body & ~shackle
    creases = (
        cv2.morphologyEx(creases.astype(np.uint8) * 255, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8)) > 0
    ) & bridged & ~body & ~shackle
    k_edge = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (OUTER_EDGE, OUTER_EDGE))
    outer_ring = (cv2.dilate(body.astype(np.uint8) * 255, k_edge) > 0) & ~body & ~shackle
    hole_rim = (cv2.dilate(shackle.astype(np.uint8) * 255, k_edge) > 0) & body
    return face_ink | creases | outer_ring | hole_rim


def rebuild_black(rgb_u8: np.ndarray) -> np.ndarray:
    """Classic black-studio plate key (cream lum + dark ink)."""
    rgb = rgb_u8.astype(np.float32)
    lum = rgb.mean(axis=2)
    cream = lum >= CREAM_LUM
    dark = lum <= DARK_LUM
    r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
    mouth = (r > 80) & (r > g * 1.2) & (r > b * 1.2) & (lum < 210)

    small_h, shackle = labeled_interior_holes(cream)
    body = clean_components(cream | small_h | mouth, MIN_BODY)
    body = body & ~shackle
    ink = ink_and_creases(body, shackle, dark)
    return paint_finish(rgb_u8, body, ink, mouth & body, shackle)


def sample_bg(rgb: np.ndarray) -> np.ndarray:
    h, w, _ = rgb.shape
    patches = [
        rgb[4:24, 4:24],
        rgb[4:24, w - 24 : w - 4],
        rgb[h - 24 : h - 4, 4:24],
        rgb[h - 24 : h - 4, w - 24 : w - 4],
    ]
    return np.mean([p.reshape(-1, 3).mean(0) for p in patches], axis=0)


def exterior_bg(dist_bg, lum, warm):
    h, w = dist_bg.shape
    walk = (dist_bg < WALK_DIST) | ((lum > 200) & (np.abs(warm) < 6) & (dist_bg < 40))
    reach = np.zeros((h, w), bool)
    for seed in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        bin_ = walk.astype(np.uint8) * 255
        mask = np.zeros((h + 2, w + 2), np.uint8)
        cv2.floodFill(bin_, mask, seed, 128)
        reach |= bin_ == 128
    return reach


def rebuild_light(rgb_u8: np.ndarray) -> np.ndarray:
    """Light-gray plate: warm cream vs cool BG; shackle = large interior hole.

    Outline matches black-plate treatment: cream fill only + thin synthetic
    OUTER_EDGE ring. Do **not** keep the fat baked-in source outline.
    """
    rgb = rgb_u8.astype(np.float32)
    bg = sample_bg(rgb)
    lum = rgb.mean(axis=2)
    warm = rgb[:, :, 0] - rgb[:, :, 2]
    dist_bg = np.linalg.norm(rgb - bg, axis=2)
    dark = lum <= 70
    r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
    mouth = (r > 80) & (r > g * 1.2) & (r > b * 1.2) & (lum < 210)
    cream = (lum >= 170) & (warm >= CREAM_WARM) & (dist_bg > 6) & ~dark

    ext = exterior_bg(dist_bg, lum, warm)
    # Cream (+ mouth) only — exclude source outline dark from the body matte
    seed = cream | mouth
    seed = cv2.morphologyEx(
        seed.astype(np.uint8) * 255,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)),
    ) > 0
    body0 = clean_components(seed & ~ext, MIN_BODY)
    small_h, shackle = labeled_interior_holes(body0)
    body = clean_components((body0 | small_h) & ~shackle, MIN_BODY)
    mouth = mouth & body & ~shackle

    # Eyes / smile / creases: dark on the cream fill, not the outer silhouette band
    face_dark = dark & body & ~shackle
    ink = ink_and_creases(body, shackle, face_dark)
    return paint_finish(rgb_u8, body, ink, mouth, shackle)


def rebuild(rgb_u8: np.ndarray, plate: str | None = None) -> np.ndarray:
    mode = plate or os.environ.get("LOCKUP_PLATE") or detect_plate(rgb_u8)
    if mode == "black":
        return rebuild_black(rgb_u8)
    return rebuild_light(rgb_u8)


def magenta_comp(rgba: np.ndarray) -> np.ndarray:
    a = rgba[:, :, 3:4].astype(np.float32) / 255
    mag = np.full_like(rgba[:, :, :3], (255, 0, 255))
    return (rgba[:, :, :3] * a + mag * (1 - a)).astype(np.uint8)


def main():
    RGBA.mkdir(exist_ok=True)
    REFS.mkdir(exist_ok=True)

    n = len(list(RAW.glob("frame_*.png")))
    if n == 0:
        raise SystemExit(f"no frames in {RAW}")

    sample = np.array(Image.open(RAW / "frame_0001.png").convert("RGB"))
    plate = os.environ.get("LOCKUP_PLATE") or detect_plate(sample)
    global OUTER_EDGE, CREASE_CLOSE, SMALL_HOLE
    # Same border treatment for light + black plates
    OUTER_EDGE = max(5, int(round(11 * _sx)) | 1)
    CREASE_CLOSE = max(5, int(round(15 * _sx)) | 1)
    SMALL_HOLE = max(2000, int(7000 * _sx * _sy * (1.5 if plate == "black" else 1.0)))
    print(f"plate mode: {plate}  size={sample.shape[1]}x{sample.shape[0]}  wipe=({WX0},{WY0})-({WX1},{WY1}) edge={OUTER_EDGE}")

    probes = [1, max(1, n // 4), max(1, n // 2), max(1, (3 * n) // 4), n]
    for probe in probes:
        rgb = np.array(Image.open(RAW / f"frame_{probe:04d}.png").convert("RGB"))
        rgba = rebuild(rgb, plate)
        Image.fromarray(magenta_comp(rgba)).save(REFS / f"fix_key_f{probe:04d}_magenta.png")
        Image.fromarray(rgba).save(REFS / f"fix_key_f{probe:04d}.png")
        a_hole = int(rgba[min(140, rgba.shape[0] - 1), rgba.shape[1] // 2, 3])
        print(f"probe {probe}: opaque={float((rgba[:,:,3]>0).mean())*100:.1f}% hole_a={a_hole}")

    print(f"rebuilding {n}…")
    for i in range(1, n + 1):
        rgb = np.array(Image.open(RAW / f"frame_{i:04d}.png").convert("RGB"))
        Image.fromarray(rebuild(rgb, plate)).save(RGBA / f"frame_{i:04d}.png")
        if i % 40 == 0 or i == n:
            print(f"  … {i}/{n}")
    print("done")


if __name__ == "__main__":
    main()
