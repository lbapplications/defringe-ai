"""Edit-screen web app — a thin interface over the board (arrangement) and workspaces
(edit history). Builds canvas state, pushes it over SSE, and persists drags / resizes /
selection. The actual HTML/CSS/JS are static files in this directory, not embedded here.

Routes:
  /              canvas.html (the edit screen)
  /static/*      canvas.css, canvas.js
  /api/events    SSE state stream (pushes only on change)
  /api/move      POST {name,x?,y?,scale?}   persist a drag/resize
  /api/select    POST {name}                select + bring to front
  /img/{n}/{i}   the i-th history snapshot of asset n
  /chains        the per-asset reversible edit chains
"""

from __future__ import annotations

import asyncio
import json
import os
import time

# Unique per server process. Pushed to every SSE client on connect; when a tab sees it
# change (because the server restarted with new code), it reloads itself — so a stale
# tab never happens again. No Vite / build step needed.
BUILD = str(int(time.time()))

import uvicorn
from starlette.applications import Starlette
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from ..board import Board
from ..workspace import Workspace

WEBDIR = os.path.dirname(__file__)


# --- state (board arrangement + workspace edit heads) ----------------------

def build_state(home: str) -> list[dict]:
    b = Board(home).sync()
    sel = b["selected"]
    out = []
    for z, name in enumerate(b["order"]):          # z = index in back->front order
        try:
            with open(os.path.join(home, name, "manifest.json")) as f:
                m = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            continue
        head = m["head"]
        try:
            from PIL import Image

            w, h = Image.open(os.path.join(home, name, m["steps"][head]["file"])).size
        except Exception:
            w, h = 0, 0
        a = b["assets"][name]
        sess = m.get("session", {})
        out.append({
            "name": name, "x": a["x"], "y": a["y"], "scale": a["scale"], "z": z,
            "head": head, "steps": len(m["steps"]), "w": w, "h": h,
            "op": m["steps"][head]["op"], "selected": name == sel,
            "editing": bool(sess.get("active")), "intent": sess.get("intent", ""),
            "rev": f'{head}-{len(m["steps"])}',
        })
    return out


def _sig(state: list[dict]) -> str:
    return json.dumps([(a["name"], a["x"], a["y"], a["scale"], a["z"], a["rev"],
                        a["selected"], a["editing"], a["intent"]) for a in state])


# --- chains (server-rendered history view) ---------------------------------

def _chains(home: str) -> str:
    css = open(os.path.join(WEBDIR, "chains.css")).read()
    parts = [f"<!doctype html><meta charset=utf-8><title>defringe-ai · chains</title>"
             f"<meta http-equiv=refresh content=3><style>{css}</style>"
             f'<header><b>defringe-ai</b> · edit chains <a href="/">← edit screen</a></header>']
    names = Workspace.list_all(home)
    if not names:
        return parts[0] + '<div class="empty">No workspaces yet.</div>'
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
                f'</div><figcaption>{i:02d} {st["op"]}{" · HEAD" if i == head else ""}</figcaption></figure>')
        parts.append(f'<section class="ws"><h2>{name} <span class="meta">HEAD {head}/{len(steps)-1}'
                     f'</span></h2><div class="rowr">' + "".join(cards) + "</div></section>")
    return "".join(parts)


# --- server ----------------------------------------------------------------

def serve_preview(home: str, host: str, port: int) -> None:
    async def index(_r):
        return FileResponse(os.path.join(WEBDIR, "canvas.html"))

    async def chains(_r):
        return HTMLResponse(_chains(home))

    async def events(request):
        async def gen():
            yield f"event: build\ndata: {BUILD}\n\n"      # tab auto-reloads if this changed
            last, beat = None, 0
            while True:
                if await request.is_disconnected():
                    break
                sig = _sig(state := build_state(home))
                if sig != last:
                    last = sig
                    yield f"data: {json.dumps(state)}\n\n"
                elif (beat := beat + 1) % 40 == 0:
                    yield ": hb\n\n"
                await asyncio.sleep(0.4)
        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    async def api_move(request):
        b = await request.json()
        name = os.path.basename(str(b.get("name", "")))
        Board(home).place(name, x=b.get("x"), y=b.get("y"), scale=b.get("scale"))
        return JSONResponse({"ok": True})

    async def api_select(request):
        b = await request.json()
        Board(home).select(os.path.basename(str(b.get("name", ""))))
        return JSONResponse({"ok": True})

    async def image(request):
        name = os.path.basename(request.path_params["name"])
        idx = int(request.path_params["idx"])
        try:
            with open(os.path.join(home, name, "manifest.json")) as f:
                path = os.path.join(home, name, json.load(f)["steps"][idx]["file"])
        except (FileNotFoundError, IndexError, KeyError, json.JSONDecodeError):
            return HTMLResponse("not found", status_code=404)
        if not os.path.exists(path):
            return HTMLResponse("not found", status_code=404)
        return FileResponse(path)

    app = Starlette(routes=[
        Route("/", index),
        Route("/chains", chains),
        Route("/api/events", events),
        Route("/api/move", api_move, methods=["POST"]),
        Route("/api/select", api_select, methods=["POST"]),
        Route("/img/{name}/{idx:int}", image),
        Mount("/static", app=StaticFiles(directory=WEBDIR)),
    ])
    uvicorn.run(app, host=host, port=port, log_level="warning")
