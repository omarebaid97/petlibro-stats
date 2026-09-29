# petlibro-stats

Standalone poller for the PetLibro cloud API (no Home Assistant). Logs into
the PetLibro account every `POLL_INTERVAL_SECONDS` (default 300s), pulls the
device list + todays grain/feeding stats, and serves the result as JSON for
TRMNL (or anything else) to poll.

## Endpoints

- `GET /stats?token=<STATS_TOKEN>` — latest cached snapshot
- `GET /healthz` — liveness check, no token required

## Config (.env)

- `PETLIBRO_EMAIL` / `PETLIBRO_PASSWORD` — PetLibro app login
- `PETLIBRO_REGION` — default `US`
- `PETLIBRO_TIMEZONE` — default `America/Chicago`
- `POLL_INTERVAL_SECONDS` — default `300`
- `STATS_TOKEN` — required query-string token; this endpoint is public over
  the internet, so treat it as a secret
- `PORT` — internal listen port, default `8080`

## Manage

```
cd ~/petlibro-stats
docker compose config   # validate
docker compose up -d --build
docker compose logs -f
```

## Exposing to TRMNL (Cloudflare Tunnel)

Public URL: **https://petlibro.omarebaid.com/stats?token=<STATS_TOKEN>**

This service is exposed via the homelab-wide consolidated Cloudflare Tunnel
(`homelab-hub`, container `cloudflared-hub`), not a dedicated tunnel of its
own. See `/Users/omar/Downloads/homeLabAssistant/CLAUDE.md`s "Public
Exposure & Remote Access" section for how that tunnel and its ingress rules
work.

(Historical: this was previously exposed via Tailscale Funnel at
`https://homelab-1.tail193b81.ts.net/petlibro-stats`. Tailscale has been
fully decommissioned as of 2026-08-17 — if TRMNL is still configured with
that old URL it will be broken and needs updating to the URL above.)
