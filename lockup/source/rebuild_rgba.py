#!/usr/bin/env python3
"""Rebuild frames_rgba:

- Transparent plate + shackle hole
- Cream body; eyes/mouth kept (small cream-holes filled, large shackle hole not)
- Thin BLACK on the outside edge (~8px ring on a cleaned silhouette — no fat halo)
- BLACK chin / armpit / crotch creases (morph-close bridges)
- Shackle inner rim black where it touches the body
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image

RAW = Path(__file__).resolve().parent / "frames_raw"
RGBA = Path(__file__).resolve().parent / "frames_rgba"
REFS = Path(__file__).resolve().parent / "refs"

WX0, WY0, WX1, WY1 = 980, 1350, 1440, 1440
CREAM_LUM = 100
DARK_LUM = 60
SMALL_HOLE = 15000
MIN_BODY = 500
CREASE_CLOSE = 21  # wide enough to seal chin/armpit plate gaps without magenta holes
OUTER_EDGE = 17  # odd kernel size → ~8px outside stroke
INK = (5, 5, 5)


def labeled_holes(cream: np.ndarray):
    mask = cream.astype(np.uint8) * 255
    inv = 255 - mask
    ff = inv.copy()
    ffmask = np.zeros((ff.shape[0] + 2, ff.shape[1] + 2), np.uint8)
    cv2.floodFill(ff, ffmask, (0, 0), 64)
    hole_bin = (ff == 255).astype(np.uint8)
    num, labels, stats, _ = cv2.connectedComponentsWithStats(hole_bin, 8)
    small = np.zeros(cream.shape, bool)
    large = np.zeros(cream.shape, bool)
    for i in range(1, num):
        if int(stats[i, cv2.CC_STAT_AREA]) <= SMALL_HOLE:
            small[labels == i] = True
        else:
            large[labels == i] = True
    return small, large


def clean_body(body: np.ndarray) -> np.ndarray:
    """Despeckle silhouette so the outer ring isn't a bumpy double halo."""
    u8 = body.astype(np.uint8) * 255
    u8 = cv2.morphologyEx(u8, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    u8 = cv2.morphologyEx(u8, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    num, labels, stats, _ = cv2.connectedComponentsWithStats((u8 > 0).astype(np.uint8), 8)
    out = np.zeros(body.shape, bool)
    for i in range(1, num):
        if int(stats[i, cv2.CC_STAT_AREA]) >= MIN_BODY:
            out[labels == i] = True
    return out


def rebuild(rgb: np.ndarray) -> np.ndarray:
    lum = rgb.astype(np.float32).mean(axis=2)
    cream = lum >= CREAM_LUM
    dark = lum <= DARK_LUM

    small_holes, shackle_hole = labeled_holes(cream)
    body = clean_body(cream | small_holes)
    face_ink = dark & body

    # Chin / armpit / crotch: bridge gaps between body parts → solid black crease
    k_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (CREASE_CLOSE, CREASE_CLOSE))
    bridged = cv2.morphologyEx(body.astype(np.uint8) * 255, cv2.MORPH_CLOSE, k_close) > 0
    creases = bridged & ~body & ~shackle_hole
    # Seal plate ink in the same junctions (avoids magenta speckles in thick creases)
    creases |= dark & bridged & ~body & ~shackle_hole
    creases = (
        cv2.morphologyEx(creases.astype(np.uint8) * 255, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8)) > 0
    ) & bridged & ~body & ~shackle_hole

    # Outside edge: ~8px ring around the cleaned cream
    k_edge = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (OUTER_EDGE, OUTER_EDGE))
    outer_ring = (cv2.dilate(body.astype(np.uint8) * 255, k_edge) > 0) & ~body & ~shackle_hole

    # Shackle inner rim: matching stroke into the hole
    hole_rim = (cv2.dilate(shackle_hole.astype(np.uint8) * 255, k_edge) > 0) & body

    ink = face_ink | creases | outer_ring | hole_rim
    keep = (body | ink) & ~shackle_hole

    out = rgb.copy()
    alpha = np.where(keep, 255, 0).astype(np.uint8)
    out[ink] = INK

    alpha[WY0:WY1, WX0:WX1] = 0
    out[WY0:WY1, WX0:WX1] = 0
    out[alpha == 0] = 0
    return np.dstack([out, alpha])


def magenta_comp(rgba: np.ndarray) -> np.ndarray:
    a = rgba[:, :, 3:4].astype(np.float32) / 255
    mag = np.full_like(rgba[:, :, :3], (255, 0, 255))
    return (rgba[:, :, :3] * a + mag * (1 - a)).astype(np.uint8)


def main():
    RGBA.mkdir(exist_ok=True)
    REFS.mkdir(exist_ok=True)

    for probe in (1, 121, 217, 340):
        rgb = np.array(Image.open(RAW / f"frame_{probe:04d}.png").convert("RGB"))
        rgba = rebuild(rgb)
        Image.fromarray(magenta_comp(rgba)).save(REFS / f"fix_key_f{probe:04d}_magenta.png")
        Image.fromarray(rgba).save(REFS / f"fix_key_f{probe:04d}.png")
        print(f"probe {probe}: hole(720,280)a={int(rgba[280, 720, 3])}")

    n = len(list(RAW.glob("frame_*.png")))
    print(f"rebuilding {n}…")
    for i in range(1, n + 1):
        rgb = np.array(Image.open(RAW / f"frame_{i:04d}.png").convert("RGB"))
        Image.fromarray(rebuild(rgb)).save(RGBA / f"frame_{i:04d}.png")
        if i % 60 == 0 or i == n:
            print(f"  … {i}/{n}")

    for i in (49, 73, 145, 288, 361):
        rgba = np.array(Image.open(RGBA / f"frame_{i:04d}.png"))
        Image.fromarray(magenta_comp(rgba)).save(REFS / f"fix_key_f{i:04d}_magenta.png")
    print("done")


if __name__ == "__main__":
    main()
