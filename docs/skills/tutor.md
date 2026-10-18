# Tutor

Tutor teaches any subject, technical or not. It finds your real goal and starting point, chooses explanations and examples that fit, and checks understanding instead of assuming it. It belongs to the Learning domain.

## When to use it

Choose by what you want; Tutor can switch when the session shows a better fit:

- **Explanation:** one self-contained answer, complete without exercises.
- **Tutoring:** you apply the idea or explain it in your own words, and Tutor responds to the misconceptions your answers show. Ordinary exercises belong here.
- **Continuing learning:** a series, a study plan, or progress kept across sessions.

## When to use something else

- For practice papers that follow a specific written examination's real format and marking, use [Examiner](examiner.md).
- Explanations that are only incidental to other work do not need Tutor.

## How to start it

Start it yourself with `/tutor`, or the agent may start it when your request matches. For example (illustrative):

```text
/tutor : Teach me how Git rebase differs from merge; I already use branches daily.
```

## What happens

Tutor starts once the goal is clear enough and asks only questions that would change the teaching. It researches in proportion to how current, contested, or high-stakes the material is, and states uncertainty instead of inventing detail. It uses diagrams or animations only when they explain better than words. It consults [Reason](reason.md) only at decisions that matter, never on every turn.

## What you get

An explanation or a tutoring session writes nothing unless you ask to keep something. Continuing learning saves files under `.learning/<subject>/` in the folder where you started Tutor:

- `lessons/<NN>-<topic>.html`: one self-contained HTML record per lesson, numbered in learning order, holding the teaching material and what you demonstrated;
- `study-plan.html`: the one study plan for the subject, shared with Examiner.

These are ordinary files you may commit. Delivered teaching is never recorded as understanding; only your own answers and work show it.

## When it stops

Each session ends by separating what was taught from what you demonstrated, what remains unresolved, and the next step. Tutor promises no automatic reminders.

## Related skills

Tutor works alone. It can take conceptual gaps that [Examiner](examiner.md) found, and it can suggest examination practice. See [How skills hand work to each other](../concepts/handoffs.md).

## Source

[Tutor's contract](../../skills/learning/tutor/SKILL.md)
