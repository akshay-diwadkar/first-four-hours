# Update

Read this when the branch already has an open pull request. `update` replaces that pull request's body with the checked draft and keeps its title unless the user confirms a new one. It refuses a closed or merged pull request, one opened from another repository, one whose head is not the commit you pushed, and one whose base is not the `base` you checked against.

1. Read the pull request with `gh pr view <branch> --repo <HOST/OWNER/REPO> --json number,state,url,title,body,baseRefName`, where `<branch>` is the branch's upstream name and `<HOST/OWNER/REPO>` comes from its remote's URL, for example `github.com/acme/widget`, with an SSH host replaced by the `hostname` that `ssh -G <host>` prints and a `*.github.com` host written `github.com`; continue only when `state` is `OPEN`. Use its `baseRefName` as the base, for example `origin/<baseRefName>`.
2. Ground, record, draft, and check as for a new pull request. Write the description the pull request needs now, not a log of changes since the last one: keep each part of the current body that still holds, including text someone else added, and drop what the new commits made untrue.
3. Show the user the current title, the complete checked draft, and what it drops from the current body, and ask whether to update the pull request, and to push the branch first when its upstream is missing or behind. Only an explicit yes authorizes it; silence or an earlier approval does not. After a yes, push if needed, then:

```bash
python <skill-root>/scripts/cli.py --repo-root <repo> --input draft=<draft.md> \
  --input runs=<runs.jsonl> --input base=<base> \
  --input confirm=<body_sha256 from check> --format json update
```

Add `--input title=<title>` only when the user confirmed a new title. Report the pull request URL, then end as `Confirm and open` directs.
