# Observed decisions

Read this when a decision's correctness shows only in the built result, such as a layout, an interaction, user-facing copy, an API's ergonomics, a performance tune, or a prompt's effect; wording whose bytes the request settles stays declared text. Settle each such decision from the first of these that exists, never leaving it to the executor:

1. A source the user supplies, such as a mockup, design system, or reference: cite a repository file as `**Source:**`, else record the source in the request, and decide that the build matches it.
2. An earlier slice's observed result: the next plan, prepared afresh for the same request, records what was observed in Facts and the owner's verdict in the request.
3. A user question, asked once the current tree or a built slice gives the user something to look at.

With none of these, plan only the slice that produces the observation, with judged acceptance, once the request records the user's acceptance that this plan builds only that slice. Decide the slice's own choices as labelled provisional defaults, which the owner's verdict replaces in the next plan.

## Judged acceptance

Keep every check a Run can decide mechanical; judgment never replaces one. For the rest, a Run writes the observable, such as a screenshot, rendered page, or benchmark report, to a path that is not plan-bound; confirm with `git check-ignore` that it and every other path the tool writes are ignored, or have an earlier step add the ignore rule. Its `Expect:` proves only that the observable exists. The clause's Trace item cites that Run and adds `Owner gate:` naming who judges which artifact against what, as the request records; the gate carries acceptance. The owner judges after Construct, with a suitable design skill if one is installed, otherwise against the supplied design source or the request.

## Rendered output

For a user interface, the desk check's Design input states and exit paths include each supported viewport, empty and overflowing content, keyboard and focus order, and loading and error states.
