<!-- README.md -->

# plantiq

Cron job quotidien — lit les plantes depuis Supabase, récupère la météo via OpenWeatherMap, envoie une notification Bark.

## Démarrage

```bash
cp .env.example .env   # remplir les valeurs
make build
make run               # test manuel
```

## Déploiement (Fly.io)

```bash
fly launch --no-deploy   # première fois seulement
fly secrets set DATABASE_URL=... OPENWEATHERMAP_API_KEY=... BARK_TOKEN=...
make deploy
fly machine update <machine-id> --schedule daily
```
