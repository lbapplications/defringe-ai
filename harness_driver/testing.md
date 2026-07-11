# testing — the suite mirrors the source, stays ≥90%, and stays fast

Tests are part of the deterministic gate, not an afterthought. As code grows, coverage
**must not fall below 90%** — the gate enforces it, so new code lands with the tests that
cover it. Two suites, same bar:

| Suite | Where | Runner | Gate |
|---|---|---|---|
| **Python** | `tests/` (mirrors `src/defringe_ai/`) | `uv run pytest` | branch coverage of `defringe_ai` ≥ **90%** (`--cov-fail-under=90`) |
| **Frontend** | `frontend/src/*.test.ts` | `pnpm --dir frontend test` | v8 coverage of `state.ts` ≥ **90%** |

Both run under `make check` (and `make test`). The Python gate lives in
`pyproject.toml` (`[tool.pytest.ini_options]` addopts + `[tool.coverage.*]`); the frontend
gate lives in `frontend/vite.config.ts` (`test.coverage.thresholds`).

## The three rules

1. **Mirror the source.** A module at `src/defringe_ai/<x>.py` is tested by
   `tests/<x>.py` (subpackages mirror too: `imageops/…` → `tests/imageops/…`,
   `web/app.py` → `tests/web/test_app.py`). Find the test for a file by its path, not by
   searching. When you add a module, add its mirror.
2. **Stay ≥90%, as a floor not a target.** The gate fails the build under 90%. Don't lower
   it to pass — add the test. Genuinely un-testable lines (network entrypoints that call
   `uvicorn.run` / `mcp.run`, the `if __name__ == "__main__"` guard, an infinite SSE
   generator) are excluded with `# pragma: no cover` **and a reason**, never by dropping the
   threshold. Today the whole tree sits ~98%.
3. **Keep it fast — it's a requirement.** The suite runs in well under a second and must
   stay that way. How: tiny synthetic arrays (a 20×20 RGBA fixture, never a real photo),
   `tmp_path` for every workspace/file (never the real home or the live server), and drive
   the Starlette app in-process with `TestClient(build_app(home))` — no uvicorn, no sockets.
   A test that needs the running server, a real asset, or a sleep is testing the wrong
   seam; move the seam.

## How to test each kind of thing

- **Image ops** (`imageops/`): assert on array *properties* — `shape`, `dtype`, alpha
  counts (`(a[...,3]==0).sum()`), specific pixels, bounding boxes — **not** golden images
  (a one-LSB cv2/codec change breaks a byte snapshot and tells you nothing). Use
  `numpy.testing.assert_array_equal` for exact integer results.
- **MCP tools** (`server.py`): the official-SDK `@mcp.tool()` returns the plain function,
  so import and call it directly. Point the module global `HOME` at a tmp dir
  (`monkeypatch.setattr(server, "HOME", tmp)`) — the `srv` fixture does this. Gated tools
  refuse without a session: open one with `edit(...)` first.
- **CLI** (`server.main`): set `sys.argv` and call `main()`; assert on captured stdout.
- **Web routes** (`web/app.py`): `build_app(home)` is split from `serve_preview` exactly so
  `TestClient` can exercise the routes without a server.
- **Frontend logic** (`state.ts`): the module the [frontend](frontend.md) rule funnels all
  server I/O through — pure helpers plus the `useBoard` SSE hook. Test the hook with a fake
  `EventSource` (`vi.stubGlobal`) + `renderHook`; mock `fetch` for `post`. Konva canvas
  components aren't unit-tested — keep logic in `state.ts` so it's testable there.

## Adding a check-worthy invariant

A *mechanical* rule (naming, registry, docstrings) belongs in
[`hard_lint/`](../hard_lint/), not a unit test. A *behavioural* fact belongs in `tests/`.
When unsure: if it's true by construction and has no inputs, it's a lint; if it depends on
what the code computes, it's a test.
