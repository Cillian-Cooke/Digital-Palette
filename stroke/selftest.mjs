// Structural self-check for the Stroke .riv exporter.
// Loads the REAL exporter from index.html (DOM stubbed), generates a file for a
// synthetic scene, then parses it back using Rive's verified header/ToC/object
// scan to catch encoding/structure errors before the browser runtime check.
import { readFileSync } from 'node:fs';

/* ---- 1) stub a minimal DOM and eval the app's <script> --------------------*/
const html = readFileSync(new URL('./index.html', import.meta.url), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];

const noop = () => {};
const fakeCtx = new Proxy({}, { get: (_, p) => (p in {} ? undefined : (typeof p === 'string' ? noop : undefined)), set: () => true });
function fakeEl(id) {
  return {
    id, style: {}, width: 0, height: 0, disabled: false, value: '',
    clientWidth: id === 'graph' ? 400 : (id === 'timelineSvg' || id === 'tlScroll') ? 1200 : 800,
    clientHeight: id === 'graph' ? 600 : id === 'timelineSvg' ? 80 : (id === 'tlScroll' ? 90 : 600),
    classList: { add: noop, remove: noop, toggle: noop, contains: () => false },
    getContext: () => fakeCtx,
    getBoundingClientRect: () => ({ width: 800, height: 600, left: 0, top: 0 }),
    addEventListener: noop, setPointerCapture: noop, removeChild: noop, appendChild: noop, remove: noop,
    getAttribute: () => null, setAttribute: noop, closest: () => null, querySelector: () => null,
    set innerHTML(_v) {}, get innerHTML() { return ''; },
    set textContent(_v) {}, get textContent() { return ''; },
    set onclick(_v) {}, set onchange(_v) {}, set oninput(_v) {},
  };
}
const els = {};
globalThis.document = {
  getElementById: id => (els[id] ||= fakeEl(id)),
  createElement: () => fakeEl('a'),
  documentElement: { style: {} },
  body: { appendChild: noop },
};
globalThis.window = { addEventListener: noop, devicePixelRatio: 1 };
globalThis.requestAnimationFrame = noop;
globalThis.getComputedStyle = () => ({ getPropertyValue: () => '#6ad1ff' });
globalThis.performance = globalThis.performance || { now: () => 0 };
globalThis.Path2D = class { moveTo(){} bezierCurveTo(){} };

// expose the pure functions we need after eval
const exposed = ';globalThis.__exportRiv=exportRiv;globalThis.__fitCurve=fitCurve;globalThis.__centroid=centroid;';
(0, eval)(script + exposed);
const exportRiv = globalThis.__exportRiv, fitCurve = globalThis.__fitCurve, centroid = globalThis.__centroid;

/* ---- 2) build a synthetic scene & export ---------------------------------*/
function makeStroke(id, pts, nodes, drift) {
  const segments = fitCurve(pts, 6);
  const c = centroid({ segments });
  return {
    id, hue: 120, segments, nodes,
    timelineStart: 0.3, timelineDuration: 1.2, holdDuration: 0.5,
    offsetStart: { x: c.x, y: c.y },
    offsetEnd: drift ? { x: c.x + 40, y: c.y - 20 } : { x: c.x, y: c.y },
  };
}
const strokes = [
  makeStroke('a', [{x:100,y:100},{x:150,y:80},{x:200,y:140},{x:260,y:90},{x:320,y:160}],
    [{t:0,opacity:1,segmentIndex:0,segmentT:0},{t:0.5,opacity:0.25,segmentIndex:0,segmentT:0.5},{t:1,opacity:0.9,segmentIndex:0,segmentT:1}], true),
  makeStroke('b', [{x:80,y:300},{x:200,y:260},{x:340,y:320}],
    [{t:0,opacity:1,segmentIndex:0,segmentT:0},{t:1,opacity:0.5,segmentIndex:0,segmentT:1}], false),
];
const W = 800, H = 600;
const bytes = exportRiv(strokes, W, H);

