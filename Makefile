# make check — the governance entry for linting. It governs TWO lanes:
#
#   deterministic      hard_lint/ — executable/mechanical checks (code that passes or fails)
#   non-deterministic  soft_lint/ — an instruction set an agent follows to judge a PR
#                      against the rules (harness_driver/, mapped by HARNESS.md)
#
# The deterministic lane is wired: `hard_lint/check.py` runs the mechanical invariants and
# the pytest suite (with a >=90% branch-coverage gate) — both exit non-zero on failure. The
# soft lane's *driver* (the agent that runs soft_lint/instructions.md on a PR) is still
# pending. Run `make check` and it fans out to both lanes; `make test` runs the unit suite +
# the hard_lint self-tests.

PYTHON ?= python3
# The suite + coverage gate run under uv so the dev deps (pytest, pytest-cov) resolve.
PYTEST ?= uv run pytest

.PHONY: check check-deterministic check-soft test test-py test-lint test-frontend

check: check-deterministic check-soft

# Deterministic lane: mechanical invariants THEN the test suites + coverage gates. The
# suites must be fast (they are — tiny synthetic arrays, tmp workspaces, no live server).
check-deterministic:
	@$(PYTHON) hard_lint/check.py
	@$(PYTEST)
	@$(MAKE) --no-print-directory test-frontend

check-soft:
	@echo "» non-deterministic linter — soft_lint/ (agent instruction set)"
	@echo "  driver pending: on a PR, an agent reviews the diff via soft_lint/instructions.md"
	@echo "  read → soft_lint/README.md   rules → HARNESS.md → harness_driver/"

# `make test` = the Python unit suite + the frontend suite + the linter self-tests.
test: test-py test-frontend test-lint

test-py:
	@$(PYTEST)

# Frontend (Vitest, ≥90% on state.ts). Skips gracefully if deps aren't installed, so a
# Python-only checkout still passes — `cd frontend && pnpm install` to enable it.
test-frontend:
	@if [ -x frontend/node_modules/.bin/vitest ]; then \
		pnpm --dir frontend test; \
	else \
		echo "» frontend tests skipped — run 'cd frontend && pnpm install' to enable"; \
	fi

test-lint:
	@$(PYTHON) hard_lint/test_check.py
