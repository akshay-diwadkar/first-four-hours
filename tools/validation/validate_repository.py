#!/usr/bin/env python3
"""Validate the standalone skill repository."""

from __future__ import annotations


# Public command execution starts in a contained worker before project imports.
import sys as _sys
import time as _time

_VALIDATION_START = _time.monotonic()
from pathlib import Path as _Path
from validation_budget import bounded_main as _bounded_main

if __name__ == "__main__":
    raise SystemExit(_bounded_main(_Path(__file__), _sys.argv[1:], _Path(__file__).resolve().parents[2], started_at=_VALIDATION_START))

import ast
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from measure_context_load import validate_guidance  # noqa: E402
from validation_budget import run_capture  # noqa: E402
from test_ownership import validate as validate_test_ownership  # noqa: E402

from tools.skill_protocol import validate_manifest  # noqa: E402
from tools.skill_protocol.runtime import compatible_version  # noqa: E402

SKILLS_ROOT = ROOT / "skills"
ATLAS_STRUCTURE_SCRIPT = SKILLS_ROOT / "workbench" / "atlas" / "scripts" / "structure_state.py"
VERSION_PATH = ROOT / "VERSION"
README_PATH = ROOT / "README.md"
INSTALLATION_GUIDE_LABEL = "docs/getting-started/installation.md"
INSTALLATION_GUIDE_PATH = ROOT / INSTALLATION_GUIDE_LABEL
CHANGELOG_PATH = ROOT / "CHANGELOG.md"
MARKETPLACE_PATH = ROOT / ".claude-plugin" / "marketplace.json"
INVOCATION_POLICY_PATH = ROOT / "invocation-policy.json"
SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)
INVOCATION_MODES = {"user-invoked", "model-invoked", "both"}
SKILLS_CLI_VERSION = "1.5.21"
CERTIFIED_PLATFORMS = {
    "claude-code": {
        "metadata_surface": "SKILL.md frontmatter",
        "supports_implicit_policy": True,
        "supports_user_visibility": True,
    },
    "codex": {
        "metadata_surface": "agents/openai.yaml",
        "supports_implicit_policy": True,
        "supports_user_visibility": False,
    },
    "github-copilot": {
        "metadata_surface": "SKILL.md frontmatter",
        "supports_implicit_policy": True,
        "supports_user_visibility": True,
    },
}
FRONTMATTER_POLICY: dict[str, dict[str, str]] = {
    "user-invoked": {"disable-model-invocation": "true"},
    "model-invoked": {"user-invocable": "false"},
    "both": {},
}
INVOCATION_CONTROLS = ("disable-model-invocation", "user-invocable")
METADATA_KEY_ORDERS = (["version"], ["version", "implicit-authority"])
SKILL_NAME_RE = re.compile(r"[a-z0-9-]{1,64}")
RESERVED_NAME_WORDS = ("anthropic", "claude")
DESCRIPTION_MAX_CHARS = 1024
XML_TAG_RE = re.compile(r"</?[A-Za-z][^<>]*>")
# Matches when the line after `description:` is neither a top-level key nor the end of the frontmatter.
DESCRIPTION_CONTINUATION_RE = re.compile(r"^description:[^\n]*\n(?![a-zA-Z0-9_-]+:|\s*\Z)", re.MULTILINE)
OPENAI_SIDECAR_RE = re.compile(
    r'interface:\n'
    r'  display_name: "(?P<display_name>[^"\n]*[^"\s][^"\n]*)"\n'
    r'  short_description: "(?P<short_description>[^"\n]*[^"\s][^"\n]*)"\n'
    r'(?:policy:\n  allow_implicit_invocation: (?P<allow_implicit>true|false)\n)?'
)
SEALED_BLUEPRINT_AUTHORITY = "sealed-blueprint"
SEALED_BLUEPRINT_SKILL = "construct"
SEALED_BLUEPRINT_INPUTS = {"blueprint_file"}
IMPLICIT_EXTERNAL_OUTPUT_SKILLS = {"architect", "assess"}
# PR may start implicitly by the user's decision; its explicit-yes rule, not this check, guards publish and update.
IMPLICIT_CONFIRMED_PUBLICATION_SKILLS = {"pr": {"external-write", "publication", "repository-write"}}
CONSTRUCT_VERIFY_ARGV = (
    "{python}",
    "{skill_dir}/scripts/run_verification.py",
    "--repo-root",
    "{repo_root}",
    "--blueprint",
    "{input.blueprint_file}",
    "--phase",
    "{input.phase}",
)
CONSTRUCT_REVERIFY_ARGV = (
    "{python}",
    "{skill_dir}/scripts/run_verification.py",
    "--repo-root",
    "{repo_root}",
    "--blueprint",
    "{input.blueprint_file}",
    "--phase",
    "after",
    "--from-line",
    "{input.from_line}",
)
CONSTRUCT_PROVE_ARGV = (
    *CONSTRUCT_VERIFY_ARGV[:6],
    "--phase",
    "prove",
    "--instruction",
    "{input.instruction}",
    "--check",
    "{input.check}",
    "--attempt",
    "{input.attempt}",
)
CONSTRUCT_STATUS_ARGV = (*CONSTRUCT_VERIFY_ARGV[:6], "--phase", "status")
CONSTRUCT_STATUS_REPEAT = [
    {"input": "instruction", "flag": "--instruction"},
    {"input": "attempt", "flag": "--attempt"},
]
CONSTRUCT_APPLY_ARGV = (*CONSTRUCT_VERIFY_ARGV[:6], "--phase", "apply", "--instruction", "{input.instruction}")
CONSTRUCT_REPEAT = {
    "status": CONSTRUCT_STATUS_REPEAT,
    "apply": [{"input": "blocks", "flag": "--blocks"}],
}
# apply alone writes: only the declared blocks' Location files inside the repository.
CONSTRUCT_APPLY_WRITES = ["{repo_root}"]
CONSTRUCT_COMMAND_WIRING = {
    "verify": CONSTRUCT_VERIFY_ARGV,
    "reverify": CONSTRUCT_REVERIFY_ARGV,
    "apply": CONSTRUCT_APPLY_ARGV,
    "prove": CONSTRUCT_PROVE_ARGV,
    "status": CONSTRUCT_STATUS_ARGV,
}
CONSTRUCT_COMMANDS = ["apply", "prove", "reverify", "status", "verify"]
CONSTRUCT_INPUT_WIRING = {
    "blueprint_file": (True, CONSTRUCT_COMMANDS, CONSTRUCT_COMMANDS),
    "phase": (True, ["verify"], ["verify"]),
    "from_line": (None, ["reverify"], ["reverify"]),
    "instruction": (None, ["apply", "prove"], ["apply", "prove", "status"]),
    "check": (None, ["prove"], ["prove"]),
    "attempt": (None, ["prove"], ["prove", "status"]),
    "blocks": (None, [], ["apply"]),
}
LATEST_RELEASE_BADGE_RE = re.compile(r"\[!\[Latest Release\]\((?P<badge_url>[^)]+)\)\]\((?P<target_url>[^)]+)\)")
LATEST_RELEASE_URL = "https://github.com/akshay-diwadkar/first-four-hours/releases/latest"
MARKDOWN_LINK_RE = re.compile(r"!?\[[^\]]*\]\((?:<(?P<bracketed>[^>]+)>|(?P<plain>[^)\s]+))(?:\s+['\"][^)]*['\"])?\)")
REPOSITORY_FILE_URL_PREFIXES = (
    "https://github.com/akshay-diwadkar/first-four-hours/blob/main/",
    "https://github.com/akshay-diwadkar/first-four-hours/tree/main/",
)
LEGACY_SCOPE_NAME = "scope" + "-issue"
LEGACY_SCOPE_ALLOWED = {
    "skills/workbench/ticket/references/issue-plan-contract.json",
    "tests/skills/ticket/test_scope_contract.py",
    "tools/validation/test-ownership.json",
    "tools/validation/validate_repository.py",
}
ALLOWED_TOP_LEVEL = {
    "SKILL.md",
    "scripts",
    "references",
    "schemas",
    "templates",
    "assets",
    "requirements.txt",
    ".env.example",
    "README.md",
    "skill-protocol.json",
    "agents",
}
FORBIDDEN_PARTS = {"evals", "fixtures", "__pycache__"}
ALLOWED_DOMAIN_FILES = {"README.md"}
EXPECTED_DOMAINS = {"workbench", "sensemaking", "learning"}
RETIRED_PATHS = (
    "catalog",
    "skills-lock.json",
    "SECURITY.md",
    "tools/catalog",
    "tools/packaging",
    "tools/release",
    ".github/CODEOWNERS",
    ".github/ISSUE_TEMPLATE",
    ".github/PULL_REQUEST_TEMPLATE.md",
    ".github/scripts",
    ".github/workflows/release.yml",
    ".github/workflows/repository-contract.yml",
    ".github/workflows/quality.yml",
    ".github/workflows/pre-release.yml",
    ".github/workflows/publish-release.yml",
    ".github/workflows/blueprint-hardening.yml",
)
RETIRED_CAPABILITY_IDENTITIES = (
    "create-ticket",
    "scope-ticket",
    "map-codebase",
    "audit-codebase",
    "optimize-codebase",
    "optimizations",
    "design-codebase",
    "plan-change",
    "implement-plan",
    "diagram-codebase",
    "manualize",
    "raise-issue",
    "raise-ticket",
    "route-work",
)
RETIRED_ARTIFACT_FILENAMES = (
    "audit-handoff.md",
    "optimization-handoff.md",
    "design-handoff.md",
    "plan.md",
    "plan-context.md",
    "blueprint-context.md",
    "implementation.json",
    "manual.md",
    "manual-bundle.json",
    "manual-audit.md",
    "manual-audit.json",
    "ticket-handoff.md",
    "route-handoff.md",
    "optimization.md",
    "construction.json",
)
RETIRED_PACKAGE_PATHS = (
    "skills/routing",
    "skills/routing/route-work",
)
RETIRED_PACKAGE_PATH_RE = re.compile(
    rf"(?<![A-Za-z0-9_-]){re.escape(RETIRED_PACKAGE_PATHS[0])}"
    r"(?=$|[^A-Za-z0-9_-])"
)
RETIRED_REASONING_IDENTITIES = ("think", "critic", "elicit")
# Every RETIRED_REASONING_IDENTITY_RE match contains one of these words under the same flag.
RETIRED_REASONING_WORD_RE = re.compile(r"(?i)think|critic|elicit")
RETIRED_REASONING_IDENTITY_RE = re.compile(
    r"(?i)(?:/(?:think|critic|elicit)\b|skills/reasoning/(?:think|critic|elicit)\b|"
    r"`(?:think|critic|elicit)`|^name:\s*(?:think|critic|elicit)\s*$|"
    r"\b(?:think|critic|elicit)\s+"
    r"(?:skill|capability|helper|identity|package|command|contract)\b)",
    re.MULTILINE,
)
CANONICAL_REPLACEMENTS = {
    "map-codebase": "atlas",
    "audit-codebase": "diagnose",
    "optimize-codebase": "diagnose",
    "design-codebase": "architect",
    "plan-change": "blueprint",
    "implement-plan": "construct",
    "manualize": "scribe",
    "raise-issue": "ticket",
    "raise-ticket": "ticket",
    "route-work": "router",
    "audit-handoff.md": "diagnosis.md",
    "optimization-handoff.md": "diagnosis.md",
    "design-handoff.md": "architecture.md",
    "plan.md": "blueprint.md",
    "plan-context.md": "blueprint.md",
    "blueprint-context.md": "blueprint.md",
    "implementation.json": "construction.json",
    "manual.md": "document.md",
    "manual-bundle.json": "document-bundle.json",
    "manual-audit.md": "document-audit.md",
    "manual-audit.json": "document-audit.json",
    "ticket-handoff.md": "ticket-scope.md",
    "route-handoff.md": "route.md",
}
CANONICAL_CONVERGENCE_HISTORICAL_FILES = {
    "CHANGELOG.md",
}

