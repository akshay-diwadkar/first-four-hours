# Charter

`charter` keeps one living definition per project in the ignored `.first-four-hours/charters/<slug>/charter.md`. [SKILL.md](SKILL.md) owns the conversation; this file owns the workspace command and the file's shape. [Publication](references/publication.md) owns `check`, `create`, and `revise`.

## Prepare

```bash
python <skill-root>/scripts/cli.py --repo-root <repo> --input slug=<slug> --format json prepare
```

`prepare` lowercases a safe slug and turns its spaces into hyphens. It refuses a slug that contains anything other than ASCII letters, digits, spaces, and hyphens (so `/`, `\`, `.`, and `_` too), names a reserved device such as `con`, has no letter or digit, or exceeds 64 characters (`charter.slug_unsafe`); ask the user for another slug instead of rewriting it. In a Git worktree it refuses a namespace Git already tracks (`charter.namespace_tracked`), adds `/.first-four-hours/charters/` to the worktree-local exclude file that `git rev-parse --git-path info/exclude` names, and verifies the rule with `git check-ignore`. It refuses a link or non-directory on the path (`charter.workspace_unsafe`). It never replaces an existing `charter.md`: `result.status` is `created` for a new scaffold and `resumed` for an existing file, with `result.path`, `result.slug`, and `result.git_ignored` (false outside Git).

## Shape

```markdown
# Charter — <project name>

## Purpose
## Agreed
## Unsettled
## Revisions
## Authority
```

The five `##` headings appear once each, in this order, and no other `##` heading appears; use `###` inside a section. The `#` heading is the published issue's title. Before publication, Authority holds:

```markdown
- Owner: this file owns this definition until a publication is verified.
- State: settling
```

`State` is `settling` or `ready`. An optional `- Not live: <reason>` line marks a charter that is no longer the project's live definition. After a verified publication the script rewrites Authority as:

```markdown
- Owner: GitHub issue <url> owns this definition. The sections above are non-authoritative context; read the issue before acting on them.
- Issue: <owner/repo>#<number>
- Published content_sha256: <sha256>
- State: <state>
```

with any `Not live` line kept just before `State`. Never author the `Issue` or `Published content_sha256` lines.

The issue body is the text from `## Purpose` up to `## Authority`, then a generated Authority section that names the issue as the owner, repeats any `Not live` line and the `State` line, and ends with the marker `<!-- first-four-hours-charter: <slug> -->`. `content_sha256` is the SHA-256 of the compact UTF-8 JSON array `[title, body]`, with the title trimmed and the body's line endings normalized to LF and trailing whitespace removed. An issue's current text is hashed the same way, so equal hashes mean GitHub holds exactly the rendered text.

Publication refuses a missing charter (`charter.missing`), a file that breaks this shape (`charter.shape`), one without exactly one valid `State` line (`charter.state_missing`), one with only one of the two pointer lines (`charter.pointer_malformed`), a title over 256 characters or a body over 65536 (`charter.too_long`), and a `repo` that is not `owner/repo` (`charter.repo_invalid`). Repair the file or input and rerun.
