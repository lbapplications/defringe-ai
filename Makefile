# make check — the governance entry for linting. It governs TWO lanes:
#
#   deterministic      executable/mechanical checks (code that passes or fails)
#   non-deterministic  soft_lint/ — an instruction set an agent follows to judge a PR
#                      against the rules (harness_driver/, mapped by HARNESS.md)
#
# Neither lane's *driver* (the thing that actually executes it) is wired yet: the
# deterministic linters don't exist, and the soft lane's driver is the agent that runs
# soft_lint/instructions.md on a PR. This target is the stable seam they plug into — run
# `make check` and it fans out to both lanes.

.PHONY: check check-deterministic check-soft

check: check-deterministic check-soft

check-deterministic:
	@echo "» deterministic linters — none wired yet (mechanical checks + driver pending)"

check-soft:
	@echo "» non-deterministic linter — soft_lint/ (agent instruction set)"
	@echo "  driver pending: on a PR, an agent reviews the diff via soft_lint/instructions.md"
	@echo "  read → soft_lint/README.md   rules → HARNESS.md → harness_driver/"
