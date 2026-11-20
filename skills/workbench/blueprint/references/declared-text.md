# Declared text

Declared text is earned only for textual data whose bytes are the decision: deliverable wording, configuration, a format, pattern, or diagnostic string, a pure data file, a delicate anchored edit, or a mechanical rename; on an executable file use only **Edit:** lines or a **Replace:** of at most two lines. It proves bytes, never semantic completeness, so behavior steps stay specified. Otherwise state the wording's requirements and let Construct write it. Quote the least that identifies the change: an **Edit:** when under about a third of a span changes, else a **Replace:** with anchors; never quote unchanged text twice.

Write new step proof in prose: location and owner, then each case's inputs, observable result, and the compliant-but-wrong implementation it rejects, placed at the cheapest boundary exposing it, with no mock standing in for the operation whose result it claims. `**Frozen:**` holds only test data whose exact bytes discriminate; the `**Proof run:**` runs the proof. A new regression's `Red:` names the defect current source shows, not how it surfaces; Construct judges the observed failure. Shape the Proof run so its red is observable under the repository's runner traps. When the host cannot produce the red, record why and where it can in Facts, keep the regression as passing proof, and start its condition with `Owner gate:` naming who confirms it there.

Plan a break-the-code check only when ordinary proof could pass a named wrong outcome: retained proof, placed per the repository's test rules, run after its target exists and never as a `Red:`, passing unmutated and failing after a named mutation of Exact or Frozen bytes on a temporary or in-memory copy, never the worktree.

## Grammar

`check` enforces this grammar and names each fix. Each label names one of the instruction's Locations:

- `**Exact:** `path`` (or `**Frozen:**`): a `new` file's whole content, as one closed, unindented fenced block.
- `**Edit:** `path`` (or `**Frozen edit:**`): an `existing` file; one or more following lines `- `old` → `new``, each replacing the one occurrence of `old` with `new`, both on one line and free of backticks.
- `**Replace:** `path` from `start` to `end`` (or `to end`, or `section `## Heading``; or `**Frozen replace:**`): an `existing` file; one fenced block replacing the whole lines from the one line beginning with `start` up to the first later line beginning with `end`, to the end of the file, or from that exact heading line to the next heading of the same or a higher level; the end-anchor line or next heading is kept, not replaced.

Block text is the LF lines between fences, CRLF read as LF; an instruction/Location/State sequence, or a same-character fence at least as long as the outer one, inside it is ambiguous. `**With:**` is retired. One `**Proof run:** `command`` follows the Run rules, then optional `Timeout:` and `Red:` once each and a required `Expect:`. In Implementation and Verification, a line starting `Exact`, `Frozen`, `Edit`, `Replace`, `With`, `Proof`, `Red`, or `Incomplete` and a colon is reserved: spell it as above or fence it.

`check` applies every block in step order to the bound bytes and refuses `old` text or anchors that do not resolve exactly once, a block an earlier step breaks, and new text that would not be unique; Construct applies each block and reproves it after every later instruction, so a specified edit must leave each block's text intact.
