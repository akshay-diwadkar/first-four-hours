"""batch_ops - a language-agnostic batch evidence engine for coding agents.

The package exposes three MCP tools:

* ``batch_read``  - bounded, concurrent reads, surveys, diffs, greps and handles.
* ``batch_run``   - bounded, concurrent command execution with failure-first synthesis.
* ``batch_edit``  - transactional multi-file edits with dry-run, diff and verification.

The core is standard-library only.  The MCP layer (``batch_ops.server``) uses the
official ``mcp`` package and Pydantic; the CLI (``batch_ops.cli``) uses the core.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


def _build_id() -> str:
    """7 hex characters naming this exact source, so a report shows which server build ran."""
    digest = hashlib.sha256()
    for source in sorted(Path(__file__).parent.glob("*.py")):
        digest.update(source.name.encode())
        digest.update(source.read_bytes().replace(b"\r\n", b"\n"))
    return digest.hexdigest()[:7]


BUILD = _build_id()
