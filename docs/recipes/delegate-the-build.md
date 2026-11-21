# Hand the build to a cheaper model without inheriting its bugs

The cheaper model's code compiles and the tests are green, and you still read it line by line. You cannot tell which parts it was asked for and which it decided on its own.

Most of those bugs are decisions the builder was left to make: where a rule applies, which source to trust, what a short request meant. Whether the plan leaves the builder any design authority matters more than which model builds. `/blueprint` settles those decisions first and seals a plan, and `/construct` carries it out without reopening them, so a cheaper model has little left to decide. Planning costs more up front: the stronger model does that work before anything is built.

## Use this when

- Planning and review run on a stronger model, and building runs on a cheaper one.
- The build runs unwatched or in another session.

## Use something else when

- The same strong model works while you watch and mistakes show up within minutes: your agent's plan mode is enough ([`/blueprint`](../skills/blueprint.md)).
- A decision fork turns up in the middle of an edit and one model is doing the work: [Plan a change before your agent starts editing](plan-a-change.md).
- The change is finished and needs review: [Trust a change before you merge it](review-before-merge.md).

## Steps

1. Start `/provision` yourself. It gives `ffh-constructor` a model able to carry out a plan unaided, not the cheapest one, and you choose each subagent's model, so keep `ffh-challenger` and `ffh-reviewer` on stronger ones ([`/provision`](../skills/provision.md)).
2. Start `/blueprint` on the strongest model you can afford, then read the sealed plan's Goal before anything is built.
3. Start `/construct` on the sealed plan in a Git worktree, as the `ffh-constructor` subagent or in a fresh session on the cheaper model.
4. When `/construct` stops with `plan-contradiction`, run a new `/blueprint` with the original request and `/construct`'s evidence. Never patch the plan.
5. When the stakes warrant it, start `/assess` on the branch with the sealed `/blueprint` plan as its authority.

## A worked scenario

*Illustrative: FreshCart is a made-up online grocery service, and this is not a recorded run.*

Last month Mateo Rojas, who owns checkout, had a cheaper model build promo codes from a short request. It applied the discount after the delivery fee, though Mateo had said in chat that it goes before. The tests were green. Yuki Tanaka, the reviewer, checked every line to find what the model had decided on its own.

This month it is out-of-stock substitutions, with one rule: a substitute never costs more than the item it replaces unless the customer accepts it. Mateo wants the same cheaper model to build it, and this time Mateo plans first.

```text
/provision : Set up the subagents for this project. Put ffh-constructor on a model that can carry out a plan unaided rather than the cheapest one, and keep the challenger and reviewer on the strongest models you list.
```

```text
/blueprint : Plan out-of-stock substitutions for FreshCart orders. A substitute never costs more than the item it replaces unless the customer accepts it. A cheaper model will build this in another session, so leave it no decisions.
```

`/blueprint` asks one question: must customers accept each substitute? That is a product choice, and the answer changes the plan, so it goes to a person: Priya Raman, FreshCart's product owner, answers it, and the answer goes into the plan.

```text
/construct : Implement the sealed blueprint in .first-four-hours/blueprints/out-of-stock-substitutions/blueprint.md.
```

`/construct` runs on the cheaper model and finds that the stock service's substitutes carry no prices. It does not choose a price source. It stops with `plan-contradiction` and its evidence, and Mateo plans again with that evidence.

The tempting shortcut was to tell the builder to pick a price source and carry on. It would have picked one itself, and some customers would have paid more than for what they ordered.

## You are done when

`/construct`'s report shows every instruction applied, the plan's verification passed, and the diff matching the plan, and you have settled its owner gates. The agent saying it is done is not the signal.

## If it goes wrong

- Your harness cannot set a model per subagent, so `/provision` writes none: start `/construct` in a fresh session on the cheaper model ([`/provision`](../skills/provision.md)).
- `/construct` stops with `plan-contradiction`: run a new `/blueprint` with the original request and `/construct`'s evidence, then a fresh `/construct`. Never patch the plan ([`/construct`](../skills/construct.md)).
- `/construct` reports `verification-incomplete`: run it again when the environment is healthy. An incomplete check is never a pass ([`/construct`](../skills/construct.md)).
- `/construct` stops any other way: follow the table on [`/construct`](../skills/construct.md).
