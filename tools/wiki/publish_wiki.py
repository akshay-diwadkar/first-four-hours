#!/usr/bin/env python3
"""Build the flat GitHub wiki pages that mirror the user documentation in docs/."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

MARKDOWN_LINK_RE = re.compile(r"!?\[[^\]]*\]\((?:<(?P<bracketed>[^>]+)>|(?P<plain>[^)\s]+))(?:\s+['\"][^)]*['\"])?\)")
GENERATED_NOTICE = "<!-- Generated from {source} by tools/wiki/publish_wiki.py. Edit that file in the repository; changes made on the wiki are overwritten. -->"
HOME_PAGE = "README.md"
TITLE_RE = re.compile(r"^#[ \t]+(.+?)[ \t]*$")
FENCE_RE = re.compile(r"^ {0,3}(```|~~~)")
ALLOWED_TITLE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ,'-]*")
REPOSITORY_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")


class _LinkError:
    """A link the wiki cannot carry."""

    def __init__(self, message: str) -> None:
        self.message = message


def _documents(docs_root: Path) -> list[str]:
    """Return every docs page as a docs-relative POSIX path, Home first, then sorted."""
    paths = sorted(path.relative_to(docs_root).as_posix() for path in docs_root.rglob("*.md") if path.is_file())
    return ([HOME_PAGE] if HOME_PAGE in paths else []) + [path for path in paths if path != HOME_PAGE]


def _title(text: str) -> str | None:
    in_fence = False
    for line in text.splitlines():
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        match = None if in_fence else TITLE_RE.match(line)
        if match:
            return match.group(1)
    return None


def _page_names(repo_root: Path) -> tuple[dict[str, str], list[str]]:
    """Map each docs-relative path to its wiki page name, with naming errors in visiting order."""
    docs_root = repo_root / "docs"
    documents = _documents(docs_root)
    names: dict[str, str] = {}
    errors: list[str] = []
    claimed: dict[str, str] = {}
    if HOME_PAGE not in documents:
        errors.append("docs/README.md: missing, so the wiki has no Home page")
    for path in documents:
        if path == HOME_PAGE:
            name = "Home"
        else:
            title = _title((docs_root / path).read_text(encoding="utf-8"))
            if title is None:
                errors.append(f"docs/{path}: has no H1 title")
                continue
            if not ALLOWED_TITLE_RE.fullmatch(title):
                errors.append(f"docs/{path}: title {title!r} cannot name a wiki page")
                continue
            name = re.sub(r" +", "-", title)
        key = name.casefold()
        if key in claimed:
            errors.append(f"docs/{path}: wiki page name {name!r} is also used by docs/{claimed[key]}")
            continue
        claimed[key] = path
        names[path] = name
    return names, errors


def wiki_errors(repo_root: Path) -> list[str]:
    """Return the naming errors that keep docs/ from becoming a flat wiki."""
    return _page_names(repo_root)[1]


def _publish(
    repo_root: Path, repository: str, branch: str
) -> tuple[dict[str, str], dict[str, str], dict[str, list[list[str]]], list[str]]:
    """Return page names, page texts, rewritten link pairs, and every error."""
    names, errors = _page_names(repo_root)
    root = repo_root.resolve()
    docs_root = repo_root / "docs"
    page_paths = {(docs_root / path).resolve(): path for path in _documents(docs_root)}
    pages: dict[str, str] = {}
    links: dict[str, list[list[str]]] = {}
    for path in _documents(docs_root):
        document = docs_root / path
        text = document.read_text(encoding="utf-8")
        pieces: list[str] = []
        position = 0
        pairs: list[list[str]] = []
        for match in MARKDOWN_LINK_RE.finditer(text):
            group = "bracketed" if match.group("bracketed") is not None else "plain"
            raw = match.group(group)
            replacement = _rewrite(match.group(0), raw, document, root, page_paths, names, repository, branch)
            if isinstance(replacement, _LinkError):
                errors.append(f"docs/{path}: {replacement.message}: {raw}")
                continue
            if replacement != raw:
                pieces.append(text[position:match.start(group)])
                pieces.append(replacement)
                position = match.end(group)
                pairs.append([raw, replacement])
        pieces.append(text[position:])
        if pairs:
            links[f"docs/{path}"] = pairs
        if path in names:
            rewritten = "".join(pieces).rstrip("\n") + "\n"
            pages[names[path]] = GENERATED_NOTICE.format(source=f"docs/{path}") + "\n" + rewritten
    return names, ({} if errors else pages), links, errors


def _rewrite(
    whole: str,
    raw: str,
    document: Path,
    root: Path,
    page_paths: dict[Path, str],
    names: dict[str, str],
    repository: str,
    branch: str,
) -> str | _LinkError:
    if raw.startswith("#"):
        return raw
    parsed = urlsplit(raw)
    if parsed.scheme or parsed.netloc:
        return raw
    relative = unquote(parsed.path).replace("\\", "/")
    if not relative:
        return raw
    target = (document.parent / relative).resolve()
    if not target.is_relative_to(root):
        return _LinkError("link escapes the repository")
    if not target.exists():
        return _LinkError("link target does not exist")
    suffix = (f"?{parsed.query}" if parsed.query else "") + (f"#{parsed.fragment}" if parsed.fragment else "")
    if target in page_paths:
        name = names.get(page_paths[target])
        if name is None:
            return raw
        return f"https://github.com/{repository}/wiki/{name}" + (f"#{parsed.fragment}" if parsed.fragment else "")
    rel = quote(target.relative_to(root).as_posix(), safe="/")
    if target.is_dir():
        kind = "tree"
    elif whole.startswith("!"):
        kind = "raw"
    else:
        kind = "blob"
    return f"https://github.com/{repository}/{kind}/{branch}/{rel}{suffix}"


def build_pages(repo_root: Path, repository: str, branch: str) -> tuple[dict[str, str], list[str]]:
    """Return the wiki pages keyed by page name, or no pages and every error."""
    _, pages, _, errors = _publish(repo_root, repository, branch)
    return pages, errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True, help="OWNER/NAME of the GitHub repository")
    parser.add_argument("--branch", required=True, help="branch that repository file links point to")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="validate and print the page and link mapping")
    mode.add_argument("--output", type=Path, help="new folder to write the wiki pages into")
    args = parser.parse_args(argv)
    if not REPOSITORY_RE.fullmatch(args.repository):
        parser.error("--repository must be OWNER/NAME")
    if not args.branch:
        parser.error("--branch must not be empty")
    repo_root = Path(__file__).resolve().parents[2]
    names, pages, links, errors = _publish(repo_root, args.repository, args.branch)
    if errors:
        print(json.dumps({"valid": False, "errors": errors}))
        return 1
    if args.check:
        print(json.dumps({"valid": True, "pages": {f"docs/{path}": name for path, name in names.items()}, "links": links}))
        return 0
    output: Path = args.output
    if output.exists():
        print(json.dumps({"valid": False, "errors": [f"{output} already exists"]}))
        return 1
    output.mkdir(parents=True)
    for name, text in pages.items():
        with open(output / f"{name}.md", "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    print(json.dumps({"valid": True, "written": len(pages), "output": str(output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
