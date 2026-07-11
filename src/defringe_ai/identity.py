"""Identity — deterministic ids for projects and assets, and the png intake gate.

The workflow contract (specs/workflow.md, C3/C8) keys all state on *identity*, not on a
bare filename:

  * a **project** is a root directory       → ``project_id = uuid5(normalized_abs_root)``
  * an **asset** is a path within a project  → ``asset_id   = uuid5(normalized_rel_path)``

Both ids are full uuid5 (name-based, deterministic: same path → same id, forever; no
truncation, so a key collision can never route into the wrong workspace). The real path is
always stored *beside* the id so a lookup can re-derive the id and **verify** it.

Intake is **png-only** (C8): a non-png asset is rejected with a reason rather than silently
transcoded, so working states stay lossless and alpha/masks stay exact.
"""

from __future__ import annotations

import os
import uuid

# A fixed namespace for every defringe-ai id. Arbitrary but stable — changing it would
# repoint every id, so it never changes. (A clean, uuid-shaped constant.)
NAMESPACE = uuid.UUID("de1f0e1d-defa-4c7e-8a5e-0000def020ea")

# The 8-byte PNG signature — the only format we accept in (see ``is_png`` / ``ensure_png``).
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def norm_root(root: str) -> str:
    """A project root's canonical form: absolute, symlink-resolved, no trailing slash.

    This is what the ``project_id`` is derived from, so two spellings of the same directory
    (``./x``, ``x/``, a symlink) map to one project."""
    return os.path.realpath(root)


def norm_rel(rel: str) -> str:
    """An asset's canonical path *relative to its project root*: normalized, forward-slashed.

    Never absolute — the relative path is the asset's identity within its project, so it stays
    portable if the whole project moves."""
    r = os.path.normpath(rel).replace(os.sep, "/")
    return r.lstrip("/")


def project_id(root: str) -> str:
    """The deterministic id of a project root (``uuid5`` over its canonical absolute path)."""
    return str(uuid.uuid5(NAMESPACE, norm_root(root)))


def asset_id(rel: str) -> str:
    """The deterministic id of an asset (``uuid5`` over its canonical project-relative path)."""
    return str(uuid.uuid5(NAMESPACE, norm_rel(rel)))


def relativize(asset_path: str, root: str) -> str:
    """The canonical relative path of ``asset_path`` within project ``root`` (both real-path'd)."""
    return norm_rel(os.path.relpath(os.path.realpath(asset_path), norm_root(root)))


def is_png(path: str) -> bool:
    """True iff ``path`` is a real PNG — decided by its signature bytes, not its extension."""
    try:
        with open(path, "rb") as f:
            return f.read(len(PNG_MAGIC)) == PNG_MAGIC
    except OSError:
        return False


def ensure_png(path: str) -> None:
    """Gate an intake to png-only (C8). Raise a clear ``ValueError`` for a missing file or a
    non-png — the reason is the message, surfaced straight to the caller/agent."""
    if not os.path.exists(path):
        raise ValueError(f"no such asset: {path!r}")
    if not is_png(path):
        ext = os.path.splitext(path)[1] or "?"
        raise ValueError(
            f"asset must be a PNG, got {ext} ({os.path.basename(path)}). "
            "defringe-ai is png-only — convert it first; we won't silently transcode "
            "(lossy formats fringe alpha/mask edges)."
        )
