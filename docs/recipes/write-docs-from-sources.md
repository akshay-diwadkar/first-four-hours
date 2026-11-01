# Write documentation that matches its sources

Documentation that reads well but cannot be followed is the costly kind: a wrong flag in a runbook surfaces in the middle of an incident. Scribe writes from your sources, keeps commands, paths, values, warnings, and recovery steps exactly, and records a gap instead of filling it. An audit checks an existing document without changing it.

## Use this when

- A runbook, procedure, setup guide, notice, error message, or reference page must carry supplied facts exactly.
- You want an existing document checked against its sources.

## Use something else when

- You want to learn a subject: [Learn a subject and practise for its exam](learn-and-practise.md).

## Steps

1. Start Scribe naming the document and its sources. Writing needs your authority to create or revise it.
2. Answer only the publication or content-policy questions it asks.
3. Read the document and the gaps it recorded. Take each gap to the next owner it names; do not fill it by hand in the document.
4. Once that owner has closed the gap, ask Scribe to write again.

To check existing documents against their sources later, ask Scribe to audit them. An audit never modifies a document: it writes its report, one section per document, to `.first-four-hours/scribes/<slug>/scribe-audit.md`, and revising a document is a separate write.

## A worked scenario

*Illustrative: Larder is a made-up project, and this is not a recorded run.*

Larder's on-call engineers restart the job-queue workers from memory, and each of them does it slightly differently.

```text
/scribe : Write an on-call runbook for restarting Larder's queue workers from deploy/worker.yaml and scripts/restart-workers.sh.
```

Scribe asks one question the sources cannot answer: where the runbook will be published. It keeps every command, flag, and path exactly as the sources have them, and uses the `strict` profile, because the runbook holds commands and a recovery step.

One fact is missing. The restart script accepts a drain timeout, but neither source says what value is safe. Scribe does not guess one. It records the gap in step 3 and names who can close it: the operations lead, who owns `deploy/worker.yaml`. Until then, the runbook is not done.

Once the operations lead adds the value to `deploy/worker.yaml`, Scribe writes again and the gap closes. Months later, someone renames a flag in the script:

```text
/scribe : Audit docs/runbooks/restart-workers.md against deploy/worker.yaml and scripts/restart-workers.sh.
```

The audit reports the mismatch and changes nothing. Revising the runbook is a separate write, with your authority.

## You are done when

The document is where you wanted it, its check passes, and no material reader job is left unsupported. A recorded gap means the document is not done yet: its next owner closes it, then write again. A passing check shows that the facts it binds match the sources, not that the sources are correct.

## If it goes wrong

- Scribe reports a reader job the sources cannot support: take the gap to the next owner it names, and write again once that owner has closed it ([Scribe](../skills/scribe.md)).
- An audit reports findings: revising the document is a separate write that needs your authority ([Scribe](../skills/scribe.md)).
