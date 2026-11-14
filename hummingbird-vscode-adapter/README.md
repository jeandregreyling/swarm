# Hummingbird Peer Adapter

This VS Code extension explicitly verifies a dedicated `copilot-instructor`
service token and previews its inbox. It uses the actual backend endpoints:

- `GET /api/peer/v1/whoami`: authenticate the peer identity and read scope.
- `GET /api/peer/v1/inbox?limit=4`: inspect a bounded inbox page.

The previous scaffold called `/api/peer-bridge/v1/capabilities` and `/requests`,
which the backend does not serve. Version 0.1.1 corrects both paths and validates
actual response schemas. Inbox reads do not acknowledge work; delivery timestamps
are displayed as the server returns them.

Pair through **Hummingbird: Store Peer Service Token**, then **Verify Peer
Connection** and **Inspect Pending Peer Requests**. Tokens stay in VS Code
SecretStorage. Only explicit loopback HTTP origins with a port are accepted;
no redirects, cookies, proxy lookup or credential fallback are used. Workspace
Trust is required. Endpoint changes disconnect the client.

This extension does not bind an existing assistant session or operate Gemini.
The workspace Copilot instructor link is a separate integration. Codex uses its
own identity and the terminal/MCP peer client described in
`../CODEX_HUMMINGBIRD_CONNECTION.md`; do not pair this VSIX with a Codex token.

Use Node 22+ and the locked dev dependencies. Run `npm run check`, `npm test`
and `npm run package`. Network fixture tests require permission to bind a local
test socket. Type checks and protocol tests do not prove VS Code activation or
a live authenticated Hummingbird connection.
