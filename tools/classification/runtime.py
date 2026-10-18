#!/usr/bin/env python3
"""Deterministic, data-only classifiers for mechanical skill decisions."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable, Sequence

KINDS = {
    "blueprint",
    "ticket",
}
SOURCE_SUFFIXES = {
    ".c", ".cc", ".cpp", ".cs", ".go", ".h", ".hpp", ".java", ".js", ".jsx",
    ".kt", ".kts", ".py", ".rb", ".rs", ".sh", ".sql", ".ts", ".tsx",
    ".yaml", ".yml", ".json", ".toml", ".xml",
}
UNTRUSTED_PARTS = {
    ".agent", ".git", ".github", "build", "coverage", "dist", "docs", "fixtures",
    "generated", "node_modules", "target", "vendor",
}
COMMENT_PREFIXES = ("#", "//", "/*", "*", "<!--", "--")
GENERATED_MARKERS = ("generated file", "do not edit", "code generated", "@generated")
def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def recommendation_sha256(result: dict[str, Any]) -> str:
    return _sha(_canonical(result["recommendation"]))


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+(?:[-_][a-z0-9]+)*", text.casefold()))


def _contains(text: str, phrases: Iterable[str]) -> bool:
    folded = text.casefold()
    return any(phrase in folded for phrase in phrases)


def _read(path: Path) -> tuple[str, bytes]:
    data = path.read_bytes()
    return data.decode("utf-8", errors="replace"), data


def _trusted_request_text(text: str) -> str:
    """Remove quoted/data blocks so embedded content cannot become request authority."""
    without_fences = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    lines = [
        line for line in without_fences.splitlines()
        if not line.lstrip().startswith((">", "//", "#", "<!--"))
    ]
    return "\n".join(lines)


def _tracked_files(root: Path) -> list[Path]:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            capture_output=True,
            check=False,
        )
        if result.returncode == 0:
            paths = [
                (root / item.decode("utf-8", errors="surrogateescape")).resolve()
                for item in result.stdout.split(b"\0") if item
            ]
            return sorted(path for path in paths if path.is_file())
    except OSError:
        pass
    return sorted(
        path.resolve()
        for path in root.rglob("*")
        if path.is_file() and not any(part.casefold() in UNTRUSTED_PARTS for part in path.relative_to(root).parts)
    )


def _trusted_sources(root: Path) -> list[Path]:
    resolved = root.resolve()
    sources: list[Path] = []
    for path in _tracked_files(resolved):
        try:
            relative = path.relative_to(resolved)
        except ValueError:
            continue
        parts = {part.casefold() for part in relative.parts}
        if parts & UNTRUSTED_PARTS or path.suffix.casefold() not in SOURCE_SUFFIXES:
            continue
        sources.append(path)
    return sources


def _repo_observations(root: Path, needles: dict[str, tuple[str, ...]]) -> dict[str, list[Path]]:
    found: dict[str, list[Path]] = {name: [] for name in needles}
    trusted = {path.resolve() for path in _trusted_sources(root)}
    pattern = "|".join(
        re.escape(term)
        for terms in needles.values()
        for term in terms
    )
    candidates: list[Path]
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "grep", "-I", "-i", "-l", "-E", pattern, "--"],
            capture_output=True,
            text=True,
            check=False,
        )
        candidates = [
            (root / line).resolve()
            for line in result.stdout.splitlines()
            if line.strip()
        ]
    except OSError:
        candidates = list(trusted)
    for path in sorted(set(candidates) & trusted):
        relative = path.relative_to(root.resolve()).as_posix().casefold()
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")[:100_000].casefold()
        except OSError:
            continue
        if any(marker in text[:2048] for marker in GENERATED_MARKERS):
            continue
        haystack = f"{relative}\n{text}"
        for name, terms in needles.items():
            if any(term in haystack for term in terms):
                found[name].append(path)
    return {key: sorted(value)[:3] for key, value in sorted(found.items())}


def _evidence(
    *,
    source_kind: str,
    path: Path,
    observation: str,
    supports: Iterable[str],
    root: Path | None = None,
) -> dict[str, Any]:
    data = path.read_bytes()
    if source_kind == "workflow-artifact":
        display = path.name
    else:
        display = (
            path.resolve().relative_to(root.resolve()).as_posix()
            if root is not None and path.resolve().is_relative_to(root.resolve())
            else str(path.resolve())
        )
    return {
        "id": "",
        "source_kind": source_kind,
        "path": display,
        "sha256": _sha(data),
        "observation": observation,
        "supports": sorted(set(supports)),
    }


def _finish(
    values: dict[str, Any],
    evidence: list[dict[str, Any]],
    confidence: str,
    alternatives: list[dict[str, Any]],
    overrides: dict[str, str],
    *,
    status: str = "ready",
) -> dict[str, Any]:
    ordered_evidence = sorted(
        evidence,
        key=lambda item: (
            item["source_kind"], item["path"], item["observation"], tuple(item["supports"])
        ),
    )
    for index, item in enumerate(ordered_evidence, 1):
        item["id"] = f"E-{index}"
    return {
        "recommendation": {
            "status": status,
            "values": {key: values[key] for key in sorted(values)},
        },
        "evidence": ordered_evidence,
        "confidence": confidence,
        "alternatives": sorted(
            alternatives,
            key=lambda item: (item["field"], json.dumps(item["value"], sort_keys=True), item["reason"]),
        ),
        "override_requirements": [
            {"field": field, "requirement": requirement}
            for field, requirement in sorted(overrides.items())
        ],
    }


def _request_evidence(path: Path, supports: Iterable[str], observation: str) -> dict[str, Any]:
    return _evidence(
        source_kind="request",
        path=path,
        observation=observation,
        supports=supports,
    )


def _blueprint(request_path: Path, root: Path, text: str) -> dict[str, Any]:
    intent_hits = {
        "bug-fix": _contains(text, ("fix ", "bug", "broken", "regression", "incorrect", "fails ")),
        "feature": _contains(text, ("add ", "create ", "introduce ", "support ", "new capability", "implement ")),
        "refactor": _contains(text, ("refactor", "rename", "reorganize", "preserve behavior", "no behavior change")),
    }
    intents = sorted(key for key, hit in intent_hits.items() if hit)
    intent = intents[0] if len(intents) == 1 else None
    status = "ready" if intent else "needs-product-input"

    probes = _repo_observations(
        root,
        {
            "public-contract": ("public ", "export ", "api", "cli", "schema", "config"),
            "durable-state": ("database", "persist", "storage", "model", "table"),
            "migration": ("migration", "migrate", "alembic"),
            "security": ("auth", "permission", "tenant", "secret", "credential"),
            "concurrency": ("async ", "lock", "queue", "thread", "atomic", "idempot"),
            "external-integration": ("http", "https", "sdk", "client", "webhook", "requests."),
            "irreversible-external-effect": ("delete", "billing", "charge", "email", "publish", "deploy"),
        },
    )
    domain_terms = {
        "public-contract": ("public api", "public contract", "cli", "schema", "compatib"),
        "durable-state": ("persist", "database", "durable state", "stored data"),
        "migration": ("migration", "migrate"),
        "security": ("security", "auth", "permission", "tenant", "secret"),
        "concurrency": ("concurr", "race", "ordering", "idempot", "duplicate delivery"),
        "external-integration": ("external integration", "webhook", "third-party", "sdk", "api client"),
        "irreversible-external-effect": ("irreversible", "billing", "charge", "send email", "delete data"),
    }
    risk_domains = sorted(
        domain
        for domain, terms in domain_terms.items()
        if _contains(text, terms)
    )
    signal_terms = {
        "transitive-consumers": ("consumer", "caller", "re-export", "propagat"),
        "shared-internal-interface": ("shared interface", "shared internal", "multiple modules"),
        "uncertain-root-cause": ("investigate", "unknown cause", "uncertain", "diagnose"),
        "multiple-architectural-layers": ("end to end", "cross-layer", "multiple layers", "route and service"),
        "mixed-sync-async-consumers": ("sync and async", "synchronous and asynchronous"),
        "multiple-test-surfaces": ("integration test", "end-to-end test", "multiple test"),
    }
    tier_signals = sorted(signal for signal, terms in signal_terms.items() if _contains(text, terms))
    source_mentions = sorted(set(re.findall(r"(?i)\b[\w./-]+\.(?:py|ts|tsx|js|go|rs|java|rb|kt)\b", text)))
    symbol_match = re.search(
        r"(?i)(?:\b(?:function|method|symbol)\s+|:[ \t]*)([A-Za-z_][A-Za-z0-9_]*)",
        text,
    )
    symbol_paths: list[Path] = []
    local_symbol_proven = False
    if symbol_match:
        symbol = symbol_match.group(1)
        trusted_set = set(_trusted_sources(root))
        try:
            result = subprocess.run(
                ["git", "-C", str(root), "grep", "-I", "-l", "-F", symbol, "--"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode not in {0, 1}:
                symbol_paths = [
                    path for path in trusted_set
                    if symbol in path.read_text(encoding="utf-8", errors="ignore")
                ]
            else:
                symbol_paths = sorted(
                    path
                    for line in result.stdout.splitlines()
                    if line.strip()
                    for path in [(root / line).resolve()]
                    if path in trusted_set
                )
        except OSError:
            symbol_paths = [
                path for path in trusted_set
                if symbol in path.read_text(encoding="utf-8", errors="ignore")
            ]
        production = [path for path in symbol_paths if "test" not in path.relative_to(root).as_posix().casefold()]
        tests = [path for path in symbol_paths if "test" in path.relative_to(root).as_posix().casefold()]
        local_symbol_proven = len(production) == 1 and not tests
        if len(production) > 1:
            tier_signals.extend(["transitive-consumers", "shared-internal-interface"])
        if len(tests) > 1:
            tier_signals.append("multiple-test-surfaces")
        has_async = any("async " in path.read_text(encoding="utf-8", errors="ignore") for path in production)
        has_sync = any("async " not in path.read_text(encoding="utf-8", errors="ignore") for path in production)
        if has_async and has_sync:
            tier_signals.append("mixed-sync-async-consumers")
        tier_signals = sorted(set(tier_signals))
    if risk_domains:
        tier = "high-risk"
    elif tier_signals or len(source_mentions) != 1 or not local_symbol_proven:
        tier = "standard"
    else:
        tier = "tiny"
    if status != "ready":
        tier = "high-risk" if risk_domains else "standard"

    evidence = [_request_evidence(request_path, ["intent", "tier", *risk_domains, *tier_signals], "Trusted request classification signals.")]
    for path in symbol_paths[:5]:
        evidence.append(
            _evidence(
                source_kind="repository-source",
                path=path,
                root=root,
                observation="Current source references the named classification anchor.",
                supports=tier_signals or ["tier"],
            )
        )
    for domain in risk_domains:
        for path in probes[domain]:
            relative = path.relative_to(root.resolve()).as_posix().casefold()
            if source_mentions and not any(mention.casefold() in relative for mention in source_mentions):
                continue
            evidence.append(
                _evidence(
                    source_kind="repository-source",
                    path=path,
                    root=root,
                    observation=f"Trusted source contains structural {domain} signals.",
                    supports=[domain, "tier"],
                )
            )
    alternatives = []
    for candidate in ("feature", "bug-fix", "refactor"):
        if candidate != intent:
            alternatives.append({"field": "intent", "value": candidate, "reason": "Not uniquely supported by trusted request signals."})
    for candidate in ("tiny", "standard", "high-risk"):
        if candidate != tier:
            alternatives.append({"field": "tier", "value": candidate, "reason": "Does not match the conservative risk and propagation rules."})
    values = {
        "intent": intent,
        "risk_domain": risk_domains,
        "tier": tier,
        "tier_signal": tier_signals,
    }
    return _finish(
        values,
        evidence,
        "high" if status == "ready" and (risk_domains or len(source_mentions) == 1) else "low" if status != "ready" else "medium",
        alternatives,
        {
            "intent": "Cite an explicit trusted user decision when intent signals conflict or are absent.",
            "risk_domain": "Cite current non-generated source proving the domain is present or absent.",
            "tier": "Cite current source proving every stricter tier condition is absent or present.",
            "tier_signal": "Cite current source proving the typed propagation signal.",
        },
        status=status,
    )


def _ticket(artifact: Path, root: Path, text: str) -> dict[str, Any]:
    metadata_match = re.search(
        r"<!--\s*ticket-scope-metadata\s*-->\s*```json\s*(\{.*?\})\s*```",
        text,
        re.DOTALL,
    )
    metadata: dict[str, Any] = {}
    if metadata_match:
        try:
            parsed = json.loads(metadata_match.group(1))
            metadata = parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            metadata = {}
    questions = list(metadata.get("questions", []))
    blockers = metadata.get("blockers", [])
    close_evidence = metadata.get("close_evidence", [])
    if blockers or not metadata:
        status = "blocked"
    elif questions:
        status = "needs-info"
    elif close_evidence:
        status = "close-candidate"
    else:
        status = "plan-ready"
    values = {
        "status": status,
    }
    return _finish(
        values,
        [_evidence(source_kind="workflow-artifact", path=artifact, observation="Structured issue-plan state.", supports=["readiness", "routing"])],
        "high" if metadata else "low",
        [
            {"field": "status", "value": value, "reason": "Status precedence is determined by structured blockers, questions, close evidence, and mandatory routing."}
            for value in ("blocked", "needs-info", "close-candidate", "plan-ready") if value != status
        ],
        {
            "status": "Cite current checkout evidence and the matching structured status requirement.",
        },
        status="ready" if metadata else "insufficient-evidence",
    )


def classify(
    kind: str,
    repo_root: Path,
    source: Path,
    anchors: Sequence[str] = (),
) -> dict[str, Any]:
    if kind not in KINDS:
        raise ValueError(f"unsupported classifier kind: {kind}")
    root = repo_root.resolve(strict=True)
    source_path = source.resolve(strict=True)
    text, _data = _read(source_path)
    if kind != "ticket":
        text = _trusted_request_text(text)
    if kind == "blueprint" and anchors:
        text = text + "\n" + "\n".join(sorted(set(anchors)))
    if kind == "blueprint":
        return _blueprint(source_path, root, text)
    if kind == "ticket":
        return _ticket(source_path, root, text)
    raise ValueError(f"unsupported classifier kind: {kind}")


def _resolve_evidence_path(raw: str, repo_root: Path, request_file: Path | None, source_kind: str) -> Path:
    candidate = Path(raw).expanduser().resolve(strict=True)
    if source_kind == "request":
        if request_file is None or candidate != request_file.resolve():
            raise ValueError("override request evidence must cite the original trusted request file")
        return candidate
    if source_kind != "repository-source":
        raise ValueError("override evidence source_kind must be request or repository-source")
    try:
        relative = candidate.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise ValueError("override repository evidence escapes the repository") from exc
    if {part.casefold() for part in relative.parts} & UNTRUSTED_PARTS:
        raise ValueError("override evidence cannot cite generated, fixture, documentation, vendor, or build content")
    if candidate.suffix.casefold() not in SOURCE_SUFFIXES:
        raise ValueError("override repository evidence must cite a supported source or configuration file")
    head = candidate.read_text(encoding="utf-8", errors="ignore")[:2048].casefold()
    if any(marker in head for marker in GENERATED_MARKERS):
        raise ValueError("override evidence cannot cite generated content")
    return candidate


def verify_override(
    result: dict[str, Any],
    override_path: Path,
    repo_root: Path,
    request_file: Path | None = None,
) -> dict[str, Any]:
    payload = json.loads(override_path.resolve(strict=True).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or set(payload) != {"recommendation_sha256", "overrides", "evidence"}:
        raise ValueError("override must contain recommendation_sha256, overrides, and evidence")
    if payload["recommendation_sha256"] != recommendation_sha256(result):
        raise ValueError("override recommendation hash is stale")
    overrides = payload["overrides"]
    evidence = payload["evidence"]
    if not isinstance(overrides, dict) or not overrides or not isinstance(evidence, list) or not evidence:
        raise ValueError("override requires non-empty overrides and evidence")
    allowed_fields = set(result["recommendation"]["values"])
    if not set(overrides) <= allowed_fields:
        raise ValueError("override contains an unknown classification field")
    for item in evidence:
        required = {"field", "source_kind", "path", "sha256", "start_line", "end_line", "excerpt_sha256", "observation"}
        if not isinstance(item, dict) or set(item) != required or item["field"] not in overrides:
            raise ValueError("override evidence has an invalid contract or unrelated field")
        path = _resolve_evidence_path(str(item["path"]), repo_root, request_file, str(item["source_kind"]))
        data = path.read_bytes()
        if _sha(data) != item["sha256"]:
            raise ValueError("override evidence file hash is stale")
        lines = data.decode("utf-8", errors="replace").splitlines()
        start, end = int(item["start_line"]), int(item["end_line"])
        if start < 1 or end < start or end > len(lines):
            raise ValueError("override evidence line range is invalid")
        excerpt = "\n".join(lines[start - 1:end]).encode("utf-8")
        if _sha(excerpt) != item["excerpt_sha256"]:
            raise ValueError("override evidence excerpt hash is stale")
        meaningful = [line.strip() for line in lines[start - 1:end] if line.strip()]
        if not meaningful or all(line.startswith(COMMENT_PREFIXES) for line in meaningful):
            raise ValueError("repository comments cannot become override authority")
        if not isinstance(item["observation"], str) or not item["observation"].strip():
            raise ValueError("override evidence requires a concrete observation")
    merged = dict(result["recommendation"]["values"])
    merged.update(overrides)
    return merged


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", required=True, choices=sorted(KINDS))
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--classification", type=Path)
    parser.add_argument("--override-file", type=Path)
    parser.add_argument("--verify-override", action="store_true")
    parser.add_argument("--anchor", action="append", default=[])
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.verify_override:
            if args.classification is None or args.override_file is None:
                raise ValueError("--verify-override requires --classification and --override-file")
            result = json.loads(args.classification.resolve(strict=True).read_text(encoding="utf-8"))
            values = verify_override(result, args.override_file, args.repo_root, args.source)
            print(json.dumps(values, sort_keys=True, separators=(",", ":")))
            return 0
        result = classify(args.kind, args.repo_root, args.source, args.anchor)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"classification failed: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
