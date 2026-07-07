"""The edit screen — a shared canvas of the assets in play.

Each workspace's current image is placed on a canvas at its stored (x, y, scale).
Assets are movable and resizable two ways:
  - by the agent, via the `move` tool (arranges/scales the layout while it works)
  - by a human: drag to move, drag the corner handle to expand/contract

Updates are **pushed**, not polled: the browser opens one Server-Sent-Events stream
and the server emits state only when it actually changes (an agent move/edit, a new
asset). A drag/resize updates locally on the spot and persists on release, so it
never fights the stream.

`/`            canvas / edit screen (SSE-driven, draggable, resizable)
`/chains`      the per-asset reversible edit chains, HEAD marked
`/api/events`  SSE state stream    `/api/move`  persist a drag/resize
"""

from __future__ import annotations

import asyncio
import json
import os

import uvicorn
from starlette.applications import Starlette
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from starlette.routing import Route

from .workspace import Workspace, _get_active


# --- shared data -----------------------------------------------------------

def _state(home: str) -> list[dict]:
    active = _get_active(home)
    out = []
    for name in Workspace.list_all(home):
        try:
            with open(os.path.join(home, name, "manifest.json")) as f:
                m = json.load(f)
        except FileNotFoundError:
            continue
        head = m["head"]
        img = os.path.join(home, name, m["steps"][head]["file"])
        try:
            from PIL import Image

            w, h = Image.open(img).size
        except Exception:
            w, h = 0, 0
        c = {"x": 40, "y": 40, "scale": 1.0, **m.get("canvas", {})}
        out.append({
            "name": name, "x": c["x"], "y": c["y"], "scale": c["scale"],
            "head": head, "steps": len(m["steps"]), "w": w, "h": h,
            "op": m["steps"][head]["op"], "active": name == active,
            "rev": f'{head}-{len(m["steps"])}',
        })
    return out


def _sig(state: list[dict]) -> str:
    """A cheap signature of everything the canvas cares about — used to push only on change."""
    return json.dumps([(a["name"], a["x"], a["y"], a["scale"], a["rev"], a["active"]) for a in state])


# --- canvas / edit screen --------------------------------------------------

