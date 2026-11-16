"""Byte/token budget with must/should/nice priorities, shared after the work is done.

Items are produced first (each bounded by its own per-item cap), then the batch
budget is shared by ``water_fill``: items smaller than their fair share keep
everything, and what they leave unused goes to the larger ones.  Batching more
items therefore never cuts an item while budget sits unused.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from .safety import format_bytes

TIERS = {"must": 0, "should": 1, "nice": 2}

# Claude Code saves a tool result above its inline limit to a file and shows the model a 2KB
# preview, which agents tend to ignore (observed: 42.9KB shown inline, 63.6KB saved to file).
# Every report is therefore capped below that limit; over the cap, items share the budget
# and are cut with continuations instead.
REPORT_CAP_BYTES = max(4096, int(os.environ.get("BATCH_OPS_MAX_REPORT_BYTES", 40 * 1024)))


def cap_tokens(tokens: int) -> int:
    """A token budget clamped so the rendered report stays within REPORT_CAP_BYTES."""
    return max(64, min(int(tokens), REPORT_CAP_BYTES // 4))


@dataclass
class Budget:
    tokens: int = 40000
    item_tokens: int = 10000
    time_s: float = 60.0
    max_items: int = 64

    def __post_init__(self) -> None:
        self.tokens = max(256, int(self.tokens))
        self.item_tokens = max(64, int(self.item_tokens))
        self.time_s = max(0.5, float(self.time_s))
        self.max_items = max(1, int(self.max_items))

    @property
    def bytes(self) -> int:
        return self.tokens * 4

    @property
    def item_bytes(self) -> int:
        return self.item_tokens * 4


@dataclass
class BudgetTracker:
    budget: Budget
    used_bytes: int = 0
    skipped: int = 0
    skipped_reasons: list[str] = field(default_factory=list)

    @property
    def remaining(self) -> int:
        return max(0, self.budget.bytes - self.used_bytes)

    def skip(self, reason: str) -> None:
        self.skipped += 1
        self.skipped_reasons.append(reason)

    def summary(self) -> str:
        parts = [f"{format_bytes(self.used_bytes)}/{format_bytes(self.budget.bytes)}"]
        if self.skipped:
            parts.append(f"{self.skipped} skipped")
        return ", ".join(parts)


def body_budget(total: int, items: int) -> int:
    """Bytes left for item bodies once report headers (about 320 bytes per item) are paid for,
    so the rendered report fits the budget and is never cut in the middle by the final cap."""
    return max(1024, int(total) - 1024 - 320 * max(0, items))


def tier(priority: str) -> int:
    return TIERS.get(priority, 1)


def water_fill(sizes: list[int], tiers: list[int], total: int, *, floor: int = 256) -> list[int]:
    """Max-min fair shares of *total* bytes, served tier by tier (lower tier first).

    Within a tier, items smaller than the fair share get their full size and the
    leftover is split among the rest.  Every item with content gets at least
    *floor* bytes so nothing disappears entirely.
    """
    shares = [0] * len(sizes)
    remaining = max(0, int(total))
    for level in sorted(set(tiers)):
        members = sorted((i for i in range(len(sizes)) if tiers[i] == level), key=lambda i: sizes[i])
        for pos, i in enumerate(members):
            fair = remaining // max(1, len(members) - pos)
            share = min(max(0, sizes[i]), fair)
            shares[i] = share
            remaining -= share
    for i, size in enumerate(sizes):
        if size > 0 and shares[i] < floor:
            shares[i] = min(size, floor)
    return shares
