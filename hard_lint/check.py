#!/usr/bin/env python3
"""hard_lint — the deterministic lane of `make check`.

Mechanical, pass/fail invariants for this repo — the checks that DON'T need judgment
(those live in `soft_lint/`, mapped by `HARNESS.md`). Each check below hardens one rule
from `harness_driver/` into code:

  tool-registry   every tool is registered under a taxonomy category (tools.md)
  tool-docstrings every tool has a docstring                         (docstrings.md)
  readme-tools    every tool name appears in the README             (tools.md)
  frontend-io     no bare fetch( in a React component               (frontend.md)
  nomenclature    tool names are snake_case + no banned name        (nomenclature.md)

Tools live in the ``tools/`` package, one module per taxonomy category, each function
decorated with that module's ``core.category(...)`` decorator — so the taxonomy is derived
from the modules. This linter scans those modules by AST: a tool must go through a category
decorator (a bare ``@mcp.tool()`` that bypasses the taxonomy is flagged).

Pure stdlib + `ast` — imports nothing from the package, so it runs fast and has no side
effects. Exit code is the number of failing checks (0 = clean).
"""

from __future__ import annotations

import ast
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS_DIR = os.path.join(ROOT, "src", "defringe_ai", "tools")
README = os.path.join(ROOT, "README.md")
FRONTEND = os.path.join(ROOT, "frontend", "src")
NOMENCLATURE = os.path.join(ROOT, "harness_driver", "nomenclature.md")

SNAKE = re.compile(r"[a-z][a-z0-9_]*\Z")

# Names that appear in TAXONOMY but are deliberately NOT their own @mcp.tool() function.
# Keep this tight and explained — every entry is a real, intentional exception.
TAXONOMY_ALIASES: set[str] = set()


def _fail(check: str, msg: str) -> None:
    print(f"  \033[31m✗ {check}\033[0m — {msg}")


def _ok(check: str, msg: str) -> None:
    print(f"  \033[32m✓ {check}\033[0m — {msg}")


def _mcp_tools(tree: ast.Module, cat_names: frozenset[str] = frozenset()) -> dict[str, ast.FunctionDef]:
    """Every function that registers a tool → {name: node}.

    A tool registers either via a category decorator (a name in ``cat_names``, e.g. ``@transform``)
    or a bare ``@mcp.tool()``. The latter bypasses the taxonomy — detected so the registry check
    can flag it."""
    tools: dict[str, ast.FunctionDef] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                fn = dec.func if isinstance(dec, ast.Call) else dec
                # @mcp.tool()  → Call(func=Attribute(attr='tool', value=Name('mcp')))
                if isinstance(fn, ast.Attribute) and fn.attr == "tool" and \
                        isinstance(fn.value, ast.Name) and fn.value.id == "mcp":
                    tools[node.name] = node
                # @<category>  → a bare Name bound to core.category(...)
                elif isinstance(fn, ast.Name) and fn.id in cat_names:
                    tools[node.name] = node
    return tools


def _category_map(tree: ast.Module) -> dict[str, str]:
    """Module-level names bound to ``core.category("cat", …)`` → their category string.

    e.g. ``transform = core.category("transform", gated=True)`` → ``{"transform": "transform"}``;
    ``isolate_cat = core.category("isolate")`` → ``{"isolate_cat": "isolate"}``."""
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            fn = node.value.func
            is_cat = (isinstance(fn, ast.Attribute) and fn.attr == "category") or \
                     (isinstance(fn, ast.Name) and fn.id == "category")
            if is_cat and node.value.args and isinstance(node.value.args[0], ast.Constant):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        out[t.id] = node.value.args[0].value
    return out


def _taxonomy(tree: ast.Module) -> set[str]:
    """The names a tree registers under a taxonomy category (its category-decorated functions)."""
    cats = _category_map(tree)
    taxonomy: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                fn = dec.func if isinstance(dec, ast.Call) else dec
                if isinstance(fn, ast.Name) and fn.id in cats:
                    taxonomy.add(node.name)
    return taxonomy


def _scan_tools() -> tuple[dict[str, ast.FunctionDef], set[str]]:
    """Scan every ``tools/`` category module → (all tools {name: node}, taxonomy names).

    A category-decorated function lands in both; a bare ``@mcp.tool()`` lands only in tools,
    so the registry check surfaces it as a taxonomy bypass."""
    tools: dict[str, ast.FunctionDef] = {}
    taxonomy: set[str] = set()
    for fname in sorted(os.listdir(TOOLS_DIR)):
        if not fname.endswith(".py") or fname in ("__init__.py", "core.py"):
            continue
        with open(os.path.join(TOOLS_DIR, fname)) as f:
            tree = ast.parse(f.read(), filename=fname)
        cats = _category_map(tree)
        tools.update(_mcp_tools(tree, frozenset(cats)))
        taxonomy |= _taxonomy(tree)
    return tools, taxonomy


def check_tool_registry(tools, taxonomy) -> bool:
    """Every registered tool must go through a taxonomy category (minus documented aliases)."""
    registered = set(tools)
    declared = taxonomy - TAXONOMY_ALIASES
    missing = declared - registered          # in the taxonomy, no such tool
    unlisted = registered - declared         # a tool that bypassed the category decorator
    if missing or unlisted:
        parts = []
        if unlisted:
            parts.append(f"tools bypassing a category (bare @mcp.tool()?): {sorted(unlisted)}")
        if missing:
            parts.append(f"taxonomy names with no tool: {sorted(missing)}")
        _fail("tool-registry", "; ".join(parts))
        return False
    _ok("tool-registry", f"{len(registered)} tools, all under a taxonomy category")
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


def banned_names(text: str | None = None) -> set[str]:
    """Parse the banned-tool-name ledger out of nomenclature.md — the backtick-quoted first
    token of each `- ...` line between the `<!-- nomenclature:banned -->` markers. The doc is
    the source of truth; this reads it so a naming decision made there is enforced here."""
    if text is None:
        with open(NOMENCLATURE) as f:
            text = f.read()
    block = re.search(r"<!-- nomenclature:banned -->(.*?)<!-- /nomenclature:banned -->", text, re.S)
    if not block:
        return set()
    return set(re.findall(r"^\s*-\s*`([^`]+)`", block.group(1), re.M))


def check_nomenclature(tools, taxonomy, banned: set[str] | None = None) -> bool:
    """Tool/subcommand names must be snake_case and must not use a banned (implementation-
    named) word — the rule from nomenclature.md, enforced against the live TAXONOMY."""
    if banned is None:
        banned = banned_names()
    names = set(tools) | taxonomy
    not_snake = sorted(n for n in names if not SNAKE.match(n))
    hits = sorted(n for n in names if n in banned)
    if not_snake or hits:
        parts = []
        if not_snake:
            parts.append(f"not snake_case: {not_snake}")
        if hits:
            parts.append(f"banned (implementation-named) tool names: {hits} — see nomenclature.md")
        _fail("nomenclature", "; ".join(parts))
        return False
    _ok("nomenclature", f"{len(names)} names snake_case, none banned ({len(banned)} on the ledger)")
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
    tools, taxonomy = _scan_tools()
    results = [
        check_tool_registry(tools, taxonomy),
        check_tool_docstrings(tools),
        check_readme_tools(tools),
        check_nomenclature(tools, taxonomy),
        check_frontend_io(),
    ]
    failed = results.count(False)
    print(f"hard-lint: {failed} failing / {len(results)} checks — "
          + ("clean" if not failed else "fix before merge"))
    return failed


if __name__ == "__main__":
    sys.exit(main())
