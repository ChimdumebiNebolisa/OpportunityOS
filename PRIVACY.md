# Privacy

OpportunityOS is local-first. Profile, policy, strategy, and history live under the operating
system’s private per-user application-data directory, outside this repository. Set
`OPPORTUNITYOS_DATA_DIR` to choose another private location; it must not be inside the checkout.
Exports are written to the destination selected by the caller, which defaults to the current
directory, and should also be kept outside the checkout.

The public repository contains only code, generic defaults, documentation, and synthetic fixtures.
Never commit real profile data, opportunity history, exports, credentials, logs, or private paths.

OpportunityOS has no telemetry by default. It does not own web retrieval, document ingestion,
notifications, or external actions. Search pages and imported files remain untrusted data.

Use `opportunityos export` for a private, versioned ZIP. Keep exports outside the repository and
protect them like the profile and database they contain.