_CANVAS = """<!doctype html><meta charset=utf-8><title>defringe-ai · edit</title>
<style>
  :root { color-scheme: dark light; }
  body { margin:0; font:13px system-ui,sans-serif; background:#0d0d0f; color:#ddd; overflow:hidden; }
  header { position:fixed; z-index:10; top:0; left:0; right:0; display:flex; gap:16px;
           align-items:center; padding:9px 14px; background:#0d0d0fcc; backdrop-filter:blur(6px);
           border-bottom:1px solid #262629; }
  header b { color:#6cf; } header a { color:#888; text-decoration:none; }
  header .hint { color:#555; margin-left:auto; }
  #canvas { position:absolute; inset:0; }
  .asset { position:absolute; cursor:grab; user-select:none;
           background-image:
             linear-gradient(45deg,#ffffff10 25%,transparent 25%,transparent 75%,#ffffff10 75%),
             linear-gradient(45deg,#ffffff10 25%,transparent 25%,transparent 75%,#ffffff10 75%);
           background-size:16px 16px; background-position:0 0,8px 8px;
           border:1px solid #ffffff14; border-radius:6px; padding:4px; }
  .asset.active { border-color:#6cf; box-shadow:0 0 0 1px #6cf6; }
  .asset.busy { cursor:grabbing; z-index:99; box-shadow:0 8px 30px #000a; }
  .asset img { display:block; pointer-events:none; }
  .asset .cap { font-size:11px; color:#aaa; padding:3px 2px 1px; white-space:nowrap; }
  .asset .cap .op { color:#666; }
  .handle { position:absolute; right:-6px; bottom:-6px; width:14px; height:14px;
            background:#6cf; border:2px solid #0d0d0f; border-radius:50%;
            cursor:nwse-resize; opacity:0; transition:opacity .12s; }
  .asset:hover .handle, .asset.active .handle { opacity:1; }
</style>
<header><b>defringe-ai</b> · edit screen <a href="/chains">edit chains →</a>
  <span class="hint">drag to move · drag corner to resize · pushed live</span></header>
<div id="canvas"></div>
<script>
const canvas = document.getElementById('canvas');
const els = new Map();          // name -> {node, img, cap, handle}
let act = null;                 // {name, node, mode:'move'|'resize', ...} while interacting
let topZ = 10;                  // click/interact raises an asset above the rest

function surface(node){ node.style.zIndex = ++topZ; }

function baseW(a){ return a.w >= a.h ? 200 : 200 * (a.w / a.h); }

function make(a) {
  const node = document.createElement('div');
  node.className = 'asset';
  const img = document.createElement('img');
  const cap = document.createElement('div'); cap.className = 'cap';
  const handle = document.createElement('div'); handle.className = 'handle';
  node.append(img, cap, handle);
  canvas.append(node);
  node.addEventListener('mousedown', e => { if (e.target !== handle) startMove(a.name, e); });
  handle.addEventListener('mousedown', e => startResize(a.name, e));
  const rec = {node, img, cap, handle}; els.set(a.name, rec); return rec;
}

function paint(a) {
  const rec = els.get(a.name) || make(a);
  if (rec.node === act?.node) return;            // don't stomp what the user is holding
  rec.node.style.left = a.x+'px'; rec.node.style.top = a.y+'px';
  rec.img.style.width = (baseW(a) * a.scale) + 'px';
  rec.node.classList.toggle('active', a.active);
  if (rec.img.dataset.rev !== a.rev) {
    rec.img.dataset.rev = a.rev;
    rec.img.src = `/img/${a.name}/${a.head}?v=${encodeURIComponent(a.rev)}`;
  }
  rec.node.dataset.w = a.w; rec.node.dataset.h = a.h; rec.node.dataset.scale = a.scale;
  rec.cap.innerHTML = `${a.name} <span class="op">· ${a.op} · ${a.w}×${a.h} · ${Math.round(a.scale*100)}%</span>`;
}

function startMove(name, e) {
  const rec = els.get(name), r = rec.node.getBoundingClientRect();
  surface(rec.node);            // clicking an asset brings it to the front
  act = {name, node: rec.node, mode:'move', dx: e.clientX - r.left, dy: e.clientY - r.top};
  rec.node.classList.add('busy'); e.preventDefault();
}
function startResize(name, e) {
  const rec = els.get(name), r = rec.node.getBoundingClientRect();
  surface(rec.node);
  act = {name, node: rec.node, img: rec.img, mode:'resize', left: r.left,
         base: baseW({w:+rec.node.dataset.w, h:+rec.node.dataset.h})};
  rec.node.classList.add('busy'); e.preventDefault(); e.stopPropagation();
}
window.addEventListener('mousemove', e => {
  if (!act) return;
  if (act.mode === 'move') {
    act.node.style.left = (e.clientX - act.dx) + 'px';
    act.node.style.top  = (e.clientY - act.dy) + 'px';
  } else {
    let s = (e.clientX - act.left - 4) / act.base;
    s = Math.max(0.15, Math.min(6, s));
    act.scale = s; act.img.style.width = (act.base * s) + 'px';
  }
});
window.addEventListener('mouseup', () => {
  if (!act) return;
  const a = act; act = null; a.node.classList.remove('busy');
  const body = a.mode === 'move'
    ? {name:a.name, x:parseInt(a.node.style.left), y:parseInt(a.node.style.top)}
    : {name:a.name, scale:a.scale};
  fetch('/api/move', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
});

// pushed updates — one stream, no polling
const es = new EventSource('/api/events');
es.onmessage = e => {
  const state = JSON.parse(e.data);
  const seen = new Set(state.map(a => a.name));
  for (const [name, rec] of els) if (!seen.has(name)) { rec.node.remove(); els.delete(name); }
  state.forEach(paint);
};
</script>
"""


# --- chain view (the reversible history) -----------------------------------

