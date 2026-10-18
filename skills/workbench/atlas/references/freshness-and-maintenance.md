# Freshness and maintenance

Freshness proves eligible project-file deltas were reviewed, not semantic accuracy. `check` and `baseline` form an occasional, deliberate drift audit, for example before a release, after a large merge, or when a pointer proves wrong. It catches changes made without pointer upkeep; per-change upkeep never requires it, and it never runs during orientation.

Three facts stay independent: the wiki is valid when `run` passes; root guidance is installed when `setup-guidance` succeeded; freshness is current when an exact reviewed `check` cycle was baselined. Orientation needs neither of the last two, and neither `run` nor `setup-guidance` writes freshness state.

## Check

`check` validates topology and reports deltas, affected Satellites, unmapped paths, wiki/policy changes, and a cycle. Missing, malformed, or incompatible state is not an error: `check` returns a full review cycle over the eligible universe, and later cycles report only deltas since the last baseline.

The universe excludes wiki/state, VCS, dependency/cache/build directories, and `.mapignore` matches. Relative globs allow comments, not leading `/`, negation, or `..`. Policy changes invalidate state. Escaping links, directory links or junctions, and directory bindings fail.

## Review and baseline

Review affected Satellites; edit or retain them. Link or acknowledge every unmapped path. Rebalance only the touched subtree. On a first cycle, scan the unmapped list for local scratch, cache, or generated paths, exclude them in `.mapignore`, and rerun `check` before baselining.

Run `baseline` with check's `cycle_fingerprint` and one `reviewed_satellite=<path>` input per Satellite obligation. Acknowledge unmapped paths with one `acknowledged_unmapped=<path>` input each, or with `acknowledge_unmapped=all`, which covers exactly that cycle's unmapped list; never combine the two. It rejects changed cycles and inexact or malformed values, and atomically writes `.map/.state/freshness.json`. Underlying project files and Markdown remain authoritative.
