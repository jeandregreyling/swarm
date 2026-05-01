# Mac remote-access path for Seven's Swarm (Phase-4 M24)

> Goal: From Ghost One's MacBook, reach the Dell OptiPlex 7090 ("Seven") and
> use the full Swarm UI **including push-to-talk voice into the chat tile**,
> without exposing the box to the public internet.

## TL;DR

```
MacBook ── Tailscale tunnel ──> Seven (Dell, Linux)
                                http://seven:5050    ← UI in Safari/Chrome
                                ws://seven:5050/...  ← live updates
                                mic capture: WebRTC over Tailscale (TLS not required on Tailnet)
```

## 1. Tailscale on Seven (already up)

```bash
sudo tailscale status            # confirm node "seven" is online
tailscale ip -4                  # note the 100.x.y.z IP
```

If Tailscale is **not** yet running on Seven:

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo systemctl enable --now tailscaled
sudo tailscale up --ssh --accept-routes
```

`--ssh` lets you `ssh seven` from the Mac without an SSH key dance.
`--accept-routes` lets you reach any other Tailnet subnet later.

## 2. Tailscale on the Mac

1. Install: `brew install --cask tailscale`
2. Sign in with the same account that owns Seven's Tailnet.
3. Verify: `tailscale status` should list `seven` with the 100.x address.

You can now hit the Swarm UI from Safari/Chrome at:

```
http://seven:5050        ← Tailscale MagicDNS short name
http://100.x.y.z:5050    ← raw Tailnet IP
```

## 3. Voice (push-to-talk into chat)

Browsers require **a secure context** (HTTPS or localhost) before they will
hand over the microphone via `getUserMedia`. There are three viable paths,
listed in order of preference:

### Option A — Tailscale Serve with HTTPS (recommended)

`tailscale serve` issues a Let's-Encrypt cert for your `.ts.net` hostname.

```bash
# On Seven:
sudo tailscale serve --bg --https=443 http://localhost:5050
# Result: https://seven.<your-tailnet>.ts.net  → Flask on :5050
```

On the Mac, open `https://seven.<your-tailnet>.ts.net` in Safari. The mic
prompt now appears the first time the chat tile asks for it. Voice → text
goes through the existing `/api/stt` endpoint (Whisper); voice playback uses
Piper via `/api/tts`.

### Option B — localhost SSH tunnel

```bash
# From the Mac:
ssh -N -L 5050:localhost:5050 seven
# Then open http://localhost:5050 on the Mac
```

`localhost` counts as a secure context, so the mic works. Downside: you have
to keep the SSH tunnel alive.

### Option C — self-signed cert + flag

Only if the above two don't work; you'd generate a self-signed cert, install
it on the Mac keychain as trusted, and bind Flask to 0.0.0.0:5443 with TLS.
Documented but not the preferred path — Tailscale Serve is one command.

## 4. Voice loop summary

| Stage | Component | Endpoint |
|---|---|---|
| Mic capture | Browser `getUserMedia` (Safari / Chrome on Mac) | client-side |
| Upload | `MediaRecorder` → POST audio blob | `POST /api/stt` |
| STT | Whisper (server-side, CPU) | `frontend/blueprints/voice_bp.py` |
| Reply | Existing chat pipeline | `/api/chat/...` |
| TTS playback | Piper (server-side) → audio response | `POST /api/tts` |

Whisper + Piper are the chosen non-robotic pair (see Phase-4 B19). Speech
quality is good enough that Ghost One does not need a separate Mac-side
voice runtime. All voice processing happens on Seven; the Mac is just a
microphone and speaker.

## 5. Same persona across Discord / Telegram / chat

The bridge layer lives at `frontend/services/chat_relay.py`. The Discord and
Telegram bots already share the same memory + persona profile through the
unified queue, so a voice message sent from the Mac reaches the same Gemma
slot that Discord and Telegram talk to.

## 6. Smoke test from the Mac

```bash
# 1. Reachability
curl -s -o /dev/null -w "%{http_code}\n" http://seven:5050/        # → 200

# 2. STT health
curl -s http://seven:5050/api/voice/health | jq .                  # → {"ok": true, ...}

# 3. Open https://seven.<tailnet>.ts.net  in Safari, click the chat tile,
#    hit the mic icon, speak — transcript appears, reply comes back.
```

## Closes
Phase-4 step **M24** — `S-3C362268F5`.
