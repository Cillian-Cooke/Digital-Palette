// Structural self-check for the Lockup .riv exporter (Fill + closed paths).
import { readFileSync } from 'node:fs';

const html = readFileSync(new URL('./index.html', import.meta.url), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];

const noop = () => {};
const fakeCtx = new Proxy({}, { get: () => noop, set: () => true });
function fakeEl(id) {
  return {
    id, style: {}, width: 0, height: 0, disabled: false, value: '',
    clientWidth: id === 'tlScroll' ? 1200 : 800,
    clientHeight: id === 'tlScroll' ? 90 : 600,
    classList: { add: noop, remove: noop, toggle: noop, contains: () => false },
    getContext: () => fakeCtx,
    getBoundingClientRect: () => ({ width: 800, height: 600, left: 0, top: 0 }),
    addEventListener: noop, setPointerCapture: noop, removeChild: noop, appendChild: noop, remove: noop,
    getAttribute: () => null, setAttribute: noop, closest: () => null, querySelector: () => null,
    set innerHTML(_v) {}, get innerHTML() { return ''; },
    set textContent(_v) {}, get textContent() { return ''; },
    set onclick(_v) {}, set onchange(_v) {}, set oninput(_v) {},
    children: [],
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
globalThis.getComputedStyle = () => ({ getPropertyValue: () => '#8ee06a' });
globalThis.performance = globalThis.performance || { now: () => 0 };
globalThis.navigator = { clipboard: { writeText: noop } };

(0, eval)(script + ';globalThis.__exportRiv=exportRiv;globalThis.__buildPadlock=buildPadlock;');
const { __exportRiv: exportRiv, __buildPadlock: buildPadlock } = globalThis;

const W = 512, H = 512;
const layers = buildPadlock(W, H);
layers.forEach((l, i) => {
  const rest = l.rest;
  l.timelineStart = i * 0.1;
  l.timelineDuration = 0.45;
  l.holdToEnd = true;
  l.easing = [0.42, 0, 0.58, 1];
  if (l.name === 'Shackle') {
    l.offsetStart = { x: rest.x, y: rest.y - 40 };
    l.useTrim = false;
  } else if (l.name === 'Body') {
    l.offsetStart = { x: rest.x, y: rest.y + 30 };
  } else {
    l.offsetStart = { x: rest.x, y: rest.y + 8 };
  }
  l.offsetEnd = { x: rest.x, y: rest.y };
});
const mouth = layers.find(l => l.name === 'Mouth');
if (mouth) mouth.useTrim = true;

const bytes = exportRiv(layers, W, H, 1);

let pos = 0;
const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
const fail = [];
const ok = (cond, msg) => { if (!cond) fail.push(msg); };

function readVarUint() { let r = 0, s = 0, b; do { b = bytes[pos++]; r |= (b & 0x7f) << s; s += 7; } while (b & 0x80); return r >>> 0; }
function readU32() { const v = dv.getUint32(pos, true); pos += 4; return v >>> 0; }
function readF32() { const v = dv.getFloat32(pos, true); pos += 4; return v; }
function readStr() { const n = readVarUint(); const s = Buffer.from(bytes.slice(pos, pos + n)).toString('utf8'); pos += n; return s; }

const magic = String.fromCharCode(bytes[0], bytes[1], bytes[2], bytes[3]); pos = 4;
ok(magic === 'RIVE', `magic should be RIVE, got "${magic}"`);
const major = readVarUint(), minor = readVarUint(), fileId = readVarUint();
ok(major === 7, `major version should be 7, got ${major}`);
ok(minor === 0, `minor version should be 0, got ${minor}`);

const keys = [];
for (let k = readVarUint(); k !== 0; k = readVarUint()) keys.push(k);
const codeOf = new Map();
const words = Math.ceil(keys.length / 4);
const bitmap = []; for (let i = 0; i < words; i++) bitmap.push(readU32());
for (let i = 0; i < keys.length; i++) codeOf.set(keys[i], (bitmap[i >> 2] >> ((i % 4) * 2)) & 3);
ok([...codeOf.values()].every(c => c >= 0 && c <= 3), 'all ToC codes in 0..3');
ok(keys.every((k, i) => i === 0 || k > keys[i - 1]), 'ToC keys strictly ascending');

// bool + uint share ToC code 0; decode bools by known property key
const BOOL_KEYS = new Set([32]); // isClosed
const objects = [];
while (pos < bytes.length) {
  const typeKey = readVarUint();
  const props = {};
  for (;;) {
    const pk = readVarUint();
    if (pk === 0) break;
    ok(codeOf.has(pk), `property key ${pk} present in ToC`);
    const code = codeOf.get(pk);
    if (code === 0) {
      if (BOOL_KEYS.has(pk)) props[pk] = bytes[pos++];
      else props[pk] = readVarUint();
    } else if (code === 1) props[pk] = readStr();
    else if (code === 2) props[pk] = readF32();
    else if (code === 3) props[pk] = readU32();
    else throw new Error('bad code ' + code);
  }
  objects.push({ typeKey, props });
}
ok(pos === bytes.length, `stream consumed exactly (pos=${pos}, len=${bytes.length})`);

const T = {
  Backboard: 23, Artboard: 1, Shape: 3, PointsPath: 16, CubicVertex: 6,
  Fill: 20, Stroke: 24, SolidColor: 18, TrimPath: 47,
  LinearAnimation: 31, KeyedObject: 25, KeyedProperty: 26, KeyFrameDouble: 30,
};
const count = t => objects.filter(o => o.typeKey === t).length;
const n = layers.length;
const nFill = layers.filter(l => l.paint === 'fill').length;
const nStroke = layers.filter(l => l.paint === 'stroke').length;
const nTrim = layers.filter(l => l.paint === 'stroke' && l.useTrim).length;
const nClosed = layers.filter(l => l.closed).length;

ok(objects[0].typeKey === T.Backboard, 'first object is Backboard');
ok(objects[1].typeKey === T.Artboard, 'second object is Artboard');
ok(Math.abs(objects[1].props[7] - W) < 0.5, `artboard width ≈ ${W}`);
ok(Math.abs(objects[1].props[8] - H) < 0.5, `artboard height ≈ ${H}`);
ok(objects[1].props[4] === 'Main', 'artboard name Main');

ok(count(T.Shape) === n, `${n} Shape objects (got ${count(T.Shape)})`);
ok(count(T.PointsPath) === n, `${n} PointsPath objects`);
ok(count(T.Fill) === nFill, `${nFill} Fill paints (got ${count(T.Fill)})`);
ok(count(T.Stroke) === nStroke, `${nStroke} Stroke paints (got ${count(T.Stroke)})`);
ok(count(T.SolidColor) === n, `${n} SolidColor objects`);
ok(count(T.TrimPath) === nTrim, `${nTrim} TrimPath objects (got ${count(T.TrimPath)})`);
ok(count(T.LinearAnimation) === 1, '1 LinearAnimation');

const closedPaths = objects.filter(o => o.typeKey === T.PointsPath && o.props[32]);
ok(closedPaths.length === nClosed, `${nClosed} closed PointsPaths (got ${closedPaths.length})`);

const COMPONENT_TYPES = new Set([
  T.Shape, T.PointsPath, T.CubicVertex, T.Fill, T.Stroke, T.SolidColor, T.TrimPath,
]);
const indexed = [{ typeKey: T.Artboard }];
for (const o of objects.slice(2)) if (COMPONENT_TYPES.has(o.typeKey)) indexed.push(o);
const maxIndex = indexed.length - 1;

for (const o of objects) if (COMPONENT_TYPES.has(o.typeKey)) {
  const pid = o.props[5];
  ok(pid !== undefined && pid >= 0 && pid <= maxIndex, `parentId ${pid} valid for type ${o.typeKey}`);
}
for (const o of objects) if (o.typeKey === T.KeyedObject) {
  const oid = o.props[51];
  ok(oid >= 1 && oid <= maxIndex, `KeyedObject.objectId ${oid} in range`);
  const tgt = indexed[oid];
  ok(tgt && (tgt.typeKey === T.Shape || tgt.typeKey === T.TrimPath),
    `objectId ${oid} targets Shape/TrimPath (got ${tgt && tgt.typeKey})`);
}

let lastFrame = -1, kfTotal = 0, curProp = null;
for (const o of objects) {
  if (o.typeKey === T.KeyedProperty) { curProp = o.props[53]; lastFrame = -1; }
  else if (o.typeKey === T.KeyFrameDouble) {
    kfTotal++;
    ok(o.props[68] === 1, 'keyframe interp = linear');
    ok(Number.isFinite(o.props[70]), 'keyframe value finite');
    ok(o.props[67] > lastFrame, `frames strictly increasing in property ${curProp}`);
    lastFrame = o.props[67];
  }
}
const propKeys = objects.filter(o => o.typeKey === T.KeyedProperty).map(o => o.props[53]);
ok(propKeys.includes(18), 'opacity (18) keyed');
ok(propKeys.includes(115), 'trimEnd (115) keyed (mouth draw-on)');
ok(propKeys.includes(13), 'positionX (13) keyed (assemble)');
ok(propKeys.includes(14), 'positionY (14) keyed (assemble)');

console.log(`bytes: ${bytes.length}`);
console.log(`version: ${major}.${minor}  fileId: ${fileId}`);
console.log(`ToC keys (${keys.length}): ${keys.join(',')}`);
console.log(`objects: ${objects.length}  fills=${count(T.Fill)} strokes=${count(T.Stroke)} trim=${count(T.TrimPath)} keyframes=${kfTotal}`);
console.log(`artboard index space size: ${indexed.length} (indices 0..${maxIndex})`);
if (fail.length) { console.error('\nFAILURES:'); for (const f of fail) console.error('  ✗ ' + f); process.exit(1); }
console.log('\n✓ all structural checks passed');
