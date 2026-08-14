# Mascot MOV → Lottie — conversion plan

**Goal:** Turn a dropped `.mov` of the lockup mascot into **1:1** vector Lottie(s). Keep the character animation exact; **discard the black background**. Split the timeline into natural beats (wave, sit, etc.) as separate Lottie clips *and* as named markers in a master file.

**Non-goals:** Raster-in-Lottie (embedding PNG frames). Approximate “inspired by” redraws. Keeping any black plate / letterbox. **The logo bug in the bottom-right of the plate — ignore completely** (do not trace, matte, or export it).

---

## 0. Drop the source

Put the file here when ready:

```
lockup/source/mascot.mov
```

(Create `lockup/source/` if needed. Keep the original filename in a note below if you rename it.)

| Field | Fill in after drop |
|-------|--------------------|
| Source file | `lockup/source/mascot.mov` |
| Original path | `/home/cillian/Downloads/kling_20260815_VIDEO_can_you_an_147_0.mov` |
| Duration | **15.04 s** |
| Frame rate | **24 fps** |
| Resolution | **1440 × 1440** (square) |
| Frame count | **361** (`frames_raw/` + `frames_rgba/`) |
| Codec | H.264 (yuv420p) |
| Colour space | Progressive; treat as sRGB for sampling |
| Notes | KlingAI watermark BR — ignore. Black plate keyed to alpha. Draft segments in [`source/segments.md`](source/segments.md). Contact sheet: [`source/refs/poses.png`](source/refs/poses.png). |

---

## 1. Principles (1:1 + efficient)

1. **Geometry first.** Rebuild every visible shape as vectors (paths / ellipses / rects). No bitmap fills for the mascot body unless a tiny texture is truly unavoidable (prefer solid fills + strokes).
2. **Match on-screen pixels.** At the artboard size of the source (or a clean integer scale, e.g. 1× or 0.5×), a flipbook of the Lottie vs the `.mov` must line up: silhouette, proportions, timing, easing.
3. **Animate properties, not morph soup.** Prefer transform (position / rotation / scale), opacity, path trim, and a *small* set of morph targets over hundreds of unique path keyframes per frame.
4. **Kill the black.** Export with **transparent** background. Never include a full-bleed black rectangle in the Lottie.
5. **Ignore bottom-right logo.** Crop it out of attention when tracing, or mask that corner off reference frames. It must not appear in any Lottie.
6. **Split by performance beat.** One Lottie per action for product use; one master with markers for editorial.

Efficiency checklist:

- Reuse shapes across frames (same fill colours, shared assets).
- Collapse static layers (no keyframes on idle props).
- Prefer few layers with keyed transforms over per-frame path dumps.
- Round coordinates sensibly (e.g. 0.1 px) once fidelity is locked — not before.
- Final JSON gzip / `.lottie` zip; strip editor junk (hidden layers, guides).

---

## 2. Pipeline overview

```
mascot.mov
    │
    ├─ A. Probe (fps, size, duration)
    ├─ B. Extract frames (PNG sequence, full fidelity)
    ├─ C. Remove black → transparent (per frame)
    ├─ D. Segment timeline (wave / sit / …)
    ├─ E. Vector rebuild 1:1 (paths + hierarchy)
    ├─ F. Rig & keyframe to match source timing
    ├─ G. Export Lottie (+ per-segment clips)
    └─ H. QC: flipbook A/B vs source
```

---

## 3. Step A — Probe the `.mov`

Record ground truth before any conversion:

```bash
ffprobe -v error -select_streams v:0 \
  -show_entries stream=width,height,r_frame_rate,avg_frame_rate,nb_frames,duration \
  -of default=noprint_wrappers=1 \
  lockup/source/mascot.mov
```

Write results into the table in §0. **All later timing uses this fps** (frame numbers, not wall-clock guesses).

---

## 4. Step B — Extract frames

```bash
mkdir -p lockup/source/frames_raw
ffmpeg -i lockup/source/mascot.mov \
  -vsync 0 \
  lockup/source/frames_raw/frame_%04d.png
```

- Do **not** retime or change fps here.
- Keep lossless PNG.
- Confirm `nb_frames` matches file count.

---

## 5. Step C — Remove black background

Black plate must go **before** vector tracing so auto tools don’t bake a black rect, and so silhouette mattes are clean.

Approach:

1. Treat near-black as chroma key (threshold ~8–16 in 0–255; tune so soft edges / anti-alias aren’t eaten).
2. Output **RGBA** PNGs with alpha.

