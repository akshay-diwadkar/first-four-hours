# Examiner

Examiner writes original practice papers for a specific written examination, grounded in its researched syllabus, format, and marking scheme, and can mark your attempts against that scheme. It belongs to the Learning domain.

## When to use it

- You are preparing for a named written examination, or one whose requirements you supply.
- You want a full mock, section practice, or topic practice, optionally marked.

## When to use something else

- To learn the concepts, or for ordinary exercises, use [Tutor](tutor.md).
- Oral and practical examinations are out of scope. For an examination with such parts, Examiner covers only the written ones and says so.

## How to start it

Start it yourself with `/examiner`, or the agent may start it when your request matches. Name the examination as exactly as you can: awarding body, qualification, subject, level, and session. For example (illustrative):

```text
/examiner : Write a full mock for AQA GCSE Chemistry Paper 1 for the current specification.
```

## What happens

Examiner researches the official syllabus, examination scheme, specimen and past papers, and marking guidance, and keeps official requirements, patterns inferred from past papers, and your own changes distinct. When official requirements cannot be verified, it offers a clearly labelled approximation with its assumptions; an inferred format is never presented as official. It writes original questions, never copies past papers, and solves and audits every question before delivery. It consults [Reason](reason.md) only at decisions that matter.

## What you get

One practice set per folder, under `.learning/<subject>/exams/<exam>/<YYYY-MM-DD>-<practice-kind>-<NN>/` in the folder where you started Examiner: the paper, a separate answer key that explains every question, the marking scheme where the examination uses one, and source notes. Answers are not revealed in the reply unless you ask. Attempts and their marking are added to the same set and never overwrite earlier files. These are ordinary files you may commit.

Marking is optional. When you ask for it, Examiner explains each deduction against the scheme, diagnoses only gaps your attempt shows, and offers follow-up practice. When you ask for a plan, it keeps the examination section of the subject's shared `study-plan.html`.

## When it stops

Examiner promises no predicted questions, official equivalence, or future scores, and states the limitations it could not resolve.

## Related skills

Examiner works alone. When marking shows conceptual gaps, it may offer to continue with [Tutor](tutor.md). See [How skills hand work to each other](../concepts/handoffs.md).

## Source

[Examiner's contract](../../skills/learning/examiner/SKILL.md)
