import { createCanvas, CanvasError, joinSession } from "@github/copilot-sdk/extension";
import { startRelay } from "./relay.mjs";
import { createPeerClient } from "./peer.mjs";

const panels = new Map();
let session;

const peer = createPeerClient({
  deliver: prompt => session.send({ prompt }),
  log: message => session?.log(message),
});

function action(name, description, inputSchema, run) {
  return {
    name,
    description,
    inputSchema,
    async handler({ input }) {
      try {
        return await run(input ?? {});
      } catch (error) {
        throw new CanvasError("hummingbird_peer_failed", error.message);
      }
    },
  };
}

const conversation = { type: "integer", description: "Hummingbird conversation id" };
const canvas = createCanvas({
  id: "hummingbird-attached-instructor-link",
  displayName: "Hummingbird instructor link",
  description: "Hummingbird peer bridge for the attached instructor: inbox delivery, replies, thread context and memory pool.",
  actions: [
    action("connection_status", "Read panel handoff counts and live Hummingbird peer inbox status.", undefined,
      () => ({ panels: Array.from(panels.values(), panel => panel.status()), peer: peer.status() })),
    action("post_reply", "Post a reply into a Hummingbird thread as the instructor, or as gemini-advisor when relaying Gemini.",
      {
        type: "object",
        properties: {
          conversation_id: conversation,
          text: { type: "string", maxLength: 4000 },
          as: { type: "string", enum: ["gemini-advisor"], description: "Only when relaying Gemini's reply" },
        },
        required: ["conversation_id", "text"],
        additionalProperties: false,
      },
      input => peer.postReply(input)),
    action("read_thread", "Read recent messages from a Hummingbird thread where the instructor was addressed.",
      {
        type: "object",
        properties: { conversation_id: conversation, limit: { type: "integer", minimum: 1, maximum: 30 } },
        required: ["conversation_id"],
        additionalProperties: false,
      },
      input => peer.readThread(input)),
    action("remember", "Append a note, decision or lesson to the instructor's auditable Hummingbird memory pool.",
      {
        type: "object",
        properties: {
          kind: { type: "string", enum: ["note", "decision", "lesson"] },
          content: { type: "string", maxLength: 4000 },
          receipt: { type: "string", maxLength: 200, description: "Evidence or message receipt this memory is based on" },
        },
        required: ["kind", "content", "receipt"],
        additionalProperties: false,
      },
      input => peer.remember(input)),
    action("recall", "Read the instructor's recent Hummingbird memory pool entries.",
      {
        type: "object",
        properties: { limit: { type: "integer", minimum: 1, maximum: 50 } },
        additionalProperties: false,
      },
      input => peer.recall(input)),
  ],
  async open({ instanceId }) {
    try {
      if (!panels.has(instanceId)) {
        panels.set(instanceId, await startRelay(
          message => session.send(message),
          error => session.log(`Hummingbird handoff error: ${error.message}`),
        ));
      }
      return { url: panels.get(instanceId).url, title: "Hummingbird instructor link", status: "ready" };
    } catch (error) {
      throw new CanvasError("handoff_panel_failed", error.message);
    }
  },
  async onClose({ instanceId }) {
    const panel = panels.get(instanceId);
    if (panel) {
      await panel.close();
      panels.delete(instanceId);
    }
  },
});
session = await joinSession({ canvases: [canvas] });
await peer.start();
