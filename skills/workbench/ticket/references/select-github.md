# GitHub select

Read this reference only when select runs with `"backend": "github"`. In `scope_inputs.json`, bind `repository` as `owner/repo` and give `ticket` or `epic` its issue `number` and `url`. GitHub access is CLI-only; install `gh` and run `gh auth login` when preflight fails.

Direct ticket: fetch the named issue plus its eligibility chain:

```bash
python /absolute/skill-root/scripts/fetch_github_issues.py fetch \
  --github-repo owner/repo --issue-number 7 --mode single \
  --repo-root /absolute/repo --output /absolute/run/snapshot.json
```

Epic: fetch the named epic/umbrella graph:

```bash
python /absolute/skill-root/scripts/fetch_github_issues.py fetch \
  --github-repo owner/repo --epic-issue-number 123 --mode epic \
  --repo-root /absolute/repo --output /absolute/run/snapshot.json
```

Revalidate the chosen work and the graph facts that made it eligible:

```bash
python /absolute/skill-root/scripts/fetch_github_issues.py verify \
  --snapshot /absolute/run/snapshot.json \
  --scope-inputs /absolute/scope-inputs.json \
  --selected-issue-number 209
```

On success the verifier returns `next_action: narrow_selected`. Terminal epic checks without a chosen child omit `--selected-issue-number`.

Verification is fail-closed: unavailable issue, relationship, comment, native membership, or linked-PR readback is not equivalent to an empty response. A previously recorded, immaterial missing sibling may remain `unknown` when the same absence is re-observed and no selected or prerequisite fact depends on it; new or decision-changing evidence remains stale and must be reacquired.

The default `auto` fetch reads bounded comments for every fetched issue that reports comments. Use `none` only when comment evidence is intentionally out of scope, and use `all` when the bounded default is insufficient for a material relationship. If deliberately omitted or exhausted comments affect eligibility, preserve the evidence gap as non-plan-ready and reacquire with an appropriate policy or budget.
