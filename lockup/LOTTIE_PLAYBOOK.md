# Kling / plate → Lottie — playbook (lessons learned)

Hard-won rules from the first mascot convert (`lockup/source/mascot.mov` →
`lockup/lottie/export/`). Follow this for **future animations** so we don’t
re-learn the same failures.

Related: plan of record [`MOV_TO_LOTTIE_PLAN.md`](MOV_TO_LOTTIE_PLAN.md) ·
segments [`source/segments.md`](source/segments.md) ·
from photo / no-ref [`LOTTIE_FROM_STILL.md`](LOTTIE_FROM_STILL.md) · scripts below.

---

## 0. Goal & non-goals (never blur these)

**Goal:** 1:1 vector Lottie of the character only — same pose per source frame,
transparent background, no plate chrome.

**Non-goals:**

- Embedding PNG frames inside Lottie (raster flipbook)
- “Inspired by” redraws that drift from the plate
- Keeping the black studio plate or letterbox
- Tracing / keeping the **bottom-right Kling watermark** (wipe it)

---

## 1. Source invariants (probe first)

Always probe before extracting:

```bash
# fps, size, duration, frame count — use imageio-ffmpeg if system ffmpeg missing
ffprobe …   # or OpenCV / imageio
```

Record in the plan table. This convert’s ground truth:

| Spec | Value |
|------|--------|
| Size | 1440×1440 |
| FPS | **24** (all timing is frame-indexed at this fps) |
| Frames | 361 (1-based `frame_%04d.png`) |
| Duration | ~15.04 s |
| Plate | Black BG, cream mascot, thick black linework |

**Rule:** Lottie `fr` = source fps. Keyframe time `t` is in **frames**, not ms.

---

## 2. Folder layout (reuse every time)

```
lockup/source/
  mascot.mov              # gitignored (large)
  frames_raw/             # gitignored — full plate PNGs
  frames_rgba/            # gitignored — keyed RGBA
  rebuild_rgba.py         # plate → RGBA (outline + creases)
  segments.md             # beat cuts
  refs/                   # poses.png, heroes/, magenta QC only
  .venv/                  # gitignored — opencv, pillow, numpy, imageio-ffmpeg

lockup/lottie/
  build_lottie.py         # RGBA → Lottie JSON
  qc_fidelity.py          # extractor / player QC
  preview.html            # lottie-web SVG scrubber (needs http)
  render_frame.html       # headless single-frame render
  export/                 # mascot_*.json (gitignored — regenerate)
  qc/                     # diffs, player shots, one_to_one/
```

Commands:

```bash
cd lockup/source && .venv/bin/python rebuild_rgba.py
cd lockup/lottie && ../source/.venv/bin/python build_lottie.py
cd lockup/lottie && ../source/.venv/bin/python qc_fidelity.py --every 2
python3 -m http.server 8767   # from lockup/lottie → preview.html
```

---

## 3. Plate → RGBA keying (the hard part)

### 3.1 What failed (don’t repeat)

| Mistake | Symptom | Fix |
|---------|---------|-----|
| Key all near-black | Eyes / mouth vanish | Only key **large** dark regions (BG + shackle hole); keep small dark blobs |
| Synthetic fat outer dilate / contour halo | Double outline, magenta gaps, bumpy edge | Clean matte, then **fixed-width** outer ring only |
| Keep dark BG in a wide “edge band” | Speckled outer halo | Don’t treat BG as ink; paint a silhouette ring |
| Punch mouth/eyes out of cream for Lottie | Transparent face when mouth layer missing | Cream underlay = full matte − shackle only; paint mouth/ink **on top** |
| Split cream into head + body | Transparent “neck” | Cream underlay must be **one** connected fill under the chin crease |
| `approxPolyDP` then **arc-length resample** to fewer pts | Ink IoU collapses | For QC fidelity use light approx; for **player** use **fixed** vertex counts |
| Variable vertex counts across hold keys | Animation “does nothing” / breaks in lottie-web | **Same `len(v)` per path slot for every keyframe** |
| Mouth slot opacity 0 on closed-mouth frames while cream has mouth holes | Magenta hole in face | Don’t hole-punch mouth; opacity-gate mouth layer only when red exists |

