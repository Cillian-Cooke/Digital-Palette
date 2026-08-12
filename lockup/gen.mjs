// Writes lockup/test.riv from the real exporter (DOM stubbed).
import { readFileSync, writeFileSync } from 'node:fs';
const html = readFileSync(new URL('./index.html', import.meta.url), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];

const noop = () => {};
const fakeCtx = new Proxy({}, { get: () => noop, set: () => true });
function fakeEl(id) {
  return {
    id, style: {}, width: 0, height: 0, disabled: false, value: '',
    clientWidth: 800, clientHeight: 600,
    classList: { add: noop, remove: noop, toggle: noop, contains: () => false },
    getContext: () => fakeCtx,
    getBoundingClientRect: () => ({ width: 800, height: 600, left: 0, top: 0 }),
    addEventListener: noop, appendChild: noop, remove: noop,
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

(0, eval)(script + ';globalThis.__e=exportRiv;globalThis.__b=buildPadlock;');
const { __e: exportRiv, __b: buildPadlock } = globalThis;

const W = 512, H = 512;
const layers = buildPadlock(W, H);
layers.forEach((l, i) => {
  const rest = l.rest;
  l.timelineStart = i * 0.1;
  l.timelineDuration = 0.45;
  l.holdToEnd = true;
  l.easing = [0.16, 1, 0.3, 1];
  if (l.name === 'Shackle') l.offsetStart = { x: rest.x, y: rest.y - 50 };
  else if (l.name === 'Body') l.offsetStart = { x: rest.x, y: rest.y + 40 };
  else if (l.name === 'Eye L') l.offsetStart = { x: rest.x - 20, y: rest.y };
  else if (l.name === 'Eye R') l.offsetStart = { x: rest.x + 20, y: rest.y };
  else l.offsetStart = { x: rest.x, y: rest.y + 12 };
  l.offsetEnd = { ...rest };
  if (l.paint === 'stroke') l.useTrim = true;
});
const bytes = exportRiv(layers, W, H, 1);
writeFileSync(new URL('./test.riv', import.meta.url), bytes);
console.log('wrote test.riv', bytes.length, 'bytes');
