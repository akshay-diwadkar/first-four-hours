# Keep the agent inside the change you asked for

You asked for one small fix. The diff touches five files. One of them is a helper nobody mentioned, now "simplified". Your rules file said to leave it alone.

A request that only says what to do leaves everything else open, and a rule in a rules file is advice the agent weighs in the middle of an edit. Blueprint turns what must not change into part of the plan: the Goal names it, every step names the files it may touch, and the completion conditions say how each protected behavior is checked. Construct carries out that plan without widening it and compares the final diff with it. Nothing here forces an agent to obey. It gives you something exact to check the change against, and a step that checks it.

## Use this when

- An agent keeps changing, deleting, or "simplifying" code you did not ask it to touch.
- Your rules file says not to, and the diff does it anyway.
- Code near the change must stay exactly as it is, and your request would not say so on its own.

## Use something else when

- The edit is small and clear, and you will read the whole diff yourself: it needs no plan.
- The extra changes point at a real structural question, such as two helpers that should become one: [Settle the structure before agents add parallel machinery](settle-structure.md).
- The change is already made: [Trust a change before you merge it](review-before-merge.md).

## Steps

1. Start Blueprint with the change and, in the same request, what must not change: the files, the behavior, the interfaces. Name them. "Don't touch anything else" is not something a check can show.
2. Read the sealed plan's Goal. Each thing you named should appear in its load-bearing invariants or under what does not change, and the completion conditions should name the check that shows it. Anything missing there is not protected. A sealed plan never changes, so ask Blueprint for a new plan that states it.
3. Start Construct on the sealed plan in a Git worktree. It never changes the plan's method, scope, or decisions. When the code turns out to need something the plan does not allow, it stops with `plan-contradiction` instead of widening the change.
4. Read Construct's report. A completion report means every instruction was applied, the plan's verification passed, and the final diff matches the plan.
5. When the protected code matters enough to want a second reader, start Assess on the branch with the sealed Blueprint as its authority.

## A worked scenario

*Illustrative: FreshCart is a made-up online grocery service, and this is not a recorded run. Excerpts are shortened.*

Last month an agent changed the label on FreshCart's "Place order" button. The same diff also "tidied" the payment retry helper and dropped its wait between attempts. Nobody read that file in review, because nobody expected it to change. During the next payment-provider outage, checkout hammered the provider with instant retries, and Amara Okafor, who leads support, spent the evening apologising for declined cards.

This week Mateo Rojas, who owns checkout, needs the delivery fee shown on the order summary. It is a small change, and the retry helper sits two functions away from it.

```text
/blueprint : Show the delivery fee as its own line on FreshCart's order summary. The order total must not change, and the payment retry helper must stay exactly as it is; last time a small checkout change quietly rewrote it.
```

Blueprint reads the summary view and the code around it, and writes what must stay true into the Goal:

```markdown
## Goal

Approach: add a delivery-fee line to the order summary, read from the fee the order already stores. No calculation moves or changes.

Load-bearing invariants: the order total is exactly what it is today; the payment retry helper is unchanged.

What changes: the order summary template and its view test. What does not change: the order total calculation, the payment module, and the retry helper.

Main risk: the summary view also builds the confirmation email, so the email gains the fee line too.
```

Each step names its target files, and none of them is in the payment module. One completion condition reads: "The payment module is byte-for-byte unchanged. Shown by `git diff --exit-code main -- freshcart/payments`." The main risk is a decision someone has to make, so Priya Raman, FreshCart's product owner, confirms that the email should show the fee too.

```text
/construct : Implement the sealed blueprint in .first-four-hours/blueprints/delivery-fee-on-summary/blueprint.md.
```

Construct applies the two steps and runs the plan's verification, including that diff check, which exits 0. Its report says the final diff matches the plan: two files, the ones the plan named. Yuki Tanaka, reviewing on Friday, does not have to wonder what else moved.

The tempting shortcut was the one from last month: ask for the change and trust the summary. That route would have put the payment module back in the diff, unread.

## You are done when

Construct's report shows every instruction applied, the plan's verification passed, and the diff matching the plan; every behavior you named as protected has a completion condition whose check passed; and you have settled the owner gates.

## If it goes wrong

- Something you asked to protect is missing from the Goal or the completion conditions: ask Blueprint for a new plan that names it. A sealed plan never changes ([Blueprint](../skills/blueprint.md)).
- Construct stops with `plan-contradiction` because the change really does need the protected code: decide whether that is acceptable, then run a new `/blueprint` with the original request, your decision, and Construct's evidence ([Construct](../skills/construct.md)).
- Construct stops any other way: follow the table on [Construct](../skills/construct.md).
