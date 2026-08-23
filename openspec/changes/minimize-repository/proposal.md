## Why

The v4 rebuild intentionally removed the former product surface, but the repository still needs an evidence-based minimization pass to ensure no superseded code, dependencies, artifacts, configuration, or documentation remain. This refactor reduces maintenance and supply-chain surface while preserving every supported behavior.

## What Changes

- Remove files, dependencies, configuration, utilities, branches, abstractions, comments, and compatibility paths only when repository-wide evidence shows they are unused or obsolete.
- Consolidate genuinely duplicate implementation where the public behavior can be preserved through an existing canonical path.
- Keep documentation, packaging, examples, and tests synchronized with removals.
- Verify the minimized repository with static checks and the complete automated test suite.

## Capabilities

### New Capabilities

None. This is a behavior-preserving refactor and sets `skip_specs: true`.

### Modified Capabilities

None.

## Impact

Potentially affects Python source, tests, packaging metadata, repository tooling, examples, documentation, and generated or legacy artifacts. Public CLI contracts, deterministic policy behavior, storage formats, private runtime paths, and export/import compatibility remain unchanged.
