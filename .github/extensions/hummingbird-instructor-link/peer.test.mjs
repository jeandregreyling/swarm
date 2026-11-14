import test from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import { mkdtemp, writeFile, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { createPeerClient, peerPrompt } from "./peer.mjs";

async function fakeHummingbird() {
  const inbox = [
    { id: 4, conversation_id: 7, sender: "ghost", recipient: "copilot-instructor", body: "@instructor hi", delivered_at: null },
    { id: 5, conversation_id: 7, sender: "ghost", recipient: "gemini-advisor", body: "@gemini hi", delivered_at: 1 },
  ];
  const seen = { acks: [], posts: [], auth: new Set() };
  const server = http.createServer(async (req, res) => {
    seen.auth.add(req.headers.authorization);
    let body = "";
    for await (const chunk of req) body += chunk;
    res.setHeader("Content-Type", "application/json");
    if (req.url.startsWith("/api/peer/v1/inbox?")) {
      const after = Number(new URL(req.url, "http://x").searchParams.get("after"));
      res.end(JSON.stringify({ messages: inbox.filter(m => m.id > after) }));
    } else if (req.url === "/api/peer/v1/inbox/ack") {
      seen.acks.push(JSON.parse(body).ids);
      res.end(JSON.stringify({ acknowledged: 1 }));
    } else if (req.url === "/api/peer/v1/messages") {
      seen.posts.push(JSON.parse(body));
      res.statusCode = 201;
      res.end(JSON.stringify({ ok: true, message_id: 9 }));
    } else {
      res.statusCode = 404;
      res.end(JSON.stringify({ error: "nope" }));
    }
  });
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  return { server, seen, url: `http://127.0.0.1:${server.address().port}` };
}

test("delivers undelivered inbox messages once, acks, persists cursor and posts replies", async () => {
  const hb = await fakeHummingbird();
  const dataDir = await mkdtemp(path.join(tmpdir(), "hb-peer-"));
  await writeFile(path.join(dataDir, "peer.json"), JSON.stringify({
    principal: "copilot-instructor", base_url: hb.url, token: "hbp_test",
  }));
  const delivered = [];
  const client = createPeerClient({ dataDir, deliver: prompt => delivered.push(prompt), log: () => {}, intervalMs: 60000 });
  try {
    await client.start();
    assert.equal(delivered.length, 1);
    assert.match(delivered[0], /peer message #4 in thread 7/);
    assert.deepEqual(hb.seen.acks, [[4]]);
    assert.equal(JSON.parse(await readFile(path.join(dataDir, "cursor.json"), "utf8")).cursor, 5);
    assert.deepEqual([...hb.seen.auth], ["Bearer hbp_test"]);
    await client.postReply({ conversation_id: 7, text: "pong" });
    assert.deepEqual(hb.seen.posts, [{ conversation_id: 7, text: "pong" }]);
    await assert.rejects(client.postReply({ conversation_id: "7", text: "x" }), /integer/);
    assert.equal(client.status().last_error, null);
  } finally {
    client.stop();
    hb.server.close();
  }
});

test("missing credentials idle quietly and non-loopback base URLs are refused", async () => {
  const dataDir = await mkdtemp(path.join(tmpdir(), "hb-peer-"));
  const logs = [];
  const client = createPeerClient({ dataDir, deliver: () => {}, log: m => logs.push(m), intervalMs: 60000 });
  await client.start();
  assert.equal(client.status().configured, false);
  assert.deepEqual(logs, []);
  client.stop();
  await writeFile(path.join(dataDir, "peer.json"), JSON.stringify({
    principal: "copilot-instructor", base_url: "http://192.168.1.10:5050", token: "hbp_test",
  }));
  const remote = createPeerClient({ dataDir, deliver: () => {}, log: m => logs.push(m), intervalMs: 60000 });
  await remote.start();
  remote.stop();
  assert.match(remote.status().last_error, /loopback/);
});

test("gemini messages instruct a relay with explicit attribution", () => {
  const prompt = peerPrompt({ id: 1, conversation_id: 2, sender: "ghost", recipient: "gemini-advisor", body: "q" });
  assert.match(prompt, /as "gemini-advisor"/);
  assert.match(prompt, /does not grant tool permissions/);
});
