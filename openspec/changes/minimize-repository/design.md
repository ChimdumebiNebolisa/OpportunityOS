## Context

The v4 source is intentionally small, but the repository contains historical change artifacts, packaging metadata, developer tooling, examples, tests, and generated outputs that may still reference earlier implementations. Removal decisions must account for Python imports, CLI entry points, package-data rules, subprocess-based tests, documentation contracts, migration fixtures, and dynamic file loading.

## Goals / Non-Goals

**Goals:**

- Build a repository-wide reference map before deleting code or files.
- Prefer deletion over refactoring when no supported consumer exists.
- Preserve observable CLI, storage, policy, deduplication, export/import, and private-path behavior.
- Leave the repository with synchronized source, tests, docs, examples, packaging, and CI configuration.

**Non-Goals:**

- No new product capability, compatibility promise, or framework.
- No speculative redesign of working v4 modules.
- No deletion based solely on coverage or naming when dynamic or external use is plausible.
- No removal of archived OpenSpec history merely because it is not runtime code.

## Decisions

### Use layered evidence for every removal

Candidates are accepted only after checking repository references, import graphs, packaging and entry-point metadata, tests, documentation, and dynamic loading patterns. Static-analysis results are leads, not proof. This is safer than a bulk unused-code tool and produces reviewable rationale.

### Audit from the public surface inward

Start with declared CLI/package interfaces and trace reachable modules. Then inspect dependencies, repository-only tooling, tests, docs, examples, and generated artifacts. This makes it easier to distinguish deep modules from unnecessary wrappers and avoids deleting code that is exercised only through subprocess or serialization boundaries.

### Work in independently verified tranches

First remove unquestionably generated or ignored artifacts only if tracked; then unused dependencies/configuration; then unreachable source and redundant abstractions; finally stale docs/comments/tests made obsolete by those removals. Run focused checks after each behavioral tranche and the full suite at the end. A single broad deletion would make regressions and rollback harder to isolate.

### Preserve historical planning artifacts

Archived OpenSpec changes are durable project history, not runtime dead files. They remain unless they are duplicated generated output or conflict with repository policy. This avoids confusing “not imported” with “not valuable.”

## Risks / Trade-offs

- [Dynamic file or subprocess consumer is missed] -> Search commands, package data, fixtures, documentation, and string references in addition to imports; keep uncertain candidates.
- [Tests encode an obsolete implementation and falsely justify it] -> Trace the documented/public contract before retaining test-only code.
- [Cleanup changes behavior accidentally] -> Keep edits minimal, compare CLI help/contracts where relevant, and run focused plus full verification.
- [Repository shrinks only cosmetically] -> Report retained candidates and uncertainty explicitly rather than forcing removals without evidence.
