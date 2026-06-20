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
fly machine update <machine-id> --schedule daily
```
