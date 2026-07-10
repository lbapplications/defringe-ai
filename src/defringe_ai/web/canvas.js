// Edit-screen canvas: renders board state pushed over SSE. Click selects + raises
// (server owns the z-order as an ordered list); drag moves; corner handle resizes.
// All mutations POST to the server and come back through the stream — no polling.
//
// Toolbox (left) drives an interaction mode:
//   move — drag/resize images (default)
//   dot  — click an image to drop a "surface dot" onto its invisible mask layer
// Each image carries an invisible .mask overlay; dots live in image-pixel space and are
// positioned by percentage, so they ride with the image as it moves/scales. Locking an
// image pins it (no drag/resize) so clicks land as dots cleanly.

const canvas = document.getElementById('canvas');
const els = new Map();            // name -> {node, wrap, img, mask, cap, handle, badge, lockTag}
let act = null;                   // interaction in progress: {name, node, mode, ...}
let tool = 'move';                // 'move' | 'dot'
let latest = [];                  // last state array from SSE

const baseW = a => (a.w >= a.h ? 200 : 200 * (a.w / a.h));
const byName = n => latest.find(a => a.name === n);
const selected = () => latest.find(a => a.selected) || null;
const post = (url, body) =>
  fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });

function make(name) {
  const node = document.createElement('div'); node.className = 'asset';
  const badge = document.createElement('div'); badge.className = 'badge';
  const lockTag = document.createElement('div'); lockTag.className = 'lock-tag'; lockTag.textContent = '🔒 locked';
  const wrap = document.createElement('div'); wrap.className = 'imgwrap';
  const img = document.createElement('img');
  const mask = document.createElement('div'); mask.className = 'mask';
  wrap.append(img, mask);
  const cap = document.createElement('div'); cap.className = 'cap';
  const handle = document.createElement('div'); handle.className = 'handle';
  node.append(badge, lockTag, wrap, cap, handle);
  canvas.append(node);
  node.addEventListener('mousedown', e => {
    if (e.target === handle) return;               // handle has its own listener
    onAssetDown(name, e);
  });
  handle.addEventListener('mousedown', e => startResize(name, e));
  const rec = { node, wrap, img, mask, cap, handle, badge, lockTag }; els.set(name, rec); return rec;
}

function paint(a) {
  const rec = els.get(a.name) || make(a.name);
  if (rec.node === act?.node) return;              // don't stomp what the user is holding
  rec.node.style.left = a.x + 'px';
  rec.node.style.top = a.y + 'px';
  rec.node.style.zIndex = a.z;                     // z-order = index in the server's list
  rec.img.style.width = (baseW(a) * a.scale) + 'px';
  rec.node.classList.toggle('selected', a.selected);
  rec.node.classList.toggle('editing', a.editing);
  rec.node.classList.toggle('locked', a.locked);
  rec.badge.textContent = a.editing ? `✎ editing · ${a.intent}` : '';
  rec.badge.style.display = a.editing ? 'block' : 'none';
  if (rec.img.dataset.rev !== a.rev) {
    rec.img.dataset.rev = a.rev;
    rec.img.src = `/img/${a.name}/${a.head}?v=${encodeURIComponent(a.rev)}`;
  }
  rec.node.dataset.w = a.w; rec.node.dataset.h = a.h;
  paintDots(rec, a);
  rec.cap.innerHTML = `${a.name} <span class="op">· ${a.op} · ${a.w}×${a.h} · ${Math.round(a.scale * 100)}%</span>`;
}

// dots + derived outline live on the invisible mask. Dots are % positioned; the outline
// is an SVG polygon in image-space (viewBox = w×h), so both scale/move with the image.
function paintDots(rec, a) {
  const dots = a.dots || [], outline = a.outline || [];
  const svg = outline.length >= 2
    ? `<svg class="outline" viewBox="0 0 ${a.w} ${a.h}" preserveAspectRatio="none">
         <polygon points="${outline.map(p => p.join(',')).join(' ')}" /></svg>`
    : '';
  const marks = dots.map(([x, y]) =>
    `<span class="dot" style="left:${(x / a.w) * 100}%;top:${(y / a.h) * 100}%"></span>`).join('');
  rec.mask.innerHTML = svg + marks;
}

// --- interaction ------------------------------------------------------------

function onAssetDown(name, e) {
  const a = byName(name);
  if (tool === 'dot') { addDot(name, e); e.preventDefault(); return; }
  post('/api/select', { name });                   // always select on click
  if (a && a.locked) { e.preventDefault(); return; } // locked: select only, no move
  startMove(name, e);
}

function addDot(name, e) {
  const rec = els.get(name); const a = byName(name); if (!a) return;
  const r = rec.img.getBoundingClientRect();
  const x = Math.round(((e.clientX - r.left) / r.width) * a.w);
  const y = Math.round(((e.clientY - r.top) / r.height) * a.h);
  if (x < 0 || y < 0 || x > a.w || y > a.h) return;
  a.dots = [...(a.dots || []), [x, y]];             // optimistic; SSE reconciles
  paintDots(rec, a);
  if (!a.selected) post('/api/select', { name });   // work on the image you're dotting
  post('/api/dot', { name, x, y });
}

function beginInteraction(name, node) {
  node.style.zIndex = 99999;                        // instant local raise; SSE reconciles
  node.classList.add('busy');
  post('/api/select', { name });
}

