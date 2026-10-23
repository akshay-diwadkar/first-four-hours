---
name: scribe
description: Write source-grounded technical documentation such as runbooks, procedures, setup guides, notices, error messages, and reference pages, or audit an existing document read-only. Use when a document must faithfully carry supplied commands, paths, values, warnings, and recovery without invented facts.
metadata:
  version: "1.0.0"
---

# Scribe

## Purpose and authority

Turn supplied technical sources into a document its reader can execute and trace. Never invent source facts; preserve bound commands, paths, values, ordering, warnings, and recovery. Validation does not establish independent factual truth.

Write only with document-creation or revision authority; implicit invocation never grants write or remediation authority. Audit is a separate read-only operation. Audit must not modify the document, bundle, or bound sources.

Derive audience, reader job, and scope from the request and sources. Ask the user only for a material publication or content-policy choice the sources cannot settle; a missing source fact is an unresolved gap. Consult `reason` before committing to a document plan, after a failed direction, and before reporting completion. Final and stop reports trace `reason` checkpoints per its Checkpoint trace.

## Write and audit

`document.md` is the deliverable: keep it where the user wants it, outside `.first-four-hours/document-bundles/`. Both operations check it against a `document-bundle.json` bound per [Document Bundle](references/document-bundle.md) and [Source Grounding](references/source-grounding.md). Prepare the ignored support namespace, then write the bundle at the returned `result.bundle`:

```bash
python /absolute/skill-root/scripts/cli.py --repo-root /absolute/repo \
  --input slug=<document-slug> --format json prepare
```

To write, follow [Write](references/write.md); its language checks apply [MTE-1](references/mte-1.md), an original contract only inspired by ASD-STE100: never claim official ASD-STE100 compliance or imply that this skill contains its approved-word dictionary. To audit, follow [Audit](references/audit.md). Run the operation, `write` or `audit`:

```bash
python /absolute/skill-root/scripts/cli.py --repo-root /absolute/repo \
  --input slug=<document-slug> --input document=/absolute/document.md \
  --format json write
```

Neither command edits a file.

## Completion

Write completes only when `write` returns `status: complete`; repair `document.md` or the bundle as each diagnostic's `required_action` directs, then rerun. Audit completes only when `audit` returns `status: complete`; report its `document_sha256` and every finding. A passing result is not completion while a material reader job stays unsupported: report the exact gap and its next owner. End with one optional next step fitting this outcome: a fenced, self-contained prompt naming any repository, issue, PR, or artifact it needs, or say none is needed. Only a "yes" starts it, via any skill it names, but the user runs a `charter`, `diagnose`, `pr`, or `ticket` step as its `/<skill>` command.
