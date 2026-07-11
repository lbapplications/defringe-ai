# specs — top-down artifacts that govern this repo

A **spec** is a governing artifact. It states, top-down, how a system in this repo is
*supposed* to work — the intended shape, before and above the code that implements it. Where
`harness_driver/` tells an agent **how to work in the repo** (rules of conduct), a spec says
**what a system is meant to be** (the design it must conform to).

Scope of what gets a spec: the **workflow**, the **taxonomy**, and any **load-bearing feature**
— the things that, if they drift, quietly break the whole experiment.

## What a spec is (and isn't)
- **Is:** the intended design + the rationale behind it. Load-bearing decisions with their *why*.
- **Isn't:** a changelog, a tutorial, or a mirror of the code. If the code is the record, it
  doesn't belong here.

## How specs get written
Design decisions are **derived, not decreed** — worked out via the Socratic loop
(`/socratic-skill`) and captured here as they land, principle + rationale. A spec is done when
the system it governs could be rebuilt from it and would feel the same.

## Index
- [workflow.md](workflow.md) — how the editing workflow feels, in the UI window **and** headless
  (an agent driving the MCP with no UI). *Contract derived (C1–C10); concrete schema in
  [`../design/workflow.md`](../design/workflow.md).*
