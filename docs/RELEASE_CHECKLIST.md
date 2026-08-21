# Release checklist

- [ ] Confirm the OpenSpec change is valid and all completed task boxes have evidence.
- [ ] Sync with `uv lock --check` and build wheel/sdist from the lockfile.
- [ ] Run Ruff format/lint, strict mypy, all tests, overall coverage ≥80%, and domain coverage ≥90%.
- [ ] Run fresh and upgrade migrations, SQLite integrity, backup/restore equivalence, and CLI help.
- [ ] Run `pip-audit`, Gitleaks over git history, and `scripts/audit_public_repo.py`.
- [ ] Inspect the entire staged diff for personal data, local paths, credentials, databases, and packets.
- [ ] Verify no MCP or CLI capability performs submission, messaging, purchases, terms, or account mutation.
- [ ] Render and inspect decision, review-required, failure, quiet-scout, and packet response states.
- [ ] Record Hermes, OAuth, Discord, and GitHub live checks as PASS or GATED in `COMPATIBILITY.md`.
- [ ] Run the Vibe Security and Code Review Expert checklists; accept no Critical/High or P0/P1 finding.
- [ ] Verify README commands and current upstream Hermes links.
- [ ] Tag only after CI passes on the intended public commit.
