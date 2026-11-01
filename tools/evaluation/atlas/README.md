# Atlas evaluation

This harness measures whether an Atlas map reduces the tokens and cost an agent spends exploring a repository, without lowering answer accuracy. It is an evaluation you can rerun by hand. It is not part of the test suite or CI, because a single repository costs real usage and takes far longer than the 120-second suite limit.

## Method

The method is fixed so results stay comparable:

- **Answering:** Sonnet 5.5 (`claude-sonnet-5-5`) at medium effort answers every question, and the same model and effort build each map. Each run is a fresh headless `claude -p` session. It loads project settings only, has an empty MCP config, gets read-only tools (Read, Grep, Glob, Skill) and runs no subagents.
- **Arms:** both arms use the same checkout at the question set's pinned commit.
  - The baseline arm has no `.map/`, no Atlas block in `CLAUDE.md` or `AGENTS.md`, and no Atlas skill.
  - The Atlas arm has all three. The skill is installed at `.claude/skills/atlas`.
  - `run.py answer` refuses a checkout that doesn't match its arm, or one with a `CLAUDE.md`, `CLAUDE.local.md` or `AGENTS.md` in a parent folder, since that file would load into every run. Keep checkouts outside this repository. It records a run as failed if the Atlas skill's loaded state doesn't match the arm.
- **Repeats:** each question runs 3 times per arm.
- **Grading:** Opus 5.5 (`claude-opus-5-5`) at high effort grades all of a question's answers together against the reference answer, as correct, partial or wrong. Answers are shuffled, and mentions of Atlas and `.map/` paths are removed first. You then hand-check about 10% of the graded runs using the spot-check file.
- **Tool calls:** every tool call is recorded from stream-json output. A call counts as map use when it reads or searches `.map/` or invokes the Atlas skill.
- **Failures:** a failed run, a usage-limited run, or a run on the wrong model is never counted as a result. Rerunning a command resumes the runs that didn't finish.

## Questions

Each repository has one question set in `questions/<name>.json`. Write it, including the reference answers, before that repository has a map.

A set with `"connection_rule": true` holds 8-10 connection questions and exactly one control question.

- **Connection questions:**
  - Each answer joins code across at least three files or two packages.
  - At least one step in the chain shares no searchable identifier with the question's wording. Typical cases are wiring by string name, config, registry, reflection or dependency injection; dispatch through an interface; event or RPC boundaries; generated code; and protocol or language boundaries.
  - The wording describes behaviour. It doesn't name the symbols or files that hold the answer.
- **The control question:** a single-symbol question where grep should win. It is reported separately.

Each question has these fields:

```json
{
  "id": "q01",
  "kind": "trace-flow",
  "question": "Behaviour-level question, naming no hop symbol",
  "reference": "Reference answer naming each file and symbol",
  "must_have": ["points the grader requires"],
  "hops": [{"file": "path/in/repo", "symbol": "Name"}],
  "grep_gap": {"hop": 2, "reason": "why a search from the wording does not reach this hop"},
  "key_terms": ["terms a searcher would grep from the wording"]
}
```

The control question has `"control": true` and needs no `hops`, `grep_gap` or `key_terms`.

Before using a set, run `check-questions --repo-dir` against the pinned checkout. It checks four things:

- every set and question has its required fields;
- every hop file exists and contains its symbol;
- no question names one of its own hop symbols;
- no single key term finds the grep-gap hop's file among 25 or fewer matching files. A search with that few results is one an agent can read through, so the step wouldn't really be hidden. Common words that match thousands of files don't count as reaching it.

## Running one repository

Run these from the repository root. Raw records, answers and grades go to `.scratch/atlas-eval/<name>/` (change this with `--work`), which git ignores.

```bash
H=tools/evaluation/atlas; Q=$H/questions/<name>.json; R=<path to pinned checkout>
python $H/run.py check-questions --questions $Q --repo-dir $R
python $H/run.py answer --repo-dir $R --questions $Q --arm baseline
python $H/run.py install-skill --repo-dir $R
python $H/run.py build-map --repo-dir $R --questions $Q
python $H/run.py answer --repo-dir $R --questions $Q --arm atlas
python $H/grade.py --questions $Q
python $H/summarize.py --questions $Q --spot-check
```

`summarize.py` writes the committed results to `results/<name>/`:

- **`runs.csv`** has one row per run: grade, cost, turns, token counts (input, cache creation, cache read and output, each reported separately), and counts of reads, greps, globs, skill calls and map calls.
- **`summary.json`** gives per-arm averages for the main question group and the control, plus the map-build cost and the number of questions needed to pay it back.

Neither file includes answers or transcripts. `--spot-check` writes a blinded sample of about 10% of runs to the work directory for your hand check.

## Recorded sets

- **`django`:** the Django 6.1.2 pilot, which serves as the memorized-repository control. It was recorded before tool-call capture and before the connection-question rule, so its runs have no tool counts and its main group is labelled `standard`.
