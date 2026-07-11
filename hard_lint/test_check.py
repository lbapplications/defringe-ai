#!/usr/bin/env python3
"""Tests for hard_lint/check.py — each invariant must PASS on good input and FAIL on a
planted violation. Pure stdlib (no pytest needed): run `python hard_lint/test_check.py`.

This also runs the real checks against the actual repo and asserts they're clean, so the
test suite doubles as the CI gate."""

from __future__ import annotations

import ast
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check  # noqa: E402


def _tools(src: str) -> dict:
    """Parse a snippet of server-like source into the {name: node} tool map."""
    return check._mcp_tools(ast.parse(src))


PASS = 0
FAIL = 0


def expect(name: str, cond: bool) -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name}")


# --- parsing --------------------------------------------------------------

TWO_TOOLS = """
from x import mcp
@mcp.tool()
def alpha():
    "doc a"
    return 1
@mcp.tool()
def beta():
    "doc b"
    return 2
def not_a_tool():
    return 3
"""

tools = _tools(TWO_TOOLS)
expect("mcp_tools finds decorated fns", set(tools) == {"alpha", "beta"})
expect("mcp_tools ignores undecorated", "not_a_tool" not in tools)

# The real structure: a category decorator from core.category(...), applied to the tools.
CAT_SRC = """
from . import core
transform = core.category("transform", gated=True)
manage = core.category("workspace")
@transform
def alpha():
    "doc a"
    return 1
@manage
def beta():
    "doc b"
    return 2
def not_a_tool():
    return 3
"""
cat_tree = ast.parse(CAT_SRC)
cmap = check._category_map(cat_tree)
expect("category_map reads decorator names", cmap == {"transform": "transform", "manage": "workspace"})
expect("mcp_tools finds category-decorated fns",
       set(check._mcp_tools(cat_tree, frozenset(cmap))) == {"alpha", "beta"})
expect("taxonomy derived from category decorators", check._taxonomy(cat_tree) == {"alpha", "beta"})
expect("bare mcp.tool bypass counts as a tool, not in taxonomy",
       set(_tools(TWO_TOOLS)) - check._taxonomy(ast.parse(TWO_TOOLS)) == {"alpha", "beta"})


# --- tool-registry --------------------------------------------------------

expect("registry: matched sets pass", check.check_tool_registry(tools, {"alpha", "beta"}))
expect("registry: tool missing from taxonomy fails",
       not check.check_tool_registry(tools, {"alpha"}))
expect("registry: taxonomy name with no tool fails",
       not check.check_tool_registry(tools, {"alpha", "beta", "ghost"}))


# --- tool-docstrings ------------------------------------------------------

expect("docstrings: all documented pass", check.check_tool_docstrings(tools))
undoc = _tools('from x import mcp\n@mcp.tool()\ndef nodoc():\n    return 1\n')
expect("docstrings: missing docstring fails", not check.check_tool_docstrings(undoc))


# --- readme-tools ---------------------------------------------------------

good_readme = "See `alpha` and `beta(...)` for details."
expect("readme: both referenced pass", check.check_readme_tools(tools, good_readme))
expect("readme: seed-style args form counts",
       check.check_readme_tools(_tools('from x import mcp\n@mcp.tool()\ndef seed():\n "d"\n'),
                                "use `seed [[x,y],…]`"))
expect("readme: absent tool fails", not check.check_readme_tools(tools, "only `alpha` here"))
expect("readme: substring must be in backticks",
       not check.check_readme_tools(tools, "alpha and beta as plain words"))


# --- nomenclature ---------------------------------------------------------

LEDGER = """
prose before
<!-- nomenclature:banned -->
- `canny` → `edge_detect` (name the outcome)
- `grabcut` → name the outcome
<!-- /nomenclature:banned -->
prose after
"""
banned = check.banned_names(LEDGER)
expect("nomenclature: ledger parsed from markers", banned == {"canny", "grabcut"})
expect("nomenclature: no-marker text is empty", check.banned_names("nothing here") == set())
expect("nomenclature: clean snake_case names pass",
       check.check_nomenclature(tools, {"alpha", "beta"}, banned))
expect("nomenclature: a banned tool name fails",
       not check.check_nomenclature(_tools('from x import mcp\n@mcp.tool()\ndef canny():\n "d"\n'),
                                    {"canny"}, banned))
expect("nomenclature: camelCase name fails",
       not check.check_nomenclature(tools, {"alpha", "betaTool"}, banned))
expect("nomenclature: hyphen name fails",
       not check.check_nomenclature(tools, {"alpha", "edge-detect"}, banned))


# --- frontend-io ----------------------------------------------------------

with tempfile.TemporaryDirectory() as d:
    open(os.path.join(d, "state.ts"), "w").write("export const post = () => fetch('/api')\n")
    open(os.path.join(d, "Clean.tsx"), "w").write("import {post} from './state'\npost()\n")
    expect("frontend: fetch only in state.ts passes", check.check_frontend_io(d))
    open(os.path.join(d, "Bad.tsx"), "w").write("function x(){ return fetch('/api/x') }\n")
    expect("frontend: bare fetch in component fails", not check.check_frontend_io(d))


# --- the real repo must be clean ------------------------------------------

print("\n  -- against the live repo --")
expect("live repo passes all checks", check.main() == 0)


print(f"\ntest_check: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
