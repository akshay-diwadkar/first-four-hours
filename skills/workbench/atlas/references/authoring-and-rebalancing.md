# Authoring and rebalancing

- [Initial mapping](#initial-mapping)
- [Promote a Satellite](#promote-a-satellite)
- [Collapse or merge a Landmark](#collapse-or-merge-a-landmark)
- [Completion](#completion)
- [Reviewed patterns](#reviewed-patterns)
- [Anti-patterns](#anti-patterns)

## Initial mapping

1. Inspect current project-folder structure and documentation enough to identify major areas.
2. Define coarse top-level Landmarks.
3. Inspect current project files for the entrypoints, cues, and costly cross-file conclusions worth caching.
4. Create cohesive Satellites inside each Landmark.
5. Add nested Landmarks only when another navigation level prevents unrelated reads.
6. Write the tiny Map, navigation-only Landmarks, and project-file-linked Satellites.
7. Add only decision-useful wiki and project-file links.
8. Merge file-shaped, symbol-shaped, or trivially thin Satellites.
9. Promote already-separable Satellites.
10. Stop when Map -> Landmark -> Satellite reliably reaches relevant current project files without implying that the wiki is exhaustive or authoritative.
11. Finish as in [Completion](#completion).

Use bounded read-only scouts only for genuinely independent project-folder areas. The primary agent owns hierarchy and reconciliation.

## Promote a Satellite

Promote when one Satellite contains independently useful concepts that should not always be read together. Separability is the trigger; line count, heading count, project-file-link fan-out, and repeated partial use are review signals only.

```text
.map/auth/tokens.md

->

.map/auth/tokens/LANDMARK.md
.map/auth/tokens/access.md
.map/auth/tokens/refresh.md
```

Replace the old Satellite link in the parent Landmark with the new Landmark. Keep routing in the Landmark and project-file-linked meaning in its child Satellites.

## Collapse or merge a Landmark

Collapse a nested Landmark into one Satellite when its children are cohesive or effectively always read together. If a top-level Landmark no longer deserves a cluster, merge or reorganize it into another top-level Landmark; never make `MAP.md` point directly to a Satellite.

Do not scan the full wiki routinely. Reconsider hierarchy during initial mapping, freshness review of an already affected subtree, an encountered navigation defect, or an explicit reorganization request.

## Completion

Walk a representative actual task through each affected route from `MAP.md` as a fresh agent would, and repair any ambiguous cue, unnecessary hop, or missing entrypoint you meet. This proportionate qualitative check proves no navigation quality.

Authoring or rebalancing is complete after that walkthrough, when `run` succeeds and `setup-guidance` then succeeds. Root guidance is required: agents will not discover the map without it, so run `setup-guidance` without waiting for a request. It creates a missing root `AGENTS.md` or `CLAUDE.md`. Repair every `run` diagnostic and the map diagnostics `setup-guidance` reports (`map.guidance_setup_requires_valid_map`, `map.guidance_map_unreadable`), then rerun until both succeed. Report any other `setup-guidance` diagnostic, or the user declining root guidance, as incomplete authoring with that diagnostic or refusal; never hand-edit, relink, re-encode, or restore root instruction files to get past it, and never add `<!-- OPT-OUT ATLAS -->` yourself. Completion never requires freshness state; [freshness and maintenance](freshness-and-maintenance.md) makes freshness current.

## Reviewed patterns

### Simple hierarchy

```text
MAP.md
  -> .map/auth/LANDMARK.md
       -> .map/auth/request-auth.md
```

The Map says when authentication context is useful. The Landmark routes within authentication. The Satellite points to productive project-file entrypoints with brief cues about request authentication.

### Nested hierarchy and cross-link

```text
MAP.md
  -> .map/auth/LANDMARK.md
       -> .map/auth/tokens/LANDMARK.md
            -> access.md
            -> refresh.md
       -> sessions.md
```

`sessions.md` may cross-link to `tokens/refresh.md`; both retain their path-derived structural parents.

### Overview Satellite

When cluster-level project-file orientation is valuable, route through a real Satellite rather than putting project-file context in the Landmark:

```markdown
<!-- .map/auth/LANDMARK.md -->
- [Overview][overview] — read for the request identity boundary; not for authorization rules.

[overview]: overview.md

<!-- .map/auth/overview.md -->
# Authentication overview

Authentication establishes a principal before authorization.

- [Request middleware][request-middleware] — principal construction starts here.

[request-middleware]: ../../src/auth.py
```

### Overgrown Satellite promotion

Before, `tokens.md` mixes independently useful access and refresh concepts:

```markdown
# Tokens

## Access tokens
Short-lived request credentials.

## Refresh tokens
Longer-lived renewal credentials with distinct invalidation behavior.
```

After promotion, the Landmark routes and each Satellite owns one concept:

```markdown
<!-- .map/auth/tokens/LANDMARK.md -->
- [Access tokens][access] — read for request credentials.
- [Refresh tokens][refresh] — read for renewal and invalidation.

[access]: access.md
[refresh]: refresh.md

<!-- .map/auth/tokens/access.md -->
# Access tokens

- [Token service][token-service] — issuance and verification start here.

[token-service]: ../../../src/tokens.py
```

### Unnecessary Landmark collapse

Before, a sessions Landmark separates lifecycle and invalidation pages that are effectively always read together. Collapse them into one cohesive Satellite:

```markdown
<!-- .map/auth/sessions.md -->
# Sessions

Sessions are created, renewed, and invalidated as one lifecycle.

- [Session store][session-store] — lifecycle state transitions live here.

[session-store]: ../../src/sessions.py
```

### File-shaped Satellite

Avoid pages that merely mirror a project file or symbol inventory:

```markdown
<!-- bad: .map/auth/jwt_decode.md -->
# jwt_decode.py

- `decode_token()`
- `verify_signature()`
```

Prefer a Satellite such as `access-tokens.md` that points to the productive entrypoint with a brief cue and adds only cross-file conclusions that are costly to rediscover.

## Anti-patterns

- A Map that lists project files, symbols, or Satellites bypasses progressive disclosure.
- A Landmark with project-file links or implementation details mixes navigation with freshness-bearing knowledge.
- A Satellite for one trivial helper or a generated caller inventory caches cheap project-folder facts.
- A Satellite containing access tokens, refresh tokens, and sessions despite independent use should promote.
- A nested Landmark whose children are always read together should collapse.
- A resolver, fuzzy/BM25 ranker, embedding/vector search, top-K selector, alias registry, section injector, or hierarchy scorer duplicates agent navigation and project-folder filesystem truth.
