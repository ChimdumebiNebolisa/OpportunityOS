# Threat model

## Protected assets

Profile facts, source documents, application drafts, opportunity decisions, OAuth credentials, bot
tokens, audit history, and backups are sensitive. Repository source and synthetic fixtures are public.

## Trust boundaries and controls

| Threat | Control | Residual risk |
| --- | --- | --- |
| Public-repo data leak | Private platform roots, containment checks, ignore rules, staged-file/content audit, Gitleaks | A user can still force-add a novel sensitive format; review diffs. |
| Prompt injection in pages/docs | Source content labeled untrusted, signal detection, typed model boundaries, deterministic decisions | A model may summarize malicious text poorly; inspect official evidence. |
| SSRF/redirect abuse | HTTPS/HTTP normalization, DNS resolution, global-IP requirement on every hop, redirect cap | DNS rebinding between validation and connection is not fully eliminated without a pinned transport. |
| Oversized or disguised files | Byte/page caps, MIME signature and extension agreement, symlink/path checks, bounded formats | Parser-library vulnerabilities remain possible; keep dependencies patched. |
| Hallucinated profile/application claims | Provenance ledger, conflict review, evidence-map validation, artifact hashes, READY blockers | Human-approved bad evidence can still be wrong. |
| Unauthorized Discord control | Hermes deny-by-default numeric allowlist, private DMs, limited attachment type/size | Any allowed user may invoke other enabled Hermes tools. |
| Credential exposure | OpportunityOS never reads Hermes auth/token stores; redacted errors; public audit | Credentials remain in Hermes' security boundary. |
| Runaway scouts/cost | Per-run query/page/model/time/notification caps, persisted budget stops, daily configuration | Hermes/provider accounting may differ; plan quotas are not estimated. |
| Unwanted external action | No MCP/CLI tool for submission, messaging, purchase, terms, or account mutation | Unrelated Hermes tools are outside OpportunityOS' control. |

## Assumptions

The operating-system user account and private data directory are trusted; this is not a multi-tenant
service. The user reviews official pages and submits manually. Hermes and parser dependencies are
third-party components and must be updated independently.
