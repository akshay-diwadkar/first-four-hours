# Canon

`/canon` keeps one deliberate design direction per product, the one you approved, in a committed `canon.md` that every later surface follows: website, app, document, and slide deck. This version defines the canon file, checks that a canon holds every part, and keeps a catalogue of generic design and copy patterns, called slop, that grows from your own slop calls; choosing a direction and judging surfaces for drift come later. It belongs to the Workbench domain.

## When to use it

Use it when you write or review a product's `canon.md` and want to know it holds every agreed part. To plan or build interface code, use [`/blueprint`](blueprint.md) and [`/construct`](construct.md); in this version neither reads a canon.

## What you get

A committed folder `.canon/<slug>/` at your repository root holding `canon.md` and the sample renders it links. `canon.md` states the product's character and voice, its translation into each medium, the concrete system, the viewing contexts it supports, its handling of empty, error, loading, and dense states, what it bans, its samples, the paths it governs, and a change log, with a reason on every rule. The check reports `complete`, or names each missing or malformed part. When you call slop the catalogue missed, canon adds it to a committed `.canon/slop-additions.md` with your words as the reason; the catalogue shipped with the skill grows only through a reviewed change to First Four Hours.

## Why it's built this way

Model-made design swings between runs and between surfaces of one product, and the model cannot reliably see its own drift. A written canon held to one shape gives every later session the same direction to follow. Nothing becomes canon without your explicit approval, and the written `canon.md`, not a sample, is the authority.

## Source

[`/canon`'s contract](https://github.com/akshay-diwadkar/first-four-hours/blob/main/skills/workbench/canon/SKILL.md)
