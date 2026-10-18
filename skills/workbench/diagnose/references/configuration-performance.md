# Configuration Performance

Hard-Problem Method owns symptom-first localization and [Improvement Evidence](improvement-evidence.md) owns baseline sufficiency and the acceptance boundary; this reference adds where configuration headroom hides and how to establish what is actually in effect.

## Establish the effective configuration

Declared configuration is a hypothesis, not evidence of what runs ([Hard-Problem Method step 4](hard-problem-method.md#4-inventory-differences-from-captured-facts)). Establish the configuration as built and as run: environment variables, CLI flags, profiles, launcher scripts, container entrypoints and deployment manifests, and the defaults of the installed framework version. Cite the value that takes effect as `config`, `source`, `command`, or `capture` evidence; a config file alone proves only what was requested.

## Where headroom hides

Orient with lever families where configuration commonly costs order-of-magnitude performance: build or compile mode; runtime, JIT, or compiler settings; concurrency and thread pools; batching and request shaping; caching and warm-up; precision, quantization, and device placement; I/O, serialization, and connection pooling; dependency or runtime version. Inspect only the families current evidence makes plausible for this target.

## Verify against what is installed

Verify every candidate setting against the installed framework and runtime versions (lockfile, `--version`, or package-query output) and the target hardware. A setting that is renamed, removed, already default, or unsupported there is not a lever. Cite external documentation only as the [finding gate](diagnosis-techniques.md#finding-gate) allows, beside a local current-file, command, or capture record.

## Establish headroom

For a setting, a quick A/B probe or a stated first-principles bound is often the cheapest trustworthy observation. Flip a setting only in a scratch copy, temporary environment override, or throwaway process, never by editing the target repository. Record an unrun decision-changing setting flip as an `open_probe`.

## State the trade-off

An accepted configuration finding states in `impact` its material cost in accuracy, memory, determinism, startup time, or portability, or that none is material. "The framework recommends this setting" is generic best practice and never passes the [finding gate](diagnosis-techniques.md#finding-gate) on its own.
