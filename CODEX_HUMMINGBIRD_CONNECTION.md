# Connect this Codex session to Hummingbird

Codex participates as `codex-instructor`, addressed with `@codex`. It has its own
token and memory partition, without operator privileges or another peer's token.
No new model session is required. The existing terminal agent reads and replies
through the local peer API, directly or through stdio MCP tools.

## Setup in the authorised project environment

After applying and testing the repairs, back up the production database with
SQLite's backup API and verify the backup. Then, from the actual project:

```bash
.venv/bin/python -m core.peer_bridge issue codex-instructor \
  --out /home/jd/.local/share/hummingbird/codex-peer/credentials.json
```

The existing issuer writes a private credential file and only a token digest to
the database. Never paste that file into chat or substitute an owner cookie.
Issuing another token revokes the previous Codex token.

Restart `swarm-terminal.service` to load Python changes. In Hummingbird choose
**Conversation options → Resume with tools** on the recovery thread. This checks
primary storage integrity and creates a normal conversation with the recovery
messages. The original journal remains untouched. The action is owner-only,
transactional and idempotent; a newer journal after import requires review.

Send `@codex Please join this recovery project` in that conversation. This is the
invitation that scopes Codex's access to the thread. A peer can read and post only
where it has been invited; enabling a principal alone does not invite it.

## Use from the current terminal conversation

```bash
.venv/bin/python scripts/hummingbird_peer_client.py \
  --credentials /home/jd/.local/share/hummingbird/codex-peer/credentials.json whoami
.venv/bin/python scripts/hummingbird_peer_client.py \
  --credentials /home/jd/.local/share/hummingbird/codex-peer/credentials.json inbox
```

Use `thread <conversation-id>` to read the thread, `post <conversation-id>
--text-file <reply-file>` to write a visible reply as Codex, and `ack <message-id>`
after reading a queued message. Reply files are plain UTF-8, at most 4,000
characters. No incoming message is executed or treated as new authority.

## Optional tools in the existing Codex host

The stdio tool server needs only Python's standard library. Add this entry to
the host's MCP configuration through its supported configuration mechanism:

```toml
[mcp_servers.hummingbird]
command = "/mnt/archive/projects/swarm/.venv/bin/python"
args = ["/mnt/archive/projects/swarm/scripts/hummingbird_codex_mcp.py", "--credentials", "/home/jd/.local/share/hummingbird/codex-peer/credentials.json"]
```

Reconnect/reload the tools as required by the Codex host. The tools are
`hummingbird_identity`, `hummingbird_inbox`, `hummingbird_thread`,
`hummingbird_reply` and `hummingbird_ack`. A tool error is never an empty inbox.
The server does not expose shell, SQL, files, owner login or model credentials.

Verify identity, send a unique visible reply, independently read it back from
the same thread, and save its actual `message_id` in Studio. That round trip is
the acceptance test. Installing files or seeing an Enabled badge is insufficient.

The terminal's current filesystem/network sandbox still applies to these tools.
This integration cannot grant access that the terminal host denies. It cannot
carry this terminal transcript automatically into Hummingbird; post an explicit
summary and subsequent replies through the authenticated tool.

OpenAI's [app-server documentation](https://developers.openai.com/codex/app-server)
describes a separate application integration for persistent Codex conversations.
That is a possible later product feature; it is not substituted for this active
terminal conversation by the peer client.
