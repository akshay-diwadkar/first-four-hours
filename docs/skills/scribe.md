# Scribe

Scribe writes technical documentation that a reader can follow and trace back to its sources, such as runbooks, procedures, setup guides, notices, error messages, and reference pages. It can also audit an existing document without changing it. It belongs to the Sensemaking domain.

## When to use it

- A document must carry supplied commands, paths, values, warnings, and recovery steps exactly, without invented facts.
- You want an existing document checked against its sources.

## When to use something else

- To keep a navigation map for agents, use [Atlas](atlas.md).
- To learn a subject, use [Tutor](tutor.md).

## How to start it

Start it yourself with `/scribe`, or the agent may start it when your request matches. Writing needs your authority to create or revise the document; when the agent starts Scribe on its own, that grants no permission to write or fix anything. For example (illustrative):

```text
/scribe : Write a deployment runbook from our docker-compose file and deploy scripts.
```

## What happens

Scribe works out the audience and the reader's job from your request and sources, and asks you only about publication or content-policy choices the sources cannot settle. A fact missing from the sources stays a recorded gap; it is never filled in. Its language checks apply MTE-1, an original controlled-language contract inspired by ASD-STE100; Scribe claims no official ASD-STE100 compliance. The `strict` profile is for hazardous procedures, commands, warnings, notices, and recovery; everything else uses `standard`. Scribe consults [Reason](reason.md) at its judgment points.

## What you get

- Write: `document.md`, the deliverable, kept where you want it and committable. Its support bundle, `document-bundle.json`, lives in the ignored folder `.first-four-hours/document-bundles/<slug>/`.
- Audit: the document's hash and every finding. An audit never modifies the document, its bundle, or its sources.

A passing check shows only that the facts the bundle binds, such as commands, paths, values, warnings, and recovery steps, still match their sources and the document. It does not prove that the sources are correct or that they support every claim; that judgment stays with the agent.

## When it stops

Scribe reports a reader job the sources cannot support as an exact gap with its next owner, instead of calling the document complete.

## Why it's built this way

**The failure it prevents.** Documentation that reads well but cannot be carried out is the real failure: a wrong flag, a missing step, or an invented value surfaces in the middle of an incident. Scribe makes supplied technical information explicit, executable, and traceable to its sources.

**What it refuses, and why.** It never invents a source fact; a fact the sources lack stays a recorded gap with the next owner named. An audit never fixes what it finds, because a review that quietly becomes a rewrite hides what was wrong. Starting it automatically never grants permission to write. It claims no official ASD-STE100 compliance: MTE-1 is its own contract, only inspired by that standard. A clean check means the document is grounded and consistent, not that its sources are correct.

**Floor and ceiling.** A weaker agent keeps every bound command, path, value, warning, and recovery step exactly as supplied, and a mechanical check confirms it. A stronger agent shapes the document around the reader's job, and uses the `strict` profile only where an error would be costly.

## Related skills

See [How skills hand work to each other](../concepts/handoffs.md).

## Source

[Scribe's contract](../../skills/sensemaking/scribe/SKILL.md)
