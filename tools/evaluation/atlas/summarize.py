"""Summarize one question set's runs into committed results: runs.csv and summary.json.

Reads raw records and grades from the work directory and writes only metrics, grades, and
tool-call counts (no answers or transcripts) to tools/evaluation/atlas/results/<set>/.
Connection and control questions are aggregated separately. --spot-check writes a hand-review
sample of about 10% of graded runs, with answers, to the work directory only.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import statistics as st
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tools.evaluation.atlas import common as c  # noqa: E402

FIELDS = ["qid", "kind", "group", "arm", "repeat", "grade", "grade_reason", "cost_usd", "turns",
          "input_tokens", "cache_creation_tokens", "cache_read_tokens", "output_tokens", "total_tokens",
          "tool_calls", "reads", "greps", "globs", "skills", "map_calls", "used_map"]
POINTS = {"correct": 1.0, "partial": 0.5, "wrong": 0.0}


def _mean(values: list[float], digits: int) -> float | None:
    return round(st.mean(values), digits) if values else None


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {}
    grades = [r["grade"] for r in rows]
    agg: dict[str, Any] = {
        "runs": len(rows),
        "mean_cost_usd": _mean([r["cost_usd"] for r in rows], 4),
        "mean_turns": _mean([r["turns"] for r in rows], 1),
    }
    for key in ("input_tokens", "cache_creation_tokens", "cache_read_tokens", "output_tokens", "total_tokens"):
        agg[f"mean_{key}"] = round(st.mean(r[key] for r in rows))
    tooled = [r for r in rows if r["tool_calls"] != ""]
    if tooled:
        for key in ("tool_calls", "reads", "greps", "globs", "map_calls"):
            agg[f"mean_{key}"] = _mean([r[key] for r in tooled], 2)
        agg["runs_using_map"] = sum(1 for r in tooled if r["used_map"])
    for g in POINTS:
        agg[g] = grades.count(g)
    agg["ungraded"] = sum(1 for g in grades if g not in POINTS)
    agg["score"] = _mean([POINTS[g] for g in grades if g in POINTS], 3)
    return agg


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--questions", required=True, type=Path)
    ap.add_argument("--work", type=Path, help="work directory root (default .scratch/atlas-eval)")
    ap.add_argument("--spot-check", action="store_true")
    args = ap.parse_args(argv)
    qset = c.load_questions(args.questions)
    work = (args.work or c.DEFAULT_WORK) / qset["name"]
    dest = c.HERE / "results" / qset["name"]
    dest.mkdir(parents=True, exist_ok=True)

    grades: dict[tuple[str, str, int], dict[str, Any]] = {}
    for g in (work / "grades").glob("*.json"):
        for row in json.loads(g.read_text(encoding="utf-8"))["grades"]:
            grades[(g.stem, row["arm"], int(row["repeat"]))] = row

    main_group = "connection" if qset.get("connection_rule") else "standard"
    rows: list[dict[str, Any]] = []
    answers: dict[tuple[str, str, int], str] = {}
    for q in qset["questions"]:
        for arm in c.ARMS:
            for f in sorted((work / arm).glob(f'{q["id"]}-*.json')):
                rec = json.loads(f.read_text(encoding="utf-8"))
                if rec.get("status") != "ok":
                    continue
                key = (q["id"], arm, int(rec["repeat"]))
                answers[key] = rec.get("result") or ""
                tk = c.tokens(rec.get("usage") or {})
                calls = rec.get("tool_calls")
                counts = c.tool_counts(calls) if calls is not None else None
                g = grades.get(key, {})
                rows.append({
                    "qid": q["id"], "kind": q["kind"], "group": "control" if c.is_control(q) else main_group,
                    "arm": arm, "repeat": key[2], "grade": g.get("grade", ""), "grade_reason": g.get("reason", ""),
                    "cost_usd": round(rec["total_cost_usd"], 6), "turns": rec["num_turns"],
                    "input_tokens": tk["input"], "cache_creation_tokens": tk["cache_creation"],
                    "cache_read_tokens": tk["cache_read"], "output_tokens": tk["output"], "total_tokens": tk["total"],
                    **({k: counts[k] for k in ("tool_calls", "reads", "greps", "globs", "skills", "map_calls")}
                       if counts else dict.fromkeys(("tool_calls", "reads", "greps", "globs", "skills", "map_calls"), "")),
                    "used_map": (counts["map_calls"] > 0) if counts else "",
                })

    with (dest / "runs.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    summary: dict[str, Any] = {
        "set": qset["name"], "repo": qset["repo"], "ref": qset["ref"], "commit": qset["commit"],
        "answer_model": c.ANSWER_MODEL, "answer_effort": c.ANSWER_EFFORT,
        "grader_model": c.GRADER_MODEL, "grader_effort": c.GRADER_EFFORT,
        "connection_rule": bool(qset.get("connection_rule")),
        "tool_calls_recorded": all(r["tool_calls"] != "" for r in rows) if rows else False,
        "groups": {},
    }
    if qset.get("note"):
        summary["note"] = qset["note"]
    for group in (main_group, "control"):
        arms = {arm: aggregate([r for r in rows if r["group"] == group and r["arm"] == arm]) for arm in c.ARMS}
        if any(arms.values()):
            summary["groups"][group] = arms

    build_file = work / "map-build.json"
    if build_file.exists():
        b = json.loads(build_file.read_text(encoding="utf-8"))
        build: dict[str, Any] = {"cost_usd": round(b["total_cost_usd"], 6) if b.get("total_cost_usd") else None, "turns": b.get("num_turns"),
                                 **c.tokens(b.get("usage") or {})}
        if b.get("tool_calls") is not None:
            build.update(c.tool_counts(b["tool_calls"]))
        summary["map_build"] = build
        main = summary["groups"].get(main_group, {})
        base, atlas = main.get("baseline"), main.get("atlas")
        if base and atlas and build["cost_usd"]:
            saving = base["mean_cost_usd"] - atlas["mean_cost_usd"]
            summary["payback_questions"] = round(build["cost_usd"] / saving, 1) if saving > 0 else None
    (dest / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))

    if args.spot_check:
        graded = sorted(k for k in answers if k in grades)
        sample = random.Random(7).sample(graded, max(1, round(len(graded) / 10))) if graded else []
        qmap = {q["id"]: q for q in qset["questions"]}
        lines = [f"# Spot check: {qset['name']} ({len(sample)} of {len(graded)} graded runs)\n",
                 "Arms are listed at the end so the check stays blind.\n"]
        key_lines = ["## Arm key\n"]
        for i, (qid, arm, n) in enumerate(sorted(sample), 1):
            q, g = qmap[qid], grades[(qid, arm, n)]
            key_lines.append(f"- S{i}: {arm}")
            lines += [f"## S{i}: {qid}, graded {g.get('grade')}", f"Reason: {g.get('reason')}",
                      f"\n**Question:** {q['question']}", f"\n**Reference:** {q['reference']}",
                      f"\n**Answer:**\n\n{answers[(qid, arm, n)]}\n"]
        (work / "spot-check.md").write_text("\n".join(lines + key_lines) + "\n", encoding="utf-8")
        print(f"spot-check sample written to {work / 'spot-check.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