# Retired strings in these files are retained as explicit rejection evidence.
# The token sets are deliberately exact: adding a new retained string requires
# classifying that string at its owning location instead of gaining a whole-file
# exemption or relying on control-flow inference.
CANONICAL_CONVERGENCE_REJECTION_LOCATIONS: dict[str, frozenset[str]] = {
    "blueprints/issue-172-adaptive-architecture-contract/blueprint.md": frozenset({"map-codebase"}),
    "blueprints/issue-172-adaptive-architecture-contract/request.md": frozenset({"map-codebase"}),
    "skills/workbench/architect/scripts/seal_assessment.py": frozenset(
        {
            "audit-handoff.md",
            "optimization-handoff.md",
            "design-handoff.md",
            "ticket-handoff.md",
        }
    ),
    "skills/workbench/blueprint/scripts/blueprint_runtime.py": frozenset(
        {
            "audit-handoff.md",
            "optimization-handoff.md",
            "optimization.md",
            "design-handoff.md",
            "ticket-handoff.md",
            "issue-handoff.md",
            "plan.md",
            "plan-context.md",
            "blueprint-context.md",
        }
    ),
    "skills/workbench/construct/scripts/blueprint_runtime.py": frozenset(
        {
            "audit-handoff.md",
            "optimization-handoff.md",
            "optimization.md",
            "design-handoff.md",
            "ticket-handoff.md",
            "issue-handoff.md",
            "plan.md",
            "plan-context.md",
            "blueprint-context.md",
        }
    ),
    "tests/classification/test_classification.py": frozenset({"diagram-codebase", "manualize", "optimizations"}),
    "tests/integration/test_installed_skill_execution.py": frozenset({"route-handoff.md", "blueprint-context.md"}),
    "tests/repository/test_routine_validation.py": frozenset({"map-codebase", "skills/routing", "retired reasoning identity"}),
    "tests/repository/test_skill_repository.py": frozenset(
        {
            *RETIRED_CAPABILITY_IDENTITIES,
            *RETIRED_ARTIFACT_FILENAMES,
            "skills/routing",
            "retired reasoning identity",
        }
    ),
    "tests/skills/architect/test_sealing_and_integration.py": frozenset(
        {
            "audit-handoff.md",
            "optimization-handoff.md",
            "design-handoff.md",
            "ticket-handoff.md",
        }
    ),
    "tests/skills/atlas/test_repository_guidance.py": frozenset({"map-codebase"}),
    "skills/workbench/blueprint/SKILL.md": frozenset({"blueprint-context.md"}),
    "skills/workbench/blueprint/README.md": frozenset({"blueprint-context.md"}),
    "tests/skills/blueprint/test_blueprint_contract.py": frozenset(
        {"blueprint-context.md", "plan.md", "plan-context.md"}
    ),
    "tests/skills/blueprint/test_calibration_fixtures.py": frozenset({"blueprint-context.md"}),
    "tests/skills/blueprint/test_typed_handoff_intake.py": frozenset({"optimization.md"}),
    "tests/skills/diagnose/test_diagnosis.py": frozenset(
        {"audit-handoff.md", "optimization-handoff.md", "design-handoff.md"}
    ),
    "tests/skills/reason/test_reason_contract.py": frozenset({"retired reasoning identity"}),
    "tests/skills/ticket/test_ticket_scope_sealer.py": frozenset({"ticket-handoff.md"}),
}
CANONICAL_CONVERGENCE_AUTHORITY_FILES = {"tools/validation/validate_repository.py"}
# Each skill-owned contract version declaration and the skill that owns it.
# "exact" values equal the owner's metadata.version; "major" values are a
# consumer's built-against producer version and share the owner's major.
CONTRACT_VERSION_DECLARATIONS = (
    ("skills/workbench/blueprint/scripts/blueprint_runtime.py", r'^CONTRACT_VERSION = "([^"]+)"$', "workbench/blueprint", "exact"),
    ("skills/workbench/construct/scripts/blueprint_runtime.py", r'^CONTRACT_VERSION = "([^"]+)"$', "workbench/blueprint", "exact"),
    ("skills/workbench/blueprint/scripts/blueprint_runtime.py", r'^DIAGNOSIS_HANDOFF_VERSION = "([^"]+)"$', "workbench/diagnose", "major"),
    ("skills/workbench/construct/scripts/blueprint_runtime.py", r'^DIAGNOSIS_HANDOFF_VERSION = "([^"]+)"$', "workbench/diagnose", "major"),
    ("skills/workbench/blueprint/scripts/blueprint_runtime.py", r'^ARCHITECTURE_HANDOFF_VERSION = "([^"]+)"$', "workbench/architect", "major"),
    ("skills/workbench/construct/scripts/blueprint_runtime.py", r'^ARCHITECTURE_HANDOFF_VERSION = "([^"]+)"$', "workbench/architect", "major"),
    ("skills/workbench/blueprint/scripts/blueprint_runtime.py", r'^TICKET_SCOPE_HANDOFF_VERSION = "([^"]+)"$', "workbench/ticket", "major"),
    ("skills/workbench/construct/scripts/blueprint_runtime.py", r'^TICKET_SCOPE_HANDOFF_VERSION = "([^"]+)"$', "workbench/ticket", "major"),
    ("skills/workbench/architect/scripts/architecture_handoff.py", r'^ARCHITECT_VERSION = "([^"]+)"$', "workbench/architect", "exact"),
    ("skills/workbench/blueprint/scripts/architecture_handoff.py", r'^ARCHITECT_VERSION = "([^"]+)"$', "workbench/architect", "exact"),
    ("skills/workbench/assess/scripts/assess_contract.py", r'^CONTRACT_VERSION = "([^"]+)"$', "workbench/assess", "exact"),
    ("skills/workbench/assess/templates/assessment-bundle.json", r'^  "schema_version": "([^"]+)",$', "workbench/assess", "exact"),
    ("skills/workbench/diagnose/scripts/diagnosis_handoff.py", r'^CONTRACT_VERSION = "([^"]+)"$', "workbench/diagnose", "exact"),
    ("skills/workbench/diagnose/templates/diagnosis-bundle.json", r'^  "schema_version": "([^"]+)",$', "workbench/diagnose", "exact"),
    ("skills/workbench/atlas/scripts/freshness_state.py", r'^STATE_VERSION = "([^"]+)"$', "workbench/atlas", "exact"),
    ("skills/workbench/ticket/scripts/github_common.py", r'^TICKET_VERSION = "([^"]+)"$', "workbench/ticket", "exact"),
    ("skills/sensemaking/ideate/scripts/ideation_contract.py", r'^IDEATE_VERSION = "([^"]+)"$', "sensemaking/ideate", "exact"),
    ("skills/sensemaking/scribe/scripts/check_document.py", r'^BUNDLE_CONTRACT_VERSION = "([^"]+)"$', "sensemaking/scribe", "exact"),
    ("skills/sensemaking/scribe/templates/document-bundle.json", r'^  "contract_version": "([^"]+)",$', "sensemaking/scribe", "exact"),
)

