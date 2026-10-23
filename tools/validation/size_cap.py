#!/usr/bin/env python3
"""Enforce three cases per skill, 12 shared, and 48 total before any test body.

Loaded into every pytest process ``test_ownership.py run`` starts; a run split
into several shards first collects the whole selection once, so the count covers
every selected case before any shard runs a body. Counting collected items keeps the cap
deterministic: a loaded host cannot cause a false failure, and one function
parametrized hundreds of times counts as heavily as hundreds of separate
functions, so the cap cannot be side-stepped by merging tests.

The runner supplies SKILLS_MAX_GATED_ITEMS. The hard ceilings also apply when
the plugin is loaded independently; repository pytest requires the supervisor.
"""

from __future__ import annotations

import json
from collections import Counter
import os
import sys
from pathlib import PurePosixPath

CAP_ENV = "SKILLS_MAX_GATED_ITEMS"
MAX_SKILL_ITEMS = 3
MAX_SHARED_ITEMS = 12
MAX_TOTAL_ITEMS = 48
SKILL_NAMES = frozenset({"architect", "assess", "atlas", "blueprint", "charter", "construct", "diagnose", "ideate", "pr", "reason", "router", "scribe", "ticket"})
_REPORT_PATH = os.environ.get("SKILLS_CASE_REPORT")


def normalize_test_target(target: str) -> str:
    """Canonicalize only the safe file portion; node/parameter text is opaque."""
    file_part, separator, node = target.partition("::")
    path = PurePosixPath(file_part.replace("\\", "/"))
    if not file_part or path.is_absolute() or ".." in path.parts or ":" in file_part:
        raise ValueError(f"unsafe pytest target path: {file_part}")
    return path.as_posix() + separator + node


def case_group(nodeid: str) -> str:
    parts = normalize_test_target(nodeid).partition("::")[0].split("/")
    if len(parts) >= 4 and parts[:2] == ["tests", "skills"] and parts[2] in SKILL_NAMES:
        return parts[2]
    if len(parts) >= 3 and parts[0] == "tests" and parts[1] in {"repository", "skill_protocol"}:
        return "shared"
    raise ValueError(f"{'/'.join(parts)}: unrecognized test location; skill tests including integrations belong under tests/skills/<registered-skill>/; shared checks belong under tests/repository/ or tests/skill_protocol/")


def collection_errors(nodeids: list[str], cap: int) -> list[str]:
    counts: Counter[str] = Counter()
    errors: list[str] = []
    for node in nodeids:
        try:
            counts[case_group(node)] += 1
        except ValueError as exc:
            errors.append(str(exc))
    errors.extend(f"{name}: {count} collected cases exceeds the hard {MAX_SHARED_ITEMS if name == 'shared' else MAX_SKILL_ITEMS}-case limit"
                  for name, count in sorted(counts.items())
                  if count > (MAX_SHARED_ITEMS if name == "shared" else MAX_SKILL_ITEMS))
    if not 1 <= cap <= MAX_TOTAL_ITEMS:
        errors.append(f"suite limit must be between 1 and {MAX_TOTAL_ITEMS}")
    elif len(nodeids) > cap:
        errors.append(f"{len(nodeids)} collected cases exceeds the {cap}-case suite limit")
    return errors


def _progress(record) -> None:
    path = _REPORT_PATH
    if path:
        line = (json.dumps(record) + "\n").encode("utf-8")
        # Parallel shard processes share one report; an exclusive lock keeps each record whole.
        with open(path, "ab") as stream:
            if os.name == "nt":
                import msvcrt
                import time
                stream.seek(0)
                while True:
                    try:
                        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except PermissionError:
                        time.sleep(0.001)
                try:
                    stream.write(line)
                    stream.flush()
                finally:
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                getattr(fcntl, "flock")(stream.fileno(), getattr(fcntl, "LOCK_EX"))
                try:
                    stream.write(line)
                    stream.flush()
                finally:
                    getattr(fcntl, "flock")(stream.fileno(), getattr(fcntl, "LOCK_UN"))


def pytest_runtest_logreport(report) -> None:
    _progress({"event": "case", "nodeid": report.nodeid, "phase": report.when, "outcome": report.outcome})


def pytest_collection_finish(session) -> None:
    _progress({"event": "collection", "nodes": [item.nodeid for item in session.items]})
    raw = os.environ.get(CAP_ENV, str(MAX_TOTAL_ITEMS))
    try:
        cap = int(raw)
    except ValueError:
        cap = 0
    collected = len(session.items)
    errors = collection_errors([item.nodeid for item in session.items], cap)
    if not errors:
        return
    record = {
        "event": "size-cap",
        "valid": False,
        "collected_items": collected,
        "max_gated_items": cap,
        "errors": errors,
    }
    print(json.dumps(record, separators=(",", ":"), sort_keys=True), file=sys.stderr, flush=True)
    # Clear the collected items as well as stopping, so no test body runs: the
    # point is to refuse the run, not to execute part of it.
    session.items[:] = []
    session.shouldstop = True
    session.exitstatus = 2
