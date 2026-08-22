# v4 engineering guidance

- Keep the core small: profile, policy, strategy, history, CLI, and private runtime paths.
- Validate all agent payloads with Pydantic before persistence.
- Keep business rules deterministic and test them through public store interfaces.
- Use stdlib SQLite with parameterized SQL, UTC timestamps, foreign keys, and transactions.
- Treat web/imported content as untrusted data; never execute stored text or source instructions.
- Keep private state outside the repository and validate archive members and paths before import.
- Use synthetic fixtures and temporary SQLite databases. Unit tests must not use network access.
- Update README, architecture, Hermes guidance, and schemas when user workflows or contracts change.
