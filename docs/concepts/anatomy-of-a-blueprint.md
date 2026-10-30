# Anatomy of a sealed blueprint

A sealed `blueprint.md` is the file a weaker agent will carry out without making engineering decisions of its own, so every part of it has a job. This page walks through one plan, section by section, and says why each part is there.

The plan is illustrative. It belongs to Larder, the made-up online grocery service the [recipes](../recipes/README.md) follow, and it is shortened. The format is real; [Blueprint's README](../../skills/workbench/blueprint/README.md) owns its exact rules.

## The request

```text
/blueprint : Plan rate limiting for Larder's public search endpoint; existing API clients must keep working unchanged.
```

Blueprint froze these words into `request.md`, next to the plan. It asked one question, because only you could answer it and the answer changes the correct plan: should partner API keys be exempt from the limit? You said yes. It did not ask where the limiter should live, which library to use, or how to test it. Those answers are in the repository, and making you choose them would be a planning failure.

## Goal: the part you approve

```markdown
## Goal

Approach: add a per-client token bucket to the existing middleware chain, keyed on the API key when one is present and on the client address otherwise. Partner keys bypass the limit. A limited request gets 429 with a Retry-After header; every other response is unchanged.

Load-bearing invariants: responses under the limit are exactly what they are today; partner keys are never limited; the client address comes only from the app's trusted proxy helper.

What changes: the middleware chain, one new module, settings, and one new test module. What does not change: the search handlers, their responses, and the public API.

Main risk: /search/suggest shares the search handler, so it is limited too.
```

**Why it's there.** This is the part to read before you go on. In a few lines it states the approach, what must stay true, and what will not change. If the Goal is wrong, nothing below it matters, so it comes first and it is short enough to reject.

## Current State: facts with receipts

```markdown
## Current State

- `larder/api/middleware.py::build_chain` runs authentication before any handler, so the API key is known to anything added after it.
- `larder/api/client_address.py::client_address` reads the client address from the forwarded header only when the request came through the trusted proxy.
- `/search` and `/search/suggest` both route to `larder/search/handlers.py::search`.

**Source:** `larder/api/middleware.py`
**Source:** `larder/api/client_address.py`
**Source:** `larder/search/handlers.py`
```

**Why it's there.** Each fact is one the plan depends on, read from the code rather than remembered. The second one matters: an agent writing its own limiter would likely read the forwarded header directly, and any client can forge that header. The plan reuses the trusted helper instead.

The `**Source:**` lines bind the plan to the code. Sealing records the exact bytes of every cited file, and Construct checks them before it starts. If one of those files changed after planning, Construct stops instead of applying a plan written for code that no longer exists.

## Implementation: decisions, not code

Step 2, "Limit requests after authentication", starts with its targets and then settles its decisions in prose:

```markdown
**Location:** `larder/api/rate_limit.py`
**State:** new
**Location:** `larder/api/middleware.py::build_chain`
**State:** existing
**Location:** `tests/api/test_rate_limit.py`
**State:** new

Add `rate_limit` to `build_chain` immediately after `authenticate`. Allow 60 requests a minute per key, read from `settings.SEARCH_RATE_LIMIT`. Key each bucket on `request.api_key` when it is set, otherwise on `client_address(request)`; never read the forwarded header directly. Skip the bucket when the key is in `settings.PARTNER_KEYS`. When a bucket is empty, return 429 with Retry-After set to the whole seconds until the next token, and do not call the handler. Every other path returns the handler's response untouched.
```

**Why it's there.** Every step names the files it touches and whether each one exists or is new. Sealing refuses a `new` file that already exists and an `existing` one that does not, so a mistyped path cannot quietly create a second module.

The instruction is prose, not code. It settles every choice a faithful executor with no design authority could get wrong: where in the chain, the limit, which key, the partner exemption, the exact response. It leaves the typing to the executor. Blueprint never builds or runs the planned change, so code written into the plan would be untested code the executor copies. Prose is the default; short pseudocode appears only where prose cannot settle control flow, and exact text only where the bytes themselves are the decision, such as an error message.

## Proof that would catch a wrong implementation

```markdown
Write `tests/api/test_rate_limit.py` with four cases, each through the real middleware chain:
- the 61st search request in one minute from one key gets 429 with Retry-After set to the whole seconds until the next token, and the handler is not called (rejects a limiter that never fires or still calls the handler);
- two keys each sending 60 requests in a minute get no 429 (rejects one bucket shared by every client);
- a request with no API key is limited by `client_address(request)` even when it sends a forwarded header (rejects a limiter keyed on the spoofable header);
- a key in `settings.PARTNER_KEYS` sending 100 requests in a minute gets no 429 (rejects a limiter that ignores the exemption).

**Proof run:** `python -m pytest -p no:cacheprovider tests/api/test_rate_limit.py -q`
Red: today a client can send any number of search requests; the request after the limit returns 200 instead of 429.
Expect: exits 0 and reports 4 passed.
```

**Why it's there.** The plan decides what the tests must catch: each case, its input, the result it expects, and the wrong implementation it rejects. Construct writes the test code from those cases; a test that skips a case is a defect it repairs, never a reason to change the plan. The planner never runs its own code, so the plan freezes exact bytes only for test data, such as expected output, never for the tests themselves.

`Red:` names the defect the new test must show before the change. A test that already passes on today's code proves nothing about the change, so Construct checks that the test fails for that reason first, then passes after the step.

## Verification and completion

```markdown
## Verification

### After implementation

Run: `python -m pytest -p no:cacheprovider tests/api tests/search -q`
Expect: exits 0 with no failures; the existing search tests pass unchanged.

## Completion Conditions

- A client over the limit on /search or /search/suggest gets 429 with Retry-After; under the limit, responses are unchanged. Shown by `python -m pytest -p no:cacheprovider tests/api tests/search -q`.
- A partner key sending 100 requests in a minute gets no 429. Shown by `python -m pytest -p no:cacheprovider tests/api tests/search -q`.
- Owner gate: the operations lead confirms that 60 requests a minute suits production traffic.
```

**Why it's there.** Verification is a list of exact commands, each with the result it must show. Construct runs them as written and reports each result against its expectation, so "done" means the commands passed, not that an agent said so. Each command only reads: Construct stops one that writes anything inside the worktree, caches included, which is why the example turns pytest's cache off with `-p no:cacheprovider`.

Completion conditions state outcomes, not tasks. The Goal summarizes the approach and what must stay true; the concrete outcomes, each ending with the command whose result shows it, appear only here, so a condition no check can show stands out as a missing check. The last one starts with `Owner gate:` because no command can settle it; a person has to. Construct lists it as pending for its owner and never claims it.

## What the seal adds, and what it does not

Line 1 of the file is an HTML comment naming the contract version. Sealing appends two generated receipts as the last two lines: `blueprint-proof` records the hash of every cited source and every existing target, and `blueprint-validation` binds the plan's text to that proof. A sealed plan never changes. If the request changes, Blueprint writes a new plan in a fresh folder.

The seal proves shape and binding: the sections are in order, each target exists or is absent as declared, and the cited files are the ones the planner read. It does not prove the plan is good. That was the challenger's job. Before sealing, a separate fresh-context agent read the draft the way a faithful executor with no design authority would follow it. In this plan it noticed that step 2 never mentioned `/search/suggest`, which shares the search handler: a faithful executor would have limited it without anyone deciding to. The planner made it explicit in the Goal and the completion conditions, and only then sealed.

## Read next

- [Plan a change before your agent starts editing](../recipes/plan-a-change.md): the recipe this plan comes from.
- [Blueprint](../skills/blueprint.md) and [Construct](../skills/construct.md): what each skill does, where it stops, and why it is built that way.
