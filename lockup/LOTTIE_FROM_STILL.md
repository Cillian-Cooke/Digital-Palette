# Making a mascot Lottie — from a photo, or from nothing

Guide for when someone says: “animate this” and hands you either:

1. **A photo / still reference** (logo, character sheet, screenshot), or  
2. **No reference at all** (“make a cute padlock that waves”)

Also documents **what is actually inside** our exported Lottie JSON today (arms, mouth, etc.) vs the **rig you should build** for clean, editable animation.

Companion docs: [`LOTTIE_PLAYBOOK.md`](LOTTIE_PLAYBOOK.md) (pipeline lessons) · [`MOV_TO_LOTTIE_PLAN.md`](MOV_TO_LOTTIE_PLAN.md) (full convert plan).

---

## Two different jobs

| Brief | Best approach |
|-------|----------------|
| Match an existing **video** frame-for-frame | Plate → RGBA → contour Lottie (this repo’s current pipeline) |
| Match a **still photo / logo** | Design vector parts → rig → animate transforms |
| **No reference** | Invent character from brand rules → same as still path |

The video pipeline is for **1:1 capture**. The photo / no-ref path is for **authored animation** (smaller files, real arm/mouth controls).

---

## A. If you only have a photo reference

### A1. Read the photo like a kit of parts

Print or open the still at full size. Label every closed shape you can see:

| Part | What to look for on this mascot |
|------|----------------------------------|
| **Shackle** | U-loop on top; hole in the middle stays transparent |
| **Head** | Big rounded square / squircle |
| **Eyes** | Two black dots (or closed arcs when smiling/sleeping) |
| **Mouth** | Closed = thin black smile stroke; open = dark red cavity + pink tongue |
| **Neck crease** | Black line under the chin (not a gap in the fill) |
| **Torso** | Short body under the head |
| **Arm_L / Arm_R** | Stubby limbs; note which side waves |
| **Leg_L / Leg_R** | Feet / sit pose |
| **Outline** | Continuous black stroke around the silhouette (~8px on our plate) |

Sample fills from **flat interiors**, not anti-aliased edges:

| Token | Approx RGB | Where |
|-------|------------|--------|
| cream | `251, 244, 236` | body / head / limbs |
| ink | `5, 5, 5` | outline, eyes, closed mouth, creases |
| mouth dark | `140, 28, 28` | open mouth cavity |
| tongue | `220, 120, 120` | tongue |

### A2. Trace once as a **rig**, not as one blob

In Figma / Illustrator / Affinity / AE:

1. Lock the photo as underlay at ~40% opacity.  
2. Trace **separate** closed paths for each row in the table above.  
3. Parent limbs to torso (or use layer hierarchy).  
4. Set **anchor points** at joints (shoulder for arms, hip for legs).  
5. Export as shapes into After Effects / Haiku / Jitter / or hand-build Lottie JSON.

**Do not** flatten the whole character into one path if you want a wave or sit later — you’ll be stuck morphing silhouettes.

### A3. Animate from the photo’s “rest pose”

Typical beats for this character:

| Beat | What moves |
|------|------------|
| Idle | Tiny bob on root; blink (swap eye shapes) |
| Wave | `Arm_R` rotation (+ small hand path); body can lean opposite |
| Sit | Root Y down; legs rotate/squash; maybe eyes close |
| Talk / cheer | Mouth opacity swap: closed stroke ↔ open cavity+tongue |

Prefer **rotation / position / opacity** keyframes. Only morph paths when the silhouette truly changes shape (squash).

### A4. If the “photo” is actually a video frame

Treat it as a hero still for the **rest pose**, then either:

- Author the animation as in A3, or  
- Run the full MOV→Lottie playbook if they need every frame identical to a plate video.

---

## B. If you have **no** reference at all

### B1. Lock a character bible first (one page)

Write this before drawing:

1. **Silhouette** — recognisable as a padlock (shackle hole required).  
2. **Palette** — 3–4 colours max (cream, ink, mouth, tongue).  
3. **Proportions** — head : body : limb scale (ours is head-dominant).  
4. **Line weight** — e.g. 8px outer stroke at 1440 artboard.  
5. **Personality** — friendly, stubby limbs, simple face.  
6. **Artboard** — square 1440×1440 @ 24fps (matches product / this repo).

### B2. Draw the rest pose, then duplicate for extremes

Minimum drawings:

1. Rest / idle  
2. Wave peak (arm up)  
3. Sit hold  
4. Mouth open (optional)  
5. Eyes closed (optional)

Build the **same layer hierarchy** on every drawing so you can interpolate with transforms instead of redrawing.

### B3. Invent motion with intent

| Ask | Default for this mascot |
|-----|-------------------------|
| How long is a wave? | ~1–2s up, hold, ~1–2s down @ 24fps |
| Loop? | Wave maybe; sit holds on last pose |
| Easing | Soft ease out on raise; ease in on settle |
| Overshoot? | Tiny on arm tip only — keep brand clean |

---

## C. What’s inside **our** Lottie files today

Exports live in `lottie/export/` (`mascot_intro.json`, `mascot_wave.json`, `mascot_sit.json`).  
They are **player-safe 1:1 traces of the video**, not a jointed puppet.

### C1. Top-level

| Field | Meaning |
|-------|---------|
| `fr` | 24 |
| `w` / `h` | 1440 |
| `ip` / `op` | Clip range in frames (e.g. wave `0`–`144`) |
| `layers` | Shape layers (see below) |