### 3.2 Working RGBA recipe (`rebuild_rgba.py`)

Tunable constants (this mascot):

```text
CREAM_LUM = 100          # ≥ cream body
DARK_LUM  = 60           # ≤ ink / outline candidates
SMALL_HOLE = 15000       # ≤ eyes/mouth voids filled; > shackle stays open
CREASE_CLOSE = 21        # morph-close bridges chin / armpits / crotch
OUTER_EDGE = 17          # odd kernel → ~8px black outer stroke
Watermark wipe: x≥980, y≥1350
```

Pipeline:

1. **Cream mask** = lum ≥ CREAM_LUM  
2. **Labeled holes** in cream: small → fill into body (eyes); large → shackle (stay transparent)  
3. **`clean_body`**: morph open 3 + close 5; drop comps &lt; MIN_BODY (kills edge noise that caused double outlines)  
4. **Creases** = morph-close(body) − body − shackle → paint black (chin / armpits)  
5. **Outer ring** = dilate(body, OUTER_EDGE) − body − shackle → paint black  
6. **Hole rim** = dilate(shackle) ∩ body → paint black  
7. Face ink = dark ∩ body → paint black  
8. Wipe watermark rect to alpha 0  

QC: composite on **magenta**, not checker alone — gaps scream.

### 3.3 Outline thickness

User dial: 1 → 2 → 4 → **8 px**. Kernel size ≈ `2*px + 1` (ellipse). Keep stroke **outside** the cream, not a second floating halo.

---

## 4. Segments

Cut on pose holds. This film:

| id | Frames (1-based) | Notes |
|----|------------------|-------|
| intro | 1–144 | idle / shush / clasp / welcome |
| wave | 145–288 | right-arm wave |
| sit | 289–361 | sit + hold |

Lottie index mapping (0-based `t`):

- intro: `t` → `frame_{t+1}`  
- wave: `t` → `frame_{145+t}`  
- sit: `t` → `frame_{289+t}`  
- full: `t` → `frame_{t+1}` (+ markers intro/wave/sit)

Verify with offset probe: render Lottie frame L, score vs S−1 / S / S+1 — expected S must win (or tie within AA noise).

---

## 5. Vector / Lottie layer model (player-safe)

### 5.1 Layers (bottom → top in file = cream under ink)

Draw order in Lottie: **earlier list entry = on top**.

1. **cream** — solid underlay = opaque matte **minus shackle hole only**  
   - Outer: `RETR_EXTERNAL` on cream underlay  
   - Holes: **only** explicit shackle contours (never CCOMP holes from cream — those punched eyes/mouth)  
2. **cavity (mouth base)** — red open-mouth region (`cavity ∪ tongue`, morph-closed)  
3. **tongue** — lighter pink subset on top of cavity  
4. **ink** — black: outline rings, eyes, closed smile, creases (even-odd for rings)

Palette sampled from plate interiors (not fringes):

| Token | RGB | Use |
|-------|-----|-----|
| cream | 251, 244, 236 | body underlay |
| ink | 5, 5, 5 | linework |
| mouth dark | 140, 28, 28 | open mouth |
| tongue | 220, 120, 120 | tongue |

Fill rule: **evenOdd (`r: 2`)** for cream (shackle) and ink rings.

### 5.2 Keyframes

- One held key per source frame: `"h": 1` (no morph softening — timing stays 1:1)  
- **Fixed vertex count per path slot** across the whole clip (resample every key to the same N)  
- Empty slots: tiny degenerate path + **opacity 0** (don’t leave random holes in cream)  
- Typical budgets (player-safe): cream outer 256, holes 128, ink 192, mouth 96  

### 5.3 What “1:1” means in practice

- **Timing:** frame N of clip = plate frame mapped above (proven by offset probe)  
- **Pose:** silhouette + limbs match  
- **Player SVG AA:** expect ~1–2px fringe → raw mask IoU ~0.93–0.94 vs plate; **color closeness on overlap ~97%+**, MAD ~4–5 is a pass for SVG  
- Don’t chase 0.99 IoU against SVG screenshots without accounting for AA  

