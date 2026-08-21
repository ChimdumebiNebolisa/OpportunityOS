# Security policy

## Supported version

Security fixes target the current `1.x` release line.

## Report a vulnerability

Do not open a public issue containing credentials, private profile data, or an exploit that
exposes local files. Use GitHub's private vulnerability reporting for this repository. Include the
affected version, a minimal reproduction, impact, and any proposed mitigation. Remove real secrets
and personal data from the report.

## Security boundaries

OpportunityOS is a single-user local application. It does not make a multi-user Hermes or Discord
installation safe. Keep Hermes' numeric Discord allowlist enabled, use DMs, and treat every allowed
user as capable of invoking agent tools.

The MCP server never submits applications, sends messages, accepts terms, purchases credits, or
changes external accounts. Source text is untrusted evidence, never instruction. URL intake rejects
private and non-global destinations, revalidates every redirect, limits bytes while streaming, and
accepts only text content. File intake validates containment, symlinks, size, signature, and format.

Before publishing a change, run:

```text
opportunityos audit public-repo
gitleaks git .
```

See [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md) for assumptions and residual risk.
