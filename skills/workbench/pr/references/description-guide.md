# Description guide

Write for a reviewer who reads the diff next. Carry what only the author knows; never narrate the diff ("changed X in file Y").

## Content

Include a part only when this change gives it something to say: a one-line fix may need two sentences. Use no fixed template and no empty headings.

- **Intent:** the problem solved and why; link the issue (`Closes #N`) or name the sealed Blueprint.
- **Decisions:** settled choices and the rejected alternatives a reviewer would otherwise reopen.
- **Reading guide:** where to start, which changes are core, and which are mechanical (renames, generated or synced copies, version bumps).
- **Risk and compatibility:** changed behavior, interfaces, data, or compatibility, and who it affects.
- **Verification:** what you ran and what you did not verify, and why.

## Diagrams

Add one Mermaid diagram when the change alters control or data flow, dependency direction, a state machine or lifecycle, or how components interact; show before and after when the structure itself changes. Give a trivial or linear change none. A diagram that restates the file list helps no reviewer.

Fence each diagram with the info string `mermaid` exactly. The check accepts flowchart, graph, sequenceDiagram, classDiagram, stateDiagram, stateDiagram-v2, erDiagram, journey, gantt, pie, gitGraph, mindmap, and timeline. In flowcharts it balances quotes, brackets, and `subgraph`/`end` lines; in sequence diagrams, block `end` lines. It checks shape, not a full render, so keep diagrams simple.

## Citations

Cite files as repo-relative paths with extensions in backticks or link targets, such as `src/app.py` or `src/app.py:42`, and symbols as `src/app.py::name`; in a diagram, put the path in a node label. A cited path must exist at HEAD or at the merge base and be a changed file, a file in the same directory as a changed file, or a file a changed file names literally. A cited symbol must appear in that file. Describe anything else without a path.

## Verification claims

Claim each run on its own line as ``- Ran: `<command>` ``, copying the `command` string that `record` returned, and add the result in words after it. A claim passes only when its latest recording exited 0 at the current HEAD on a clean worktree. Only `Ran:` lines are checked, so never claim a run anywhere else. State everything else on `Not verified:` lines in plain words.
