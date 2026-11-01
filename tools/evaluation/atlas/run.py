"""Atlas evaluation runner.

Commands:
  check-questions  validate a question set; with --repo-dir, also prove each hop exists and
                   that grepping the question's key terms misses at least one hop file
  install-skill    copy this repository's Atlas skill into <repo>/.claude/skills/atlas
  build-map        have Atlas build .map/ and its CLAUDE.md block in <repo>; records the cost
  answer           run one arm (3 runs per question by default); resumable per run

Raw run records, including answers, go to the work directory (default .scratch/atlas-eval/<repo>/),
never into the repository. summarize.py writes the committed CSV/JSON.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tools.evaluation.atlas import common as c  # noqa: E402

ANSWER_PROMPT = (
    "Answer this question about the codebase in the current directory. "
    "Cite the file paths and symbol names your answer relies on. Do not modify any files.\n\n"
    "Question: {q}"
)
BUILD_PROMPT = (
    "Use the atlas skill to author an Atlas map for this repository from scratch: build the .map/ "
    "hierarchy, run the structure check and repair every diagnostic, then run setup-guidance so "
    "CLAUDE.md and AGENTS.md carry the Map. Do not change any other file."
)
SKIP_DIRS = {".git", "node_modules", ".map", ".claude", "vendor", "target", "build", "dist", "__pycache__"}
MAX_SCAN_BYTES = 2_000_000


def work_dir(args: argparse.Namespace, qset: dict[str, Any]) -> Path:
    base: Path = args.work or c.DEFAULT_WORK
    return base / qset["name"]


def _hop_problems(q: dict[str, Any]) -> list[str]:
    problems = []
    hops = q.get("hops") or []
    if len(hops) < 3:
        problems.append("needs at least three hops")
    files = {h.get("file", "") for h in hops}
    dirs = {str(Path(f).parent) for f in files}
    if len(files) < 3 and len(dirs) < 2:
        problems.append("hops must span at least three files or two packages")
    gap = q.get("grep_gap") or {}
    if not isinstance(gap.get("hop"), int) or not 0 <= gap["hop"] < len(hops) or not gap.get("reason"):
        problems.append("grep_gap needs a valid hop index and a reason")
    if not q.get("key_terms"):
        problems.append("key_terms (what a searcher would grep from the wording) are required")
    for h in hops:
        sym = h.get("symbol", "")
        if sym and re.search(rf"\b{re.escape(sym)}\b", q["question"]):
            problems.append(f"wording names hop symbol {sym}")
    return problems


def _repo_files(repo: Path) -> list[Path]:
    out = []
    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            p = Path(root) / name
            try:
                if p.stat().st_size <= MAX_SCAN_BYTES:
                    out.append(p)
            except OSError:
                continue
    return out


def _grep_hits(files: list[Path], repo: Path, terms: list[str]) -> set[str]:
    pats = [re.compile(re.escape(t), re.I) for t in terms]
    hits = set()
    for p in files:
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if any(pat.search(text) for pat in pats):
            hits.add(p.relative_to(repo).as_posix())
    return hits


def cmd_check_questions(args: argparse.Namespace) -> int:
    qset = c.load_questions(args.questions)
    problems: list[str] = []
    for key in ("name", "repo", "ref", "commit", "questions"):
        if key not in qset:
            problems.append(f"set: missing {key}")
    qs = qset.get("questions", [])
    ids = [q.get("id") for q in qs]
    if len(set(ids)) != len(ids):
        problems.append("set: duplicate question ids")
    for q in qs:
        for key in ("id", "kind", "question", "reference", "must_have"):
            if not q.get(key):
                problems.append(f'{q.get("id")}: missing {key}')
    if qset.get("connection_rule"):
        controls = [q for q in qs if c.is_control(q)]
        if len(controls) != 1:
            problems.append(f"set: needs exactly one control question, found {len(controls)}")
        if not 8 <= len(qs) - len(controls) <= 10:
            problems.append("set: needs 8-10 connection questions")
        for q in qs:
            if not c.is_control(q):
                problems += [f'{q["id"]}: {p}' for p in _hop_problems(q)]
        if args.repo_dir:
            repo = args.repo_dir.resolve()
            files = _repo_files(repo)
            for q in qs:
                if c.is_control(q) or not q.get("hops") or not q.get("key_terms"):
                    continue
                for h in q["hops"]:
                    f = repo / h["file"]
                    if not f.is_file():
                        problems.append(f'{q["id"]}: hop file {h["file"]} does not exist')
                    elif h.get("symbol") and h["symbol"] not in f.read_text(encoding="utf-8", errors="replace"):
                        problems.append(f'{q["id"]}: {h["symbol"]} not found in {h["file"]}')
                hits = _grep_hits(files, repo, q["key_terms"])
                hop_files = {h["file"] for h in q["hops"]}
                if hop_files <= hits:
                    problems.append(f'{q["id"]}: grepping its key terms reaches every hop file; rewrite it')
    for p in problems:
        print(p)
    print("ok" if not problems else f"{len(problems)} problem(s)")
    return 0 if not problems else 1


def cmd_install_skill(args: argparse.Namespace) -> int:
    dest = args.repo_dir / ".claude" / "skills" / "atlas"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(c.ATLAS_SKILL_SOURCE, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    print(f"installed Atlas skill at {dest}")
    return 0


def cmd_build_map(args: argparse.Namespace) -> int:
    qset = c.load_questions(args.questions)
    repo = args.repo_dir.resolve()
    state = c.arm_state(repo)
    if state["map"] or state["guidance"] or not state["skill"]:
        print(f"build-map needs the Atlas skill installed and no map or guidance yet; found {state}")
        return 2
    out = work_dir(args, qset)
    out.mkdir(parents=True, exist_ok=True)
    cmd = c.claude_cmd(BUILD_PROMPT, model=c.ANSWER_MODEL, effort=c.ANSWER_EFFORT,
                       allowed=c.BUILD_TOOLS, denied=c.BUILD_DENIED)
    raw = c.run_stream(cmd, cwd=repo, timeout=args.timeout)
    ok, reason = c.run_ok(raw, c.ANSWER_MODEL)
    state = c.arm_state(repo)
    if ok and not (state["map"] and state["guidance"]):
        ok, reason = False, f"build finished without a complete map: {state}"
    record = _record(raw, ok, reason)
    (out / "map-build.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(f"map build: {record['status']} {reason}".strip())
    return 0 if ok else 1


def _record(raw: dict[str, Any], ok: bool, reason: str) -> dict[str, Any]:
    data = raw["result_event"] or {}
    return {
        "status": "ok" if ok else "failed",
        "fail_reason": reason,
        "returncode": raw["returncode"],
        "wall_s": raw["wall_s"],
        "stderr": raw["stderr"],
        "result": data.get("result"),
        "usage": data.get("usage"),
        "modelUsage": data.get("modelUsage"),
        "total_cost_usd": data.get("total_cost_usd"),
        "num_turns": data.get("num_turns"),
        "duration_ms": data.get("duration_ms"),
        "skills_loaded": raw["skills_loaded"],
        "tool_calls": raw["tool_calls"],
    }


def _answer_one(repo: Path, arm: str, q: dict[str, Any], n: int, out_file: Path, timeout: int) -> str:
    cmd = c.claude_cmd(ANSWER_PROMPT.format(q=q["question"]), model=c.ANSWER_MODEL, effort=c.ANSWER_EFFORT,
                       allowed=c.READ_ONLY_TOOLS, denied=c.DENIED_TOOLS)
    raw = c.run_stream(cmd, cwd=repo, timeout=timeout)
    ok, reason = c.run_ok(raw, c.ANSWER_MODEL)
    has_atlas = any("atlas" in s.lower() for s in raw["skills_loaded"])
    if ok and has_atlas != (arm == "atlas"):
        ok, reason = False, f"Atlas skill loaded={has_atlas} in {arm} arm"
    record = {"qid": q["id"], "arm": arm, "repeat": n, **_record(raw, ok, reason)}
    out_file.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return f'{q["id"]}-{n}: {record["status"]} {reason}'.rstrip()


def cmd_answer(args: argparse.Namespace) -> int:
    qset = c.load_questions(args.questions)
    repo = args.repo_dir.resolve()
    problems = c.check_arm(repo, args.arm, qset["commit"])
    if problems:
        print("refusing to run: " + "; ".join(problems))
        return 2
    qs = qset["questions"]
    if args.only:
        qs = [q for q in qs if q["id"] in args.only]
    arm_dir = work_dir(args, qset) / args.arm
    arm_dir.mkdir(parents=True, exist_ok=True)
    todo = []
    for q in qs:
        for n in range(1, args.runs + 1):
            f = arm_dir / f'{q["id"]}-{n}.json'
            if f.exists() and json.loads(f.read_text(encoding="utf-8")).get("status") == "ok":
                continue
            todo.append((q, n, f))
    print(f"{len(todo)} runs to do", flush=True)
    consecutive_fail = 0
    with cf.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(_answer_one, repo, args.arm, q, n, f, args.timeout) for q, n, f in todo]
        for fut in cf.as_completed(futures):
            line = fut.result()
            print(line, flush=True)
            consecutive_fail = consecutive_fail + 1 if ": failed" in line else 0
            if consecutive_fail >= 3:
                print("3 consecutive failures (likely a usage limit); stopping. Rerun to resume.", flush=True)
                for f in futures:
                    f.cancel()
                return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("check-questions")
    p.add_argument("--questions", required=True, type=Path)
    p.add_argument("--repo-dir", type=Path)
    p = sub.add_parser("install-skill")
    p.add_argument("--repo-dir", required=True, type=Path)
    for name in ("build-map", "answer"):
        p = sub.add_parser(name)
        p.add_argument("--repo-dir", required=True, type=Path)
        p.add_argument("--questions", required=True, type=Path)
        p.add_argument("--work", type=Path, help="work directory root (default .scratch/atlas-eval)")
        p.add_argument("--timeout", type=int, default=3600 if name == "build-map" else 900)
        if name == "answer":
            p.add_argument("--arm", required=True, choices=c.ARMS)
            p.add_argument("--runs", type=int, default=3)
            p.add_argument("--workers", type=int, default=3)
            p.add_argument("--only", nargs="*", help="limit to these question ids")
    args = ap.parse_args(argv)
    handler = {"check-questions": cmd_check_questions, "install-skill": cmd_install_skill,
               "build-map": cmd_build_map, "answer": cmd_answer}[args.command]
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
