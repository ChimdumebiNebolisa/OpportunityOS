## 1. Establish the evidence baseline

- [x] 1.1 Inventory tracked files, package metadata, entry points, import and string references, documentation, CI, and dynamic-loading paths; verify every removal candidate has repository-wide reference evidence.
- [x] 1.2 Run the full pre-change quality and test suite; verify the baseline is green or record pre-existing failures before editing implementation.

## 2. Remove safe repository overhead

- [x] 2.1 Remove unused runtime and development dependencies and obsolete tool configuration; verify clean environment installation metadata and all configured checks still run.
- [x] 2.2 Remove tracked generated output, dead files, abandoned implementations, and legacy compatibility paths with no supported consumers; verify references and focused tests after each tranche.
- [x] 2.3 Collapse duplicate utilities or unnecessary abstractions into the existing canonical implementation where behavior remains identical; verify through public interfaces.

## 3. Synchronize and prove the minimized repository

- [x] 3.1 Remove or correct stale comments, examples, documentation, tests, and packaging entries made obsolete by the cleanup; verify repository searches find no dangling references.
- [x] 3.2 Run formatting, lint, type checking, security/static checks, packaging validation, and the complete test suite; verify all required checks pass.
- [x] 3.3 Review the final diff and repository footprint; verify every deletion is justified, behavior is preserved, and residual uncertainty is documented.