# Blueprint sealed-contract authority (akshay-diwadkar/skills#464): the HEAD-divergence runtime
# machinery is retired. These exact identifiers must not reappear in
# Blueprint's active package surfaces; tests are deliberately not scanned so
# regression tests can name retired behavior as rejection evidence.
BLUEPRINT_ACTIVE_SURFACES = (
    "skills/workbench/blueprint/scripts",
    "skills/workbench/blueprint/SKILL.md",
    "skills/workbench/blueprint/README.md",
    "skills/workbench/blueprint/references",
)
BLUEPRINT_RETIRED_RUNTIME_TOKENS = (
    "head_divergent_locators",
    "dirty_source_locators",
    "binding.repository.stale",
    "differs_from_head",
)


def validate_blueprint_retired_runtime(
    root: Path = ROOT, source_files: list[Path] | None = None
) -> list[str]:
    """Keep retired Blueprint HEAD-divergence machinery out of its active package."""

    errors: list[str] = []
    if source_files is None:
        scanned: list[tuple[str, str]] = []
        for surface in BLUEPRINT_ACTIVE_SURFACES:
            base = root / Path(surface)
            if base.is_file():
                candidates = [base]
            elif base.is_dir():
                candidates = [
                    path for path in base.rglob("*") if path.is_file() and "__pycache__" not in path.parts
                ]
            else:
                continue
            for path in candidates:
                try:
                    scanned.append((path.relative_to(root).as_posix(), path.read_text(encoding="utf-8")))
                except (OSError, UnicodeDecodeError):
                    continue
    else:
        scanned = []
        for path in source_files:
            try:
                scanned.append((path.relative_to(root).as_posix(), path.read_text(encoding="utf-8")))
            except (OSError, UnicodeDecodeError, ValueError):
                continue
    for relative, text in scanned:
        hits = sorted(token for token in BLUEPRINT_RETIRED_RUNTIME_TOKENS if token in text)
        if hits:
            errors.append(f"{relative}: retired Blueprint runtime token remains: {', '.join(hits)}")
    return errors


def tracked_files() -> list[Path]:
    """Return repository files tracked by Git, excluding missing paths."""
    result = run_capture(["git", "ls-files", "-z"], cwd=ROOT)
    if result.returncode:
        return []
    return [
        path
        for relative in result.stdout.decode("utf-8").split("\0")
        if relative
        for path in [ROOT / relative]
        if path.is_file()
    ]


def discover_skills() -> list[Path]:
    if not SKILLS_ROOT.is_dir():
        return []
    return sorted(
        skill
        for domain in SKILLS_ROOT.iterdir()
        if domain.is_dir()
        for skill in domain.iterdir()
        if skill.is_dir() and (skill / "SKILL.md").is_file()
    )


def validate_domain_layout() -> list[str]:
    errors: list[str] = []
    if not SKILLS_ROOT.is_dir():
        return errors
    domains = {child.name for child in SKILLS_ROOT.iterdir() if child.is_dir()}
    if domains != EXPECTED_DOMAINS:
        errors.append(f"skills/: active domains must be exactly {sorted(EXPECTED_DOMAINS)}; found {sorted(domains)}")
    skill_names: dict[str, Path] = {}
    for child in SKILLS_ROOT.iterdir():
        if not child.is_dir():
            errors.append(f"{child.relative_to(ROOT)}: skill root may contain only domain directories")
            continue
        for item in child.iterdir():
            if not item.is_dir() and item.name not in ALLOWED_DOMAIN_FILES:
                errors.append(f"{item.relative_to(ROOT)}: domain may contain only skill directories")
            if item.is_dir() and (item / "SKILL.md").is_file():
                previous = skill_names.get(item.name)
                if previous is not None:
                    errors.append(
                        f"duplicate active skill package {item.name!r}: {previous.relative_to(ROOT)} and {item.relative_to(ROOT)}"
                    )
                else:
                    skill_names[item.name] = item
    return errors


def validate_frontmatter(skill_dir: Path) -> list[str]:
    skill_md = skill_dir / "SKILL.md"
    rel_md = skill_md.relative_to(ROOT) if skill_md.is_relative_to(ROOT) else skill_md
    rel_dir = skill_dir.relative_to(ROOT) if skill_dir.is_relative_to(ROOT) else skill_dir
    if not skill_md.is_file():
        return [f"{rel_dir}: missing SKILL.md"]
    text = skill_md.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return [f"{rel_md}: missing YAML frontmatter"]
    frontmatter = text.split("---", 2)[1]
    name = re.search(r"^name:\s*(.+)$", frontmatter, re.MULTILINE)
    description = re.search(r"^description:\s*(.+)$", frontmatter, re.MULTILINE)
    errors: list[str] = []
    if not name or name.group(1).strip() != skill_dir.name:
        errors.append(f"{rel_md}: frontmatter name must match the skill directory")
    if not description or not description.group(1).strip():
        errors.append(f"{rel_md}: frontmatter description is required")
    if name:
        value = name.group(1).strip()
        if not SKILL_NAME_RE.fullmatch(value):
            errors.append(f"{rel_md}: frontmatter name must be at most 64 lowercase letters, digits, and hyphens")
        for word in RESERVED_NAME_WORDS:
            if word in value:
                errors.append(f"{rel_md}: frontmatter name must not contain reserved word {word!r}")
    if description and description.group(1).strip():
        decoded = _frontmatter_description(frontmatter)
        if description.group(1).strip()[0] in ">|!&*" or DESCRIPTION_CONTINUATION_RE.search(frontmatter):
            # Block scalars, tags, anchors, aliases, and continued values put the text out of reach of the limit checks.
            errors.append(f"{rel_md}: frontmatter description must be a single line")
        elif decoded is None:
            errors.append(f"{rel_md}: frontmatter description must be a valid double-quoted string")
        else:
            if len(decoded) > DESCRIPTION_MAX_CHARS:
                errors.append(f"{rel_md}: frontmatter description must be at most 1024 characters")
            if XML_TAG_RE.search(decoded):
                errors.append(f"{rel_md}: frontmatter description must not contain XML tags")

    top_keys = re.findall(r"^([a-zA-Z0-9_-]+):", frontmatter, re.MULTILINE)
    expected_keys = ["name", "description", *[c for c in INVOCATION_CONTROLS if c in top_keys], "metadata"]
    if top_keys != expected_keys:
        errors.append(
            f"{rel_md}: frontmatter keys must be name, description, any non-default invocation controls, then metadata"
        )

    metadata_match = re.search(
        r"^metadata:\s*\n(?P<body>(?:^[ \t]+[^\n]*(?:\n|$))*)",
        frontmatter,
        re.MULTILINE,
    )
    meta_keys = (
        re.findall(r"^[ \t]+([a-zA-Z0-9_-]+):", metadata_match.group("body"), re.MULTILINE)
        if metadata_match
        else []
    )
    if meta_keys not in METADATA_KEY_ORDERS:
        errors.append(f"{rel_md}: metadata keys must be version, then implicit-authority only where declared")

    raw_version = _metadata_field(frontmatter, "version")
    if raw_version is None:
        errors.append(f"{rel_md}: metadata.version is required")
    else:
        quoted = re.fullmatch(r'"([^"]+)"', raw_version)
        if quoted is None or not SEMVER_RE.fullmatch(quoted.group(1)):
            errors.append(f"{rel_md}: metadata.version {raw_version!r} must be a quoted Semantic Versioning string")

    return errors


def _frontmatter(skill_dir: Path) -> str | None:
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        return None
    text = skill_md.read_text(encoding="utf-8")
    if not text.startswith("---\n") or "---" not in text[4:]:
        return None
    return text.split("---", 2)[1]


def _frontmatter_field(frontmatter: str, field: str) -> str | None:
    match = re.search(rf"^{re.escape(field)}:\s*(\S.*?)\s*$", frontmatter, re.MULTILINE)
    return match.group(1) if match else None


def _frontmatter_description(frontmatter: str) -> str | None:
    raw = _frontmatter_field(frontmatter, "description")
    if raw is None or not raw.startswith('"'):
        return raw
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, str) else None


def _metadata_field(frontmatter: str, field: str) -> str | None:
    metadata = re.search(
        r"^metadata:\s*\n(?P<body>(?:^[ \t]+[^\n]*(?:\n|$))*)",
        frontmatter,
        re.MULTILINE,
    )
    if metadata is None:
        return None
    match = re.search(
        rf"^[ \t]+{re.escape(field)}:\s*(\S.*?)\s*$",
        metadata.group("body"),
        re.MULTILINE,
    )
    return match.group(1) if match else None


