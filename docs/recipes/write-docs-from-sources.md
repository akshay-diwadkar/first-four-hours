# Write documentation that matches its sources

Documentation that reads well but cannot be followed is the costly kind: a wrong flag in a runbook surfaces in the middle of an incident. Scribe writes from your sources, keeps commands, paths, values, warnings, and recovery steps exactly, and records a gap instead of filling it. An audit checks an existing document without changing it.

## Use this when

- A runbook, procedure, setup guide, notice, error message, or reference page must carry supplied facts exactly.
- You want an existing document checked against its sources.

## Use something else when

- You need a navigation map for agents: [Stop rediscovering an unfamiliar codebase](orient-in-a-codebase.md).
- You want to learn a subject: [Learn a subject and practise for its exam](learn-and-practise.md).

## Steps

1. Start Scribe naming the document and its sources. Writing needs your authority to create or revise it.
2. Answer only the publication or content-policy questions it asks.
3. Read `document.md` and the gaps it recorded. Each gap names its next owner, so close it in the sources, not by hand in the document.
4. After the sources change, ask Scribe to audit the document. An audit never modifies it.

## Example

For example (illustrative):

```text
/scribe : Write an on-call runbook for restarting the ingestion workers from deploy/ingest.yaml and scripts/restart-ingest.sh.
```

```text
/scribe : Audit docs/runbooks/restart-ingest.md against deploy/ingest.yaml and scripts/restart-ingest.sh.
```

The file names are placeholders for your own.

## You are done when

`document.md` is where you wanted it, its check passes, and no material reader job is left unsupported. A recorded gap means the document is not done yet: its next owner closes it, then write again. A passing check shows that the facts it binds match the sources, not that the sources are correct.

## If it goes wrong

- Scribe reports a reader job the sources cannot support: close the gap it names in the sources, then write again ([Scribe](../skills/scribe.md)).
- An audit reports findings: revising the document is a separate write that needs your authority ([Scribe](../skills/scribe.md)).
