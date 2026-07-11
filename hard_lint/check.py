#!/usr/bin/env python3
"""hard_lint — the deterministic lane of `make check`.

Mechanical, pass/fail invariants for this repo — the checks that DON'T need judgment
(those live in `soft_lint/`, mapped by `HARNESS.md`). Each check below hardens one rule
from `harness_driver/` into code:

  tool-registry   every @mcp.tool() is in TAXONOMY and vice-versa   (tools.md)
  tool-docstrings every @mcp.tool() has a docstring                 (docstrings.md)
  readme-tools    every tool name appears in the README             (tools.md)
  frontend-io     no bare fetch( in a React component               (frontend.md)

Pure stdlib + `ast` — imports nothing from the package, so it runs fast and has no side
effects. Exit code is the number of failing checks (0 = clean).
"""

from __future__ import annotations

import ast
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER = os.path.join(ROOT, "src", "defringe_ai", "server.py")
README = os.path.join(ROOT, "README.md")
FRONTEND = os.path.join(ROOT, "frontend", "src")

# Names that appear in TAXONOMY but are deliberately NOT their own @mcp.tool() function.
# Keep this tight and explained — every entry is a real, intentional exception.
TAXONOMY_ALIASES: set[str] = set()


def _fail(check: str, msg: str) -> None:
    print(f"  \033[31m✗ {check}\033[0m — {msg}")


def _ok(check: str, msg: str) -> None:
    print(f"  \033[32m✓ {check}\033[0m — {msg}")


def _server_ast() -> ast.Module:
    with open(SERVER) as f:
        return ast.parse(f.read(), filename=SERVER)


def _mcp_tools(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    """Every function decorated with @mcp.tool() → {name: node}."""
    tools: dict[str, ast.FunctionDef] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                # @mcp.tool()  → Call(func=Attribute(attr='tool', value=Name('mcp')))
                fn = dec.func if isinstance(dec, ast.Call) else dec
                if isinstance(fn, ast.Attribute) and fn.attr == "tool" and \
                        isinstance(fn.value, ast.Name) and fn.value.id == "mcp":
                    tools[node.name] = node
    return tools


def _taxonomy(tree: ast.Module) -> set[str]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "TAXONOMY" for t in node.targets
        ):
            groups = ast.literal_eval(node.value)
            return {name for names in groups.values() for name in names}
    raise SystemExit("hard_lint: TAXONOMY not found in server.py")


def check_tool_registry(tools, taxonomy) -> bool:
    """@mcp.tool() set must equal TAXONOMY set (minus documented aliases)."""
    registered = set(tools)
    declared = taxonomy - TAXONOMY_ALIASES
    missing = declared - registered          # in TAXONOMY, no such tool
    unlisted = registered - declared         # a tool nobody put in TAXONOMY
    if missing or unlisted:
        parts = []
        if unlisted:
            parts.append(f"tools not in TAXONOMY: {sorted(unlisted)}")
        if missing:
            parts.append(f"TAXONOMY names with no @mcp.tool(): {sorted(missing)}")
        _fail("tool-registry", "; ".join(parts))
        return False
    _ok("tool-registry", f"{len(registered)} tools, all in TAXONOMY")
    return True


def check_tool_docstrings(tools) -> bool:
    bad = [n for n, node in tools.items() if not ast.get_docstring(node)]
    if bad:
        _fail("tool-docstrings", f"@mcp.tool() with no docstring: {sorted(bad)}")
        return False
    _ok("tool-docstrings", f"all {len(tools)} tools documented")
    return True


def check_readme_tools(tools, text: str | None = None) -> bool:
    if text is None:
        with open(README) as f:
            text = f.read()
    # A tool counts as documented if its name appears inside an inline-code span, allowing
    # a trailing call/args form: `edit`, `edit(...)`, `seed [[x,y],…]` all match.
    missing = [n for n in tools if not re.search(r"`" + re.escape(n) + r"\b", text)]
    if missing:
        _fail("readme-tools", f"tools absent from README (as `name`): {sorted(missing)}")
        return False
    _ok("readme-tools", f"all {len(tools)} tools referenced in README")
    return True


def check_frontend_io(srcdir: str | None = None) -> bool:
    """All server I/O goes through state.ts — no bare fetch( in a component."""
    srcdir = srcdir or FRONTEND
    if not os.path.isdir(srcdir):
        _ok("frontend-io", "no frontend/src (skipped)")
        return True
    offenders = []
    for fn in sorted(os.listdir(srcdir)):
        if not fn.endswith((".tsx", ".ts")) or fn == "state.ts":
            continue
        with open(os.path.join(srcdir, fn)) as f:
            for i, line in enumerate(f, 1):
                if re.search(r"\bfetch\s*\(", line):
                    offenders.append(f"{fn}:{i}")
    if offenders:
        _fail("frontend-io", f"bare fetch( outside state.ts: {offenders} — route it through state.ts")
        return False
    _ok("frontend-io", "no ad-hoc fetch( in components")
    return True


def main() -> int:
    print("» hard_lint — deterministic invariants")
    tree = _server_ast()
    tools = _mcp_tools(tree)
    taxonomy = _taxonomy(tree)
    results = [
        check_tool_registry(tools, taxonomy),
        check_tool_docstrings(tools),
        check_readme_tools(tools),
        check_frontend_io(),
    ]
    failed = results.count(False)
    print(f"hard-lint: {failed} failing / {len(results)} checks — "
          + ("clean" if not failed else "fix before merge"))
    return failed


if __name__ == "__main__":
    sys.exit(main())