def _frontmatter_invocation_mode(frontmatter: str) -> str | None:
    """Derive the invocation mode from the non-default controls the frontmatter declares."""
    controls = {
        field: value
        for field in INVOCATION_CONTROLS
        if (value := _frontmatter_field(frontmatter, field)) is not None
    }
    return next((mode for mode, expected in FRONTMATTER_POLICY.items() if controls == expected), None)


def _validate_construct_authority_manifest(manifest: dict[str, object], prefix: str) -> list[str]:
    """Check the declarative Construct verify/reverify intake boundary without inspecting its implementation."""
    errors: list[str] = []
    if manifest.get("skill") != SEALED_BLUEPRINT_SKILL:
        errors.append(
            f"{prefix}: sealed-blueprint implicit authority requires the protocol manifest "
            f"skill to be {SEALED_BLUEPRINT_SKILL!r}; restore the Construct manifest identity"
        )
    commands = manifest.get("commands")
    if not isinstance(commands, dict) or set(commands) != set(CONSTRUCT_COMMAND_WIRING):
        errors.append(
            f"{prefix}: sealed-blueprint implicit authority requires exactly the canonical verify, "
            "repair-only reverify, instruction apply, instruction prove, and read-only status commands; "
            "restore the canonical Construct wiring"
        )
        return errors

    artifacts = manifest.get("artifacts")
    if artifacts != []:
        errors.append(
            f"{prefix}: sealed-blueprint implicit authority requires an artifact-free Construct manifest"
        )

    inputs = manifest.get("inputs")
    definitions = (
        {item.get("name"): item for item in inputs if isinstance(item, dict) and isinstance(item.get("name"), str)}
        if isinstance(inputs, list)
        else {}
    )
    for input_name, (required_flag, required_for, accepted_for) in CONSTRUCT_INPUT_WIRING.items():
        definition = definitions.get(input_name)
        if definition is None:
            errors.append(
                f"{prefix}: sealed-blueprint implicit authority requires input {input_name!r}"
            )
            continue
        if required_flag is True and definition.get("required") is not True:
            errors.append(
                f"{prefix}: sealed-blueprint implicit authority requires input {input_name!r} to be required, "
                "never an optional authority input"
            )
        if (
            sorted(str(item) for item in definition.get("required_for", [])) != sorted(required_for)
            or sorted(str(item) for item in definition.get("accepted_for", [])) != sorted(accepted_for)
        ):
            errors.append(
                f"{prefix}: sealed-blueprint implicit authority requires input {input_name!r} for exactly "
                f"{sorted(required_for)}; restore the canonical input binding"
            )

    for command_name, wiring in CONSTRUCT_COMMAND_WIRING.items():
        raw_command = commands.get(command_name)
        variants = raw_command if isinstance(raw_command, list) else [raw_command]
        if len(variants) != 1 or not isinstance(variants[0], dict):
            errors.append(
                f"{prefix}: sealed-blueprint implicit authority requires one unambiguous Construct "
                f"{command_name} command variant; restore the canonical {command_name} command"
            )
            continue
        command = variants[0]
        expected_writes = CONSTRUCT_APPLY_WRITES if command_name == "apply" else []
        if command.get("allowed_writes", []) != expected_writes:
            errors.append(
                f"{prefix}: sealed-blueprint implicit authority requires the Construct {command_name} "
                + ("command to declare only the {repo_root} write" if command_name == "apply" else "command to remain write-free")
            )
        steps = command.get("steps")
        if not isinstance(steps, list) or len(steps) != 1 or not isinstance(steps[0], dict):
            errors.append(
                f"{prefix}: sealed-blueprint implicit authority requires the Construct {command_name} command "
                "to expose one canonical verification step; restore the canonical "
                f"{command_name} command"
            )
            continue
        argv = steps[0].get("argv")
        expected_repeat = CONSTRUCT_REPEAT.get(command_name, [])
        if steps[0].get("repeat") != expected_repeat:
            errors.append(
                f"{prefix}: sealed-blueprint implicit authority requires canonical Construct {command_name} "
                "optional-input forwarding; only status forwards paired instruction/attempt context and "
                "apply its blocks selection"
            )
        if argv != list(wiring):
            if command_name == "verify":
                errors.append(
                    f"{prefix}: sealed-blueprint implicit authority requires Construct verify to bind "
                    "blueprint_file to run_verification.py; restore the canonical verify wiring"
                )
            elif command_name in ("apply", "prove", "status"):
                errors.append(
                    f"{prefix}: sealed-blueprint implicit authority requires Construct {command_name} to run "
                    f"run_verification.py with --phase {command_name} from blueprint_file; restore the canonical {command_name} wiring"
                )
            else:
                errors.append(
                    f"{prefix}: sealed-blueprint implicit authority requires the repair-only reverify command "
                    "to rerun run_verification.py with --phase after and --from-line from blueprint_file; "
                    "restore the canonical reverify wiring"
                )
    return errors


def _load_json_object(path: Path, label: str) -> tuple[dict[str, object] | None, list[str]]:
    if not path.is_file():
        return None, [f"Missing {label}"]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, [f"{label}: invalid JSON: {exc}"]
    if not isinstance(payload, dict):
        return None, [f"{label}: root must be an object"]
    return payload, []


def derive_invocation_safety_capabilities(skill_dir: Path) -> set[str]:
    """Derive capabilities that must never be exposed through implicit invocation."""
    capabilities: set[str] = set()
    manifest_path = skill_dir / "skill-protocol.json"
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            manifest = {}
        if isinstance(manifest, dict):
            phases = manifest.get("phases", {})
            if isinstance(phases, dict):
                for phase in phases.values():
                    if not isinstance(phase, dict):
                        continue
                    writes = phase.get("allowed_writes", [])
                    if isinstance(writes, list) and "{repo_root}" in writes:
                        capabilities.add("repository-write")
            artifacts = manifest.get("artifacts", [])
            if isinstance(artifacts, list) and any(
                isinstance(artifact, dict) and artifact.get("external") is True for artifact in artifacts
            ):
                capabilities.add("external-output")
            commands = manifest.get("commands", {})
            if isinstance(commands, dict):
                for name, raw_command in commands.items():
                    variants = raw_command if isinstance(raw_command, list) else [raw_command]
                    if any(
                        isinstance(command, dict) and "{repo_root}" in command.get("allowed_writes", [])
                        for command in variants
                    ):
                        capabilities.add("repository-write")
                    if "publish" in str(name):
                        capabilities.add("publication")

    scripts = skill_dir / "scripts"
    if scripts.is_dir() and any(
        any(token in path.stem for token in ("post_merge", "publish_")) for path in scripts.glob("*.py")
    ):
        capabilities.add("external-write")
    return capabilities


