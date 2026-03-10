# Deployment

## Goal

The main deployment goal is to let you use the Codex runtime running on your machine from somewhere else, including a phone.

## Important Security Note

This bridge fronts a privileged local coding runtime.

Do not expose it directly to the public internet without a strong access layer.

Treat it like privileged developer infrastructure.

## Recommended Access Patterns

### 1. Private network access

Best default options:

- Tailscale
- WireGuard
- private VPN

This is the safest default for “I want to use my workstation from my phone”.

### 2. SSH tunnel

Useful for quick remote access:

```bash
ssh -L 8787:127.0.0.1:8787 user@your-machine
```

Then use the bridge locally through `http://127.0.0.1:8787`.

### 3. Protected reverse proxy

If you need a web-facing entry point, put the bridge behind:

- strong authentication
- access policies
- TLS
- rate limiting

Examples:

- Cloudflare Access
- private Nginx/Caddy behind SSO
- internal gateway

## Local Run

```bash
codex-runtime-bridge serve
```

Default bind:

- `127.0.0.1:8787`

That default is intentional.

## Remote Product Direction

This repository should make the runtime reachable.

A future consumer application can add:

- mobile UI
- session browsing
- push notifications
- agent-specific UX
- personalization

Those capabilities should sit on top of this bridge rather than forcing this repository to become the final product.

