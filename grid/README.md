# Grid

A field of four Rive animations — **grass · trees · rocks · water** — scattered
naturally so like sits next to like: organic forest clumps, rocky patches and
ponds over a grass base. You **grow it with the cursor**: each tile the cursor
reaches plays its grow-in animation forward (latched — even a quick pass
completes), then stays. Sweep across and the terrain fills in behind you.

The layout is random (a separate smooth value-noise per type → clumps), not a
pattern or word. Each tile is one `.riv` — there's no stacking; the feature `.riv`
files carry their own grass, so they blend into the grass field.

Tiles **fade in** and start at a random **stagger** delay, so a swept area fills
in scattered rather than all at once — it reads as natural growth.

All the knobs are live in the on-screen **controls** panel: trees / rocks / water
density, cols per side, tile size, reach, grow speed, stagger, fade out — plus
**regenerate** (new random layout) and **clear**.

![grid](https://img.shields.io/badge/runtime-Rive%20(vendored)-6ad1ff)

## How it works

The Rive renderer can't draw a different animation time per cell, so:

1. At load, each `.riv` is posed at evenly spaced times by one **advanced Rive**
   instance and rendered into a **filmstrip** of frames (readable 2D canvases).
   The renderer batches its draws (`tr.H`); we run them ourselves to capture each
   posed frame synchronously. `topIdx` = the last full-coverage frame (fully grown).
2. A separate **value-noise** field per feature type is thresholded at its density
   (water > rocks > trees > grass) to pick each tile's terrain, then a cleanup pass
   drops isolated features so like clusters with like.
3. Each tile carries a growth `0…1` (→ filmstrip frame `0…topIdx`). The render loop
   grows tiles near the cursor and (optionally) fades the rest.

This keeps it to **four** Rive instances total — one per animation (browsers cap
WebGL contexts, so a grid of instances is a non-starter).

Tunables: live in the controls panel (`DTREE`/`DROCK`/`DWATER`, `GRID`, `CELL`,
`REACH`, `FWD`, `FADE`), and `TILE` / `FRAMES` at the top of [`index.html`](index.html).

## Run it

It needs to be served over http (ES-module import + `fetch` of the `.riv` /
`.wasm` don't work from `file://`):

```bash
python3 -m http.server 8000
# open http://localhost:8000/grid/
```

## Files

| File | Purpose |
|------|---------|
| `index.html` | The whole tool — load, generation, render loop. |
| `grass.riv`, `trees.riv`, `rocks.riv`, `water.riv` | The four grow-in animations scattered across the field. |
| `rive/canvas_advanced.mjs`, `rive/rive.wasm` | Vendored Rive runtime, so the tool is self-contained (no CDN at runtime). |

Swap in your own `grass`/`trees`/`rocks`/`water` `.riv` (square artboards tile most cleanly).
