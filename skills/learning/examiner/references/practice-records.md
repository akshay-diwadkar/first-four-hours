# Practice records

Read this before saving anything.

## Layout

Keep every file under `.learning/` in the folder where the student invoked Examiner, never under `.first-four-hours/`:

```text
.learning/<subject>/
  study-plan.html          the one shared study plan
  lessons/                 Tutor's lessons; Examiner may read them but never writes there
  exams/<exam>/<YYYY-MM-DD>-<practice-kind>-<NN>/
    paper.html  answer-key.html  marking-scheme.html  source-notes.html
    attempt-1.html  marking-1.html
```

- `<subject>` names the subject or learning goal, such as `chemistry`. `<exam>` names the examination by awarding body, qualification, and subject or code, such as `aqa-gcse-chemistry-8462`, or describes a custom examination. Use lowercase words joined by hyphens, from `a-z` and `0-9` only, and real names, never generic labels such as `exam` or `test`.
- `<YYYY-MM-DD>` is the date the set was created. `<practice-kind>` is `full-mock`, `section-practice`, `topic-practice`, or `supplied-paper`. `<NN>` is one more than the highest set number already in that `exams/<exam>/` folder, zero-padded to two digits.
- List `.learning/` and the subject's `exams/` before creating a folder. Reuse the existing subject or examination folder for the same goal or examination instead of creating a near-duplicate; when you cannot tell, ask.
- The files are ordinary files the student may commit. Never add them to `.gitignore`, `.git/info/exclude`, or any other ignore rule.

## Never overwrite

Never replace or delete an earlier paper, answer key, marking scheme, source notes, attempt, or marking. A corrected or revised paper, answer key, or marking scheme always revises the last set in its correction chain, as a new set of the same practice kind holding the paper, every corrected file (a change to anything the answer key repeats, such as a question, its supplied material, or an option or its label, also corrects the key), and an unchanged copy of each answer key or marking scheme it does not correct, whose source notes name the set it revises and what changed and keep every basis the earlier set cites that it does not correct; add `correction-<K>.html`, the next correction number, to the earlier set, stating the error and linking the new set, then re-mark every attempt marked against a corrected file as [Marking](marking.md) describes. A correction to a document the student supplied is Examiner's, labelled unofficial in the file and in the source notes. A retry is the next attempt number. If a chosen name already exists, take the next number.
