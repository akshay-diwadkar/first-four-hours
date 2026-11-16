#!/usr/bin/env python3
"""Deployed entrypoint for batch-ops MCP server."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from batch_ops.server import mcp, main
if __name__ == "__main__":
    main()
