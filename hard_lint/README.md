# hard_lint — the deterministic linter

`make check` governs **two lanes** of linting for this repo:

| Lane | What it is | Status |
|---|---|---|
| **deterministic** | **this** — executable/mechanical checks (code that passes or fails) | wired: `hard_lint/check.py` |
| **non-deterministic** | `soft_lint/` — an *instruction set* an agent follows to judge a PR | instructions here; driver pending |

`hard_lint` is the **deterministic** lane: a small stdlib program (`check.py`) that hardens
the mechanical parts of the `harness_driver/` rules into pass/fail checks. It imports
nothing from the package (pure `ast` + file reads), so it's fast and side-effect-free.

## Checks

| Check | Rule hardened | Fails when |
|---|---|---|
| `tool-registry` | [tools](../harness_driver/tools.md) | an `@mcp.tool()` isn't in `TAXONOMY`, or a `TAXONOMY` name has no tool |
| `tool-docstrings` | [docstrings](../harness_driver/docstrings.md) | an `@mcp.tool()` has no docstring |
| `readme-tools` | [tools](../harness_driver/tools.md) | a tool name isn't referenced in the README (as `` `name` ``) |
| `frontend-io` | [frontend](../harness_driver/frontend.md) | a bare `fetch(` appears in a component (server I/O must go through `state.ts`) |

## Run

```bash
make check          # both lanes (hard_lint runs the deterministic lane)
python hard_lint/check.py     # just the hard checks — exit code = # failing
make test           # hard_lint self-tests (each check passes clean + catches a plant)
```

## Adding a check

A check is a `check_*` function that prints a `✓`/`✗` line and returns a bool. Add it to the
`results` list in `main()`, and add a test to `test_check.py` that proves it both **passes on
good input and fails on a planted violation** — a linter with no failing-case test is
untrusted. Keep checks **mechanical**: if it needs judgment, it belongs in `soft_lint/`, not
here. A `soft_lint` `SCRUTINY`/`BREAK` item **graduates** into a hard check once it's
mechanical enough to automate.
