# Privacy

OpportunityOS is local-first. By default, its database, attachments, source cache, logs, exports,
backups, and application packets live under the operating system's private per-user application-data
directory, outside this repository. `OPPORTUNITYOS_DATA_DIR` and `OPPORTUNITYOS_CONFIG_DIR` may
override those locations; choose private directories outside any synchronized or public tree.

The public repository contains only code, defaults, tests, synthetic examples, and documentation.
It must never contain real resumes, transcripts, screenshots, profile exports, opportunity packets,
bot tokens, OAuth credentials, database files, logs, or private absolute paths.

OpportunityOS does not upload analytics. `analytics_uploaded` is always zero. Network access occurs
only for an explicit URL intake, optional GitHub profile sync, or through Hermes tools the user asks
to run. ChatGPT/Codex OAuth credentials are owned by Hermes and are never read or stored by
OpportunityOS.

Use `opportunityos export` for a private JSON export, `opportunityos backup` for a verified SQLite
backup, and `opportunityos purge --older-than-days N` for scoped cached-attachment retention. These
outputs remain private and are not suitable for committing.