def _validate_implicit_authority_declaration(skill_dir: Path, frontmatter: str, mode: str) -> tuple[bool, list[str]]:
    """Allow only Construct's sealed-Blueprint authority boundary to be implicit."""
    declaration = _metadata_field(frontmatter, "implicit-authority")
    if declaration is None:
        return False, []

    relative = skill_dir.relative_to(ROOT) if skill_dir.is_relative_to(ROOT) else skill_dir
    prefix = f"{relative}/SKILL.md"
    errors: list[str] = []
    if skill_dir.name != SEALED_BLUEPRINT_SKILL:
        errors.append(f"{prefix}: implicit-authority is only supported for {SEALED_BLUEPRINT_SKILL!r}")
    if declaration != SEALED_BLUEPRINT_AUTHORITY:
        errors.append(f"{prefix}: unsupported implicit-authority {declaration!r}")
    if mode != "both":
        errors.append(f"{prefix}: implicit-authority requires invocation mode 'both'")
    if errors:
        return False, errors

    manifest_path = skill_dir / "skill-protocol.json"
    if not manifest_path.is_file():
        return False, [f"{prefix}: sealed-blueprint implicit authority requires skill-protocol.json"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return False, [f"{prefix}: sealed-blueprint implicit authority requires valid skill-protocol.json: {exc}"]
    if not isinstance(manifest, dict):
        return False, [f"{prefix}: sealed-blueprint implicit authority requires a manifest object"]

    inputs = manifest.get("inputs")
    definitions = (
        {item.get("name"): item for item in inputs if isinstance(item, dict) and isinstance(item.get("name"), str)}
        if isinstance(inputs, list)
        else {}
    )
    validation_errors: list[str] = []
    for input_name in sorted(SEALED_BLUEPRINT_INPUTS):
        definition = definitions.get(input_name)
        if definition is None:
            validation_errors.append(f"{prefix}: sealed-blueprint implicit authority requires input {input_name!r}")
        elif definition.get("required") is not True and "verify" not in definition.get("required_for", []):
            validation_errors.append(
                f"{prefix}: sealed-blueprint implicit authority requires input {input_name!r} for Construct verify"
            )

    validation_errors.extend(_validate_construct_authority_manifest(manifest, prefix))
    return not validation_errors, validation_errors


def validate_skill_invocation_metadata(skill_dir: Path, mode: str) -> list[str]:
    relative = skill_dir.relative_to(ROOT) if skill_dir.is_relative_to(ROOT) else skill_dir
    prefix = f"{relative}/SKILL.md"
    frontmatter = _frontmatter(skill_dir)
    if frontmatter is None:
        return [f"{prefix}: cannot validate invocation metadata without frontmatter"]

    errors: list[str] = []
    expected_controls = FRONTMATTER_POLICY.get(mode)
    if expected_controls is None:
        errors.append(f"{prefix}: unsupported invocation mode {mode!r}")
    elif _frontmatter_invocation_mode(frontmatter) != mode:
        shown = ", ".join(f"{field}: {value}" for field, value in expected_controls.items()) or "absent"
        errors.append(f"{prefix}: invocation controls must be {shown} for {mode}")

    agents_dir = skill_dir / "agents"
    openai_path = agents_dir / "openai.yaml"
    if not openai_path.is_file():
        errors.append(f"{relative}/agents/openai.yaml: missing OpenAI sidecar")
    else:
        text = openai_path.read_text(encoding="utf-8")
        match = OPENAI_SIDECAR_RE.fullmatch(text)
        if match is None:
            errors.append(f"{relative}/agents/openai.yaml: unsupported or malformed sidecar")
        else:
            if match["display_name"].casefold() != skill_dir.name.replace("-", " "):
                errors.append(
                    f"{relative}/agents/openai.yaml: interface.display_name must name the skill {skill_dir.name!r}"
                )
            policy = match["allow_implicit"]
            if mode == "user-invoked" and policy != "false":
                errors.append(
                    f"{relative}/agents/openai.yaml: policy.allow_implicit_invocation must be false for user-invoked"
                )
            elif mode != "user-invoked" and policy is not None:
                errors.append(
                    f"{relative}/agents/openai.yaml: omit policy for {mode}; allow_implicit_invocation defaults to true"
                )
    if agents_dir.is_dir():
        unexpected = sorted(
            path.relative_to(skill_dir).as_posix()
            for path in agents_dir.rglob("*")
            if path.is_file() and path != openai_path
        )
        for path in unexpected:
            errors.append(f"{relative}/{path}: unsupported provider metadata")

    implicit_authority, authority_errors = _validate_implicit_authority_declaration(skill_dir, frontmatter, mode)
    errors.extend(authority_errors)

    dangerous = derive_invocation_safety_capabilities(skill_dir)
    blocked_capabilities = set(dangerous)
    if skill_dir.name in IMPLICIT_EXTERNAL_OUTPUT_SKILLS:
        blocked_capabilities.discard("external-output")
    blocked_capabilities -= IMPLICIT_CONFIRMED_PUBLICATION_SKILLS.get(skill_dir.name, set())
    if blocked_capabilities and mode != "user-invoked" and not implicit_authority:
        errors.append(
            f"{prefix}: {mode} conflicts with authority-required capabilities: "
            + ", ".join(sorted(blocked_capabilities))
        )
    if mode == "model-invoked":
        manifest_path = skill_dir / "skill-protocol.json"
        if manifest_path.is_file():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                manifest = {}
            phases = manifest.get("phases", {}) if isinstance(manifest, dict) else {}
            writes = (
                [
                    value
                    for phase in phases.values()
                    if isinstance(phase, dict)
                    for value in phase.get("allowed_writes", [])
                ]
                if isinstance(phases, dict)
                else []
            )
            if writes:
                errors.append(f"{prefix}: model-invoked protocol phases must be read-only")
    return errors


def validate_invocation_policy(
    path: Path | None = None,
    skill_dirs: list[Path] | None = None,
) -> list[str]:
    path = path or INVOCATION_POLICY_PATH
    skill_dirs = skill_dirs or discover_skills()
    label = path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)
    payload, errors = _load_json_object(path, label)
    if payload is None:
        return errors

    if set(payload) != {"schema_version", "certified_platforms", "skills"}:
        errors.append(f"{label}: fields must be schema_version, certified_platforms, and skills")
    if payload.get("schema_version") != "1.0.0":
        errors.append(f"{label}: schema_version must be '1.0.0'")
    if payload.get("certified_platforms") != CERTIFIED_PLATFORMS:
        errors.append(f"{label}: certified_platforms must match the supported provider adapters")

    modes = payload.get("skills")
    if not isinstance(modes, dict) or not all(
        isinstance(name, str) and isinstance(mode, str) for name, mode in modes.items()
    ):
        errors.append(f"{label}: skills must map skill names to invocation modes")
        return errors

    discovered = {skill.name: skill for skill in skill_dirs}
    if set(modes) != set(discovered):
        missing = sorted(set(discovered) - set(modes))
        stale = sorted(set(modes) - set(discovered))
        if missing:
            errors.append(f"{label}: missing skills: {missing}")
        if stale:
            errors.append(f"{label}: references unknown skills: {stale}")
    for name, mode in modes.items():
        if mode not in INVOCATION_MODES:
            errors.append(f"{label}: {name} has unsupported invocation mode {mode!r}")
        elif name in discovered:
            errors.extend(validate_skill_invocation_metadata(discovered[name], mode))
    return errors


def validate_certified_platform_coverage(guide_path: Path | None = None) -> list[str]:
    """Keep the installation guide's agent names aligned with certified platforms."""
    guide_path = guide_path or INSTALLATION_GUIDE_PATH
    errors: list[str] = []
    expected = set(CERTIFIED_PLATFORMS)

    if not guide_path.is_file():
        errors.append(f"Missing {INSTALLATION_GUIDE_LABEL}")
    else:
        text = guide_path.read_text(encoding="utf-8")
        match = re.search(
            r"The repository's own install check covers the agent names (?P<names>.+?)\.$", text, re.MULTILINE
        )
        names = set(re.findall(r"`([^`]+)`", match.group("names"))) if match else set()
        if names != expected:
            errors.append(f"{INSTALLATION_GUIDE_LABEL}: install-check agent names must be exactly {sorted(expected)}")
    return errors


def validate_version() -> list[str]:
    if not VERSION_PATH.is_file():
        return ["Missing VERSION"]
    version = VERSION_PATH.read_text(encoding="utf-8").strip()
    if not SEMVER_RE.fullmatch(version):
        return [f"VERSION {version!r} is not valid Semantic Versioning"]
    return []


def validate_changelog(path: Path | None = None) -> list[str]:
    """Require the root release history."""
    path = path or CHANGELOG_PATH
    if not path.is_file():
        return ["Missing CHANGELOG.md"]
    if not path.read_text(encoding="utf-8").strip():
        return ["CHANGELOG.md must contain the release history"]
    return []


def validate_contract_versions(root: Path = ROOT) -> list[str]:
    """Keep each skill-owned contract version on its owning skill's version."""
    errors: list[str] = []
    for relative, pattern, owner, mode in CONTRACT_VERSION_DECLARATIONS:
        path = root / relative
        if not path.is_file():
            errors.append(f"{relative}: contract version declaration file is missing")
            continue
        values = re.findall(pattern, path.read_text(encoding="utf-8"), re.MULTILINE)
        if len(values) != 1:
            errors.append(f"{relative}: expected exactly one contract version declaration matching {pattern}")
            continue
        value = values[0]
        frontmatter = _frontmatter(root / "skills" / owner)
        raw = _metadata_field(frontmatter, "version") if frontmatter is not None else None
        quoted = re.fullmatch(r'"([^"]+)"', raw) if raw is not None else None
        owner_version = quoted.group(1) if quoted is not None else None
        if owner_version is None or not compatible_version(owner_version, owner_version):
            errors.append(
                f"{relative}: owner skills/{owner} metadata.version {owner_version!r} must be a plain "
                "MAJOR.MINOR.PATCH version its contract consumers accept"
            )
            continue
        if mode == "exact":
            if value != owner_version:
                errors.append(
                    f"{relative}: contract version {value!r} must equal skills/{owner} metadata.version {owner_version!r}"
                )
        elif not compatible_version(value, owner_version):
            errors.append(
                f"{relative}: built-against version {value!r} must share the major of "
                f"skills/{owner} metadata.version {owner_version!r}"
            )
    return errors


def validate_readme_release_link(readme_path: Path | None = None) -> list[str]:
    """Keep the dynamic latest-release badge pointed at the release page."""
    readme_path = readme_path or README_PATH
    if not readme_path.is_file():
        return ["Missing README.md"]

    match = LATEST_RELEASE_BADGE_RE.search(readme_path.read_text(encoding="utf-8"))
    if match is None:
        return ["README.md: missing Latest Release badge"]
    if match.group("target_url") != LATEST_RELEASE_URL:
        return [f"README.md: Latest Release badge must target {LATEST_RELEASE_URL}"]
    return []


