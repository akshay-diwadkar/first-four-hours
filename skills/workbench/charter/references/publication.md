# Publication

Read this only when the user asks to publish the charter or to revise a published one. Publication is optional and separate from agreement: it creates exactly one GitHub umbrella issue and never creates child issues, starts Ticket, or authorizes implementation.

Publication requires the user's explicit confirmation of the exact text. Each command takes the destination as `owner/repo` from the user; never infer it.

```bash
python <skill-root>/scripts/cli.py --repo-root <repo> --input slug=<slug> \
  --input repo=<owner/repo> --format json check
```

`check` writes nothing. It reports the issue `title` and `body` rendered from the local file, their `content_sha256`, the local `pointer`, and each `existing` umbrella issue for this slug with its own `title`, `body`, and `content_sha256`.

## Create

Show the user the destination, the title, and the complete body, and ask whether to publish. Only an explicit yes authorizes it; silence or an earlier approval does not. Then run `create`:

```bash
python <skill-root>/scripts/cli.py --repo-root <repo> --input slug=<slug> \
  --input repo=<owner/repo> --input confirm=<content_sha256 from check> --format json create
```

`create` publishes only the text whose hash the user confirmed. Before writing, it looks for an umbrella already carrying this slug's marker: it adopts one that holds the confirmed text and stops on one that differs, which only `revise` may replace. It reads the issue back and writes the local pointer only when the read-back matches. After any edit, check, show, and ask again.

## After publication

The issue owns the definition. The local file keeps its five sections as non-authoritative context, and its Authority records the issue and the published `content_sha256`. Before acting on the charter or revising it, run `check`: when the issue's `content_sha256` differs from `pointer.content_sha256`, the issue changed on GitHub; when `local_matches_pointer` is false, the local context differs from what was published.

## Revise

A revision follows [the contract's revision rule](charter-contract.md#revisions). When the issue changed on GitHub, its current text is the authority: show it to the user and bring the local sections to it before drafting. Edit the local sections to the agreed revision, then check, show the complete result, and ask. After an explicit yes:

```bash
python <skill-root>/scripts/cli.py --repo-root <repo> --input slug=<slug> \
  --input repo=<owner/repo> --input confirm=<content_sha256 from check> --format json revise
```

`revise` updates the pointed issue only while its current text still matches the pointer, reads it back, and only then updates the pointer. To replace issue text that no longer matches, first show the user that issue's `title` and `body` from `check`; only after their decision to replace it, add `--input base=<that issue's content_sha256>`. Without a pointer, `revise` replaces the one umbrella carrying this slug's marker, and always requires `base`.

## Stops

A failed or unverified publication leaves the local file as the authority it was. Never retry a failed write blindly.

- `charter.unconfirmed`: the text changed since the user confirmed it. Check, show, and ask again.
- `charter.publish_uncertain`: a write failed or its result was lost, so an issue may have changed. Rerun `check`, then the same command; it adopts an issue that already holds the confirmed text.
- `charter.readback_mismatch`: GitHub holds other text than was sent, and the pointer was not written. Show the user the issue, then revise with `base` after their decision.
- `charter.pointer_write_failed`: the issue is verified but the local pointer was not written. Repair the file problem and rerun the same command.
- `charter.already_published` or `charter.not_published`: use `revise` or `create` instead.
- `charter.umbrella_differs` or `charter.issue_changed`: the issue holds text the user has not confirmed. Show it; bring the local file to it, or run `revise` with `base` after their decision to replace it.
- `charter.umbrella_ambiguous`: several issues carry this slug's marker. Ask the user which is the umbrella and to remove the marker from the others.
- `charter.umbrella_closed`: ask the user to reopen it, or define a different project under a new slug.
- `charter.issue_missing`: the pointed issue is gone. Ask the user; restoring local authority means restoring the unpublished Authority lines in [README](../README.md).
- `charter.destination_mismatch`: pass the pointer's repository.
- `charter.github_failed`: a read failed and nothing was written. Repair `gh` or the network and rerun.