```bash
mkdir -p lockup/source/frames_rgba
# Example: near-black → alpha (tune similarity/blend against a few hard frames)
ffmpeg -i lockup/source/frames_raw/frame_%04d.png \
  -vf "colorkey=0x000000:0.08:0.08,format=rgba" \
  lockup/source/frames_rgba/frame_%04d.png
```

Manual pass:

- Spot-check frames where the mascot is darkest (feet, outlines). If holes appear, lower threshold or matte by hand in those ranges.
- Confirm **no** full-frame black remains in any RGBA still.
- **Bottom-right logo:** **removed from all `frames_raw/` and `frames_rgba/`** (wipe rect x≥980, y≥1350 → black / alpha 0). Re-check if the plate is re-extracted.
- **RGBA keying:** large near-black regions only (plate + shackle hole) → transparent. Small dark blobs (eyes/mouth) stay opaque. Cleaned silhouette + **~8px** black outer edge + chin/armpit crease fills (`source/rebuild_rgba.py`).

Store a contact sheet of 8–12 key poses for reference:

```
lockup/source/refs/poses.png
```

---

## 6. Step D — Split into performance segments

Scrub the RGBA sequence and mark **inclusive** frame ranges. Names below are starters — rename to match what the clip actually does.

| Segment id | Label (working) | Start frame | End frame | Loop? | Notes |
|------------|-----------------|-------------|-----------|-------|-------|
| `intro` | idle + expressions | 1 | 144 | no | shush, clasp, eyes closed, arms wide — see `source/segments.md` |
| `wave` | waving | 145 | 288 | maybe | right-arm wave |
| `sit` | sitting down | 289 | 361 | hold | seated, eyes closed smile |

Rules:

- Cuts land on **clean pose holds** when possible (easier looping and product triggers).
- Overlap 0 frames between clips unless a shared in-between is required; prefer hard cuts at holds.
- Document easing personality per segment (snappy vs soft) from the plate.

Outputs:

- `lockup/source/segments.md` — filled table above  
- Optional trimmed MOV refs: `lockup/source/segments/<id>.mov` (for side-by-side only)

---

## 7. Step E — Vector rebuild (1:1)

### 7.1 Artboard

- Size = source pixel size (or exact half/double with scale noted).
- Origin and character placement must match the plate (center / baseline).
- Background empty (transparent).

### 7.2 Layer inventory

Break the mascot into a **stable hierarchy** used for every frame, e.g.:

```
Mascot
  Root (hips / body translate)
    Torso
    Head
      Face (eyes / mouth / blush …)
    Arm_L
    Arm_R
    Leg_L
    Leg_R
  Props (if any)
```

Fill this after studying refs:

| Layer | Shape type | Fill / stroke | Anchored at | Animated? |
|-------|------------|---------------|-------------|-----------|
| | | | | |

### 7.3 How to get vectors (in order of preference for 1:1)

1. **Manual rebuild in a vector tool** (Illustrator / Figma / Affinity / Inkscape) over the RGBA frames as locked underlays — best fidelity for a mascot.
2. **Pose-by-pose path trace** only for silhouettes that stay simple; clean nodes aggressively.
3. **Avoid** dumping every frame through Image Trace unchecked — it produces noisy, inefficient paths and breaks hierarchy.

For each **hero pose** (segment start, mid extreme, end):

- Trace under the plate at 100% opacity underlay → match outline exactly → then dim underlay and refine overlaps / z-order.
- Snap shared edges (e.g. arm in torso socket) so joints don’t slip.

### 7.4 Colour

- Sample fills from non-anti-aliased interior pixels (not edge fringes).
- Build a tiny palette table; reuse hex values everywhere.

| Token | Hex | Used on |
|-------|-----|---------|
| | | |

---

## 8. Step F — Rig & match timing

### 8.1 Prefer this animation model

| Motion type | Prefer | Avoid |
|-------------|--------|-------|
| Wave | Arm rotation + small hand path | Full-body path morph each frame |
| Sit | Root/hip Y + torso rotate + leg rotate | Replacing whole silhouette per frame |
| Face | Swap or slight path morph on mouth/eyes | New head path every frame |

### 8.2 Timing lock

- Timeline fps = source fps.
- Keyframes on **whole frames** that match the plate (frame 12 in MOV = frame 12 in Lottie).
- Where the plate eases, either:
  - match with bezier spatial/temporal easings, or
  - hold linear keys on every source frame for that channel until QC passes, then simplify.

### 8.3 Tools (pick one stack and stay there)