_CHAINS_HEAD = """<!doctype html><meta charset=utf-8><title>defringe-ai · chains</title>
<meta http-equiv=refresh content=3>
<style>
  :root { color-scheme: dark light; }
  body { margin:0; font:14px system-ui,sans-serif; background:#111; color:#ddd; }
  header { padding:12px 16px; position:sticky; top:0; background:#111; border-bottom:1px solid #333; }
  header b { color:#6cf; } header a { color:#888; text-decoration:none; margin-left:12px; }
  h2 { margin:0; padding:14px 16px 0; font-size:14px; color:#bbb; }
  h2 .active { color:#6cf; } h2 .meta { color:#666; font-weight:400; }
  .rowr { display:flex; gap:12px; padding:10px 16px 16px; overflow-x:auto; align-items:flex-start; }
  figure { margin:0; flex:0 0 auto; width:180px; opacity:.5; }
  figure.head { opacity:1; outline:2px solid #6cf; border-radius:6px; }
  figure.future { opacity:.28; }
  .swatches { display:flex; border-radius:4px; overflow:hidden; }
  .swatch { flex:1; padding:6px; }
  .checker { background-image:
      linear-gradient(45deg,#0004 25%,transparent 25%,transparent 75%,#0004 75%),
      linear-gradient(45deg,#0004 25%,transparent 25%,transparent 75%,#0004 75%);
      background-size:14px 14px; background-position:0 0,7px 7px; }
  .dark { background:#1b1b1b; } .light { background:#e8e8e8; }
  img { max-width:100%; display:block; margin:auto; }
  figcaption { padding:6px 4px; color:#aaa; font-size:12px; }
  .n { color:#666; } .arrow { align-self:center; color:#444; }
  .ws + .ws { border-top:1px solid #262626; }
</style>
<header><b>defringe-ai</b> · edit chains <a href="/">← edit screen</a></header>
"""


def _chains(home: str) -> str:
    active = _get_active(home)
    names = Workspace.list_all(home)
    if not names:
        return _CHAINS_HEAD + '<div style="padding:40px 16px;color:#777">No workspaces yet.</div>'
    parts = [_CHAINS_HEAD]
    for name in names:
        with open(os.path.join(home, name, "manifest.json")) as f:
            m = json.load(f)
        steps, head = m["steps"], m["head"]
        cards = []
        for i, st in enumerate(steps):
            if i:
                cards.append('<div class="arrow">→</div>')
            cls = "head" if i == head else ("future" if i > head else "")
            cards.append(
                f'<figure class="{cls}"><div class="swatches">'
                f'<div class="swatch dark checker"><img src="/img/{name}/{i}"></div>'
                f'<div class="swatch light checker"><img src="/img/{name}/{i}"></div>'
                f'</div><figcaption><span class="n">{i:02d}</span> {st["op"]}'
                f'{" · HEAD" if i == head else ""}</figcaption></figure>'
            )
        act = ' class="active"' if name == active else ""
        parts.append(
            f'<section class="ws"><h2><span{act}>{name}</span>'
            f' <span class="meta">HEAD {head}/{len(steps) - 1}</span></h2>'
            f'<div class="rowr">' + "".join(cards) + "</div></section>"
        )
    return "".join(parts)


# --- server ----------------------------------------------------------------

def serve_preview(home: str, host: str, port: int) -> None:
    async def canvas(_request):
        return HTMLResponse(_CANVAS)

    async def chains(_request):
        return HTMLResponse(_chains(home))

    async def events(request):
        async def gen():
            last, beat = None, 0
            while True:
                if await request.is_disconnected():
                    break
                st = _state(home)
                sig = _sig(st)
                if sig != last:
                    last = sig
                    yield f"data: {json.dumps(st)}\n\n"
                else:
                    beat += 1
                    if beat % 40 == 0:            # ~15s keep-alive comment
                        yield ": hb\n\n"
                await asyncio.sleep(0.4)
        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    async def api_move(request):
        b = await request.json()
        name = os.path.basename(str(b.get("name", "")))
        if name in Workspace.list_all(home):
            Workspace(os.path.join(home, name)).set_canvas(
                x=b.get("x"), y=b.get("y"), scale=b.get("scale"))
        return JSONResponse({"ok": True})

    async def image(request):
        name = os.path.basename(request.path_params["name"])
        idx = int(request.path_params["idx"])
        try:
            with open(os.path.join(home, name, "manifest.json")) as f:
                m = json.load(f)
            path = os.path.join(home, name, m["steps"][idx]["file"])
        except (FileNotFoundError, IndexError, KeyError):
            return HTMLResponse("not found", status_code=404)
        if not os.path.exists(path):
            return HTMLResponse("not found", status_code=404)
        return FileResponse(path)

    app = Starlette(routes=[
        Route("/", canvas),
        Route("/chains", chains),
        Route("/api/events", events),
        Route("/api/move", api_move, methods=["POST"]),
        Route("/img/{name}/{idx:int}", image),
    ])
    uvicorn.run(app, host=host, port=port, log_level="warning")
