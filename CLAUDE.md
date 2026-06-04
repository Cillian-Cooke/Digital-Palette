# Digital Palette — project guide

A monorepo of small, self-contained, **dependency-free static** design tools.
One folder per tool; the root [`index.html`](index.html) is the palette landing
page (each colour dab links to a tool). No build step — serve the repo root and
open a tool. Add a tool: drop a folder in, add a row to the `projects` array in
the root `index.html`.

- **stroke/** — draw mouse strokes → export real `.riv` files (hand-written Rive
  binary writer). Easing editor, global transparency, line smoothing, live paint
  preview, pickable canvas size, timeline, groups, undo.
- **grid/** — a field of four Rive animations (grass · trees · rocks · water)
  scattered into natural clumps (per-type value-noise) that you grow with the
  cursor: tiles near the pointer play their grow-in forward (latched) and stay.
  Live per-type density controls + regenerate.

`**/test.riv` is gitignored (it's a generated fixture). Run the stroke checks:
`node stroke/selftest.mjs` (structural) and `node stroke/gen.mjs` (writes
`test.riv`). The whole site assumes it's served over http (see Rive note below).

---

# Rive — everything learned the hard way

There are two distinct Rive concerns here: **writing** `.riv` files (stroke), and
**playing** them at runtime (grid). They share nothing in code.

## 1. Writing `.riv` from scratch (stroke/index.html §8)

- The exporter hand-writes the binary: `RIVE` magic, varuint header (major **7**,
  minor 0, fileId), a property **ToC** (sorted keys + a 2-bits-per-key backing-type
  bitmap), then the object stream. Verified against `@rive-app/canvas` 2.21.6.
- Core/property/type keys live in the `T` / `P` / `C` tables in §8. Gotchas baked
  into the code (keep them): emit shapes in **reverse** array order (importer
  paints earlier-declared drawables on top); nudge a knot sub-pixel on
  axis-aligned paths (zero-area bbox gets dropped by trim/stroke tessellation);
  `KeyFrameDouble` interp is **linear only**, so curves (easing) must be **sampled
  into multiple keyframes**; frames must be **strictly increasing** per property.
- `selftest.mjs` parses the output back with the real header/ToC/object scan; it
  evals the page's `<script>` with a stubbed DOM. If you change the script's
  bootstrap or element refs, keep the stub working (guard DOM access, e.g.
  `Array.from(el.children || [])`).

## 2. Playing `.riv` at runtime — runtime packages

- **`@rive-app/canvas`** — classic-script UMD, global `rive`; high-level
  `new rive.Rive({ src, canvas, autoplay, layout })`. WebGL-backed: renders fine
  to a **visible** canvas, but you **cannot read its pixels** (`getImageData` /
  `drawImage` from another tick return blank — drawing buffer isn't preserved).
  Fine for simple single-canvas playback; useless for compositing/tiling.
- **`@rive-app/canvas-advanced`** — low-level control, needed for tiling. It is an
  **ES module** (`canvas_advanced.mjs`, `package.json` main); the default export is
  an async factory. Load it: `const rive = await (await import('./rive/canvas_advanced.mjs')).default({ locateFile })`.

## 3. canvas-advanced specifics (grid/ uses all of these)

- **wasm path:** the build requests `canvas_advanced.wasm`, but the package ships
  it as **`rive.wasm`**. `locateFile` MUST remap it and return an **absolute** URL:
  `locateFile: f => new URL(f.endsWith('.wasm') ? 'rive/rive.wasm' : 'rive/'+f, location.href).href`.
- **Vendor it.** Don't depend on a CDN at runtime — copy `canvas_advanced.mjs` +
  `rive.wasm` into the tool (`grid/rive/`) so it's self-contained.
- **API:** `file.defaultArtboard()` → `artboard.animationByIndex(0)` (a
  `LinearAnimation`) → `new rive.LinearAnimationInstance(la, artboard)`.
  - `la.duration` is in **frames**, `la.fps` is fps → `durationSeconds = duration/fps`.
  - `inst.time` is **settable, in seconds**. To pose a specific moment:
    `inst.time = seconds; inst.apply(1.0); artboard.advance(0);` then draw.
  - `rive.makeRenderer(canvas)` → a 2D CanvasRenderer (Proxy). Draw with
    `renderer.align(rive.Fit.contain, rive.Alignment.center, {minX,minY,maxX,maxY}, artboard.bounds)`,
    `save/restore/translate/rotate/transform`, then `artboard.draw(renderer)`.
- **`flush()` is a NO-OP.** The renderer batches draw closures into `renderer.H`
  (a real array, reachable through the Proxy). The runtime normally drains them on
  its **own** internal rAF, one frame later. Two ways to actually get pixels:
  1. Run a continuous `rive.requestAnimationFrame(loop)` and read the canvas **one
     frame behind**. Do NOT chain `rive.requestAnimationFrame` one-frame-at-a-time
     to step through poses — it **stalls after ~2 frames**.
  2. **Flush manually** (used for the filmstrip): after building commands,
     `const H = renderer.H; for (const fn of H) fn(); H.length = 0;` — renders
     synchronously and the canvas is immediately readable.
- **No per-draw opacity.** The renderer has no alpha lever; the 2D context's
  `globalAlpha` is clobbered by each paint, and `artboard.opacity` isn't a real
  property. To vary opacity/rotation **per instance**, render the artboard to one
  tile canvas, then composite it yourself onto a plain 2D canvas with `drawImage`
  + `globalAlpha`/transform. (grid/ pre-renders a filmstrip and blits per cell.)
- **Context limit:** browsers cap WebGL contexts (~16), so **one** Rive instance
  + tiling/filmstrip — never 100 instances.

## 4. Serving & file:// 

ES-module `import()` and `fetch()` of the `.riv`/`.wasm` are **blocked on
`file://`** (null origin). Tools that use the runtime must be served over http
(`python3 -m http.server`, open `http://localhost:8000/grid/`). grid/ detects
`location.protocol === 'file:'` and shows a help message instead of failing
silently. The stroke editor is pure canvas/JS and works from `file://`.

## 5. The bundled animations (grid/grass · trees · rocks · water .riv)

All are **stroke exports**: artboard `Main`, one looping linear animation `Play`.
They draw on (trim 0→1) then hold, then blank on the very last frame — so grid/
picks the **last full-coverage frame** as "fully grown", never the blank end
(measure coverage per pre-rendered frame). The feature .rivs already include their
own grass, so tiles are drawn one-`.riv`-per-cell (no stacking). Swap in any `.riv`;
a **square** artboard tiles cleanest. To re-derive duration/structure at runtime, log
`Object.getOwnPropertyNames(Object.getPrototypeOf(obj))` on the wasm wrappers —
names are minified, so probe at runtime rather than reading the `.mjs`.

## Debugging Rive headlessly

`google-chrome --headless=new --no-sandbox --virtual-time-budget=7000
--screenshot=out.png URL` is the source of truth (the on-screen composite).
`getImageData`/`drawImage` readback of a Rive-rendered canvas is unreliable unless
you used the manual-flush path above — trust screenshots over pixel sampling.

Caveat for **time-based** behaviour (per-frame `requestAnimationFrame` integration
of a value, e.g. grid/'s paint progress): `--virtual-time-budget` does **not**
reliably advance rAF `dt`, so values barely climb and screenshots look stuck
mid-animation. Don't conclude the logic is broken — verify by cranking the speed
constant way up (so it completes in a frame or two) or test the integration logic
in Node separately. The pre-render filmstrip itself is deterministic and fine to
screenshot.