/* ---- 3) faithful reader (mirrors runtime_header.read + object scan) -------*/
let pos = 0;
const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
const fail = [];
const ok = (cond, msg) => { if (!cond) fail.push(msg); };

function readVarUint() { let r = 0, s = 0, b; do { b = bytes[pos++]; r |= (b & 0x7f) << s; s += 7; } while (b & 0x80); return r >>> 0; }
function readU32() { const v = dv.getUint32(pos, true); pos += 4; return v >>> 0; }
function readF32() { const v = dv.getFloat32(pos, true); pos += 4; return v; }
function readStr() { const n = readVarUint(); const s = Buffer.from(bytes.slice(pos, pos + n)).toString('utf8'); pos += n; return s; }

// header
const magic = String.fromCharCode(bytes[0], bytes[1], bytes[2], bytes[3]); pos = 4;
ok(magic === 'RIVE', `magic should be RIVE, got "${magic}"`);
const major = readVarUint(), minor = readVarUint(), fileId = readVarUint();
ok(major === 7, `major version should be 7, got ${major}`);
ok(minor === 0, `minor version should be 0, got ${minor}`);

// ToC keys + bitmap
const keys = [];
for (let k = readVarUint(); k !== 0; k = readVarUint()) keys.push(k);
const codeOf = new Map();
const words = Math.ceil(keys.length / 4);
const bitmap = []; for (let i = 0; i < words; i++) bitmap.push(readU32());
for (let i = 0; i < keys.length; i++) codeOf.set(keys[i], (bitmap[i >> 2] >> ((i % 4) * 2)) & 3);
ok([...codeOf.values()].every(c => c >= 0 && c <= 3), 'all ToC codes in 0..3');
ok(keys.every((k, i) => i === 0 || k > keys[i - 1]), 'ToC keys strictly ascending (we sort them)');

// object scan
const FIELD = { 0: 'uint', 1: 'str', 2: 'dbl', 3: 'color' };
function readValueByCode(code) {
  if (code === 0) return readVarUint();
  if (code === 1) return readStr();
  if (code === 2) return readF32();
  if (code === 3) return readU32();
  throw new Error('bad code ' + code);
}
const objects = [];
while (pos < bytes.length) {
  const typeKey = readVarUint();
  const props = {};
  for (;;) {
    const pk = readVarUint();
    if (pk === 0) break;
    ok(codeOf.has(pk), `property key ${pk} present in ToC`);
    props[pk] = readValueByCode(codeOf.get(pk));
  }
  objects.push({ typeKey, props });
}
ok(pos === bytes.length, `stream consumed exactly (pos=${pos}, len=${bytes.length})`);

/* ---- 4) semantic structure assertions ------------------------------------*/
const T = { Backboard:23, Artboard:1, Shape:3, PointsPath:16, CubicVertex:6, Stroke:24, SolidColor:18, TrimPath:47, LinearAnimation:31, KeyedObject:25, KeyedProperty:26, KeyFrameDouble:30 };
const count = t => objects.filter(o => o.typeKey === t).length;
const n = strokes.length;

ok(objects[0].typeKey === T.Backboard, 'first object is Backboard');
ok(objects[1].typeKey === T.Artboard, 'second object is Artboard');
ok(Math.abs(objects[1].props[7] - W) < 0.5, `artboard width ≈ ${W} (got ${objects[1].props[7]})`);
ok(Math.abs(objects[1].props[8] - H) < 0.5, `artboard height ≈ ${H} (got ${objects[1].props[8]})`);
ok(objects[1].props[4] === 'Main', `artboard name "Main" (got "${objects[1].props[4]}")`);

