#!/usr/bin/env python3
"""Run the common stateful skill CLI protocol."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.skill_protocol.runtime import main  # noqa: E402, I001


if __name__ == "__main__":
    raise SystemExit(main())
