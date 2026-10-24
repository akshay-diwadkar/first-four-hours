---
name: assess
description: Assess a PR or code change against its issue/spec, acceptance criteria, repository rules, tests, and base behavior for correctness, code quality, maintainability, and proportionate security. Use for PR review, re-review, acceptance-criteria checks, or merge readiness.
metadata:
  version: "1.0.0"
---

# Assess

## Authority

Assess reconciles one exact target/base/head with the original user request, authoritative requirements, any available Blueprint, repository rules, tests, and base behavior. Snapshot every used external target, authority, evidence, proof, or diagnosis; Git/repository-local truth needs none. Unknown required external currentness means `blocked`.

The assessment is read-only: never repair, edit the target, merge, approve, or mutate GitHub. Construct owns implementation; Diagnose owns broader defect/risk investigation. `assessment.md` is a result, never approval, certification, or merge authority.

## Assessment

First read [assess guidance](references/assess-guidance.md). Establish exact target/base/head, current authority, base truth, and requested delta once. Derive requirements from authority and the change from base/head before reading PR prose, comments, audits, or prior reviews; those are hints that may add candidates, never clear one.

Delegate only per the [Bounded Delegation Protocol](references/delegation-protocol.md); a change you wrote or planned in this context first needs its fresh-context review.

## Author and seal

Copy the [minimal bundle template](templates/assessment-bundle.json) outside the skill and target repository and fill it per the guidance's bundle fields; it has no default verdict. Prepare first; sealing accepts only its ignored `.first-four-hours/assessments/<slug>/assessment.md`. The agent decides currentness, depth, compliance, severity, findings, limitations, Diagnose need, and result; scripts verify only shape, exact Git/snapshot identity and freshness, locators, safe output, and integrity.

```bash
python /absolute/skill-root/scripts/cli.py --repo-root /absolute/repo \
  --input slug=<slug> --format json prepare
python /absolute/skill-root/scripts/cli.py --repo-root /absolute/repo \
  --input bundle=/absolute/assessment-bundle.json \
  --input output=<prepared output_path> --format json run
```

Result precedence: `blocked` when unavailable or contradictory authority/evidence/proof prevents a trustworthy result; else `findings`, reporting every independently material defect discovered in the bounded assessment; else `clear`. `assessment.md` holds only the compact result.

## Complete

```bash
python /absolute/skill-root/scripts/cli.py --repo-root /absolute/repo \
  --input output=<prepared output_path> --format json check
```

Report the sealed result, path, and each finding's severity and defect as sealed, with no approval or readiness claim beyond it. Stop after one current `assessment.md` is sealed and checked. End with one optional next step fitting this outcome: a fenced, self-contained prompt naming any repository, issue, PR, or artifact it needs, or say none is needed. Only a "yes" starts it, via any skill it names, but the user runs a `charter`, `diagnose`, or `ticket` step as its `/<skill>` command.
