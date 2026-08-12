# Lockup

Shape-layer lockups → clean, consistent **Rive** (`.riv`) files. Built for logo
lockup work (fills + strokes), not freehand drawing.

The starter template is a parametric padlock (shackle · body · eyes · mouth)
matching the cream / tan / black logo.

## What it does

- **Padlock template** — editable colour / stroke width per layer; reset anytime.
- **Presets** — fade · assemble · pop · draw (trim draw-on for strokes).
- **Timeline** — staggered start / duration per layer; scrub and play.
- **Easing** — cubic-bezier presets + paste, baked into opacity / position / trim keyframes.
- **Export** — from-scratch `.riv` v7.0 with **Fill** (closed paths) and Stroke (+ optional TrimPath).

## Run it

```bash
python3 -m http.server 8000
# http://localhost:8000/lockup/
```

Works from `file://` for the editor (canvas preview). Use http for
[`validate.html`](validate.html) (CDN runtime).

## Files

| File | Purpose |
|------|---------|
| `index.html` | Editor + Fill-capable `.riv` exporter |
| `selftest.mjs` | Structural check (Fill / closed paths / keyframes) |
| `gen.mjs` | Writes gitignored `test.riv` |
| `validate.html` | Drop a `.riv` into the real `@rive-app/canvas` runtime |

```bash
node lockup/selftest.mjs
node lockup/gen.mjs
```

## Notes

Exporter is a self-contained fork of stroke's binary writer, plus:

- Fill core type **20**, `fillRule` **40**
- PointsPath `isClosed` **32** (bool) for body / eyes
- Shape opacity + x/y for assemble; TrimPath `trimEnd` for draw-on strokes
