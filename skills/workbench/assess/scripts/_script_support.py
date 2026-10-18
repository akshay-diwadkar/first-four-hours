"""Small provider-free adapters for Assess action scripts."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from assess_contract import AssessError


def run_action(action: Callable[[], Any], *, phase: str) -> int:
    try:
        result = action()
    except AssessError as exc:
        print(json.dumps({"diagnostics": [exc.diagnostic(phase=phase)]}, sort_keys=True, separators=(",", ":")))
        return 3
    except (OSError, ValueError, KeyError, TypeError) as exc:
        error = AssessError("runtime.action_invalid", str(exc) or exc.__class__.__name__)
        print(json.dumps({"diagnostics": [error.diagnostic(phase=phase)]}, sort_keys=True, separators=(",", ":")))
        return 3
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0
