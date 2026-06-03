# Grid

A big grid of the same Rive logo at fixed random 90° rotations that you **paint
with the cursor**. A cell the cursor reaches plays *forward* to the finished logo
(latched — even a quick pass completes, which is the couple-seconds lag), holds
while hovered, then plays *back in reverse* and disappears once the cursor leaves.
Zoom across and you leave a trail of logos that draw on and dissolve behind you.

All the knobs are live in the on-screen **controls** panel: logos / side, logo
size, reach, paint speed, fade speed.

![grid](https://img.shields.io/badge/runtime-Rive%20(vendored)-6ad1ff)

## How it works

The Rive renderer can't draw a different animation time per cell, so:

1. At load, one **advanced Rive** instance poses the animation at evenly spaced
   times and renders each into a **filmstrip** of frames (readable 2D canvases).
   The renderer batches its draws (`tr.H`); we run them ourselves to capture each
   posed frame synchronously.
2. `topIdx` = the **last full-coverage frame** (the finished, coloured logo). This
   logo draws on, recolours while held at full, then blanks on the very last frame
   — so we target that final coloured state, never the blank end.
3. Each cell carries a playback position `prog` (0…1 → filmstrip frame `0…topIdx`)
   and a phase (idle · painting-forward · holding · reversing). The render loop
   advances every cell each frame from its distance to the cursor.

This keeps it to **one** Rive instance (browsers cap WebGL contexts, so a grid of
instances is a non-starter).

Tunables: live in the controls panel (`GRID`, `CELL`, `REACH`, `FWD`, `REV`), and
`TILE` / `FRAMES` at the top of [`index.html`](index.html).

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
| `index.html` | The whole tool — load, render loop, and grid compositing. |
| `logo.riv` | The animation tiled across the grid (swap in your own). |
| `rive/canvas_advanced.mjs`, `rive/rive.wasm` | Vendored Rive runtime, so the tool is self-contained (no CDN at runtime). |

To use a different animation, drop in your own `logo.riv` (a square artboard
tiles most cleanly).
