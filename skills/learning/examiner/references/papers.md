# Papers

Read this before writing a paper.

## Fidelity

Match the real examination wherever its requirements establish it: question types and command words, sections and any choice of questions, marks per question and in total, the rules for candidates, rubric, answer format such as lines, boxes, or option letters, permitted materials, and syllabus coverage. Section and topic practice keep the real question style and marks for that part. Name each deliberate departure from representative conditions, such as an easier warm-up, a harder stretch set, or a shorter time, in the paper's instructions and the source notes. Difficulty and time are judgment: label them as estimates.

## Set contents

- **Paper** (`paper.html`): a question paper a student can sit on screen or printed, with cover instructions naming it an original practice paper, not the awarding body's, with any approximation label, the rules for candidates, total marks, numbered questions with their marks, answer space where the real paper has it, and every diagram, data set, table, source extract, or formula sheet the examination supplies. It contains no answers or hints, not even hidden in markup, comments, or scripts. On screen, the student answers through labelled controls: radio buttons for one choice, checkboxes stating how many to choose, and a text field for each written answer or part; printed, the paper keeps the real paper's answer space. Copy in [the paper runtime](../assets/paper-runtime.html) as its opening comment directs; everything it adds is a practice feature, never an examination rule. Where an answer cannot be typed, such as a drawing, the instructions say how to submit it.
- **Answer key** (`answer-key.html`): for every question, repeated in full with the supplied material it needs and every option labelled as in the paper, the correct answer and why it is right and, where a tempting wrong answer exists, why it is wrong, so a student who chose it can correct their understanding from the key alone. For open questions, give a model answer and what earns each mark.
- **Marking scheme** (`marking-scheme.html`): only when the examination uses one, in its style: point-based marks, levels of response with descriptors, or both, with accepted alternatives.
- **Source notes** (`source-notes.html`): each requirement used with its source and session, labelled official, inferred from past papers, requested by the student, or good practice, not an examination rule; the approximation label and its assumptions when official requirements were not verified; deliberate departures; and unresolved limitations. No answers.

Make each file one self-contained HTML file a browser opens directly: CSS, SVG, and images inline, mathematics as MathML or plain text, and no network dependency for essential content. It prints cleanly, uses real text rather than text in images, gives every figure alt text or a caption, never relies on colour alone, and links the set's other files relatively.

## Solve and audit

Before delivery, solve every question from the paper alone, as a student would, and check that:

- each answer is correct and the question gives enough information to reach it;
- each question has one defensible reading, or the scheme accepts every defensible answer;
- each multiple-choice or multiple-response question has exactly as many correct options as its instructions state, and plausible wrong options;
- marks sum to the stated totals, and numbering and section order are continuous;
- coverage matches the request and the syllabus areas the source notes claim;
- your solution, the answer key, and the marking scheme agree, and every explanation supports the answer it explains;
- the key repeats each question and its options exactly as the paper labels them, and each answer control matches its question's instructions;
- the runtime appears byte for byte and its timing data matches the instructions; in a browser when available, reloading or loading a saved answer file restores every answer.

Fix every failure and audit the changed questions again. An audit cannot prove difficulty or timing; keep those as labelled estimates.
