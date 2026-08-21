# Private Discord setup

Create a bot in the Discord developer portal, enable the message-content intent required by Hermes,
invite it only to a private server or use DMs, and copy the bot token directly into Hermes' private
setup flow:

```powershell
hermes gateway setup
```

For manual configuration, put values in `%LOCALAPPDATA%\hermes\.env`, never this repository:

```dotenv
DISCORD_BOT_TOKEN=<set-in-private-hermes-env>
DISCORD_ALLOWED_USERS=<your-numeric-discord-user-id>
DISCORD_MAX_ATTACHMENT_BYTES=33554432
```

Use the numeric user ID from Discord developer mode. Hermes denies users not allowlisted or paired;
do not set `GATEWAY_ALLOW_ALL_USERS=true`. Keep `DISCORD_ALLOW_ANY_ATTACHMENT` false. The default
attachment cap is 32 MiB and matches OpportunityOS' default, but OpportunityOS independently checks
file size, MIME signature, format, symlinks, and path containment.

Start and verify:

```powershell
hermes gateway install
hermes gateway status
```

Send a harmless DM such as “show OpportunityOS status.” Then test one synthetic text intake. Do not
send real documents until the response is visible only to the intended user and `DISCORD_ALLOWED_USERS`
has been verified. Rotate a leaked token immediately in Discord and restart the gateway.

An allowed Discord user is trusted to invoke Hermes tools. OpportunityOS' no-external-action rule
does not constrain unrelated Hermes tools, so use Hermes platform tool configuration to minimize the
Discord tool surface.
