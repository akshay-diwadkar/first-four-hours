# Structural Techniques

Load this during no-target discovery, or when gate 4's lenses leave materially distinct candidates that evidence cannot yet rank. Each question is a discriminator: it can show why one candidate resolves the pressure better, but a principle never qualifies a pressure on its own. Skip any question that does not bear on this pressure.

## Discriminators

- **Hidden decision (Parnas).** Name the design decision most likely to change, such as a provider, format, policy, or storage choice. Prefer the candidate in which one owner hides it, so changing it edits one place.
- **Depth (Ousterhout).** An abstraction earns its place when its interface is much simpler than what it hides. One that only forwards calls, or whose callers must still know what it wraps, adds a layer without hiding a decision; removing it can be the better candidate.
- **Leakage.** When one decision, such as a field layout, error taxonomy, or retry rule, is encoded in several modules, prefer the candidate that gives it one owner unless evidence shows the copies must diverge.
- **Connascence.** For each candidate, list what the two sides of its boundary must agree on, from weakest to strongest: a name, a type, the meaning of a value, argument position, a shared algorithm, execution order, timing, values that must change together, or the identity of one shared instance. Prefer the candidate that keeps strong agreements inside one owner and lets only weak ones cross; the same agreement costs more the more places share it and the farther apart they are.
- **Scattered functionality.** One responsibility split across modules that each hold part of it points to consolidation under one owner.
- **Unstable dependencies.** A module many others rely on should not depend on one that changes more often; prefer the candidate whose dependencies point toward the more stable side.

## Cheap evidence

These read-only probes find candidates and test direction claims; each result is a lead, never a verdict.

- **Change coupling.** `git log --name-only --format=%h -n <count> -- <scope>` lists the files each recent commit touched. Files that keep changing together without an import between them suggest hidden coupling or duplicated policy.
- **Churn hotspots.** `git log --name-only --format= -- <scope>` counted per file, set against file size, shows where frequent change meets large code: a place to look for recurring propagation burden, not its cause.
- **Import graph.** Search the scope's import statements to confirm which way a dependency points before relying on a direction claim.

When history is unavailable or shallow, skip the history probes and record that as an unknown; missing history is not evidence of low coupling. Read the source a lead names before relying on it: generated files, bulk renames, and formatting sweeps also change together. Cite what you confirm as `code` evidence. When the decision rests on the history or graph pattern itself, add a `runtime` Evidence Ledger record whose locator names the command and revision and whose claim states the pattern, and cite it in the section by its exact locator in backticks beside the `code` citations for the files it concerns. Never put ` | ` in a locator or claim, because it splits the record; describe a piped step in words.
