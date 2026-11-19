"""Post-capture stream slicing for command output and file reads.

Operators are language-agnostic and line-oriented:

    head:N, tail:N, lines:N-M, raw:N-M, target:N-M,
    context:PATTERN[:N], fails[:N], grep:PATTERN, grepv:PATTERN,
    count, num[:START], dedupe

Invalid operators are reported, not silently ignored.  ``target`` and ``count``
are terminal; placing operators after them is an error.
"""

from __future__ import annotations

import re
from collections import Counter

from .safety import parse_range


class SliceError(ValueError):
    pass


# Plain failure words only: no test-runner, compiler or language output formats.
_FAIL_PATTERN = re.compile(r"\b(fail(s|ed|ure|ures|ing)?|errors?|exceptions?|panic(ked)?|fatal)\b", re.IGNORECASE)


def apply_slices(text: str, ops: list[str]) -> tuple[str, list[str]]:
    """Apply slice operators in order and return (text, errors)."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    if not normalized or normalized.endswith("\n"):
        lines.pop()
    errors: list[str] = []

    for op_index, raw_op in enumerate(ops):
        op = raw_op.strip()
        if not op:
            continue
        try:
            if op.startswith("head:"):
                n = _nonneg_int(op.split(":", 1)[1], op)
                lines = lines[:n]

            elif op.startswith("tail:"):
                n = _nonneg_int(op.split(":", 1)[1], op)
                lines = lines[-n:] if n > 0 else []

            elif op.startswith("lines:") or op.startswith("raw:"):
                value = op.split(":", 1)[1]
                ranges = parse_range(value)
                if len(ranges) != 1:
                    raise SliceError(f"{op}: expected one range N-M")
                start, end = ranges[0]
                lines = lines[start - 1 : end]

            elif op.startswith("target:"):
                value = op.split(":", 1)[1]
                ranges = parse_range(value)
                if len(ranges) != 1:
                    raise SliceError(f"{op}: expected one range N-M")
                start, end = ranges[0]
                start = max(1, start)
                end = min(len(lines), end)
                block = lines[start - 1 : end]
                rendered = [f"=== [context {start}-{end} (numbered)] ==="]
                rendered.extend(f"{i}: {line}" for i, line in enumerate(block, start=start))
                rendered.append("")
                rendered.append("=== [target: copy verbatim to batch_edit] ===")
                rendered.extend(block)
                rendered.append("=== [end target] ===")
                if any(o.strip() for o in ops[op_index + 1 :]):
                    errors.append("target: must be the final slice; later operators ignored")
                return "\n".join(rendered), errors

            elif op.startswith("context:"):
                rest = op[len("context:") :]
                pattern = rest
                ctx = 3
                if ":" in rest:
                    maybe_pattern, maybe_n = rest.rsplit(":", 1)
                    if maybe_n.strip().isdigit():
                        pattern = maybe_pattern
                        ctx = max(0, int(maybe_n))
                if not pattern:
                    raise SliceError("context: pattern must not be empty")
                try:
                    rx = re.compile(pattern, re.IGNORECASE)
                    match = lambda line: rx.search(line) is not None
                except re.error:
                    needle = pattern.lower()
                    match = lambda line: needle in line.lower()
                selected: set[int] = set()
                for i, line in enumerate(lines):
                    if match(line):
                        selected.update(range(max(0, i - ctx), min(len(lines), i + ctx + 1)))
                if not selected:
                    lines = [f"(no matches for context:{pattern})"]
                else:
                    out: list[str] = []
                    prev = -1
                    for idx in sorted(selected):
                        if prev != -1 and idx > prev + 1 and ctx > 0:
                            out.append("--")
                        out.append(f"{idx + 1}: {lines[idx]}")
                        prev = idx
                    lines = out

            elif op == "fails" or op.startswith("fails:"):
                window: int | None = None
                if ":" in op:
                    window = _nonneg_int(op.split(":", 1)[1], op)
                lines = _filter_failures(lines, window)

            elif op.startswith("grep:"):
                pattern = op.split(":", 1)[1]
                lines = _grep(lines, pattern, invert=False)

            elif op.startswith("grepv:"):
                pattern = op.split(":", 1)[1]
                lines = _grep(lines, pattern, invert=True)

            elif op == "count":
                if any(o.strip() for o in ops[op_index + 1 :]):
                    errors.append("count: must be the final slice; later operators ignored")
                return str(len(lines)), errors

            elif op == "num" or op.startswith("num:"):
                start = 1
                if ":" in op:
                    start = int(op.split(":", 1)[1])
                lines = [f"{i}: {line}" for i, line in enumerate(lines, start=start)]

            elif op == "dedupe":
                lines = _dedupe(lines)

            else:
                raise SliceError(f"unknown slice operator: {op}")

        except SliceError as exc:
            errors.append(str(exc))
        except Exception as exc:  # defensive: one bad operator never kills the batch
            errors.append(f"{op}: {exc}")

    return "\n".join(lines), errors


def _nonneg_int(value: str, op: str) -> int:
    try:
        n = int(value.strip())
    except ValueError as exc:
        raise SliceError(f"{op}: expected an integer") from exc
    if n < 0:
        raise SliceError(f"{op}: expected a non-negative integer")
    return n


def _grep(lines: list[str], pattern: str, *, invert: bool) -> list[str]:
    if not pattern:
        raise SliceError("grep: pattern must not be empty")
    try:
        rx = re.compile(pattern, re.IGNORECASE)
        test = lambda line: rx.search(line) is not None
    except re.error:
        needle = pattern.lower()

        def test(line: str) -> bool:
            return needle in line.lower()

    return [line for line in lines if test(line) != invert]


FAIL_BEFORE = 5  # lines kept before each failure word (default window)
FAIL_AFTER = 10  # lines kept after it
FAIL_TAIL = 10  # last lines always kept: run summaries usually end the output


def _filter_failures(lines: list[str], window: int | None) -> list[str]:
    """Windows around lines with a failure word, plus the last lines of the output.

    Default: 5 lines before and 10 after each match.  ``fails:N``: 2 before, N after.
    """
    if not lines:
        return lines

    matched = [i for i, line in enumerate(lines) if _FAIL_PATTERN.search(line)]
    if not matched:
        return lines[-25:] if len(lines) > 25 else lines

    before, after = (FAIL_BEFORE, FAIL_AFTER) if window is None else (2, window)
    selected: set[int] = set(range(max(0, len(lines) - FAIL_TAIL), len(lines)))
    for idx in matched:
        selected.update(range(max(0, idx - before), min(len(lines), idx + after + 1)))
    out: list[str] = []
    prev = -1
    for idx in sorted(selected):
        if prev != -1 and idx > prev + 1:
            out.append("--")
        out.append(lines[idx])
        prev = idx
    return out


def _dedupe(lines: list[str]) -> list[str]:
    if not lines:
        return lines
    out: list[str] = []
    run_line = lines[0]
    run = 1
    for line in lines[1:]:
        if line == run_line:
            run += 1
            continue
        out.append(run_line if run == 1 else f"{run_line}  (x{run})")
        run_line = line
        run = 1
    out.append(run_line if run == 1 else f"{run_line}  (x{run})")
    return out


def summarize_repeats(lines: list[str], *, limit: int = 10) -> list[tuple[str, int]]:
    """Return the most repeated non-empty lines (utility for renderers)."""
    counts = Counter(line.strip() for line in lines if line.strip())
    return counts.most_common(limit)
