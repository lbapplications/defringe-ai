"""A slim, dependency-light browser gallery of the output dir.

Auto-refreshes so you can watch assets land as the agent works. Renders on a dark
*and* a light checkerboard so you can judge alpha edges (the whole point of the
defringe/key tools) against both.
"""

from __future__ import annotations

import glob
import os

import uvicorn
from starlette.applications import Starlette
from starlette.responses import FileResponse, HTMLResponse
from starlette.routing import Route

_PAGE = """<!doctype html><meta charset=utf-8>
<title>defringe-ai preview</title>
<meta http-equiv=refresh content=2>
<style>
  :root {{ color-scheme: dark light; }}
  body {{ margin:0; font:14px system-ui, sans-serif; background:#111; color:#ddd; }}
  header {{ padding:12px 16px; position:sticky; top:0; background:#111; border-bottom:1px solid #333; }}
  .grid {{ display:grid; gap:16px; padding:16px; grid-template-columns:repeat(auto-fill,minmax(240px,1fr)); }}
  figure {{ margin:0; }}
  .swatches {{ display:flex; }}
  .swatch {{ flex:1; padding:8px; }}
  .dark {{ background:#1b1b1b; }}
  .light {{ background:#e8e8e8; }}
  .checker {{ background-image:
      linear-gradient(45deg,#0003 25%,transparent 25%,transparent 75%,#0003 75%),
      linear-gradient(45deg,#0003 25%,transparent 25%,transparent 75%,#0003 75%);
      background-size:16px 16px; background-position:0 0,8px 8px; }}
  img {{ max-width:100%; display:block; margin:auto; }}
  figcaption {{ padding:6px 8px; color:#999; font-size:12px; word-break:break-all; }}
  .empty {{ padding:40px 16px; color:#777; }}
</style>
<header><b>defringe-ai</b> &middot; {n} output(s) &middot; auto-refresh 2s</header>
{body}
"""


def _render(out_dir: str) -> str:
    files = sorted(glob.glob(os.path.join(out_dir, "*.png")), key=os.path.getmtime, reverse=True)
    if not files:
        return _PAGE.format(n=0, body='<div class="empty">No outputs yet. Run a tool.</div>')
    cards = []
    for f in files:
        name = os.path.basename(f)
        cards.append(
            f'<figure><div class="swatches">'
            f'<div class="swatch dark checker"><img src="/img/{name}"></div>'
            f'<div class="swatch light checker"><img src="/img/{name}"></div>'
            f"</div><figcaption>{name}</figcaption></figure>"
        )
    return _PAGE.format(n=len(files), body='<div class="grid">' + "".join(cards) + "</div>")


def serve_preview(out_dir: str, host: str, port: int) -> None:
    async def index(_request):
        return HTMLResponse(_render(out_dir))

    async def image(request):
        name = os.path.basename(request.path_params["name"])  # prevent traversal
        path = os.path.join(out_dir, name)
        if not os.path.exists(path):
            return HTMLResponse("not found", status_code=404)
        return FileResponse(path)

    app = Starlette(routes=[Route("/", index), Route("/img/{name}", image)])
    uvicorn.run(app, host=host, port=port, log_level="warning")
