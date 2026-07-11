# Rule: docstrings — Google style on every forward-facing function

**Scope — read before** writing or **editing** any function. Editing a function's
behaviour or signature means **updating its docstring in the same change** — a stale
docstring is a bug.

## The standard (forward-facing functions)

Every public / forward-facing function — MCP tools, CLI handlers, and each tool-class
`@staticmethod` — gets a **Google-style** docstring: a one-line summary, then `Args:`,
`Returns:`, and `Raises:` (only the sections that apply).

```python
def final_price(price: float, discount_percentage: float) -> float:
    """Calculate the final price of an item after applying a discount.

    Args:
        price: The original cost of the item before discount.
        discount_percentage: The discount rate as a whole number (e.g. 20 for 20%).

    Returns:
        The updated price after subtracting the discount amount.

    Raises:
        ValueError: If price or discount_percentage is negative.
    """
```

- Summary line: imperative mood, one line, ends with a period.
- `Args:` one entry per parameter (skip `self`); `Returns:` describes the value, not the
  type (the type is in the signature); `Raises:` every exception the caller should expect.

## Lighter for internal helpers ("a little less on the descriptors")

Module-private helpers (leading `_`, not exported, not a tool) get a **one-line** summary
— no `Args`/`Returns` ceremony unless the behaviour is non-obvious. Don't gold-plate
plumbing; do fully document anything an agent or another module calls.

## Keep it true

If you change what a function does, takes, returns, or raises, edit the docstring in the
same commit. Reviewer's rule of thumb: a diff that changes a signature but not its
docstring is incomplete.
