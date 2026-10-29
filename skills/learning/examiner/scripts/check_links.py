#!/usr/bin/env python3
"""Check that saved learning HTML links resolve and needs no network for essential content."""

from __future__ import annotations

import argparse
import json
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _diagnostic_contract import normalize_diagnostic  # noqa: E402

SKIPPED_SCHEMES = {"mailto", "tel", "javascript", "data"}
REMOTE_SCHEMES = {"http", "https"}
Problem = tuple[str, str, str]


class _Page(HTMLParser):
    """Collect anchor targets and every href or src with its line."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: set[str] = set()
        self.links: list[tuple[int, str, str, bool]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name: value or "" for name, value in attrs}
        if values.get("id"):
            self.ids.add(values["id"])
        if tag == "a" and values.get("name"):
            self.ids.add(values["name"])
        line = self.getpos()[0]
        stylesheet = tag == "link" and "stylesheet" in values.get("rel", "").lower().split()
        if "href" in values:
            # A citation link may leave the page; a stylesheet it loads may not.
            self.links.append((line, "href", values["href"].strip(), stylesheet))
        if "src" in values:
            self.links.append((line, "src", values["src"].strip(), True))

    handle_startendtag = handle_starttag


def _parse(path: Path, cache: dict[Path, _Page]) -> _Page:
    if path not in cache:
        page = _Page()
        page.feed(path.read_text(encoding="utf-8", errors="replace"))
        page.close()
        cache[path] = page
    return cache[path]


def _targets(target: Path) -> list[Path]:
    if target.is_dir():
        return sorted(item for item in target.iterdir() if item.is_file() and item.suffix.lower() == ".html")
    return [target]


def check(target: Path) -> tuple[list[Problem], dict[str, int]]:
    cache: dict[Path, _Page] = {}
    problems: list[Problem] = []
    files = _targets(target)
    count = 0
    for path in files:
        for line, attribute, value, essential in _parse(path, cache).links:
            count += 1
            location = f"{path.name}:{line}"
            parts = urlsplit(value)
            scheme = parts.scheme.lower()
            if scheme in SKIPPED_SCHEMES or not value:
                continue
            if scheme in REMOTE_SCHEMES or value.startswith("//"):
                if essential:
                    problems.append((
                        "learning.network_asset",
                        f"{location}: {attribute}={value!r} loads essential content from the network.",
                        "Inline the asset (CSS, script, or a data: URI image) or remove it; link outside sources only as citations.",
                    ))
                continue
            if scheme:
                continue
            linked = path if not parts.path else (path.parent / unquote(parts.path)).resolve()
            if not linked.is_file():
                problems.append((
                    "learning.missing_target",
                    f"{location}: {attribute}={value!r} points to a file that does not exist.",
                    "Correct the relative path to an existing file, create the missing file, or remove the link.",
                ))
                continue
            fragment = unquote(parts.fragment)
            if fragment and linked.suffix.lower() == ".html" and fragment not in _parse(linked, cache).ids:
                problems.append((
                    "learning.missing_anchor",
                    f"{location}: {attribute}={value!r} names an anchor {linked.name} does not have.",
                    f"Point the link at an existing id in {linked.name}, or add id={fragment!r} to the intended element.",
                ))
    return problems, {"files": len(files), "links": count}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", help="An HTML file, or a folder whose HTML files are checked (not recursively).")
    args = parser.parse_args(argv)
    target = Path(args.target).resolve()
    problems, result = check(target)
    if problems:
        print(json.dumps(
            [
                normalize_diagnostic(
                    {"code": code, "message": message, "required_action": action},
                    skill=Path(__file__).resolve().parent.parent.name,
                    phase="validate",
                    artifact="learning-html",
                    path=target,
                )
                for code, message, action in problems
            ],
            sort_keys=True,
            separators=(",", ":"),
        ))
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
