---
name: pr
description: Write a grounded, reviewer-oriented pull request description for the current branch and open or update its PR only after explicit user confirmation. Use when a finished branch needs a PR or a refreshed description; never merges.
metadata:
  version: "1.0.0"
---

# PR

Write what a reviewer needs and the diff cannot show, check it mechanically, and open the PR only after the user confirms the exact text. Never merge, approve, or edit the branch's code.

## Ground

1. Fix the base ref (for example `origin/main`) and read the whole `git diff <base>...HEAD`. If `gh pr view <branch> --json state` shows `OPEN`, read [Update](references/update.md) first.
2. Find the authority: the linked issue (`gh issue view <n>`) or a sealed `.first-four-hours/blueprints/*/blueprint.md`. Link or quote its intent, decisions, and acceptance criteria; never re-author them as a second source of truth. With neither, say so and take intent from the user.
3. From a clean worktree at the commit you will push, run each verification you will claim through `record`, one `arg` per argv element:

```bash
python <skill-root>/scripts/cli.py --repo-root <repo> --input runs=<runs.jsonl> \
  --input arg=<argv0> --input arg=<argv1> --format json record
```

Its result gives the real `exit_code` and the `command` string to cite.

## Draft

Read [Description guide](references/description-guide.md), then write the draft outside the repository, next to `<runs.jsonl>`.

## Check

```bash
python <skill-root>/scripts/cli.py --repo-root <repo> --input draft=<draft.md> \
  --input runs=<runs.jsonl> --input base=<base> --format json check
```

Repair each diagnostic in the draft, or record the missing run, and rerun until it passes. The script checks only grounding, recorded runs, and Mermaid shape, never prose quality; the content and every diagram are your judgment.

## Confirm and open

Show the user the title and the complete checked draft, and ask whether to open the PR, and to push the branch first when its upstream is missing or behind. Only an explicit yes authorizes it; silence or an earlier approval does not. After a yes, push if needed, then:

```bash
python <skill-root>/scripts/cli.py --repo-root <repo> --input draft=<draft.md> \
  --input runs=<runs.jsonl> --input base=<base> --input title=<title> \
  --input confirm=<body_sha256 from check> --format json publish
```

`confirm` binds the exact text the user saw; after any edit, check, show, and ask again. Report the PR URL. End with one optional next step fitting this outcome: a fenced, self-contained prompt naming any repository, issue, PR, or artifact it needs, or say none is needed. Only a "yes" starts it, via any skill it names, but the user runs a `charter`, `diagnose`, or `ticket` step as its `/<skill>` command. Never merge the PR.