ok(count(T.Shape) === n, `${n} Shape objects (got ${count(T.Shape)})`);
ok(count(T.PointsPath) === n, `${n} PointsPath objects`);
ok(count(T.Stroke) === n, `${n} Stroke paints`);
ok(count(T.SolidColor) === n, `${n} SolidColor objects`);
ok(count(T.TrimPath) === n, `${n} TrimPath objects`);
ok(count(T.LinearAnimation) === 1, `1 LinearAnimation (got ${count(T.LinearAnimation)})`);
const expectVerts = strokes.reduce((a, s) => a + s.segments.length + 1, 0);
ok(count(T.CubicVertex) === expectVerts, `${expectVerts} CubicDetachedVertex objects (got ${count(T.CubicVertex)})`);

// rebuild artboard index space (artboard = index 0, then each Component in order)
const COMPONENT_TYPES = new Set([T.Shape, T.PointsPath, T.CubicVertex, T.Stroke, T.SolidColor, T.TrimPath]);
const indexed = [{ typeKey: T.Artboard }]; // index 0
for (const o of objects.slice(2)) if (COMPONENT_TYPES.has(o.typeKey)) indexed.push(o);
const maxIndex = indexed.length - 1;

// every parentId resolves within the index space
for (const o of objects) if (COMPONENT_TYPES.has(o.typeKey)) {
  const pid = o.props[5];
  ok(pid !== undefined && pid >= 0 && pid <= maxIndex, `parentId ${pid} valid for type ${o.typeKey}`);
}
// every KeyedObject.objectId resolves, and points at a Shape or TrimPath
for (const o of objects) if (o.typeKey === T.KeyedObject) {
  const oid = o.props[51];
  ok(oid >= 1 && oid <= maxIndex, `KeyedObject.objectId ${oid} in range 1..${maxIndex}`);
  const tgt = indexed[oid];
  ok(tgt && (tgt.typeKey === T.Shape || tgt.typeKey === T.TrimPath), `objectId ${oid} targets Shape/TrimPath (got ${tgt && tgt.typeKey})`);
}
// keyframes strictly increasing within each KeyedProperty; interp=1 (linear); values finite
let curProp = null, lastFrame = -1, kfTotal = 0;
for (const o of objects) {
  if (o.typeKey === T.KeyedProperty) { curProp = o.props[53]; lastFrame = -1; }
  else if (o.typeKey === T.KeyFrameDouble) {
    kfTotal++;
    ok(o.props[68] === 1, `keyframe interp = linear(1) (got ${o.props[68]})`);
    ok(Number.isFinite(o.props[70]), 'keyframe value finite');
    ok(o.props[67] > lastFrame, `frames strictly increasing in property ${curProp} (${o.props[67]} > ${lastFrame})`);
    lastFrame = o.props[67];
  }
}
// trimEnd present (115), opacity present (18); both 13/14 drift only for stroke 'a'
const propKeys = objects.filter(o => o.typeKey === T.KeyedProperty).map(o => o.props[53]);
ok(propKeys.includes(115), 'trimEnd (115) keyed');
ok(propKeys.includes(18), 'opacity (18) keyed');
ok(propKeys.filter(k => k === 13).length === 1, 'positionX (13) keyed for exactly the 1 drifting stroke');
ok(propKeys.filter(k => k === 14).length === 1, 'positionY (14) keyed for exactly the 1 drifting stroke');

/* ---- report ---------------------------------------------------------------*/
console.log(`bytes: ${bytes.length}`);
console.log(`version: ${major}.${minor}  fileId: ${fileId}`);
console.log(`ToC keys (${keys.length}): ${keys.join(',')}`);
console.log(`objects: ${objects.length}  (verts=${count(T.CubicVertex)}, keyedObjects=${count(T.KeyedObject)}, keyframes=${kfTotal})`);
console.log(`artboard index space size: ${indexed.length} (indices 0..${maxIndex})`);
if (fail.length) { console.error('\nFAILURES:'); for (const f of fail) console.error('  ✗ ' + f); process.exit(1); }
console.log('\n✓ all structural checks passed');
