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

One practice set per folder, under `.learning/<subject>/exams/<exam>/<YYYY-MM-DD>-<practice-kind>-<NN>/` in the folder where you started Examiner: the paper, a separate answer key that explains every question, the marking scheme where the examination uses one, and source notes. Answers are not revealed in the reply unless you ask. Attempts and their marking are added to the same set and never overwrite earlier files. Each save also refreshes `.learning/<subject>/START_HERE.html`, the page to open first: in plain words it says what each kind of file in the folder is, where to pick up, and what to ask to continue. These are ordinary files you may commit.

On screen, a paper is a timed rehearsal. You press Start and a countdown runs from the time the examination allows; you cannot pause or extend it unless you told Examiner about an access arrangement such as extra time or supervised rest breaks. A question list shows which questions you have answered, not answered, or flagged for review, and a flagged question without an answer counts as not answered. Flagged questions are marked in orange. On a screen wide enough for a side menu, the clock, the question list, and the buttons to move between, flag, and submit questions sit in a menu on the left that stays in view while you scroll the paper. Your answers, flags, place, and remaining time stay on your device through a refresh or a reopened file; if your browser cannot keep them, the paper says so and you save your answers to a file instead. Where the examination has several papers with a break between them, the practice paper does too, and each paper ends when you submit it or its time runs out. When the last one ends, the practice paper locks and gives you an answer file to keep or send for marking; to sit it again, start a new attempt. These are practice features, not rules of the real examination: the paper's instructions state the examination's own rules, and the source notes say where each comes from. Nothing is sent anywhere.

Marking is optional. When you ask for it, Examiner says what it marked against and whether that is official: the official scheme or key, or an unofficial one, which is its own scheme or key, or a corrected one. It applies each rule, such as levels of response, consequential marking, and negative marking with that examination's own arithmetic, only where the scheme or the examination's own rules state it, explains each deduction against the scheme, and says how it reached the total. When your attempt records the time you used, it is reported as a diagnostic, never as part of your score. It diagnoses only gaps your attempt shows and offers follow-up practice. Examiner creates a study plan, or adds an examination section to an existing one, only when you ask for a plan, a schedule, or longer-term preparation. When the subject's shared `study-plan.html` already has an examination section, Examiner keeps it current: it links each new set and updates coverage and results from marked attempts.

## When it stops

Examiner promises no predicted questions, official equivalence, or future scores, and states the limitations it could not resolve.

## Why it's built this way

**The failure it prevents.** Generic practice questions rarely look like the real paper: the wrong question types, the wrong mark allocation, an invented format presented as official. A student who practises on them rehearses the wrong examination. Examiner grounds every paper in the examination's real syllabus, format, and marking scheme, and marks attempts against that scheme.

**What it refuses, and why.** It never presents an inferred format as official; when it cannot verify the official requirements, it offers a clearly labelled approximation with its assumptions. It never copies past papers, and it promises no predicted questions, official equivalence, or future scores. It never delivers a question it has not solved and checked. It does not push the attempt, mark, and retry cycle on someone who only wants a paper.

**Floor and ceiling.** A weaker agent must research the official sources, keep official requirements, inferred patterns, and your own changes apart, and audit every answer, mark total, and explanation before delivery. A stronger agent designs the paper and diagnoses gaps from the evidence in your answers. Its difficulty and timing estimates stay judgments, never claims a check has proved.

## Related skills

Examiner works alone. When marking shows conceptual gaps, it may offer to continue with [Tutor](tutor.md). See [How skills hand work to each other](../concepts/handoffs.md).

## Source

[Examiner's contract](https://github.com/akshay-diwadkar/first-four-hours/blob/main/skills/learning/examiner/SKILL.md)
