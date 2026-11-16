"""batch_ops - a language-agnostic batch evidence engine for coding agents.

The package exposes three MCP tools:

* ``batch_read``  - bounded, concurrent reads, surveys, diffs, greps and handles.
* ``batch_run``   - bounded, concurrent command execution with failure-first synthesis.
* ``batch_edit``  - transactional multi-file edits with dry-run, diff and verification.

The core is standard-library only.  The MCP layer (``batch_ops.server``) uses the
official ``mcp`` package and Pydantic; the CLI (``batch_ops.cli``) uses the core.
"""

from __future__ import annotations
