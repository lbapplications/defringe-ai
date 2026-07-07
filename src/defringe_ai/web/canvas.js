// Edit-screen canvas: renders board state pushed over SSE. Click selects + raises
// (server owns the z-order as an ordered list); drag moves; corner handle resizes.
// All mutations POST to the server and come back through the stream — no polling.

const canvas = document.getElementById('canvas');
const els = new Map();            // name -> {node, img, cap, handle}
let act = null;                   // interaction in progress: {name, node, mode, ...}

const baseW = a => (a.w >= a.h ? 200 : 200 * (a.w / a.h));
const post = (url, body) =>
  fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });

function make(name) {
  const node = document.createElement('div'); node.className = 'asset';
  const img = document.createElement('img');
  const cap = document.createElement('div'); cap.className = 'cap';
  const handle = document.createElement('div'); handle.className = 'handle';
  node.append(img, cap, handle);
  canvas.append(node);
  node.addEventListener('mousedown', e => { if (e.target !== handle) startMove(name, e); });
  handle.addEventListener('mousedown', e => startResize(name, e));
  const rec = { node, img, cap, handle }; els.set(name, rec); return rec;
}

function paint(a) {
  const rec = els.get(a.name) || make(a.name);
  if (rec.node === act?.node) return;          // don't stomp what the user is holding
  rec.node.style.left = a.x + 'px';
  rec.node.style.top = a.y + 'px';
  rec.node.style.zIndex = a.z;                 // z-order = index in the server's list
  rec.img.style.width = (baseW(a) * a.scale) + 'px';
  rec.node.classList.toggle('selected', a.selected);
  if (rec.img.dataset.rev !== a.rev) {
    rec.img.dataset.rev = a.rev;
    rec.img.src = `/img/${a.name}/${a.head}?v=${encodeURIComponent(a.rev)}`;
  }
  rec.node.dataset.w = a.w; rec.node.dataset.h = a.h;
  rec.cap.innerHTML = `${a.name} <span class="op">· ${a.op} · ${a.w}×${a.h} · ${Math.round(a.scale * 100)}%</span>`;
}

function beginInteraction(name, node) {
  node.style.zIndex = 99999;                   // instant local raise; SSE reconciles to the real order
  node.classList.add('busy');
  post('/api/select', { name });               // server: select + bring to front
}

function startMove(name, e) {
  const rec = els.get(name), r = rec.node.getBoundingClientRect();
  beginInteraction(name, rec.node);
  act = { name, node: rec.node, mode: 'move', dx: e.clientX - r.left, dy: e.clientY - r.top };
  e.preventDefault();
}

function startResize(name, e) {
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

// one pushed stream, no polling
new EventSource('/api/events').onmessage = e => {
  const state = JSON.parse(e.data);
  const seen = new Set(state.map(a => a.name));
  for (const [name, rec] of els) if (!seen.has(name)) { rec.node.remove(); els.delete(name); }
  state.forEach(paint);
};
