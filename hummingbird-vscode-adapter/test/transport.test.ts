import { strict as assert } from "node:assert";
import { once } from "node:events";
import * as http from "node:http";
import { test } from "node:test";
import {
  BridgeError, loopbackOrigin, MAX_MESSAGE_BYTES, parseCapabilities, parseQueue,
} from "../src/protocol";
import { PeerClient } from "../src/transport";

const token = "test-only-service-token-not-a-credential";
const capabilities = {
  ok: true, principal: "copilot-instructor", display_name: "VS Code Instructor",
  scopes: ["peer.read", "peer.post", "peer.memory", "peer.relay:gemini-advisor"],
};

test("literal loopback origins only; no credential, DNS, path or redirect target", () => {
  assert.equal(loopbackOrigin("http://127.0.0.1:5050").origin, "http://127.0.0.1:5050");
  assert.equal(loopbackOrigin("http://[::1]:5050").origin, "http://[::1]:5050");
  for (const value of [
    "https://example.com", "http://localhost:5050", "http://127.0.0.1",
    "http://user:pass@127.0.0.1:5050", "http://127.0.0.1:5050/api",
    "http://127.0.0.1:5050/?token=secret", "http://127.0.0.1:5050/#fragment",
  ]) {
    assert.throws(() => loopbackOrigin(value), BridgeError);
  }
});

test("handshake verifies dedicated identity and read scope", () => {
  assert.equal(parseCapabilities(capabilities).principal, "copilot-instructor");
  assert.throws(() => parseCapabilities({ ...capabilities, principal: "apex" }), BridgeError);
  assert.throws(() => parseCapabilities({ ...capabilities, scopes: [] }), BridgeError);
  assert.throws(() => parseCapabilities({ ...capabilities, token }), BridgeError);
});

test("inbox validates actual backend contract, bounded text and identities", () => {
  const item = { id: 1, conversation_id: 1, message_id: null, sender: "ghost",
    recipient: "gemini-advisor", body: "Public architectural question", created_at: 1, delivered_at: null };
  const queue = (messages: unknown[]) => ({ ok: true, messages });
  assert.equal(parseQueue(queue([item])).length, 1);
  for (const invalid of [
    { ...item, conversation_id: true }, { ...item, recipient: "shell" },
    { ...item, created_at: "yesterday" }, { ...item, token },
    { ...item, body: "é".repeat(MAX_MESSAGE_BYTES) },
  ]) assert.throws(() => parseQueue(queue([invalid])), BridgeError);
  assert.throws(() => parseQueue(queue([item, item])), BridgeError);
});

async function serve(
  handler: http.RequestListener,
  run: (client: PeerClient) => Promise<void>,
): Promise<void> {
  const server = http.createServer(handler);
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const address = server.address();
  assert.ok(address && typeof address !== "string");
  const client = new PeerClient(`http://127.0.0.1:${address.port}`, token);
  try {
    await run(client);
  } finally {
    client.dispose();
    server.closeAllConnections();
    await new Promise<void>((resolve, reject) => {
      server.close((error) => error ? reject(error) : resolve());
    });
  }
}

test("handshake uses dedicated bearer identity and exact path", async () => {
  await serve((request, response) => {
    assert.equal(request.headers.authorization, `Bearer ${token}`);
    assert.equal(request.headers.cookie, undefined);
    assert.equal(request.url, "/api/peer/v1/whoami");
    response.writeHead(200, { "Content-Type": "application/json" });
    response.end(JSON.stringify(capabilities));
  }, async (client) => {
    assert.equal((await client.capabilities()).principal, "copilot-instructor");
  });
});

test("missing API, redirects, malformed bodies and excessive output fail explicitly", async () => {
  for (const [status, body, code] of [
    [404, "", "http_404"],
    [302, "", "http_302"],
    [200, "{bad-json", "invalid_response"],
    [200, "x".repeat(65_537), "response_too_large"],
  ] as const) {
    await serve((_request, response) => {
      response.writeHead(status, {
        "Content-Type": "application/json",
        Location: "https://example.com/never-follow",
      });
      response.end(body);
    }, async (client) => {
      await assert.rejects(client.capabilities(), (error: unknown) =>
        error instanceof BridgeError && error.code === code);
    });
  }
});

test("dispose cancels in-flight work without fallback", async () => {
  await serve((_request, _response) => {}, async (client) => {
    const pending = client.capabilities();
    client.dispose();
    await assert.rejects(pending, (error: unknown) =>
      error instanceof BridgeError && error.code === "cancelled");
    await assert.rejects(client.pending(), (error: unknown) =>
      error instanceof BridgeError && error.code === "cancelled");
  });
});
