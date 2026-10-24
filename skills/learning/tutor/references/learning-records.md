# Learning records

Read this on entering continuing learning, or when the learner asks to keep an explanation.

## Layout

Keep every record under `.learning/` in the folder where the learner invoked Tutor, never under `.first-four-hours/`:

```text
.learning/<subject>/
  START_HERE.html            the page to open first
  study-plan.html            the one shared study plan
  lessons/<NN>-<topic>.html  one file per lesson or kept explanation
  exams/<exam>/              examination practice; Tutor may read it but never creates it
```

- `<subject>` names one subject or learning goal and `<topic>` names the lesson's topic. Use lowercase words joined by hyphens, from `a-z` and `0-9` only, and real names such as `organic-chemistry` or `03-sn1-versus-sn2.html`, never generic labels such as `lesson` or `notes`.
- List `.learning/` before creating a subject folder. Reuse the existing folder for the same goal instead of creating a near-duplicate such as `learning-spanish` beside `spanish`; when you cannot tell whether a folder is the same goal, ask.
- `<NN>` is the next number in learning order, zero-padded to two digits (`01`, `02`): one more than the highest number already in `lessons/`. A kept one-off explanation takes the next number in its subject.
- The records are ordinary files the learner may commit. Never add them to `.gitignore`, `.git/info/exclude`, or any other ignore rule.

## Start here page

On every save, create or refresh in place the subject's self-contained `START_HERE.html`; the never-overwrite and next-number rules do not apply to it. In plain words, it says what each kind of file there is, including any Examiner `exams/`; that any answer key is for after an attempt; which to open first; the next step, linked to the study plan when one exists, else to its record; and what to ask Tutor or Examiner to continue. It copies no list of lessons or sets, progress, coverage, or results; keep what it says about files Tutor does not write.

## Never overwrite

Never replace or delete an earlier lesson, and never rewrite its teaching material. Re-teaching a topic, revising an explanation, or retrying gets a new lesson with the next number that links back to the earlier one. The one in-place change to an earlier lesson is updating its learning record from later practice. If a chosen file name already exists, take the next number.

## Lesson file

Each lesson is one self-contained HTML file a browser opens directly: CSS, JavaScript, SVG, and images inline (images as data URIs) where practical, with no build step and no network dependency for essential content. Link outside sources as citations, never as required assets. A lesson holds:

1. **Teaching material:** the explanation, examples, visuals, and exercises, readable later without the conversation, with citations for researched claims.
2. **Learning record:** a compact `<section id="learning-record">` with:
   - **Demonstrated:** what the learner showed they can do, each with brief evidence meeting the Check understanding rules in [Choosing how to teach](teaching-methods.md), and the representation, such as a worked example or comparison, that produced each piece;
   - **Unresolved:** difficulties and misconceptions still open, including steps passed with help, and, listed apart as not converged, anything shown unaided that does not yet meet those rules, with its evidence and representation;
   - **Next:** the next step;
   - **Updated:** the date of the last change, as `YYYY-MM-DD`.

Record only evidence the learner produced. Material taught without a check is "taught, not yet checked", never demonstrated. A kept explanation with no practice says so and omits Demonstrated.

Make lessons easy to revisit: clear headings, a readable line length, legible light and dark colour schemes and print, sufficient contrast, real text instead of text in images, alt text or a caption for every visual, and relative links to the study plan and related lessons.

## Recovering progress

At the start of a continuing session, read the subject's `study-plan.html` and the learning records of its recent lessons. They are the only progress state; write no separate Markdown or notes file that repeats them. When practice shows new understanding or a new difficulty, add it to the affected lesson's record, move it between Demonstrated and Unresolved in every other record that lists it, and update the study plan.
