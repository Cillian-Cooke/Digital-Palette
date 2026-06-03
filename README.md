# Digital Palette

A palette of small, self-contained tools for digital design — one repo, one
folder per tool. The root [`index.html`](index.html) is an artist's palette where
each colour dab links to a project.

## Projects

| Colour | Project | What it does |
|--------|---------|--------------|
| 🔵 cyan | **[stroke/](stroke/)** | Draw mouse strokes and export them as real Rive (`.riv`) animations, with an animation-speed (easing) editor, global transparency, timeline, groups, and undo. |
| ⚪ | *more drying…* | empty wells on the palette are reserved for future tools. |

## Running

Every tool is a static page — no build step. Serve the repo root and open a
project, or open a project's `index.html` directly:

```bash
python3 -m http.server 8000
# http://localhost:8000/            → the palette
# http://localhost:8000/stroke/     → the Stroke app
```

## Adding a project

1. Drop the project in its own folder (e.g. `mytool/`).
2. Add a row to the `projects` array in the root [`index.html`](index.html) with a
   colour and `href: "./mytool/"`.