Recommended path for clean Lottie:

1. Rebuild + animate in **After Effects** (or **Haiku / Jitter / Rive→Lottie** only if export is proven 1:1).
2. Export via **Bodymovin / LottieFiles plugin** → JSON.
3. Or: animate in AE-compatible vector workflow → LottieFiles converter only if AE isn’t available — then re-QC harder.

Working files live under:

```
lockup/lottie/work/     # .aep / .fig / .svg masters
lockup/lottie/export/   # json + .lottie
```

---

## 9. Step G — Export deliverables

### 9.1 Master (full performance)

```
lockup/lottie/export/mascot_full.json
lockup/lottie/export/mascot_full.lottie
```

- Transparent background  
- Named **markers** (or AE comps) matching segment ids: `wave`, `sit`, …  
- Document marker start/end frames in `lockup/lottie/export/README.md`

### 9.2 Split clips (product-ready)

For each segment row in §6:

```
lockup/lottie/export/mascot_<id>.json
lockup/lottie/export/mascot_<id>.lottie
```

Each clip:

- Starts at that segment’s first frame pose  
- Ends on a stable hold when looping is required  
- No black background  
- Same artboard size as master  

### 9.3 Export settings

- Glyphs as shapes (no missing-font risk) if any text ever appears (mascot likely none).  
- Hidden layers excluded.  
- “Glyphs” / expressions baked as needed so players don’t diverge.  
- Verify in **lottie-web** and **dotLottie** player if you ship `.lottie`.

---

## 10. Step H — QC for true 1:1

Do this before calling it done:

| Check | Method | Pass criteria |
|-------|--------|---------------|
| Transparency | Checkerboard behind player | No black plate, no dark matte fringe |
| No BR logo | Inspect bottom-right of every export | Logo absent from all Lotties |
| Silhouette | Onion-skin Lottie over RGBA frame every 4–8 frames | Outline within ~0.5–1 px at 1× |
| Timing | Play MOV and Lottie side by side, same fps | Extremes land on the same frames |
| Segments | Trigger each clip alone | Wave / sit / … match their ranges |
| Efficiency | Inspect JSON size + path counts | No per-frame full-character morph unless unavoidable; file size sane vs duration |
| Players | lottie-web + one mobile player | No missing layers / wrong draw order |
| Loop | Loop `wave` (if required) | No pop at loop point |

Flipbook script idea (later): composite `frames_rgba` vs Lottie-rendered frames, write diff heatmaps into `lockup/lottie/qc/`.

---

## 11. Acceptance criteria (definition of done)

- [x] Source probed; fps/size recorded in §0  
- [x] Full RGBA sequence with black removed  
- [x] Segment table filled (`wave`, `sit`, …) with frame ranges  
- [x] Vector layers: cream + mouth + even-odd ink (held paths @ 24 fps)  
- [x] Extractor QC 1:1 vs plate (`lottie/qc_fidelity.py`, IoU thresholds)  
- [x] Per-segment Lotties exported (`intro` / `wave` / `sit` / `full`)  
- [x] No black background in any export  
- [x] Bottom-right plate logo absent from all exports  
- [ ] Player QC: lottie-web screenshots vs plate on hard frames  
- [ ] Optional: `.lottie` package + path-count optimize after player QC  

---

## 12. Execution order (when the `.mov` lands)

1. ~~Drop file → `lockup/source/mascot.mov`~~ **done**
2. ~~Probe + extract + key out black~~ **done** (361 RGBA frames; BR logo wiped; 8px outer ink + creases)
3. ~~Draft segment table~~ **done** → refine cuts on a full scrub (`source/segments.md`)
4. ~~Vector rebuild / Lottie trace~~ **done** (cream + mouth + even-odd ink, ≤0.35px approx, held paths)
5. ~~QC extractors 1:1 vs plate~~ **done** (`lottie/qc_fidelity.py` — IoU thresholds)
6. ~~Player QC (still render)~~ **done** (`render_still.html` + headless still ≈98% plate match; full clips open in `preview.html`)
7. Optimize path counts / file size; package `.lottie`

---

## 13. Open items (fill during work)

- Exact segment list after first scrub:  
- Looping requirements per segment:  
- Target runtime (web / iOS / Android / Rive bridge):  
- Max file size budget:  

---

*This document is the plan of record. Update tables in place as the conversion proceeds; don’t fork a second plan.*

**Operational lessons / reuse checklist:** [`LOTTIE_PLAYBOOK.md`](LOTTIE_PLAYBOOK.md).
