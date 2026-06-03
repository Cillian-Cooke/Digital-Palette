// Generates test.riv from the REAL exporter (DOM stubbed) for the headless
// runtime check. Same loader approach as selftest.mjs.
import { readFileSync, writeFileSync } from 'node:fs';
const html = readFileSync(new URL('./index.html', import.meta.url), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];

const noop = () => {};
const fakeCtx = new Proxy({}, { get: () => noop, set: () => true });
function fakeEl(id){ return { id, style:{}, width:0, height:0, disabled:false, value:'',
  clientWidth: id==='graph'?400:(id==='timelineSvg'||id==='tlScroll')?1200:800,
  clientHeight: id==='graph'?600:id==='timelineSvg'?80:(id==='tlScroll'?90:600),
  classList:{add:noop,remove:noop,toggle:noop,contains:()=>false},
  getContext:()=>fakeCtx, getBoundingClientRect:()=>({width:800,height:600,left:0,top:0}),
  addEventListener:noop,setPointerCapture:noop,appendChild:noop,remove:noop,getAttribute:()=>null,setAttribute:noop,closest:()=>null,querySelector:()=>null,
  set innerHTML(_v){}, get innerHTML(){return '';}, set textContent(_v){}, get textContent(){return '';}, set onclick(_v){}, set onchange(_v){}, set oninput(_v){} }; }
const els={};
globalThis.document={ getElementById:id=>(els[id]||=fakeEl(id)), createElement:()=>fakeEl('a'), documentElement:{style:{}}, body:{appendChild:noop} };
globalThis.window={ addEventListener:noop, devicePixelRatio:1 };
globalThis.requestAnimationFrame=noop;
globalThis.getComputedStyle=()=>({getPropertyValue:()=>'#6ad1ff'});
globalThis.performance=globalThis.performance||{now:()=>0};
globalThis.Path2D=class{moveTo(){}bezierCurveTo(){}};
(0,eval)(script + ';globalThis.__e=exportRiv;globalThis.__f=fitCurve;globalThis.__c=centroid;');
const { __e:exportRiv, __f:fitCurve, __c:centroid } = globalThis;

function mk(id, pts, nodes, drift, thickness, colour){
  const segments=fitCurve(pts,6); const c=centroid({segments});
  return { id, hue:120, segments, nodes, thickness, colour,
    timelineStart:0.3, timelineDuration:1.2, holdDuration:0.5,
    offsetStart:{x:c.x,y:c.y}, offsetEnd: drift?{x:c.x+40,y:c.y-20}:{x:c.x,y:c.y} };
}
const strokes=[
  mk('a',[{x:100,y:100},{x:150,y:80},{x:200,y:140},{x:260,y:90},{x:320,y:160}],
    [{t:0,opacity:1,segmentIndex:0,segmentT:0},{t:0.5,opacity:0.25,segmentIndex:0,segmentT:0.5},{t:1,opacity:0.9,segmentIndex:0,segmentT:1}],true, 8, '#ff5a3c'),
  mk('b',[{x:80,y:300},{x:200,y:260},{x:340,y:320}],
    [{t:0,opacity:1,segmentIndex:0,segmentT:0},{t:1,opacity:0.5,segmentIndex:0,segmentT:1}],false, 3, '#6ad1ff'),
];
const bytes=exportRiv(strokes,800,600);
writeFileSync(new URL('./test.riv', import.meta.url), bytes);
console.log('wrote test.riv', bytes.length, 'bytes');