function startMove(name, e) {
  const rec = els.get(name), r = rec.node.getBoundingClientRect();
  beginInteraction(name, rec.node);
  act = { name, node: rec.node, mode: 'move', dx: e.clientX - r.left, dy: e.clientY - r.top };
  e.preventDefault();
}

function startResize(name, e) {
  const a = byName(name);
  if (tool === 'dot' || (a && a.locked)) { e.preventDefault(); e.stopPropagation(); return; }
  const rec = els.get(name), r = rec.node.getBoundingClientRect();
  beginInteraction(name, rec.node);
  act = { name, node: rec.node, img: rec.img, mode: 'resize', left: r.left,
          base: baseW({ w: +rec.node.dataset.w, h: +rec.node.dataset.h }) };
  e.preventDefault(); e.stopPropagation();
}

window.addEventListener('mousemove', e => {
  if (!act) return;
  if (act.mode === 'move') {
    act.node.style.left = (e.clientX - act.dx) + 'px';
    act.node.style.top = (e.clientY - act.dy) + 'px';
  } else {
    const s = Math.max(0.15, Math.min(6, (e.clientX - act.left - 4) / act.base));
    act.scale = s; act.img.style.width = (act.base * s) + 'px';
  }
});

window.addEventListener('mouseup', () => {
  if (!act) return;
  const a = act; act = null; a.node.classList.remove('busy');
  post('/api/move', a.mode === 'move'
    ? { name: a.name, x: parseInt(a.node.style.left), y: parseInt(a.node.style.top) }
    : { name: a.name, scale: a.scale });
});

// --- toolbox ----------------------------------------------------------------

function setTool(t) {
  tool = t;
  document.querySelectorAll('.tool-btn').forEach(b => b.classList.toggle('active', b.dataset.tool === t));
  canvas.classList.toggle('tool-dot', t === 'dot');
}
document.querySelectorAll('.tool-btn').forEach(b => b.addEventListener('click', () => setTool(b.dataset.tool)));

const lockBtn = document.getElementById('lock-btn');
const clearBtn = document.getElementById('clear-dots');
const connectBtn = document.getElementById('connect-dots');
lockBtn.addEventListener('click', () => {
  const a = selected(); if (!a) return;
  post('/api/lock', { name: a.name, locked: !a.locked });
});
clearBtn.addEventListener('click', () => {
  const a = selected(); if (!a) return;
  post('/api/dots/clear', { name: a.name });
});
connectBtn.addEventListener('click', () => {
  const a = selected(); if (!a) return;
  post('/api/connect', { name: a.name });
});

const isolateBtn = document.getElementById('isolate');
isolateBtn.addEventListener('click', () => {
  const a = selected(); if (!a) return;
  post('/api/isolate', { name: a.name });
});

const undoBtn = document.getElementById('undo-btn');
const redoBtn = document.getElementById('redo-btn');
const doUndo = () => { const a = selected(); if (a && a.can_undo) post('/api/undo', { name: a.name }); };
const doRedo = () => { const a = selected(); if (a && a.can_redo) post('/api/redo', { name: a.name }); };
undoBtn.addEventListener('click', doUndo);
redoBtn.addEventListener('click', doRedo);
window.addEventListener('keydown', e => {
  if (!(e.ctrlKey || e.metaKey) || e.key.toLowerCase() !== 'z') return;
  e.preventDefault();
  (e.shiftKey ? doRedo : doUndo)();
});

function paintToolbox() {
  const a = selected();
  document.getElementById('sel-name').textContent = a ? a.name : '— none —';
  const n = a ? (a.dots || []).length : 0;
  document.getElementById('dot-count').textContent = `${n} dot${n === 1 ? '' : 's'}`;
  lockBtn.disabled = !a;
  lockBtn.textContent = a && a.locked ? '🔒 Unlock image' : '🔓 Lock image';
  lockBtn.classList.toggle('on', !!(a && a.locked));
  clearBtn.disabled = !a || n === 0;
  connectBtn.disabled = !a || n < 3;
  isolateBtn.disabled = !a || !(a.outline && a.outline.length >= 3);
  undoBtn.disabled = !a || !a.can_undo;
  redoBtn.disabled = !a || !a.can_redo;
  const tl = a ? (a.timeline || []) : [];
  document.getElementById('timeline').innerHTML = tl.map(t => {
    const cur = t.startsWith('* '), foc = t.startsWith('~ ');
    const label = cur || foc ? t.slice(2) : t;
    return `<div class="tl-row${cur ? ' cur' : ''}${foc ? ' foc' : ''}">${label}</div>`;
  }).join('');
}

// --- one pushed stream, no polling -----------------------------------------

const es = new EventSource('/api/events');

// auto-reload: if the server restarts with new code, its build stamp changes and the
// tab reloads itself — no more manual hard-refresh, no more frozen tabs.
let build = null;
es.addEventListener('build', e => {
  if (build !== null && build !== e.data) location.reload();
  build = e.data;
});

es.onmessage = e => {
  latest = JSON.parse(e.data);
  const seen = new Set(latest.map(a => a.name));
  for (const [name, rec] of els) if (!seen.has(name)) { rec.node.remove(); els.delete(name); }
  latest.forEach(paint);
  paintToolbox();
};