---

## 6. QC that actually catches breakage

### 6.1 Magenta plate QC (RGBA stage)

- `refs/fix_key_fXXXX_magenta.png` on heroes  
- Look for: double outline, magenta in chin/armpits, keyed eyes, watermark  

### 6.2 Extractor QC (`qc_fidelity.py`)

Rasterize the **same** path extractors with `cv2.fillPoly` even-odd; IoU vs classified mattes. This validates geometry **before** the player.

### 6.3 Player QC (mandatory — extractors can pass while preview fails)

1. `preview.html` via **http** (not `file://`) using **lottie-web SVG** (more reliable than huge `lottie-player` loads)  
2. Headless Chrome: `render_frame.html?src=…&frame=N` + `--screenshot`  
3. Side-by-side: plate magenta \| player \| optional heat  
4. Dense sample (e.g. every 8th frame) + heroes  
5. Confirm animation: pixel diff across L0 / L40 / L72 must be large if the clip moves  

Store under `lottie/qc/one_to_one/`.

### 6.4 Pass bars we used

| Check | Pass |
|-------|------|
| Timing offset | Expected source frame wins (or ties within noise) |
| Overlap color close (Δ&lt;80) | ≳ 0.95 |
| MAD on overlap | ≲ 6–8 |
| Mouth open frames | Red present in player, not magenta |
| Neck | Cream underlay opaque under chin crease |
| Playback | Consecutive Lottie frames differ when plate moves |

---

## 7. Preview / sharing

- Serve `lockup/lottie/` over http; open `preview.html`  
- Prefer segment JSONs for upload (**wave/sit ~11MB**, intro ~28MB, full ~69MB)  
- Full file is large because of per-frame high-res paths — optimize **after** QC, not before  
- Friends: drop JSON on LottieFiles preview or any lottie-web host  

---

## 8. Recipe for a **new** animation

1. Drop `.mov` → `lockup/source/<name>.mov`  
2. Probe fps/size/frames; write into plan + `segments.md`  
3. Extract `frames_raw/`; wipe watermark region if present  
4. Adapt `rebuild_rgba.py` thresholds (cream/dark/holes/edge px); magenta-QC heroes  
5. Mark segments on holds  
6. Run `build_lottie.py` (same layer model); fix constants if artboard ≠ 1440  
7. Extractor QC → player screenshots → timing offset probe → dense sample  
8. Only then: reduce point counts, package `.lottie`, commit scripts/docs (not frames/mov)  

### When to change strategy

| Situation | Prefer |
|-----------|--------|
| Simple character, plate is already clean vectors-on-black | This pipeline |
| Need tiny file + rig (wave = rotate arm) | After 1:1 lock, replace morph soup with transforms (plan §8) |
| Mouth/eyes are textured photos | May need image layers (avoid if possible) |
| Player still breaks with fixed verts | Export per-frame stills or split shorter clips |

---

## 9. Tooling notes

- **No system ffmpeg?** Use `imageio_ffmpeg.get_ffmpeg_exe()` from the venv  
- **Headless Chrome** for truth screenshots (`--virtual-time-budget` must be large for multi‑MB JSON)  
- **Gitignore:** `frames_*`, `.venv`, `mascot.mov`, `export/mascot_*.json` — regenerate from scripts  
- Keep lean refs: `poses.png`, `heroes/`, magenta keys — delete `debug_*` / `qc_*` junk  

---

## 10. Failure checklist (paste when something “completely breaks”)

- [ ] Preview served over **http**?  
- [ ] Cream underlay connected (neck not a hole)?  
- [ ] Cream holes = **shackle only**?  
- [ ] Mouth/ink drawn **above** cream?  
- [ ] Every animated path slot has **constant vertex count**?  
- [ ] Hold keys `"h": 1` and `fr` = source fps?  
- [ ] Frame mapping formula correct for this segment?  
- [ ] Player screenshot vs plate — wrong frame or wrong geometry?  
- [ ] Watermark wiped?  

---

*Last updated from the Aug 2026 mascot convert. Update this file when a new gotcha appears — don’t fork a second tribal-knowledge doc.*
