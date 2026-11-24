"""Post-capture stream slicing for command output and file reads.

Operators are language-agnostic and line-oriented:

    head:N, tail:N, lines:N-M, raw:N-M, target:N-M,
    context:PATTERN[:N], fails[:N], grep:PATTERN, grepv:PATTERN,
    count, num[:START], dedupe,
    json:PATH, sort[:-|:n|:-n], uniq, countby:RE, cut:SEP:N

Invalid operators are reported, not silently ignored.  ``target`` and ``count``
are terminal; placing operators after them is an error.
"""

from __future__ import annotations

import json
import re
from collections import Counter

from .safety import parse_range


class SliceError(ValueError):
    pass


class NotJsonError(SliceError):
    """A json: operator's input is neither JSON nor JSON Lines."""


# Plain failure words only: no test-runner, compiler or language output formats.
_FAIL_PATTERN = re.compile(r"\b(fail(s|ed|ure|ures|ing)?|errors?|exceptions?|panic(ked)?|fatal)\b", re.IGNORECASE)


def apply_slices(text: str, ops: list[str], *, skip_non_json: bool = False) -> tuple[str, list[str]]:
    """Apply slice operators in order and return (text, errors).

    With *skip_non_json*, a json: operator whose input is neither JSON nor JSON Lines leaves
    the lines unchanged and reports no error."""
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

            elif op.startswith("json:"):
                lines = _json_lines(lines, op[len("json:") :])

            elif op == "sort" or op.startswith("sort:"):
                lines = _sort(lines, op[len("sort:") :] if ":" in op else "", op)

            elif op == "uniq":
                counts: dict[str, int] = {}
                for line in lines:
                    counts[line] = counts.get(line, 0) + 1
                lines = [f"{n} {line}" for line, n in counts.items()]

            elif op.startswith("countby:"):
                lines = _countby(lines, op[len("countby:") :])

            elif op.startswith("cut:"):
                lines = _cut(lines, op[len("cut:") :], op)

            else:
                raise SliceError(f"unknown slice operator: {op}")

        except NotJsonError as exc:
            if not skip_non_json:
                errors.append(str(exc))
        except SliceError as exc:
            errors.append(_with_shell_hint(str(exc), op))
        except Exception as exc:  # defensive: one bad operator never kills the batch
            errors.append(f"{op}: {exc}")

    return "\n".join(lines), errors


# A shell separator in an operator that failed to parse: shell text written after ' ||| '.
_SHELL_JOIN = re.compile(r";|&&|\|\||\s\|\s")


def _with_shell_hint(message: str, op: str) -> str:
    found = _SHELL_JOIN.search(op)
    if not found:
        return message
    shell = op[found.start() :].strip()
    return (f"{message}; slices follow ' ||| ', so `{shell}` was read as a slice and never ran: "
            "put shell commands before the first ' ||| '")


def _nonneg_int(value: str, op: str) -> int:
    try:
        n = int(value.strip())
    except ValueError as exc:
        raise SliceError(f"{op}: expected an integer") from exc
    if n < 0:
        raise SliceError(f"{op}: expected a non-negative integer")
    return n


_JSON_INDEX = re.compile(r"\[(-?\d+|\*)\]")
_JSON_SEGMENT = re.compile(r"([^\[\]]*)((?:\[(?:-?\d+|\*)\])*)")
_NUMBER = re.compile(r"(?:(?<!\w)-)?\d+(\.\d+)?")  # a minus joined to a word character is a hyphen


def _json_tokens(path: str) -> list[tuple[str, object]]:
    """PATH as ('key', name), ('index', n) and ('all', None) steps."""
    if not path:
        raise SliceError("json: PATH is required")
    tokens: list[tuple[str, object]] = []
    for part in path.split("."):
        found = _JSON_SEGMENT.fullmatch(part)
        if not part or not found:
            raise SliceError(f"json:{path}: invalid path")
        if found.group(1):
            tokens.append(("key", found.group(1)))
        for index in _JSON_INDEX.findall(found.group(2)):
            tokens.append(("all", None) if index == "*" else ("index", int(index)))
    return tokens


def _json_walk(doc: object, tokens: list[tuple[str, object]]) -> list[object]:
    values = [doc]
    for kind, arg in tokens:
        step: list[object] = []
        for value in values:
            if kind == "key":
                if isinstance(value, dict) and arg in value:
                    step.append(value[arg])
            elif kind == "index":
                if isinstance(value, list) and -len(value) <= int(arg) < len(value):  # type: ignore[arg-type]
                    step.append(value[int(arg)])  # type: ignore[arg-type]
            elif isinstance(value, list):
                step.extend(value)
            elif isinstance(value, dict):
                step.extend(value.values())
        values = step
    return values


def _json_lines(lines: list[str], path: str) -> list[str]:
    tokens = _json_tokens(path)
    text = "\n".join(lines)
    if not text.strip():
        return []
    try:
        docs = [json.loads(text)]
    except ValueError:
        try:
            docs = [json.loads(line) for line in lines if line.strip()]
        except ValueError as exc:
            raise NotJsonError("json: input is neither JSON nor JSON Lines") from exc
    out: list[str] = []
    for doc in docs:
        for value in _json_walk(doc, tokens):
            if isinstance(value, str):
                out.append(value)
            else:
                out.append(json.dumps(value, separators=(",", ":"), ensure_ascii=False))
    return out


def _sort(lines: list[str], arg: str, op: str) -> list[str]:
    if arg not in ("", "-", "n", "-n") or (op != "sort" and not arg):
        raise SliceError(f"{op}: expected sort, sort:-, sort:n or sort:-n")
    descending = arg.startswith("-")
    if not arg.endswith("n"):
        return sorted(lines, reverse=descending)
    numbered: list[tuple[float, str]] = []
    plain: list[str] = []
    for line in lines:
        found = _NUMBER.search(line)
        if found:
            numbered.append((float(found.group(0)), line))
        else:
            plain.append(line)
    numbered.sort(key=lambda pair: pair[0], reverse=descending)
    return [line for _, line in numbered] + plain


def _countby(lines: list[str], pattern: str) -> list[str]:
    if not pattern:
        raise SliceError("countby: pattern must not be empty")
    try:
        rx = re.compile(pattern, re.IGNORECASE)
    except re.error:
        rx = re.compile(re.escape(pattern), re.IGNORECASE)
    counts: dict[str, int] = {}
    for line in lines:
        found = rx.search(line)
        if not found:
            continue
        key = found.group(1) if rx.groups and found.group(1) is not None else found.group(0)
        counts[key] = counts.get(key, 0) + 1
    return [f"{n} {key}" for key, n in counts.items()]


def _cut(lines: list[str], arg: str, op: str) -> list[str]:
    if ":" not in arg:
        raise SliceError(f"{op}: expected cut:SEP:N")
    sep, count = arg.rsplit(":", 1)
    if not count.strip().isdigit() or int(count) < 1:
        raise SliceError(f"{op}: N must be a positive integer")
    n = int(count)
    if sep == "\\t":
        sep = "\t"
    out: list[str] = []
    for line in lines:
        fields = line.split(sep) if sep else line.split()
        if len(fields) >= n:
            out.append(fields[n - 1])
    return out


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
