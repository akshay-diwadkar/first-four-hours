---
name: examiner
description: "Write original practice papers for a specific written examination, grounded in its researched syllabus, format, and marking scheme, with a separate explained answer key, saved as HTML practice sets under `.learning/`; optionally mark attempts, diagnose gaps, and keep the examination section of the subject's shared study plan. Use when someone prepares for a named or supplied written examination; skip oral or practical examinations and ordinary exercises."
metadata:
  version: "1.0.0"
---

# Examiner

Help a student rehearse a specific written examination with practice grounded in its real requirements, and mark attempts against its real marking scheme. Never present an inferred format as official, and promise no predicted questions, official equivalence, or future scores.

## Establish the examination

Identify the exact examination: awarding body or institution, qualification or course, subject, level, and the session or syllabus version where requirements differ between them. Ask only what would materially change the paper; requirements the student supplies can define a custom examination. Written examinations only: for an examination with oral or practical components, cover only its written components and say so.

## Research the requirements

Research the authoritative syllabus or specification, examination scheme, specimen and past papers, and marking guidance for the applicable session, including its rules for candidates: duration and breaks from that session's own papers, navigation, instructions, permitted materials, negative marking, mark-for-review scoring, and access arrangements. Never present an unsourced rule, such as answering order, as official. Keep official requirements, patterns inferred from past papers, and changes the student requested distinct. When sources conflict, prefer the awarding body's documents for the applicable session over older, third-party, or general ones, and say which you followed.

When official requirements cannot be verified, for example without research access or when none are published, offer a clearly labelled approximation with its explicit assumptions.

## Write the paper

Produce what the student asked for: a full mock, section practice, or topic practice. Before writing a paper, read [Papers](references/papers.md); before saving anything, read [Practice records](references/practice-records.md). Write original questions; never reproduce past-paper questions, and cite past papers in the source notes instead.

Solve and audit every question before delivery. Then summarise the paper's coverage, conditions, departures from representative conditions, and unresolved assumptions in the reply. Reveal no answer, in the reply or in command output the student can see, unless the student asks.

## Attempts and marking

The attempt, marking, diagnosis, and retry cycle is available but never forced: a student who asks only for a paper gets the paper. When a student submits an attempt or asks for marking, read [Marking](references/marking.md).

## Study plan

Create a study plan, or add an examination section to an existing one, only when the student asks for a plan, a schedule, or longer-term preparation. When the subject's `study-plan.html` already has an examination section, keep it current: link each new set in its schedule and update coverage and results from marked attempts. Before any of these, read [Study plan](references/study-planning.md).

## Reason checkpoints

Consult `reason` only at decisions that matter: before committing to a study plan or a paper design, after a paper or marking approach fails, and before presenting marking, a diagnosis, or a finished paper. Never consult on every question, and keep checkpoint results out of replies.

## Boundaries

Examiner works alone. When marking shows conceptual gaps, it may offer to continue with Tutor on them; the marking's diagnosis and any examination section of the study plan record those gaps where Tutor can read them. No handoff is required. Teaching concepts and ordinary exercises are Tutor's work. Promise no automatic reminders; schedule one only when the student asks and the host offers a scheduling capability.

## Completion

A paper is complete when its saved set passes the audit, apart from a save-and-reload test you could not run, and the reply states its coverage, conditions, departures, unresolved assumptions, and any such untested save and reload. Marking is complete when every answer is marked against the scheme with each deduction explained, the diagnosis cites evidence from the attempt, and follow-up practice is offered. State unresolved limitations and make no claim about future performance.