def validate_marketplace() -> list[str]:
    if not MARKETPLACE_PATH.is_file():
        return ["Missing .claude-plugin/marketplace.json"]

    try:
        payload = json.loads(MARKETPLACE_PATH.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [f".claude-plugin/marketplace.json: invalid JSON: {exc}"]

    plugins = payload.get("plugins") if isinstance(payload, dict) else None
    if not isinstance(plugins, list):
        return [".claude-plugin/marketplace.json: plugins must be an array"]

    errors: list[str] = []
    actual_groups: dict[str, set[str]] = {}
    all_paths: list[str] = []
    for plugin in plugins:
        if not isinstance(plugin, dict):
            errors.append(".claude-plugin/marketplace.json: each plugin must be an object")
            continue
        name = plugin.get("name")
        source = plugin.get("source")
        skills = plugin.get("skills")
        if not isinstance(name, str) or not name:
            errors.append(".claude-plugin/marketplace.json: each plugin requires a name")
            continue
        if source != "./":
            errors.append(f".claude-plugin/marketplace.json: {name} source must be './'")
        if not isinstance(skills, list) or not all(isinstance(path, str) for path in skills):
            errors.append(f".claude-plugin/marketplace.json: {name} skills must be an array of paths")
            continue
        if name in actual_groups:
            errors.append(f".claude-plugin/marketplace.json: duplicate plugin group {name}")
            continue
        path_set = set(skills)
        if len(path_set) != len(skills):
            errors.append(f".claude-plugin/marketplace.json: {name} contains duplicate skill paths")
        actual_groups[name] = path_set
        all_paths.extend(skills)
        for skill_path in skills:
            if not skill_path.startswith("./skills/"):
                errors.append(f".claude-plugin/marketplace.json: invalid skill path {skill_path!r}")
                continue
            resolved = ROOT / skill_path.removeprefix("./")
            if not (resolved / "SKILL.md").is_file():
                errors.append(f".claude-plugin/marketplace.json: missing {skill_path}/SKILL.md")

    expected_groups = {
        "first-four-hours": {
            f"./skills/{skill.parent.name}/{skill.name}"
            for skill in discover_skills()
        }
    }
    if set(actual_groups) != set(expected_groups):
        errors.append(
            f".claude-plugin/marketplace.json: plugin groups must be exactly {sorted(expected_groups)}"
        )
    for name, expected_paths in expected_groups.items():
        if name in actual_groups and actual_groups[name] != expected_paths:
            errors.append(f".claude-plugin/marketplace.json: {name} must contain exactly {sorted(expected_paths)}")
    if len(all_paths) != len(set(all_paths)):
        errors.append(".claude-plugin/marketplace.json: skill paths must belong to only one group")
    if (ROOT / ".claude-plugin" / "plugin.json").exists():
        errors.append(".claude-plugin/plugin.json must remain absent; marketplace.json owns plugin metadata")
    for manifest_name in ("skill.yaml", "skill.yml", "skill.json"):
        if (ROOT / manifest_name).exists():
            errors.append(f"{manifest_name} is unsupported and must remain absent")
    return errors


def _instruction_section(path: Path, heading: str) -> str | None:
    if not path.is_file():
        return None
    pattern = re.compile(
        rf"^## {re.escape(heading)}\s*\n(.*?)(?=^## |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(path.read_text(encoding="utf-8"))
    return match.group(1).strip() if match else None


VERSIONING_DELEGATE_HEADING = "Repository Changes"
VERSIONING_AUTHORITY_PATH = ROOT / "REPO_VERSIONING.md"
VERSIONING_REQUIRED_TERMS = (
    "`VERSION`",
    "`CHANGELOG.md`",
    "Semantic Versioning",
    "only the affected",
    "unmodified skills retain",
    "highest-impact",
    "Major:",
    "Minor:",
    "Patch:",
    "validate_repository.py",
)


def _versioning_delegate_section(path: Path) -> str | None:
    for heading in (VERSIONING_DELEGATE_HEADING, "Versioning"):
        section = _instruction_section(path, heading)
        if section is not None:
            return section
    return None


def validate_versioning_instructions() -> list[str]:
    agents_section = _versioning_delegate_section(ROOT / "AGENTS.md")
    claude_section = _versioning_delegate_section(ROOT / "CLAUDE.md")
    errors: list[str] = []
    if agents_section is None:
        errors.append(f"AGENTS.md: missing {VERSIONING_DELEGATE_HEADING} section")
    if claude_section is None:
        errors.append(f"CLAUDE.md: missing {VERSIONING_DELEGATE_HEADING} section")
    if agents_section is not None and claude_section is not None and agents_section != claude_section:
        errors.append(f"AGENTS.md and CLAUDE.md {VERSIONING_DELEGATE_HEADING} sections must match")
    for label, section in (("AGENTS.md", agents_section), ("CLAUDE.md", claude_section)):
        if section is not None and "REPO_VERSIONING.md" not in section:
            errors.append(f"{label}: {VERSIONING_DELEGATE_HEADING} must reference REPO_VERSIONING.md")
    testing_sections = {name: _instruction_section(ROOT / name, "Testing Rules")
                        for name in ("AGENTS.md", "CLAUDE.md")}
    for name, section in testing_sections.items():
        if section is None:
            errors.append(f"{name}: missing Testing Rules section")
        else:
            for link in ("REPO_VERSIONING.md#adding-or-changing-tests", "REPO_VERSIONING.md#suite-size-cap"):
                if link not in section:
                    errors.append(f"{name}: Testing Rules must reference {link}")
    if all(section is not None for section in testing_sections.values()):
        if len({" ".join(section.split()) for section in testing_sections.values() if section is not None}) != 1:
            errors.append("AGENTS.md and CLAUDE.md Testing Rules sections must match")
    if not VERSIONING_AUTHORITY_PATH.is_file():
        errors.append("REPO_VERSIONING.md: missing versioning authority file")
        return errors
    authority_text = VERSIONING_AUTHORITY_PATH.read_text(encoding="utf-8")
    authority_lower = authority_text.lower()
    for term in VERSIONING_REQUIRED_TERMS:
        if term.lower() not in authority_lower:
            errors.append(f"REPO_VERSIONING.md must mention {term}")
    return errors


def validate_skill_package(skill_dir: Path) -> list[str]:
    errors = validate_frontmatter(skill_dir)
    for child in skill_dir.iterdir():
        if child.name not in ALLOWED_TOP_LEVEL:
            errors.append(f"{child.relative_to(ROOT)}: unsupported skill-package resource")
    for path in skill_dir.rglob("*"):
        if "__pycache__" in path.parts:
            continue
        if any(part in FORBIDDEN_PARTS for part in path.parts):
            errors.append(f"{path.relative_to(ROOT)}: development or platform artifact inside skill package")
    return errors


def validate_script_references(skill_dir: Path) -> list[str]:
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        return []
    text = skill_md.read_text(encoding="utf-8")
    errors: list[str] = []
    for reference in re.findall(r"python\s+[\"']?(scripts[/\\][A-Za-z0-9_-]+\.py)[\"']?", text):
        if not (skill_dir / reference.replace("\\", "/")).is_file():
            errors.append(f"{skill_md.relative_to(ROOT)}: references missing bundled script {reference}")
    return errors


def _local_link_targets(document: Path) -> list[tuple[str, Path]]:
    """Return each local Markdown link target in a document with its resolved path."""
    targets: list[tuple[str, Path]] = []
    text = document.read_text(encoding="utf-8")
    for match in MARKDOWN_LINK_RE.finditer(text):
        raw_target = match.group("bracketed") or match.group("plain")
        if raw_target.startswith("#"):
            continue
        parsed = urlsplit(raw_target)
        if parsed.scheme or parsed.netloc:
            continue
        relative = unquote(parsed.path).replace("\\", "/")
        if not relative:
            continue
        targets.append((raw_target, (document.parent / relative).resolve()))
    return targets


def validate_markdown_references(skill_dir: Path) -> list[str]:
    """Validate local Markdown targets and direct progressive-disclosure links."""
    errors: list[str] = []
    skill_root = skill_dir.resolve()
    repository_root = ROOT.resolve()
    skill_md = skill_dir / "SKILL.md"
    directly_linked: set[Path] = set()

    for document in sorted(skill_dir.rglob("*.md")):
        if "__pycache__" in document.parts:
            continue
        for raw_target, target in _local_link_targets(document):
            label = document.relative_to(ROOT)
            if not target.is_relative_to(repository_root):
                errors.append(f"{label}: local Markdown link escapes the repository: {raw_target}")
                continue
            if document == skill_md and not target.is_relative_to(skill_root):
                errors.append(f"{label}: SKILL.md link escapes its skill package: {raw_target}")
                continue
            if not target.exists():
                errors.append(f"{label}: local Markdown link target does not exist: {raw_target}")
                continue
            if document == skill_md:
                directly_linked.add(target)

    references_dir = skill_dir / "references"
    if references_dir.is_dir():
        for reference in sorted(references_dir.rglob("*.md")):
            if reference.resolve() not in directly_linked:
                errors.append(
                    f"{skill_md.relative_to(ROOT)}: reference is not linked directly: "
                    f"{reference.relative_to(skill_dir).as_posix()}"
                )
    return errors


def validate_documentation_links() -> list[str]:
    """Validate local and repository GitHub links in the README and user documentation."""
    errors: list[str] = []
    repository_root = ROOT.resolve()
    docs_root = (ROOT / "docs").resolve()
    documents: list[Path] = []
    if (ROOT / "README.md").is_file():
        documents.append(ROOT / "README.md")
    if (ROOT / "docs").is_dir():
        documents.extend(sorted((ROOT / "docs").rglob("*.md")))
    for document in documents:
        label = document.relative_to(ROOT).as_posix()
        in_docs = document.resolve().is_relative_to(docs_root)
        for raw_target, target in _local_link_targets(document):
            if not target.is_relative_to(repository_root):
                errors.append(f"{label}: local Markdown link escapes the repository: {raw_target}")
            elif in_docs and not target.is_relative_to(docs_root):
                errors.append(
                    f"{label}: local Markdown link leaves docs/, which GitBook cannot follow; "
                    f"link the file by its GitHub URL on main: {raw_target}"
                )
            elif not target.exists():
                errors.append(f"{label}: local Markdown link target does not exist: {raw_target}")
        for match in MARKDOWN_LINK_RE.finditer(document.read_text(encoding="utf-8")):
            raw_target = match.group("bracketed") or match.group("plain")
            prefix = next((p for p in REPOSITORY_FILE_URL_PREFIXES if raw_target.startswith(p)), None)
            if prefix is None:
                continue
            target = (repository_root / unquote(urlsplit(raw_target[len(prefix):]).path)).resolve()
            if not target.is_relative_to(repository_root) or not target.exists():
                errors.append(f"{label}: GitHub link target does not exist in this repository: {raw_target}")
    return errors


def validate_gitbook_navigation() -> list[str]:
    """Keep every documentation page listed in the GitBook table of contents."""
    docs = ROOT / "docs"
    if not docs.is_dir():
        return []
    summary = docs / "SUMMARY.md"
    if not summary.is_file():
        return ["docs/SUMMARY.md: missing, so GitBook would infer its own navigation"]
    listed = {target for _, target in _local_link_targets(summary)}
    errors: list[str] = []
    for page in sorted(docs.rglob("*.md"), key=lambda path: path.relative_to(docs).as_posix()):
        relative = page.relative_to(docs).as_posix()
        if relative != "SUMMARY.md" and page.resolve() not in listed:
            errors.append(f"docs/SUMMARY.md: does not list docs/{relative}, so it will not appear on GitBook")
    return errors


def validate_skill_protocol(skill_dir: Path) -> list[str]:
    """Validate protocol participants."""
    manifest_path = skill_dir / "skill-protocol.json"
    scripts_dir = skill_dir / "scripts"
    scripts = (
        {
            path.relative_to(scripts_dir).as_posix()
            for path in scripts_dir.rglob("*.py")
            if path.name != "__init__.py" and "__pycache__" not in path.parts
        }
        if scripts_dir.is_dir()
        else set()
    )
    if not manifest_path.exists():
        if not scripts:
            return []
        return [
            f"{skill_dir.relative_to(ROOT)}: executable skill is missing skill-protocol.json; "
            f"unclassified scripts: {', '.join(sorted(scripts))}"
        ]
    cli_path = scripts_dir / "cli.py"
    fallback_path = scripts_dir / "_skill_protocol_runtime.py"
    diagnostic_path = scripts_dir / "_diagnostic_contract.py"
    errors: list[str] = []
    if not cli_path.is_file():
        errors.append("executable skill must expose scripts/cli.py")
    if not fallback_path.is_file():
        errors.append("executable skill must package scripts/_skill_protocol_runtime.py")
    elif fallback_path.read_bytes() != (ROOT / "tools" / "skill_protocol" / "runtime.py").read_bytes():
        errors.append("packaged common CLI runtime is stale")
    if not diagnostic_path.is_file():
        errors.append("executable skill must package scripts/_diagnostic_contract.py")
    elif diagnostic_path.read_bytes() != (ROOT / "tools" / "diagnostics" / "runtime.py").read_bytes():
        errors.append("packaged diagnostic runtime is stale")
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [f"{manifest_path.relative_to(ROOT)}: invalid JSON: {exc}"]
    errors.extend(validate_manifest(payload, skill_dir=skill_dir))
    if isinstance(payload, dict) and payload.get("skill") != skill_dir.name:
        errors.append("manifest skill must match the installed skill directory")
    if skill_dir.name == "ticket":
        alternate_path = skill_dir / "references" / "select-protocol.json"
        if not alternate_path.is_file():
            errors.append("alternate manifest is missing: references/select-protocol.json")
        else:
            try:
                alternate = json.loads(alternate_path.read_text(encoding="utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                errors.append(f"alternate manifest is invalid JSON: {exc}")
            else:
                errors.extend(
                    f"alternate manifest: {error}"
                    for error in validate_manifest(alternate, skill_dir=skill_dir)
                )
                if isinstance(alternate, dict) and alternate.get("skill") != skill_dir.name:
                    errors.append("alternate manifest skill must match the installed skill directory")
    try:
        display_path = manifest_path.relative_to(ROOT)
    except ValueError:
        display_path = manifest_path
    return [f"{display_path}: {error}" for error in sorted(set(errors))]


def validate_retired_surfaces() -> list[str]:
    """Reject tracked-style platform surfaces while tolerating ignored bytecode caches."""
    errors: list[str] = []
    for relative_path in RETIRED_PATHS:
        path = ROOT / relative_path
        if path.is_file():
            errors.append(f"Retired platform artifact remains: {relative_path}")
        elif path.is_dir() and any("__pycache__" not in child.parts for child in path.rglob("*")):
            errors.append(f"Retired platform artifact remains: {relative_path}")
    return errors


def _compatibility_mapping_hits(text: str) -> list[str]:
    """Find executable Python retired-to-canonical dictionaries exactly."""

    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    authority_dicts: set[int] = set()
    hits: set[str] = set()
    # ast.walk is breadth-first, so an assignment is seen before the dict it assigns.
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == "CANONICAL_REPLACEMENTS" for target in node.targets):
                authority_dicts.add(id(node.value))
            continue
        if not isinstance(node, ast.Dict) or id(node) in authority_dicts:
            continue
        for key, value in zip(node.keys, node.values, strict=True):
            if not (
                isinstance(key, ast.Constant)
                and isinstance(key.value, str)
                and isinstance(value, ast.Constant)
                and isinstance(value.value, str)
            ):
                continue
            retired = re.sub(r"/+", "/", key.value.replace("\\", "/"))
            canonical = re.sub(r"/+", "/", value.value.replace("\\", "/"))
            if CANONICAL_REPLACEMENTS.get(retired) == canonical:
                hits.add(f"{retired} -> {canonical}")
    return sorted(hits)


def validate_canonical_convergence(
    root: Path = ROOT,
    source_files: list[Path] | None = None,
) -> list[str]:
    """Keep retired identities out of active source while preserving explicit proof/history."""

    errors: list[str] = []
    skills_root = root / "skills"
    if skills_root.exists():
        for retired in RETIRED_CAPABILITY_IDENTITIES:
            for path in skills_root.rglob(retired):
                if "__pycache__" not in path.parts:
                    errors.append(f"Retired skill/package identity remains: {path.relative_to(root).as_posix()}")
        for retired in RETIRED_REASONING_IDENTITIES:
            path = skills_root / "reasoning" / retired
            if path.exists():
                errors.append(f"Retired reasoning package identity remains: {path.relative_to(root).as_posix()}")
        for retired in RETIRED_ARTIFACT_FILENAMES:
            for path in skills_root.rglob(retired):
                if "__pycache__" not in path.parts:
                    errors.append(f"Retired artifact filename remains: {path.relative_to(root).as_posix()}")

    routing_root = root / "skills" / "routing"
    if routing_root.exists():
        errors.append("Retired package path remains: skills/routing/")

    files = tracked_files() if source_files is None else source_files
    retired_tokens = (
        *RETIRED_CAPABILITY_IDENTITIES,
        *RETIRED_ARTIFACT_FILENAMES,
    )
    for path in files:
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative in CANONICAL_CONVERGENCE_HISTORICAL_FILES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        hits = sorted(token for token in retired_tokens if token in text)
        # Cheap necessary conditions first; slash normalization never creates or removes these words.
        package_candidate = "skills" in text and "routing" in text
        reasoning_candidate = RETIRED_REASONING_WORD_RE.search(text) is not None
        if package_candidate or reasoning_candidate:
            normalized_text = re.sub(r"/+", "/", text.replace("\\", "/"))
            if package_candidate and RETIRED_PACKAGE_PATH_RE.search(normalized_text):
                hits.append(RETIRED_PACKAGE_PATHS[0])
            if reasoning_candidate and RETIRED_REASONING_IDENTITY_RE.search(normalized_text):
                hits.append("retired reasoning identity")
        if not hits:
            continue
        mapping_hits = _compatibility_mapping_hits(text)
        if mapping_hits:
            errors.append(f"{relative}: retired compatibility mapping remains: {', '.join(mapping_hits)}")
            continue
        if relative in CANONICAL_CONVERGENCE_AUTHORITY_FILES:
            continue
        allowed_tokens = CANONICAL_CONVERGENCE_REJECTION_LOCATIONS.get(relative)
        if allowed_tokens is None:
            errors.append(f"{relative}: retired active surface remains: {', '.join(hits)}")
            continue
        unclassified = sorted(set(hits) - allowed_tokens)
        if unclassified:
            errors.append(
                f"{relative}: retired strings are not explicitly classified as rejection evidence: "
                + ", ".join(unclassified)
            )
    return errors


def validate_ticket_rename(source_files: list[Path] | None = None) -> list[str]:
    """Reject the retired public name outside bounded history/migration evidence."""

    errors: list[str] = []
    for path in tracked_files() if source_files is None else source_files:
        relative = path.relative_to(ROOT).as_posix()
        if relative in LEGACY_SCOPE_ALLOWED:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if LEGACY_SCOPE_NAME in text or LEGACY_SCOPE_NAME.replace("-", "_") in text:
            errors.append(f"{relative}: retired `{LEGACY_SCOPE_NAME}` identity remains; replace it with `ticket`")
    return errors


def validate_atlas_wiki() -> list[str]:
    """Check a committed root Atlas wiki's structure; freshness state is never consulted."""
    wiki_path = ROOT / ".map"
    if not (wiki_path.exists() or wiki_path.is_symlink()):
        return []
    result = run_capture(
        [sys.executable, "-B", str(ATLAS_STRUCTURE_SCRIPT), "--repo-root", str(ROOT)],
        cwd=ROOT,
    )
    if result.returncode == 0:
        return []
    if result.returncode == 3:
        try:
            payload = json.loads(result.stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = None
        diagnostics = payload.get("diagnostics") if isinstance(payload, dict) else None
        if isinstance(diagnostics, list) and diagnostics and all(isinstance(item, dict) for item in diagnostics):
            return [f"Atlas wiki structure: {item.get('code')}: {item.get('message')}" for item in diagnostics]
    detail = result.stderr.decode("utf-8", errors="replace").strip()
    return [f"Atlas wiki structural validation did not complete (exit {result.returncode}): {detail}"]


PAPER_RUNTIME = SKILLS_ROOT / "learning" / "examiner" / "assets" / "paper-runtime.html"
# A write assigns (never compares, never an arrow) outside a declaration; an in-page link target is a "#" fragment
# or a blob the runtime made itself. Text cannot show where an action or background value points, so every such
# write is refused. The runtime never names src, srcset, srcdoc or ping, and its CSS uses background-color, so
# those words are refused anywhere and background anywhere except as style.background.
PAPER_RUNTIME_WRITE = r"(?:\+|\|\||&&|\?\?)?=(?![=>])"
PAPER_RUNTIME_UNDECLARED = r"(?<!\bconst )(?<!\blet )(?<!\bvar )"
PAPER_RUNTIME_OFF_PAGE = r"""(?!\s*(?:["'`]#|(?:[\w$]+\s*=\s*)?URL\.createObjectURL\s*\())"""
PAPER_RUNTIME_TAGS = r"(?:link|script|img|iframe|embed|object|video|audio|source|base|style|form|meta)"
PAPER_RUNTIME_EXTERNAL = (
    ("absolute URL", re.compile(r"\b(?:https?|wss?|ftp):", re.IGNORECASE)),
    ("protocol-relative URL", re.compile(r"""["'(=]\s*//[^/\s]""")),
    ("network API", re.compile(
        r"\b(?:fetch(?:Later)?|XMLHttpRequest|WebSocket|EventSource|sendBeacon|importScripts|RTCPeerConnection)\b")),
    ("module import", re.compile(r"\bimport\s*\(|^\s*import\b|@import", re.IGNORECASE | re.MULTILINE)),
    ("external resource element", re.compile(
        r"<\s*(?:link|iframe|img|embed|object|video|audio|source|base)\b|\bsrc\s*=", re.IGNORECASE)),
    ("worker", re.compile(r"\b(?:Worker|SharedWorker|serviceWorker)\b")),
    ("CSS resource", re.compile(r"\b(?:url|image-set)\s*\(", re.IGNORECASE)),
    ("script-created resource", re.compile(
        r"createElement\s*\(\s*[\"'`](?:link|script|img|iframe|embed|object|video|audio|source|base|style|form|meta)\b",
        re.IGNORECASE)),
    ("media load", re.compile(r"\bnew\s+(?:Image|Audio)\b")),
    ("helper-created resource", re.compile(
        r"""(?<![\w$.])[\w$]+\s*\(\s*["'`]""" + PAPER_RUNTIME_TAGS + r"""["'`]"""
        r"""|\(\s*["'`]""" + PAPER_RUNTIME_TAGS + r"""["'`]\s*,\s*\{""",
        re.IGNORECASE)),
    ("source attribute", re.compile(r"\bsrc(?:set|doc)?\b", re.IGNORECASE)),
    # The runtime's CSS sets only background-color, so background is refused everywhere but style.background.
    ("URL attribute", re.compile(r"""\bformaction\b|\bping\b|(?<!style\.)\bbackground\b(?!-)""", re.IGNORECASE)),
    ("page navigation", re.compile(
        r"""\blocation\s*(?:\.\s*(?:assign|replace)\b|\.\s*\w+\s*""" + PAPER_RUNTIME_WRITE + r"""|\[|"""
        + PAPER_RUNTIME_WRITE + r""")|(?<![\w$])open\s*(?:\?\.\s*)?\((?!\s*\))"""
        r"""|(?<![\w$])navigate\s*(?:\?\.\s*)?\("""
        r"""|\.\s*(?:open|navigate)\s*\.\s*(?:call|apply|bind)\b"""
        r"""|\b(?:window|self|globalThis|top|parent)\s*\.\s*open\b|\[\s*["'`]open["'`]\s*\]"""
        r"""|\bhistory\s*\.\s*(?:back|forward|go)\b|\bnavigation\s*\.\s*(?:back|forward|traverseTo)\b"""
        r"""|\.\s*(?:requestSubmit|submit)\s*\(|http-?equiv""",
        re.IGNORECASE)),
    # Only a form reads action, but any receiver may be one, so every action write is refused on every receiver.
    ("form action", re.compile(
        r"""setAttribute\s*\(\s*["'`]action["'`]|""" + PAPER_RUNTIME_UNDECLARED + r"""\baction["'`]?\]?\s*"""
        + PAPER_RUNTIME_WRITE,
        re.IGNORECASE)),
    # A link may only point within the page or at a blob the runtime made itself.
    ("link target", re.compile(
        PAPER_RUNTIME_UNDECLARED + r"""\bhref["'`]?\]?\s*""" + PAPER_RUNTIME_WRITE + PAPER_RUNTIME_OFF_PAGE
        + r"""|[{,]\s*["'`]?(?:xlink:)?href["'`]?\s*:""" + PAPER_RUNTIME_OFF_PAGE
        + r"""|setAttribute\s*\(\s*["'`](?:xlink:)?href["'`]\s*,""" + PAPER_RUNTIME_OFF_PAGE
        + r"""|setAttributeNS\s*\([^,()]*,\s*["'`](?:xlink:)?href["'`]\s*,""" + PAPER_RUNTIME_OFF_PAGE
        + r"""|[{,]\s*href\s*[,}]""",
        re.IGNORECASE)),
)
PAPER_RUNTIME_MAX_BYTES = 41000


def validate_paper_runtime(path: Path = PAPER_RUNTIME) -> list[str]:
    """Refuse an Examiner paper runtime that loads or sends anything outside its own file."""
    label = path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else path.as_posix()
    if not path.is_file():
        return [f"{label}: paper runtime is missing"]
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    if len(text.encode("utf-8")) > PAPER_RUNTIME_MAX_BYTES:
        errors.append(f"{label}: paper runtime is larger than {PAPER_RUNTIME_MAX_BYTES} bytes")
    errors.extend(f"{label}: paper runtime is not self-contained: {name}"
                  for name, pattern in PAPER_RUNTIME_EXTERNAL if pattern.search(text))
    return errors


def main() -> int:
    skills = discover_skills()
    errors = ["No skills found under skills/<domain>/<skill>"] if not skills else []
    files = tracked_files()
    if not files:
        errors.append("Unable to enumerate Git-tracked repository files")
    errors.extend(validate_version())
    errors.extend(validate_changelog())
    errors.extend(validate_readme_release_link())
    errors.extend(validate_documentation_links())
    errors.extend(validate_gitbook_navigation())
    errors.extend(validate_marketplace())
    errors.extend(validate_invocation_policy(skill_dirs=skills))
    errors.extend(validate_certified_platform_coverage())
    errors.extend(validate_versioning_instructions())
    errors.extend(validate_contract_versions())
    errors.extend(validate_domain_layout())
    errors.extend(validate_test_ownership())
    errors.extend(validate_atlas_wiki())
    from validate_runtime_discovery_policy import validate as validate_runtime_discovery
    errors.extend(validate_runtime_discovery())
    errors.extend(validate_guidance(ROOT))
    errors.extend(validate_paper_runtime())
    for skill_dir in skills:
        errors.extend(validate_skill_package(skill_dir))
        errors.extend(validate_script_references(skill_dir))
        errors.extend(validate_markdown_references(skill_dir))
        errors.extend(validate_skill_protocol(skill_dir))
    errors.extend(validate_retired_surfaces())
    errors.extend(validate_canonical_convergence(source_files=files))
    errors.extend(validate_blueprint_retired_runtime())
    errors.extend(validate_ticket_rename(source_files=files))
    for module_name in (
        "sync_diagnostic_runtime", "sync_classification_runtime", "sync_skill_protocol_runtime",
        "sync_architecture_handoff", "sync_delegation_projection", "sync_router_manifest",
        "sync_skill_catalog", "sync_learning_runtime",
    ):
        import importlib
        errors.extend(importlib.import_module(module_name).check())
    if errors:
        print("Repository validation failed:", file=sys.stderr)
        for error in sorted(set(errors)):
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(f"Repository validation passed for {len(skills)} skills.")
    return 0
