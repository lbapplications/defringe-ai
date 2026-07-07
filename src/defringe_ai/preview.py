"""The edit screen — a shared canvas of the assets in play.

Each workspace's current image is placed on a canvas at its stored (x, y). Assets
are movable two ways:
  - by the agent, via the `move` tool (arranges the layout while it works)
  - by a human, by dragging (drop persists the new position back to the workspace)

`/`        canvas / edit screen (draggable, live)
`/chains`  the per-asset reversible edit chains, HEAD marked
`/api/state`  JSON snapshot;  `/api/move`  persist a drag

Slim: Starlette + a little vanilla JS, no build step. The canvas polls state so
agent moves and edits show up live, but never fights a drag in progress.
"""

from __future__ import annotations

import json
import os

import uvicorn
from starlette.applications import Starlette
from starlette.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.routing import Route

from .workspace import Workspace, _get_active


# --- shared data -----------------------------------------------------------

def _state(home: str) -> list[dict]:
    active = _get_active(home)
    out = []
    for name in Workspace.list_all(home):
        with open(os.path.join(home, name, "manifest.json")) as f:
            m = json.load(f)
        head = m["head"]
        img = os.path.join(home, name, m["steps"][head]["file"])
        try:
            from PIL import Image

            w, h = Image.open(img).size
        except Exception:
            w, h = 0, 0
        c = m.get("canvas", {"x": 40, "y": 40})
        out.append({
            "name": name, "x": c["x"], "y": c["y"], "head": head,
            "steps": len(m["steps"]), "w": w, "h": h,
            "op": m["steps"][head]["op"], "active": name == active,
            "rev": f'{head}-{len(m["steps"])}',
        })
    return out


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
  .asset.dragging { cursor:grabbing; z-index:99; box-shadow:0 8px 30px #000a; }
  .asset img { display:block; max-width:200px; max-height:200px; pointer-events:none; }
  .asset .cap { font-size:11px; color:#aaa; padding:3px 2px 1px; }
  .asset .cap .op { color:#666; }
</style>
<header><b>defringe-ai</b> · edit screen <a href="/chains">edit chains →</a>
  <span class="hint">drag assets to arrange · agent can move them too · live</span></header>
<div id="canvas"></div>
<script>
const canvas = document.getElementById('canvas');
const els = new Map();          // name -> {node, img, cap}
let dragging = null;            // name currently being dragged

function make(a) {
  const node = document.createElement('div');
  node.className = 'asset';
  const img = document.createElement('img');
  const cap = document.createElement('div'); cap.className = 'cap';
  node.append(img, cap);
  canvas.append(node);
  node.addEventListener('mousedown', e => startDrag(a.name, e));
  const rec = {node, img, cap};
  els.set(a.name, rec);
  return rec;
}

function paint(a) {
  const rec = els.get(a.name) || make(a);
  if (rec.node !== dragging?.node) { rec.node.style.left = a.x+'px'; rec.node.style.top = a.y+'px'; }
  rec.node.classList.toggle('active', a.active);
  if (rec.img.dataset.rev !== a.rev) {
    rec.img.dataset.rev = a.rev;
    rec.img.src = `/img/${a.name}/${a.head}?v=${encodeURIComponent(a.rev)}`;
  }
  rec.cap.innerHTML = `${a.name} <span class="op">· ${a.op} · ${a.w}×${a.h}</span>`;
}

function startDrag(name, e) {
  const rec = els.get(name);
  const r = rec.node.getBoundingClientRect();
  dragging = {name, node: rec.node, dx: e.clientX - r.left, dy: e.clientY - r.top};
  rec.node.classList.add('dragging');
  e.preventDefault();
}
window.addEventListener('mousemove', e => {
  if (!dragging) return;
  dragging.node.style.left = (e.clientX - dragging.dx) + 'px';
  dragging.node.style.top  = (e.clientY - dragging.dy) + 'px';
});
window.addEventListener('mouseup', () => {
  if (!dragging) return;
  const d = dragging; d.node.classList.remove('dragging'); dragging = null;
  fetch('/api/move', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({name:d.name, x:parseInt(d.node.style.left), y:parseInt(d.node.style.top)})});
});

async function poll() {
  try {
    const state = await (await fetch('/api/state')).json();
    const seen = new Set(state.map(a => a.name));
    for (const [name, rec] of els) if (!seen.has(name)) { rec.node.remove(); els.delete(name); }
    state.forEach(paint);
  } catch (_) {}
}
poll(); setInterval(poll, 1500);
</script>
"""


# --- chain view (the reversible history) -----------------------------------

_CHAINS_HEAD = """<!doctype html><meta charset=utf-8><title>defringe-ai · chains</title>
<meta http-equiv=refresh content=2>
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

    async def api_state(_request):
        return JSONResponse(_state(home))

    async def api_move(request):
        body = await request.json()
        name = os.path.basename(str(body.get("name", "")))
        if name in Workspace.list_all(home):
            Workspace(os.path.join(home, name)).move(int(body["x"]), int(body["y"]))
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
        Route("/api/state", api_state),
        Route("/api/move", api_move, methods=["POST"]),
        Route("/img/{name}/{idx:int}", image),
    ])
    uvicorn.run(app, host=host, port=port, log_level="warning")
