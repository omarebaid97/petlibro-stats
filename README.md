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
(health check: `/healthz`)

This service is exposed via the homelab-wide consolidated Cloudflare Tunnel
(`homelab-hub`, container `cloudflared-hub`), not a dedicated tunnel of its
own.
