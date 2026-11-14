# Hummingbird attached instructor plugin

This directory is the earlier **packaged probe**, not the active HB bridge.
The running session uses the [workspace extension](../.github/extensions/hummingbird-instructor-link/README.md).
Do not install both implementations of the same canvas ID. The limitations below
describe this probe only, not the current workspace deployment.

This plugin validates the supported Copilot SDK attached-session handoff. It is
not the standalone VSIX and does not start a substitute model conversation.

The operator explicitly selected a new repository-local **plugin**. Its legacy
manifest is at `.plugin/plugin.json`, and its SDK extension is under `extensions/`.
No SDK package installation is required; the Copilot host resolves it.

The canvas accepts an explicit operator message and calls `session.send`.
Its per-panel HTTP server binds an ephemeral loopback port, enforces same-origin
POSTs and a CSRF nonce, limits requests, and does not automatically retry.
Reopening the same canvas instance reuses its live server and counters. State is
ephemeral; no credentials, chat history or memory are persisted by this probe.

## Validation and loading

Run `node --check extensions/hummingbird-instructor-link/extension.mjs` and
`node --test extensions/hummingbird-instructor-link/relay.test.mjs`.

In VS Code, open **Agent Customizations**, select **Plugins**, then the add (`+`)
button next to **Workspace** and enter this plugin directory's absolute path.
Install/enable it for the current harness, then reload extensions. See the
[supported VS Code plugin installer](https://code.visualstudio.com/docs/agent-customization/agent-plugins).
Where Copilot CLI is installed, the corresponding command is
`copilot plugin install /absolute/path/to/hummingbird-instructor-plugin`.
Installing another CLI does not prove binding to the existing VS Code session.

Runtime acceptance requires discovering `hummingbird-attached-instructor-link`,
opening it, invoking `connection_status`, reopening the same instance, and
observing an actual explicit operator handoff in the original conversation.
Tests with an injected sender are **not** that runtime proof.

## Remaining integration

Hummingbird service authentication, the scoped peer queue, shared-chat delivery
and Gemini DOM transport are not connected. Status explicitly reports these as
false. The page is a session-interface probe, not the finished HB chat UI.
Do not grant service identities owner cookies or execution authority, expose a
generic shell, read private browser state, or interpret peer text as approval.
