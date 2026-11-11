import test from "node:test";
import assert from "node:assert/strict";
import { startRelay } from "./relay.mjs";

test("explicit panel submission uses attached sender", async () => {
  const messages = [];
  const panel = await startRelay(message => messages.push(message), error => { throw error; });
  try {
    const state = await (await fetch(`${panel.url}/state`)).json();
    const response = await fetch(`${panel.url}/send`, {
      method: "POST",
      headers: { Origin: panel.url, "Content-Type": "application/json", "X-Panel-CSRF": state.csrf },
      body: JSON.stringify({ text: "handoff probe" }),
    });
    assert.equal(response.status, 202);
    assert.equal(messages.length, 1);
    assert.match(messages[0].prompt, /handoff probe/);
    assert.deepEqual(panel.status(), { submitted: 1, busy: false });
    assert.equal((await fetch(panel.url)).status, 200);
  } finally {
    await panel.close();
  }
});

test("cross-origin, missing CSRF, unknown fields and empty messages fail closed", async () => {
  let count = 0;
  const panel = await startRelay(() => count++, error => { throw error; });
  try {
    const state = await (await fetch(`${panel.url}/state`)).json();
    const post = (body, extra = {}) => fetch(`${panel.url}/send`, {
      method: "POST", headers: {
        Origin: panel.url, "Content-Type": "application/json", "X-Panel-CSRF": state.csrf, ...extra,
      }, body: JSON.stringify(body),
    });
    assert.equal((await post({ text: "test" }, { Origin: "http://example.test" })).status, 403);
    assert.equal((await post({ text: "test" }, { "X-Panel-CSRF": "bad" })).status, 403);
    assert.equal((await post({ text: "" })).status, 400);
    assert.equal((await post({ text: "test", approved: true })).status, 400);
    assert.equal((await post({ text: "x".repeat(9000) })).status, 413);
    assert.equal(count, 0);
  } finally {
    await panel.close();
  }
});

test("sender failure is explicit and is not retried", async () => {
  const errors = [];
  const panel = await startRelay(() => { throw Error("offline"); }, error => errors.push(error.message));
  try {
    const state = await (await fetch(`${panel.url}/state`)).json();
    const response = await fetch(`${panel.url}/send`, {
      method: "POST", headers: {
        Origin: panel.url, "Content-Type": "application/json", "X-Panel-CSRF": state.csrf,
      }, body: JSON.stringify({ text: "test" }),
    });
    assert.equal(response.status, 502);
    assert.deepEqual(errors, ["offline"]);
    assert.equal(panel.status().submitted, 0);
    assert.equal(panel.status().busy, false);
  } finally {
    await panel.close();
  }
});
