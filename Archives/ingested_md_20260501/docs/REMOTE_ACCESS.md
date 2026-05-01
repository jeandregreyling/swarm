# Remote access — theme doc

_Phase-7 theme. Owner: Swarm platform team._

## Why

Today the Swarm can only be reached through Tailscale. We want public,
opt-in, 2FA-gated remote access on a domain the user owns so they no longer
depend on a third-party mesh. Tailscale remains supported as an alternative.

## Components

| Piece | Module / File | Summary |
| --- | --- | --- |
| TOTP 2FA primitives | `core/auth_2fa.py` | Pure-stdlib HOTP/TOTP (RFC 6238). Enrol + verify. |
| 2FA routes | `frontend/blueprints/auth.py` → `/api/auth/2fa/{enroll,verify,status}` | Rate-limited, audit-logged. |
| Rate limit + audit | `core/auth_rate_limit.py` | Per-IP fixed-window limiter. Writes `audit/auth.log`. |
| Login audit | `frontend/blueprints/login_bp.py` | `/api/auth/login` hooked into limiter. |
| Reverse proxy | `ops/caddy/Caddyfile.template` | Caddy config template with TLS and auth rate-limit. |
| Tunnel alternative | `ops/cloudflared/config.yml.template` | Cloudflare Tunnel config; no port-forward. |
| Onboarding wizard | `ops/onboarding/remote_access.yaml` | Domain + 2FA step pack for the onboarding flow. |

## Threat model

- **Brute-force login / 2FA code guessing**: rate limiter caps 10 req/min
  per IP on `/api/auth/login` and `/api/auth/2fa/verify`. Verify accepts a
  ±1 step window (90s total).
- **Exposed admin surfaces**: Caddy template 404s `/admin/*` and `/_debug/*`
  at the edge.
- **Credential leak**: all auth events append to `audit/auth.log` with IP,
  user, event, ok-flag. Operators run logrotate on this file.

## Enrolment flow

```
POST /api/auth/2fa/enroll  { username }
→ { ok, username, secret, otpauth_url }

POST /api/auth/2fa/verify  { username, code }
→ { ok: true/false }

GET  /api/auth/2fa/status?username=...
→ { ok, enrolled, verified }
```

`otpauth_url` is rendered as a QR code by the wizard UI (scanning populates
GitHub/Google/Authy). The first successful verify marks the enrolment as
verified.

## Operator deployment choices

1. **Caddy on a VPS / public IP**: copy `ops/caddy/Caddyfile.template`,
   substitute the domain, install Caddy, `systemctl reload caddy`. TLS is
   automatic.
2. **Cloudflare Tunnel** (no public port): copy
   `ops/cloudflared/config.yml.template`, run `cloudflared tunnel login` +
   create, substitute `{{DOMAIN}}` and `{{TUNNEL_UUID}}`,
   `systemctl enable --now cloudflared`.
3. **Tailscale** (default, stays supported): no change required.

## Open items

- QR rendering in the onboarding wizard (currently returns raw otpauth URL).
- Backup codes for 2FA (currently enrolment + one TOTP only).
- IP allow-list at Caddy layer for extra defence-in-depth.
