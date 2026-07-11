# soft_lint — the non-deterministic linter

`make check` governs **two lanes** of linting for this repo:

| Lane | What it is | Status |
|---|---|---|
| **deterministic** | executable/mechanical checks (code that passes or fails) | not wired yet |
| **non-deterministic** | **this** — an *instruction set* an agent follows to judge a PR against the rules | instructions here; driver not wired yet |

`soft_lint` is the **non-deterministic** lane: a judgment-based review, **not a program**.
When a PR is made, an agent reads **[instructions.md](instructions.md)** and reviews the
diff against the repo's rules (`harness_driver/`, mapped by `HARNESS.md`) using the
**80/20 method** — clear mechanical breaks are flagged, but some things **pass only after
heavy scrutiny**.

## Where this sits

- **Run it via `make check`** — the single governance entry that will invoke both lanes
  once their *drivers* (the things that actually execute a lane) land.
- **Not built yet:** the deterministic linters, and the drivers for both lanes (the soft
  driver invokes an agent on the diff; the deterministic driver runs the mechanical checks).
- **The two lanes compose:** a soft `SCRUTINY`/`BREAK` item **graduates** into a
  deterministic check once it's mechanical enough to automate. soft_lint is where a rule is
  enforced first — by judgment — before it hardens into code.
