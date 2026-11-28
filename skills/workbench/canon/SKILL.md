---
name: canon
description: "Define and check a product's canon: the one design direction the user approved, kept in a committed `.canon/` folder with its sample renders and the paths it governs. Use when writing, reading, or checking a canon file."
metadata:
  version: "0.1.0"
---

# Canon

A canon is the one design direction the user approved for a product, held across every surface: website, app, document, and slide deck. Nothing becomes canon without the user's explicit approval.

## Where a canon lives

Each canon is a committed folder `.canon/<slug>/` at the repository root, or, outside a repository, in the folder where `canon` is invoked. The folder holds one `canon.md` and the approved sample renders it links by relative path. `canon.md` alone is the authority: the file by itself is a usable canon, and its samples only illustrate it. Keep the folder outside `.first-four-hours/` and every ignore rule. A project may hold several canons; each artifact follows the one canon whose `Governs` list matches its path.

## Check a canon

Write or change `canon.md` only with the user's explicit approval of its content, in the shape [Canon file](references/canon-file.md) defines, then check it:

```bash
python /absolute/skill-root/scripts/cli.py --repo-root /absolute/project \
  --input canon=/absolute/project/.canon/<slug>/canon.md --format json check
```

A `complete` status means every agreed part is present and well formed. A `blocked` status names each missing or malformed part on its own line of the diagnostic message: repair those parts and check again. A canon that fails the check is not ready for any consumer.