**Frame mapping:** Lottie time `t` (0-based) → source `frame_{start+t}.png`  
(wave start = 145, so wave `t=72` → plate frame 217).

### C2. Layers (draw order)

In Lottie, **earlier entries in `layers` draw on top**.

```
layers[0]  ink      ← black linework (on top)
layers[1]  tongue   ← pink
layers[2]  cavity   ← dark red mouth
layers[3]  cream    ← body fill (underneath)
```

### C3. What each layer actually is

#### `cream` — the whole body fill (including arms & legs)

- **One** group `cream_0`: cream fill `#FBF4EC`.  
- Path `cream_0_o`: outer silhouette (**256 points**), held key every frame.  
- Path `cream_0_h0`: **shackle hole** only (even-odd), so the loop stays transparent.  
- **Arms and legs are not separate layers.** They are bumps on this single silhouette. When the character waves, the cream path morphs each frame so the raised arm is part of the outline.

#### `ink` — outline, eyes, closed mouth, creases

- Several groups `ink_0` … `ink_N` (area-sorted blobs).  
- Each has an outer path (+ optional holes) filled black `#050505`, even-odd.  
- Together these cover: outer stroke, eye dots, chin/armpit creases, closed smile, etc.  
- Slots are **not** named `eye_L` / `Arm_R` — they’re anonymous contour slots. Identity can swap if blob ranking changes (opacity gates empty slots).

#### `cavity` — open mouth (dark red)

- `cavity_0` path, ~96 points, fill `#8C1C1C`.  
- **Opacity keyed**: 100 when the plate has an open red mouth, **0** when the mouth is a closed black smile (then ink draws the smile).

#### `tongue` — open mouth tongue

- `tongue_0`, fill `#DC7878`.  
- Same opacity idea as cavity (on only while mouth is open).

### C4. How “arms” and “mouth” behave in *this* file

| Feature | In current JSON | How it animates |
|---------|-----------------|-----------------|
| **Arm wave** | Part of `cream_0` (+ ink outline) | Per-frame path hold keys — whole silhouette morphs |
| **Legs / sit** | Same | Same morph approach |
| **Closed mouth** | Black path inside `ink_*` | Present when cavity opacity is 0 |
| **Open mouth** | `cavity` + `tongue` on top of cream | Opacity on + path morph while open |
| **Eyes** | Black fills in `ink_*` | Morph / appear as ink blobs |
| **Shackle hole** | Hole path on `cream_0` | Even-odd cutout every frame |
| **Chin crease** | Black ink between head & torso | Ink fill — cream underneath stays solid (no transparent neck) |

There are **no** properties like `Arm_R.rotation` in these files. To change the wave, you change the source plate or re-trace — you don’t tweak an arm control.

### C5. Shape group anatomy (one group)

Each group under a layer looks like:

```text
group cream_0
  ├─ sh  cream_0_o     path keys (hold, fixed point count)
  ├─ sh  cream_0_h0    hole path keys (optional)
  ├─ fl                solid fill (evenOdd if holes)
  └─ tr                opacity (static 100 or keyed 0/100)
```

Path keys use `"h": 1` (hold) so frame N matches plate frame N with no in-between morph softening.  
**Vertex count is fixed per slot** across the clip — required for lottie-web.

---

## D. The hierarchy you *should* use for authored animation

When building from a photo or from scratch (not video-trace), target this:

```text
Mascot
├─ Root                 (position bob)
│  ├─ Shackle           (fill + optional inner hole)
│  ├─ Head
│  │  ├─ HeadFill
│  │  ├─ Eye_L / Eye_R  (or EyeClosed swap)
│  │  ├─ MouthClosed    (stroke)     opacity ↔
│  │  ├─ MouthOpen
│  │  │  ├─ Cavity
│  │  │  └─ Tongue
│  │  └─ ChinCrease     (stroke)
│  ├─ Torso
│  ├─ Arm_L             (anchor at shoulder)
│  ├─ Arm_R             (anchor at shoulder)  ← wave = rotation
│  ├─ Leg_L
│  └─ Leg_R             ← sit = rotation + root Y
└─ Outline              (or per-part strokes)
```

Then:

- **Wave** = keyframe `Arm_R.r` (and maybe a little `Root.r`).  
- **Mouth** = crossfade opacities `MouthClosed` ↔ `MouthOpen`.  
- **Sit** = `Root.p` Y + leg rotations.

File size drops from tens of MB to tens of KB once you leave per-frame silhouette morphs behind.

---

## E. Suggested decision tree

```text
Got a video plate to match exactly?
  YES → LOTTIE_PLAYBOOK.md (key → trace → QC)
  NO  → Got a photo / logo still?
          YES → Section A (trace parts → rig → animate)
          NO  → Section B (bible → rest pose → extremes → animate)
```

After either authored path, still QC on magenta / checker, and keep shackle hole + watermark rules from the playbook.

---

## F. Quick reference — colours & artboard

| Item | Value |
|------|--------|
| Artboard | 1440×1440 |
| FPS | 24 |
| Cream | `rgb(251,244,236)` |
| Ink | `rgb(5,5,5)` |
| Mouth cavity | `rgb(140,28,28)` |
| Tongue | `rgb(220,120,120)` |
| Preview | `lottie/preview.html` (serve over http) |

---

*When the next brief is “just a PNG” or “make something up”, start here. When it’s “match this Kling MOV”, start in [`LOTTIE_PLAYBOOK.md`](LOTTIE_PLAYBOOK.md).*
