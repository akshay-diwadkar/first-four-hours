# Learn a subject and practise for its exam

Studying for a written examination mixes two jobs, learning the ideas and practising the real paper, and a plan that keeps neither in view drifts or repeats what you already know. Tutor teaches and keeps the learning sequence. Examiner writes practice faithful to the real examination and marks your attempts. Both keep one shared study plan per subject. This works for any subject, technical or not.

## Use this when

- You are learning a subject over several sessions toward a goal or a date.
- You are preparing for a specific written examination.

## Use something else when

- You want one explanation: use [Tutor](../skills/tutor.md) alone, which saves nothing unless you ask.
- You only want a practice paper: use [Examiner](../skills/examiner.md) alone.
- The examination is oral or practical: it is out of scope.

## Steps

1. Start Tutor for continuing learning with your goal, your available time, and any deadline. It saves lesson records and `study-plan.html` under `.learning/<subject>/` in the folder where you start it.
2. Start Examiner naming the exact examination (awarding body, qualification, subject, level, session), and ask it to add the examination to your study plan.
3. Attempt the paper, then ask Examiner to mark it. It explains each deduction against the marking scheme and diagnoses only the gaps your attempt shows.
4. Take conceptual gaps back to Tutor, and repeat.

## A worked scenario

*Illustrative: a made-up student, not a recorded run.*

A student has an A-level Chemistry examination in June and five hours a week to prepare.

```text
/tutor : Teach me organic chemistry for my exam in June; I can study five hours a week and want a study plan.
```

Tutor asks one question that changes the teaching: which topics already feel solid? Then it teaches nucleophilic substitution, and instead of asking "does that make sense?" it asks the student to draw the mechanism for bromoethane with hydroxide ions. The first curly arrow starts on the carbon instead of on the hydroxide's lone pair, a common misconception, so Tutor goes back to what an arrow means: an electron pair moving. The second attempt is right. The lesson record keeps what was taught apart from what the student showed: the mechanism, drawn correctly on the second attempt, is demonstrated; when elimination competes with substitution is still unresolved and comes next.

```text
/examiner : Write a timed mock for AQA A-level Chemistry Paper 2 and add it to my study plan.
```

Examiner researches the current specification, specimen papers, and mark schemes, and keeps what is official apart from patterns it inferred from past papers. It writes original questions, solves and checks every one, and saves the set in its own folder:

```text
.learning/chemistry/exams/aqa-a-level-chemistry-paper-2/2027-03-14-full-mock-01/
```

The paper, the answer key, and the marking scheme are separate files, so the answers stay out of sight until the student wants them.

```text
/examiner : Mark my attempt at the paper in my latest practice set.
```

Examiner explains each lost mark against the scheme. In one mechanism the arrow to bromine starts on the bromine atom instead of on the carbon to bromine bond. In two questions the student chose substitution where the conditions favour elimination. That second gap is conceptual, so Examiner offers to hand it to Tutor, and updates the examination section of the shared study plan. The next lesson is already waiting in the plan.

## You are done when

There is no single end. Each session ends by separating what was taught from what you demonstrated, what remains unresolved, and the next step. Progress is shown only by your own answers and marked attempts, never by material delivered.

## If it goes wrong

- Examiner cannot verify the official requirements: it offers a clearly labelled approximation with its assumptions. Confirm them or supply the requirements ([Examiner](../skills/examiner.md)).
- You want reminders: Tutor promises none, so use a separate reminder tool ([Tutor](../skills/tutor.md)).
