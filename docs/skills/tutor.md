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

Tutor starts once the goal is clear enough and asks only questions that would change the teaching. When your request leaves the kind of help or the depth open, it lets you choose once, and it offers every choice through your agent's choice prompt when it has one, else as a short numbered list. It researches in proportion to how current, contested, or high-stakes the material is, and states uncertainty instead of inventing detail. It uses diagrams, simulations you can steer, or animations only when they explain better than words. It consults [Reason](reason.md) only at decisions that matter, never on every turn.

When an idea is new to you, Tutor starts from what the idea is for and how it works, with a concrete case from your subject, and says where it stops applying. It uses an analogy only as a bridge, saying where the analogy breaks down. In tutoring, it moves from a worked example to a problem you finish to one you solve alone, gives less help as you need less, and ends with a question you answer from memory, with how sure you are, before it shows the answer. It counts something as understood only when more than one task, on a case different from the one it taught with, shows it, and it schedules review as answering from memory rather than re-reading.

## What you get

An explanation or a tutoring session writes nothing unless you ask to keep something; when one is substantial or would gain from a diagram, simulation, or animation, Tutor offers to keep it as a lesson page, lets you choose whether to include a visual that explains it better than words, and stops offering pages once you decline one. Everything it saves is HTML, never Markdown, apart from runnable code files such as lab starter code. Continuing learning saves files under `.learning/<subject>/` in the folder where you started Tutor:

- `lessons/<NN>-<topic>.html`: one self-contained HTML record per lesson, numbered in learning order, holding the teaching material and what you demonstrated;
- `study-plan.html`: the one study plan for the subject, shared with Examiner;
- `START_HERE.html`: the page to open first. In plain words it says what each kind of file in the folder is, where to pick up, and what to ask to continue. Tutor and Examiner refresh it whenever they save.

These are ordinary files you may commit. Delivered teaching is never recorded as understanding; only your own answers and work show it.

## When it stops

An explanation ends when it answers your question. A tutoring or continuing-learning session ends by separating what was taught from what you demonstrated, what remains unresolved, and the next step. Tutor promises no automatic reminders.

## Why it's built this way

**The failure it prevents.** An explanation that is delivered is easily assumed to have landed. Tutor helps a weaker agent teach like a skilled tutor: find the learner's real goal and starting point, choose the explanation that makes the idea land, and check understanding instead of assuming it.

**What it refuses, and why.** It never records taught material as understanding; only your own answers and work show what you understand, and how clear an explanation felt is not evidence. It uses no mandatory questionnaire, forces no exercises on a direct explanation, and follows no fixed teaching ritual. It never claims you have a learning style, a retention percentage, a brain-based explanation, or a percentage of understanding, because research does not support them. It uses visuals and motion only when they explain something words cannot; animations have playback controls and respect reduced-motion settings. It promises no automatic reminders.

**Floor and ceiling.** A weaker agent tells an explanation, tutoring, and continuing learning apart, and responds to the misconceptions your answers actually show. It chooses among worked examples, comparisons, analogies, counterexamples, visuals, and practice from memory with a research-grounded guide that says when each helps and when to stop using it. A stronger agent chooses its examples, analogies, demonstrations, and depth of research to fit the subject and the learner.

## Related skills

Tutor works alone. It can take conceptual gaps that [Examiner](examiner.md) found, and it can suggest examination practice. See [How skills hand work to each other](../concepts/handoffs.md).

## Source

[Tutor's contract](https://github.com/akshay-diwadkar/first-four-hours/blob/main/skills/learning/tutor/SKILL.md)
