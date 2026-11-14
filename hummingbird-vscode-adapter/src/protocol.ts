export const PEER_ID = "copilot-instructor";
export const MAX_RESPONSE_BYTES = 65_536;
export const MAX_MESSAGE_BYTES = 8_192;
export const QUEUE_LIMIT = 4;

export class BridgeError extends Error {
  constructor(
    public readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "BridgeError";
  }
}

export interface PeerCapabilities {
  ok: true;
  principal: typeof PEER_ID;
  display_name: string;
  scopes: string[];
}

export interface PeerRequest {
  id: number;
  conversation_id: number;
  message_id: number | null;
  sender: string;
  recipient: string;
  body: string;
  created_at: number;
  delivered_at: number | null;
}

export function loopbackOrigin(value: string): URL {
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw new BridgeError("invalid_endpoint", "A literal loopback HTTP origin is required.");
  }
  if (
    url.protocol !== "http:" ||
    !["127.0.0.1", "[::1]"].includes(url.hostname) ||
    url.username || url.password || url.search || url.hash ||
    url.pathname !== "/" || !url.port
  ) {
    throw new BridgeError(
      "invalid_endpoint",
      "Use http://127.0.0.1:PORT or http://[::1]:PORT without a path or credentials.",
    );
  }
  return url;
}

export function validateToken(token: string): void {
  if (!/^[A-Za-z0-9._~-]{24,256}$/.test(token)) {
    throw new BridgeError(
      "invalid_token",
      "Use a dedicated peer service token (24-256 URL-safe characters), not a login cookie.",
    );
  }
}

function object(value: unknown, keys: readonly string[]): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new BridgeError("invalid_response", "Expected an object from the peer API.");
  }
  const record: Record<string, unknown> = Object.fromEntries(Object.entries(value));
  if (
    Object.keys(record).length !== keys.length ||
    keys.some((key) => !Object.hasOwn(record, key))
  ) {
    throw new BridgeError("invalid_response", "Peer API fields do not match protocol version 1.");
  }
  return record;
}

export function parseCapabilities(value: unknown): PeerCapabilities {
  const record = object(value, ["ok", "principal", "display_name", "scopes"]);
  if (record.ok !== true || record.principal !== PEER_ID ||
      typeof record.display_name !== "string" || !Array.isArray(record.scopes) ||
      !record.scopes.every((scope: unknown) => typeof scope === "string") ||
      !record.scopes.includes("peer.read")) {
    throw new BridgeError("unsupported_capabilities", "The peer identity or read scope is invalid.");
  }
  return { ok: true, principal: PEER_ID, display_name: record.display_name,
    scopes: record.scopes as string[] };
}

export function parseQueue(value: unknown): PeerRequest[] {
  const record = object(value, ["ok", "messages"]);
  if (record.ok !== true || !Array.isArray(record.messages) || record.messages.length > QUEUE_LIMIT) {
    throw new BridgeError("invalid_response", "Invalid bounded inbox response.");
  }
  const ids = new Set<number>();
  const positiveId = (value: unknown): value is number =>
    typeof value === "number" && Number.isSafeInteger(value) && value > 0;
  const timestamp = (value: unknown): value is number =>
    typeof value === "number" && Number.isFinite(value) && value >= 0;
  return record.messages.map((item: unknown): PeerRequest => {
    const message = object(item, ["id", "conversation_id", "message_id", "sender", "recipient",
      "body", "created_at", "delivered_at"]);
    if (!positiveId(message.id) || ids.has(message.id) || !positiveId(message.conversation_id) ||
        (message.message_id !== null && !positiveId(message.message_id)) ||
        typeof message.sender !== "string" ||
        (message.recipient !== PEER_ID && message.recipient !== "gemini-advisor") ||
        typeof message.body !== "string" || !message.body.trim() ||
        Buffer.byteLength(message.body, "utf8") > MAX_MESSAGE_BYTES ||
        !timestamp(message.created_at) ||
        (message.delivered_at !== null && !timestamp(message.delivered_at))) {
      throw new BridgeError("invalid_response", "An inbox message violates the peer contract.");
    }
    ids.add(message.id);
    return { id: message.id, conversation_id: message.conversation_id,
      message_id: message.message_id as number | null, sender: message.sender,
      recipient: message.recipient, body: message.body, created_at: message.created_at,
      delivered_at: message.delivered_at as number | null };
  });
}
