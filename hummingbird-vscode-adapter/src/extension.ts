import * as vscode from "vscode";
import { BridgeError, loopbackOrigin, PEER_ID, validateToken } from "./protocol";
import { PeerClient } from "./transport";

export function activate(context: vscode.ExtensionContext): void {
  const output = vscode.window.createOutputChannel("Hummingbird Peer Adapter");
  const status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 30);
  status.command = "hummingbirdAdapter.showStatus";
  let client: PeerClient | undefined;
  let generation = 0;
  let busy = false;

  const setStatus = (text: string): void => {
    status.text = `$(plug) Hummingbird: ${text}`;
    status.tooltip = "Authenticated peer inbox inspection; no assistant-session binding.";
    status.show();
  };
  const disconnect = (): void => {
    generation += 1;
    client?.dispose();
    client = undefined;
    setStatus("disconnected");
  };
  const endpoint = (): string =>
    loopbackOrigin(vscode.workspace.getConfiguration("hummingbirdAdapter")
      .get<string>("endpoint", "http://127.0.0.1:5050")).origin;
  const tokenKey = (origin: string): string => `hummingbirdAdapter.peerToken:${origin}`;
  const requireTrust = (): void => {
    if (!vscode.workspace.isTrusted) {
      throw new BridgeError("workspace_untrusted", "Trust this workspace before connecting.");
    }
  };
  const register = (name: string, action: () => Promise<void>): void => {
    context.subscriptions.push(vscode.commands.registerCommand(name, async () => {
      if (busy) {
        await vscode.window.showWarningMessage("Another Hummingbird adapter command is running.");
        return;
      }
      busy = true;
      try {
        requireTrust();
        await action();
      } catch (error: unknown) {
        disconnect();
        const message = error instanceof BridgeError
          ? `${error.code}: ${error.message}`
          : "Adapter operation failed. No request was forwarded; check local host diagnostics.";
        output.appendLine(message);
        output.show(true);
        await vscode.window.showErrorMessage(message);
      } finally {
        busy = false;
      }
    }));
  };

  register("hummingbirdAdapter.pair", async () => {
    const origin = endpoint();
    const token = await vscode.window.showInputBox({
      title: "Store a dedicated Hummingbird peer service token",
      prompt: `For ${origin}, identity ${PEER_ID}. Never use an owner login cookie.`,
      password: true,
      ignoreFocusOut: true,
    });
    if (token === undefined) return;
    validateToken(token);
    await context.secrets.store(tokenKey(origin), token);
    disconnect();
    output.appendLine("Peer token saved in VS Code SecretStorage; server identity is not yet verified.");
  });

  register("hummingbirdAdapter.connect", async () => {
    disconnect();
    const revision = generation;
    const origin = endpoint();
    const token = await context.secrets.get(tokenKey(origin));
    if (!token) {
      throw new BridgeError("unpaired", "Store a server-issued peer service token first.");
    }
    if (revision !== generation) {
      throw new BridgeError("cancelled", "Endpoint changed while loading the peer token.");
    }
    const candidate = new PeerClient(origin, token);
    client = candidate;
    await candidate.capabilities();
    if (revision !== generation) {
      candidate.dispose();
      throw new BridgeError("cancelled", "Connection was superseded.");
    }
    setStatus("queue inspection only");
    output.appendLine(
      "Protocol and peer identity verified. DOM execution and existing assistant-session forwarding are unavailable.",
    );
  });

  register("hummingbirdAdapter.inspectQueue", async () => {
    const active = client;
    if (!active) {
      throw new BridgeError("disconnected", "Verify the peer connection first.");
    }
    const revision = generation;
    const requests = await active.pending();
    if (revision !== generation) {
      throw new BridgeError("cancelled", "Connection changed while reading the queue.");
    }
    const document = await vscode.workspace.openTextDocument({
      language: "plaintext",
      content: [
        "HUMMINGBIRD PEER QUEUE - UNTRUSTED REQUEST TEXT",
        "Read-only preview. Nothing below is execution authority.",
        "Inbox messages have NOT been forwarded, executed or acknowledged by this preview.",
        "",
        JSON.stringify(requests, null, 2),
      ].join("\n"),
    });
    await vscode.window.showTextDocument(document, { preview: true });
    output.appendLine(`Inspected ${requests.length} pending requests. No peer execution attempted.`);
  });

  register("hummingbirdAdapter.disconnect", async () => {
    disconnect();
    output.appendLine("Disconnected. No background polling remains.");
  });

  register("hummingbirdAdapter.forgetToken", async () => {
    const origin = endpoint();
    disconnect();
    await context.secrets.delete(tokenKey(origin));
    output.appendLine("Local service token removed. Revoke its server-side grant separately.");
  });

  register("hummingbirdAdapter.showStatus", async () => {
    output.appendLine(
      client
        ? "Transport client present; only an explicit successful handshake verifies queue access."
        : "Disconnected; no requests are being polled.",
    );
    output.appendLine(
      "This VSIX cannot access another extension's Simple Browser DOM or the existing Copilot conversation through standard VS Code APIs.",
    );
    output.show(true);
  });

  context.subscriptions.push(output, status, { dispose: disconnect });
  context.subscriptions.push(vscode.workspace.onDidChangeConfiguration((event) => {
    if (event.affectsConfiguration("hummingbirdAdapter")) disconnect();
  }));
  setStatus("disconnected");
}
