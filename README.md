<!-- README.md -->

# plantiq

Daily cron job that reads houseplants from Supabase, fetches local weather via OpenWeatherMap, and sends a push notification via ntfy.

## Getting started

```bash
cp .env.example .env   # fill in the three secrets
make build
make run               # manual test
```

## Deployment (Fly.io)

```bash
fly launch --no-deploy
fly secrets set DATABASE_URL=... OPENWEATHERMAP_API_KEY=... NTFY_TOPIC=...
make deploy
```

## Scheduling (GitHub Actions)

Create three secrets in **Settings → Secrets and variables → Actions**:

- `DATABASE_URL`
- `OPENWEATHERMAP_API_KEY`
- `NTFY_TOPIC`

The `daily-run.yml` workflow runs automatically at 18:00 UTC. To test manually: **Actions → Daily run → Run workflow**.
