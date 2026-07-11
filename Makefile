# make check — the governance entry for linting. It governs TWO lanes:
#
#   deterministic      hard_lint/ — executable/mechanical checks (code that passes or fails)
#   non-deterministic  soft_lint/ — an instruction set an agent follows to judge a PR
#                      against the rules (harness_driver/, mapped by HARNESS.md)
#
# The deterministic lane is wired: `hard_lint/check.py` runs the mechanical invariants and
# exits non-zero on failure. The soft lane's *driver* (the agent that runs
# soft_lint/instructions.md on a PR) is still pending. Run `make check` and it fans out to
# both lanes; `make test` runs the hard_lint self-tests.

PYTHON ?= python3

.PHONY: check check-deterministic check-soft test

check: check-deterministic check-soft

check-deterministic:
	@$(PYTHON) hard_lint/check.py

check-soft:
	@echo "» non-deterministic linter — soft_lint/ (agent instruction set)"
	@echo "  driver pending: on a PR, an agent reviews the diff via soft_lint/instructions.md"
	@echo "  read → soft_lint/README.md   rules → HARNESS.md → harness_driver/"

test:
	@$(PYTHON) hard_lint/test_check.py
