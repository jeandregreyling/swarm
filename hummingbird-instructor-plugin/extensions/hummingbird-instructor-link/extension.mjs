import { createCanvas, CanvasError, joinSession } from "@github/copilot-sdk/extension";
import { startRelay } from "./relay.mjs";

const panels = new Map();
let session;
const canvas = createCanvas({
  id: "hummingbird-attached-instructor-link",
  displayName: "Hummingbird instructor link",
  description: "Validate an explicit operator handoff to this attached session, without claiming HB or Gemini connectivity.",
  actions: [{
    name: "connection_status",
    description: "Read live panel handoff counts and actual bridge readiness.",
    handler() {
      return { panels: Array.from(panels.values(), panel => panel.status()) };
    },
  }],
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
