"""The MCP tool surface, split into one module per taxonomy category.

Importing this package imports every category module, which registers its tools onto the
shared :data:`core.mcp` and records its taxonomy membership. The taxonomy is therefore
**derived from the modules** — to see what's in a category, open its file.

  session · transform · shape · annotate · isolate · derive · arrange · manage(=workspace)
"""

from __future__ import annotations

from . import annotate, arrange, derive, isolate, manage, session, shape, transform  # noqa: F401
from .core import gated_set, mcp, taxonomy_map

# Snapshots, valid once every category module above has imported and registered its tools.
TAXONOMY = taxonomy_map()
GATED = gated_set()

__all__ = ["mcp", "TAXONOMY", "GATED", "taxonomy_map", "gated_set",
           "session", "transform", "shape", "annotate", "isolate", "derive", "arrange", "manage"]
