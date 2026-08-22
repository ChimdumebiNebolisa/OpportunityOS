# Security policy

Security fixes target the current `4.x` release line.

Do not open a public issue containing credentials, private profile data, or an exploit that exposes
local files. Use GitHub’s private vulnerability reporting and include a minimal synthetic
reproduction.

OpportunityOS treats web pages, imported files, and stored strategy text as untrusted data. It never
executes strategy text, accepts arbitrary config code, uses pickle, or treats source instructions as
commands. ZIP imports reject traversal, unsupported members, incompatible versions, and invalid
databases. The CLI performs no remote submissions, messages, purchases, terms acceptance, or remote
deletions.

Before publishing a change, run the test suite, lint/type checks, and
`python scripts/audit_public_repo.py`.
