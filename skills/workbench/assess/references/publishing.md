# Publishing findings

Read this when `check` passed a `findings` assessment whose `target` is a pull request's URL. Only the agent talking with the user offers to post; a delegated owner returns without offering.

Offer once to post the findings there as one comment. Preview it; this posts nothing:

```bash
python /absolute/skill-root/scripts/cli.py --repo-root /absolute/repo \
  --input output=<prepared output_path> --format json publish
```

It rechecks the assessment, renders the comment from the sealed findings alone, and refuses unless the pull request's head is still the assessed head. Show the user the returned `body` whole and unchanged and ask whether to post it. Only an explicit yes to that exact text authorizes posting; silence or an earlier approval does not. After a yes, rerun adding `--input confirm=<body_sha256>`. A no posts nothing.

Report the returned `comment_url` or refusal; never post by other means. After a moved head, assess the current head before offering again. After a failed post, look at the pull request first: the comment may exist.
