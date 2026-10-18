# MTE-1 Controlled Technical English

MTE-1 is an original controlled-English specification inspired by the goals of ASD-STE100. It is not ASD-STE100, does not certify ASD-STE100 compliance, and does not include the ASD-STE100 approved-word dictionary.

## Contract

- Give one term one meaning. Define a preferred term and reject its listed variants.
- Put one action in each sentence. Do not hide sequences behind conjunctions, commas, semicolons, or “then”.
- Use active voice when an actor exists.
- Put a condition before the action that it controls.
- Put a warning before a hazardous action.
- Replace vague references with explicit nouns.
- Replace phrasal verbs with precise single verbs.
- Replace chains of nominalizations with direct verbs.
- Define an abbreviation before its first use.

## Profiles

`strict` makes all MTE-1 findings blocking. Procedural sentences contain at most 20 words. Descriptive sentences contain at most 25 words.

`standard` keeps action, terminology, reference, condition, warning, and abbreviation findings blocking. It reports passive voice, phrasal verbs, and nominalization chains as warnings. It does not enforce sentence length.

## Deterministic Boundary

The parser uses regular expressions and supplied glossary data. A rule finding is a reproducible pattern match, not a probability. The parser can miss meanings that are not represented by text patterns. Review supplied source material when a rule result conflicts with technical intent.
