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
from ..history import History
from ..workspace import Workspace

WEBDIR = os.path.dirname(__file__)
DIST = os.path.join(WEBDIR, "dist")  # the built Vite app (frontend/ → here); served in prod


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
        _hist = History.from_dict(a["history"]) if a.get("history") else History({}, "open")
        out.append({
            "name": name, "x": a["x"], "y": a["y"], "scale": a["scale"], "z": z,
            "head": head, "steps": len(m["steps"]), "w": w, "h": h,
            "op": m["steps"][head]["op"], "selected": name == sel,
            "editing": bool(sess.get("active")), "intent": sess.get("intent", ""),
            "rev": f'{head}-{len(m["steps"])}',
            "locked": bool(a.get("locked", False)),
            "dots": a.get("mask", {}).get("dots", []),
            "outline": a.get("mask", {}).get("outline", []),
            "can_undo": _hist.can_undo, "can_redo": _hist.can_redo,
            "timeline": _hist.timeline(),
        })
    return out


def _sig(state: list[dict]) -> str:
    return json.dumps([(a["name"], a["x"], a["y"], a["scale"], a["z"], a["rev"],
                        a["selected"], a["editing"], a["intent"],
                        a["locked"], a["dots"], a["outline"],
                        a["can_undo"], a["can_redo"]) for a in state])


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

def build_app(home: str) -> Starlette:
    """Build the edit-screen Starlette app over `home` — every route closes over it.

    Split out from :func:`serve_preview` so the app can be exercised with Starlette's
    in-process ``TestClient`` (no uvicorn, no sockets) — that's what the test suite drives."""
    async def index(_r):
        idx = os.path.join(DIST, "index.html")
        if os.path.exists(idx):
            return FileResponse(idx)
        return HTMLResponse(
            "<h1>frontend not built</h1><p>Run <code>pnpm install &amp;&amp; pnpm build</code> "
            "in <code>frontend/</code> (or <code>pnpm dev</code> for the proxied dev server).</p>",
            status_code=503,
        )

    async def chains(_r):
        return HTMLResponse(_chains(home))

    async def events(request):  # pragma: no cover — infinite SSE stream; a live-server path
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

    async def api_lock(request):
        b = await request.json()
        name = os.path.basename(str(b.get("name", "")))
        Board(home).lock(name, bool(b.get("locked")))
        return JSONResponse({"ok": True})

    async def api_dot(request):
        b = await request.json()
        name = os.path.basename(str(b.get("name", "")))
        Board(home).add_dot(name, b.get("x"), b.get("y"))
        return JSONResponse({"ok": True})

    async def api_dots_clear(request):
        b = await request.json()
        name = os.path.basename(str(b.get("name", "")))
        Board(home).clear_dots(name)
        return JSONResponse({"ok": True})

    async def api_isolate(request):
        """Fill the mask outline into the image's alpha → a cutout. Runs through the
        workspace edit pipeline (begin_edit → apply → commit) so it's undoable."""
        from ..imageops import Geometry

        body = await request.json()
        name = os.path.basename(str(body.get("name", "")))
        bd = Board(home).sync()
        outline = bd.get("assets", {}).get(name, {}).get("mask", {}).get("outline", [])
        if len(outline) < 3:
            return JSONResponse({"ok": False, "error": "no outline — connect dots first"})
        ws = Workspace.resolve(name, home)
        ws.begin_edit("isolate (fill mask)")
        ws.apply("isolate", Geometry.fill_polygon_alpha, {"polygon": outline})
        ws.commit_edit()
        Board(home).record_pixel_edit(name, "isolate")   # image-level undo step
        return JSONResponse({"ok": True})

    async def api_undo(request):
        b = await request.json()
        Board(home).undo(os.path.basename(str(b.get("name", ""))))
        return JSONResponse({"ok": True})

    async def api_redo(request):
        b = await request.json()
        Board(home).redo(os.path.basename(str(b.get("name", ""))))
        return JSONResponse({"ok": True})

    async def api_goto(request):
        """Jump the asset to a chosen point on its history timeline (dropdown select)."""
        b = await request.json()
        name = os.path.basename(str(b.get("name", "")))
        Board(home).goto(name, int(b.get("index", 0)))
        return JSONResponse({"ok": True})

    async def api_reset(request):
        """Reset an asset: revert its pixels to the original open image, wipe its invisible
        mask layer (dots + outline), AND erase its per-image history — a clean slate."""
        b = await request.json()
        name = os.path.basename(str(b.get("name", "")))
        Workspace.resolve(name, home).reset()
        Board(home).reset_history(name)
        return JSONResponse({"ok": True})

    async def api_connect(request):
        """Connect an asset's mask dots into a boundary polygon: convex hull, then snap
        inward. Deterministic — stored on the mask and pushed back over SSE."""
        from ..imageops import Geometry

        body = await request.json()
        name = os.path.basename(str(body.get("name", "")))
        bd = Board(home).sync()
        dots = bd.get("assets", {}).get(name, {}).get("mask", {}).get("dots", [])
        Board(home).set_outline(name, Geometry.hull_snap(dots))
        return JSONResponse({"ok": True, "n": len(dots)})

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

    routes = [
        Route("/", index),
        Route("/chains", chains),
        Route("/api/events", events),
        Route("/api/move", api_move, methods=["POST"]),
        Route("/api/select", api_select, methods=["POST"]),
        Route("/api/lock", api_lock, methods=["POST"]),
        Route("/api/dot", api_dot, methods=["POST"]),
        Route("/api/dots/clear", api_dots_clear, methods=["POST"]),
        Route("/api/connect", api_connect, methods=["POST"]),
        Route("/api/isolate", api_isolate, methods=["POST"]),
        Route("/api/undo", api_undo, methods=["POST"]),
        Route("/api/redo", api_redo, methods=["POST"]),
        Route("/api/history/goto", api_goto, methods=["POST"]),
        Route("/api/reset", api_reset, methods=["POST"]),
        Route("/img/{name}/{idx:int}", image),
    ]
    # the built Vite bundle references /assets/*; only mount when it exists so an
    # unbuilt checkout still boots (index() then shows the "run pnpm build" hint).
    if os.path.isdir(os.path.join(DIST, "assets")):
        routes.append(Mount("/assets", app=StaticFiles(directory=os.path.join(DIST, "assets"))))
    return Starlette(routes=routes)


def serve_preview(home: str, host: str, port: int) -> None:  # pragma: no cover
    """Run the edit-screen app under uvicorn (the live server; not exercised in tests)."""
    uvicorn.run(build_app(home), host=host, port=port, log_level="warning")
