# Write documentation that matches its sources

The worst runbook reads beautifully and is wrong at step 4, at 3 a.m., for someone who has never seen the service.

Documentation that reads well but cannot be followed is the costly kind: a wrong flag in a runbook surfaces in the middle of an incident. `/scribe` writes from your sources, keeps commands, paths, values, warnings, and recovery steps exactly, and records a gap instead of filling it. An audit checks an existing document without changing it.

## Use this when

- A runbook, procedure, setup guide, notice, error message, or reference page must carry supplied facts exactly.
- You want an existing document checked against its sources.

## Use something else when

- You want to learn a subject: [Learn a subject and practise for its exam](learn-and-practise.md).

## Steps

1. Start `/scribe` naming the document and its sources. Writing needs your authority to create or revise it.
2. Answer only the publication or content-policy questions it asks.
3. Read the document and the gaps it recorded. Take each gap to the next owner it names; do not fill it by hand in the document.
4. Once that owner has closed the gap, ask `/scribe` to write again.

To check existing documents against their sources later, ask `/scribe` to audit them. An audit never modifies a document: it writes its report, one section per document, to `.first-four-hours/scribes/<slug>/scribe-audit.md`, and revising a document is a separate write.

## A worked scenario

*Illustrative: FreshCart is a made-up online grocery service, and this is not a recorded run.*

FreshCart's on-call engineers restart the job-queue workers from memory, and each of them does it slightly differently. Søren Lindqvist has done it at 3 a.m. often enough to know that "slightly differently" is how incidents get longer.

```text
/scribe : On-call engineers restart FreshCart's queue workers from memory, and no two do it the same way. Write an on-call runbook from deploy/worker.yaml and scripts/restart-workers.sh; where the sources go silent, say so instead of guessing.
```

`/scribe` asks one question the sources cannot answer: where the runbook will be published. It keeps every command, flag, and path exactly as the sources have them, and uses the `strict` profile, because the runbook holds commands and a recovery step.

One fact is missing. The restart script accepts a drain timeout, but neither source says what value is safe. `/scribe` does not guess one. It records the gap in step 3 and names who can close it: the operations lead, who owns `deploy/worker.yaml`. Until then, the runbook is not done.

Once the operations lead adds the value to `deploy/worker.yaml`, `/scribe` writes again and the gap closes. Months later, someone renames a flag in the script:

```text
/scribe : This runbook is months old. Audit docs/runbooks/restart-workers.md against deploy/worker.yaml and scripts/restart-workers.sh and tell me what would fail at 3 a.m.
```

The audit reports the mismatch and changes nothing. Revising the runbook is a separate write, with your authority.

Without the audit, the renamed flag would have been found the usual way: by whoever was on call, in the middle of an incident.

## You are done when

The document is where you wanted it, its check passes, and no material reader job is left unsupported. A recorded gap means the document is not done yet: its next owner closes it, then write again. A passing check shows that the facts it binds match the sources, not that the sources are correct.

## If it goes wrong

- `/scribe` reports a reader job the sources cannot support: take the gap to the next owner it names, and write again once that owner has closed it ([`/scribe`](../skills/scribe.md)).
- An audit reports findings: revising the document is a separate write that needs your authority ([`/scribe`](../skills/scribe.md)).
