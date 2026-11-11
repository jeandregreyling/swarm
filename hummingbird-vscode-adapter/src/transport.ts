import * as http from "node:http";
import {
  BridgeError, loopbackOrigin, MAX_RESPONSE_BYTES, parseCapabilities, parseQueue,
  PeerCapabilities, PeerRequest, QUEUE_LIMIT, validateToken,
} from "./protocol";

const TIMEOUT_MS = 5_000;

export class PeerClient {
  private readonly origin: URL;
  private readonly requests = new Set<http.ClientRequest>();
  private disposed = false;

  constructor(endpoint: string, private readonly token: string) {
    this.origin = loopbackOrigin(endpoint);
    validateToken(token);
  }

  get endpoint(): string {
    return this.origin.origin;
  }

  async capabilities(): Promise<PeerCapabilities> {
    return parseCapabilities(await this.get("/api/peer/v1/whoami"));
  }

  async pending(): Promise<PeerRequest[]> {
    return parseQueue(await this.get(`/api/peer/v1/inbox?limit=${QUEUE_LIMIT}`));
  }

  dispose(): void {
    this.disposed = true;
    for (const request of this.requests) {
      request.destroy(new BridgeError("cancelled", "Peer connection was closed."));
    }
    this.requests.clear();
  }

  private get(path: string): Promise<unknown> {
    if (this.disposed) {
      return Promise.reject(new BridgeError("cancelled", "Peer connection was closed."));
    }
    return new Promise((resolve, reject) => {
      const request = http.request(new URL(path, this.origin), {
        method: "GET",
        agent: false,
        headers: {
          Authorization: `Bearer ${this.token}`,
          Accept: "application/json",
          "X-Hummingbird-Protocol": "1",
        },
      });
      this.requests.add(request);
      let settled = false;
      const finish = (error: Error | undefined, data?: unknown): void => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        this.requests.delete(request);
        if (error) reject(error);
        else resolve(data);
      };
      const timer = setTimeout(() => {
        const error = new BridgeError("timeout", "Peer API did not finish within five seconds.");
        finish(error);
        request.destroy(error);
      }, TIMEOUT_MS);
      request.once("error", (error: Error) => {
        finish(error instanceof BridgeError
          ? error
          : new BridgeError("network_error", "Local peer API connection failed."));
      });
      request.once("response", (response) => {
        const status = response.statusCode ?? 0;
        if (status !== 200) {
          const error = new BridgeError(
            `http_${status}`,
            status === 404
              ? "Peer API is unavailable. The extension scaffold does not install a server."
              : `Peer API returned HTTP ${status}; no redirect or identity fallback was attempted.`,
          );
          finish(error);
          response.destroy();
          return;
        }
        if (!(response.headers["content-type"] ?? "").toLowerCase().startsWith("application/json")) {
          finish(new BridgeError("invalid_response", "Peer API must return JSON."));
          response.destroy();
          return;
        }
        const chunks: Buffer[] = [];
        let size = 0;
        response.on("data", (chunk: Buffer) => {
          size += chunk.length;
          if (size > MAX_RESPONSE_BYTES) {
            finish(new BridgeError("response_too_large", "Peer response exceeds 64 KiB."));
            response.destroy();
            return;
          }
          chunks.push(chunk);
        });
        response.once("error", () => {
          finish(new BridgeError("network_error", "Peer response stream failed."));
        });
        response.once("aborted", () => {
          finish(new BridgeError("network_error", "Peer response stream was interrupted."));
        });
        response.once("end", () => {
          if (settled) return;
          let data: unknown;
          try {
            data = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(Buffer.concat(chunks)));
          } catch {
            finish(new BridgeError("invalid_response", "Peer API returned invalid UTF-8 or JSON."));
            return;
          }
          finish(undefined, data);
        });
      });
      request.end();
    });
  }
}
