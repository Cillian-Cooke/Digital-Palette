# Kling MOV → Lottie — runbook (do this every time)

Consistent checklist so every new `.mov` gets the same treatment.
Companion detail: [`LOTTIE_PLAYBOOK.md`](LOTTIE_PLAYBOOK.md).

---

## 0. One-command shape (preferred)

```bash
# From repo root — job id is a short slug for this clip
lockup/source/.venv/bin/python lockup/lottie/convert_mov.py \
  --mov "/path/to/file.mov" \
  --job thumbs_5829
```

That script: probes → extracts frames → RGBA key + watermark wipe →
builds Lottie segments → writes QC traces under `lottie/qc/<job>/`.

Manual steps below if you need to debug mid-pipeline.

---

## 1. Probe first (never assume 1440 / black plate)

```bash
# imageio-ffmpeg from lockup/source/.venv
ffprobe-or-ffmpeg -i SOURCE.mov
```

Record:

| Field | Why it matters |
|-------|----------------|
| **W×H** | `build_lottie.py` `W`/`H`; watermark rect scales |
| **fps** | Lottie `fr` + hold-key `t` (frames, not ms) |
| **nb_frames** | segment end + export `op` |
| **Plate color** | **Black** vs **light gray** → different keyer |

### Plate types (2026)

| Plate | Example | Keyer |
|-------|---------|--------|
| **Black studio** | 2026-08-15 wave/sit (1440²); 2026-08-26 `clip_5896` (960²) | `CREAM_LUM` / `DARK_LUM` + topology shackle hole |
| **Light gray** | 2026-08-26 `thumbs_5829` (960²) | Corner flood + **warm cream** (`R−B`) — cream ≈ same lum as BG |

`rebuild_rgba.py` auto-detects from corner mean (`>120` → light) or `LOCKUP_PLATE=light|black`.

**Rule:** Always probe corners before trusting the keyer. Light-plate math on a black plate fills the shackle with ink/cream; black-plate math on a light plate eats the body.
---

## 2. Folder layout per job

Do **not** overwrite the previous convert blindly. Use a job slug:

```
lockup/source/jobs/<job>/
  mascot.mov            # copy of source
  frames_raw/           # gitignored
  frames_rgba/          # gitignored
  refs/                 # poses + magenta QC
  segments.md

lockup/lottie/export/<job>/
  mascot_full.json
  mascot_<segment>.json

lockup/lottie/qc/<job>/
  trace_*.png           # RGBA | contour side-by-side
```

Symlink or point `rebuild_rgba` / `build_lottie` at the job dirs (the
`convert_mov.py` helper does this).

---

## 3. Extract frames

```bash
ffmpeg -y -i mascot.mov -vsync 0 frames_raw/frame_%04d.png
```

Confirm file count == probed frame count. Build a contact sheet (`refs/poses.png`).

---

## 4. RGBA key + watermark (hard-won)

### Always

1. Transparent BG — no full-bleed plate in the Lottie  
2. **Wipe KlingAI watermark** (usually BR) — wipe rect + BG key  
3. Keep eyes / mouth / outline  
4. Shackle hole stays **transparent**  
5. QC on **magenta**, not checker alone  

### Light-gray plate (960² thumbs-up lessons)

| Mistake | Symptom | Fix |
|---------|---------|-----|
| Treat “near BG distance” as shackle | Body vanishes (only ink left) | Cream = **warm** (`R−B ≥ ~4`) + `dist_bg > 6`; shackle = **topology** large hole only |
| Fat baked outline kept on light plate | Double / heavy outline vs black plate | Cream-only body matte + synthetic `OUTER_EDGE` ring (drop source outline) |
| Flood-fill BG into shackle hole | Hole filled with cream | Hole is enclosed — punch large interior holes after body matte |
| Watermark wipe overlaps feet | Missing toes | Tight BR box after measuring; BG key already kills most of watermark |
| Keep soft floor shadow | Gray blob under feet | Exterior near-BG walk removes cool shadow |

### Black plate (1440² — earlier convert)

See playbook §3.2: `CREAM_LUM` / `DARK_LUM` / outer ring /
wipe `x≥980,y≥1350`. Both plate modes use the same `OUTER_EDGE≈11` @960.

### Scale constants with resolution

Area thresholds scale ≈ `(W/1440)²`. Stroke kernels scale ≈ `W/1440`.

| Constant (1440) | @960 (~⅔) |
|-----------------|-----------|
| SMALL_HOLE 15000 | ~7000 |
| OUTER_EDGE (unified) | **11** (~8px look) |
| CREASE_CLOSE 21 | ~15 |
| wipe (980,1350)–(1440,1440) | measure BR; thumbs used ~(640,890)–(960,960) |

---

## 5. Segments

Cut on pose holds from the contact sheet. Example thumbs-up film:

| id | Frames | Notes |
|----|--------|-------|
| idle | 1–56 | stand / mouth |
| thumbs | 57–140 | raise → hold → return |
| full | 1–169 | whole clip |

Update `SEGMENTS` in `build_lottie.py` (or pass via `convert_mov.py`).

---

## 6. Build Lottie (player-safe)

Same layer model every time:

1. **cream** — full matte − shackle hole only (no eye/mouth punches)  
2. **cavity / tongue** — when mouth opens  
3. **ink** — outline, eyes, closed smile, creases  

Rules that must not regress:

- **Fixed vertex count** per path slot (or lottie-web breaks)  
- Hold keys `h:1` @ source fps  
- Cream = one connected underlay (no transparent neck)  
- `W`/`H`/`fr` match the source  
- Size ↓ without lowering vertex budgets: skip unchanged hold keys (±0.5px),
  round verts to 0.1px; also emit `.json.gz` + `.lottie` beside JSON  

```bash
lockup/source/.venv/bin/python lockup/lottie/build_lottie.py
```

---

## 7. QC gate (ship only if green)

1. Magenta composites of RGBA: shackle hole open, no watermark, no BG  
2. Trace pairs (`write_qc_pair`): silhouette / ink / mouth line up  
3. Preview over http: `cd lockup/lottie && python3 -m http.server` → `preview.html`  
4. Optional: headless `render_frame.html?src=…&frame=N` (container size must match `W`/`H`)

**Do not** ship geometric “puppet” redraws as a substitute for this pipeline
when the brief is 1:1 to video.

---

## 8. Multi-clip batch

When the user drops several MOVs:

1. Run `convert_mov.py --job …` for each (separate export dirs)  
2. Add each job’s `mascot_full.json` to `preview.html` dropdown  
3. Keep `segments.md` per job  

---

*Update this file when a new plate type or failure mode appears.*
