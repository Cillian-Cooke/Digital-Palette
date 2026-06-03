# Stroke

Draw mouse strokes, shape them into animations, and export a real **Rive**
(`.riv`) file — all in a single, dependency-free HTML page.

![timeline + speed editor + canvas](https://img.shields.io/badge/runtime-no%20build%2C%20no%20deps-6ad1ff)

## What it does

- **Draw** on the canvas; each stroke is RDP-simplified and fit to a smooth
  poly-bézier (Schneider).
- **Shape the speed** in the animation-speed editor — pick a curvature preset
  (linear, ease in/out, exponential…) or paste in your own `cubic-bezier(…)`,
  and copy a stroke's easing back out.
- **Set transparency** once for the whole animation with the global opacity
  slider (applies to the preview and the export).
- **Animate** with a draw-on (trim) reveal shaped by the easing curve, plus an
  optional drift (a stroke moves from a start to an end position).
- **Arrange** on a timeline: per-stroke start, draw duration, and a "hold"
  section that defaults to the end of the animation (the stroke then disappears).
- **Move** strokes by dragging the body; set drift with a single arrow gizmo.
- **Organise** with box-select → groups that can be locked (uneditable) and
  hidden; locked groups collapse to a single timeline track.
- **Undo/redo** (`Ctrl+Z` / `Ctrl+Shift+Z`), width slider, colour picker.
- **Export** a from-scratch `.riv` binary (v7.0) that loads and plays in the
  real Rive runtime — stacking order and timing preserved.

## Run it

It's a static page — no build step:

```bash
python3 -m http.server 8000
# open http://localhost:8000/index.html
```

## Files

| File | Purpose |
|------|---------|
| `index.html` | The whole app — drawing, editor UI, and the `.riv` exporter. |
| `validate.html` | Dev-only harness that loads an exported `.riv` with the real `@rive-app/canvas` runtime to prove it plays. |
| `gen.mjs` | Headless (DOM-stubbed) generator that runs the real exporter and writes `test.riv`. |
| `selftest.mjs` | Structural self-check of the exported binary (header/ToC/object scan). |

## Notes

The exporter hand-writes the Rive binary format (RIVE magic, varuint header,
property ToC with a 2-bits-per-key type bitmap, then the object stream). It has
been verified against `@rive-app/canvas` 2.21.6: files load (`onLoad`) and play
the `Play` animation.
