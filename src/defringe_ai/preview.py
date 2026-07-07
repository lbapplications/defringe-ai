"""Browser view of the active workspace: the reversible edit chain, HEAD marked.

Auto-refreshes so a human shaping an asset beside the agent watches edits land, sees
where HEAD sits (what undo/redo would do), and judges alpha edges on both a dark and
a light checkerboard. Slim: stdlib + Starlette, no build step.
"""

from __future__ import annotations

import json
import os

import uvicorn
from starlette.applications import Starlette
from starlette.responses import FileResponse, HTMLResponse
from starlette.routing import Route

from .workspace import Workspace, _get_active

_PAGE = """<!doctype html><meta charset=utf-8>
<title>defringe-ai</title>
<meta http-equiv=refresh content=2>
<style>
  :root {{ color-scheme: dark light; }}
  body {{ margin:0; font:14px system-ui,sans-serif; background:#111; color:#ddd; }}
  header {{ padding:12px 16px; position:sticky; top:0; background:#111; border-bottom:1px solid #333; }}
  header b {{ color:#6cf; }}
  h2 {{ margin:0; padding:14px 16px 0; font-size:14px; color:#bbb; font-weight:600; }}
  h2 .active {{ color:#6cf; }} h2 .meta {{ color:#666; font-weight:400; }}
  .row {{ display:flex; gap:14px; padding:10px 16px 16px; overflow-x:auto; align-items:flex-start; }}
  figure {{ margin:0; flex:0 0 auto; width:200px; opacity:.5; }}
  figure.head {{ opacity:1; outline:2px solid #6cf; border-radius:6px; }}
  figure.future {{ opacity:.28; }}
  .swatches {{ display:flex; border-radius:4px; overflow:hidden; }}
  .swatch {{ flex:1; padding:6px; }}
  .checker {{ background-image:
      linear-gradient(45deg,#0004 25%,transparent 25%,transparent 75%,#0004 75%),
      linear-gradient(45deg,#0004 25%,transparent 25%,transparent 75%,#0004 75%);
      background-size:14px 14px; background-position:0 0,7px 7px; }}
  .dark {{ background:#1b1b1b; }} .light {{ background:#e8e8e8; }}
  img {{ max-width:100%; display:block; margin:auto; }}
  figcaption {{ padding:6px 4px; color:#aaa; font-size:12px; }}
  .n {{ color:#666; }} .arrow {{ align-self:center; color:#444; flex:0 0 auto; }}
  .empty {{ padding:40px 16px; color:#777; }}
  .ws + .ws {{ border-top:1px solid #262626; }}
</style>
<header><b>defringe-ai</b> · {count} workspace(s) · auto-refresh 2s</header>
{body}
"""


def _chain_html(home: str, name: str, active: str) -> str:
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
    tag = ' <span class="active">● active</span>' if name == active else ""
    return (
        f'<section class="ws"><h2><span class="{"active" if name == active else ""}">{name}</span>{tag}'
        f' <span class="meta">HEAD {head}/{len(steps) - 1}</span></h2>'
        f'<div class="row">' + "".join(cards) + "</div></section>"
    )


def _render(home: str) -> str:
    names = Workspace.list_all(home)
    if not names:
        return _PAGE.format(count=0,
                            body='<div class="empty">No workspaces yet. Run <code>defringe-ai open &lt;asset&gt;</code>.</div>')
    active = _get_active(home)
    body = "".join(_chain_html(home, n, active) for n in names)
    return _PAGE.format(count=len(names), body=body)


def serve_preview(home: str, host: str, port: int) -> None:
    async def index(_request):
        return HTMLResponse(_render(home))

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
        Route("/", index),
        Route("/img/{name}/{idx:int}", image),
    ])
    uvicorn.run(app, host=host, port=port, log_level="warning")
