"""Blinded Opus grading: per question, every answer from both arms, shuffled and scrubbed.

Writes <work>/<set>/grades/<qid>.json and is resumable. The arm of each anonymous answer is
recorded only after grading, so the grader never sees it.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tools.evaluation.atlas import common as c  # noqa: E402

SCRUB = [(re.compile(p, re.I), r) for p, r in [
    (r"\.map[/\\][^\s`)\]]*", "[path]"),
    (r"\b(atlas|landmark|satellite)s?\b", "[guide]"),
]]

RUBRIC = """You are grading answers to a codebase question against a reference answer.
Do not use tools. Judge only factual correctness and completeness against the reference.

Grades:
- correct: covers every must-have point (equivalent names/paths are fine) and states nothing materially wrong.
- partial: misses one or more must-have points, or includes a minor error, but would still point a developer to the right code.
- wrong: misses most must-have points, or a material error would send a developer to the wrong place.

Question: {question}

Reference answer: {reference}

Must-have points: {must_have}

Answers:
{answers}

Reply with only a JSON object mapping each answer id to {{"grade": "correct|partial|wrong", "reason": "<one line>"}}."""


def scrub(text: str) -> str:
    for pat, rep in SCRUB:
        text = pat.sub(rep, text)
    return text


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--questions", required=True, type=Path)
    ap.add_argument("--work", type=Path, help="work directory root (default .scratch/atlas-eval)")
    ap.add_argument("--seed", type=int, default=20261101)
    ap.add_argument("--timeout", type=int, default=900)
    args = ap.parse_args(argv)
    qset = c.load_questions(args.questions)
    out = (args.work or c.DEFAULT_WORK) / qset["name"]
    gdir = out / "grades"
    gdir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)
    failures = 0

    for q in qset["questions"]:
        gfile = gdir / f'{q["id"]}.json'
        if gfile.exists():
            continue
        items: list[dict[str, Any]] = []
        for arm in c.ARMS:
            for f in sorted((out / arm).glob(f'{q["id"]}-*.json')):
                rec = json.loads(f.read_text(encoding="utf-8"))
                if rec.get("status") == "ok":
                    items.append({"arm": arm, "repeat": rec["repeat"], "text": rec["result"] or ""})
        if not items:
            print(f'{q["id"]}: no answers', flush=True)
            continue
        rng.shuffle(items)
        for i, it in enumerate(items):
            it["anon"] = f"A{i + 1}"
        answers = "\n\n".join(f'--- {it["anon"]} ---\n{scrub(it["text"])}' for it in items)
        prompt = RUBRIC.format(question=q["question"], reference=q["reference"],
                               must_have="; ".join(q["must_have"]), answers=answers)
        cmd = c.claude_cmd(None, model=c.GRADER_MODEL, effort=c.GRADER_EFFORT, allowed=[],
                           denied=["Bash", "PowerShell", "Read", "Grep", "Glob", "Edit", "Write", "WebFetch",
                                   "WebSearch", "Agent", "Task", "Skill"])
        raw = c.run_stream(cmd, cwd=gdir, timeout=args.timeout, stdin_text=prompt)
        ok, reason = c.run_ok(raw, c.GRADER_MODEL)
        data = raw["result_event"] or {}
        try:
            if not ok:
                raise ValueError(reason)
            body = str(data["result"])
            verdicts = json.loads(body[body.index("{"): body.rindex("}") + 1])
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            failures += 1
            print(f'{q["id"]}: grading failed ({exc}); rerun to resume', flush=True)
            continue
        graded = [{**{k: it[k] for k in ("anon", "arm", "repeat")}, **verdicts.get(it["anon"], {})}
                  for it in items]
        gfile.write_text(json.dumps({"qid": q["id"], "grader": c.GRADER_MODEL, "effort": c.GRADER_EFFORT,
                                     "models": list(data.get("modelUsage") or {}),
                                     "grader_cost_usd": data.get("total_cost_usd"),
                                     "grades": graded}, indent=2), encoding="utf-8")
        print(f'{q["id"]}: graded {len(graded)}', flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
