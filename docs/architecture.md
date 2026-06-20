<!-- docs/architecture.md -->

# Architecture

## Vue d'ensemble

`plantiq` est un cron job Python qui s'exécute quotidiennement sur Fly.io. Il lit les données des plantes depuis Supabase (PostgreSQL), récupère la météo de leur ville via OpenWeatherMap, et envoie une notification push via Bark.

## Flux

```
[Fly.io cron] → scheduler
                    ├── Supabase PostgreSQL  (lecture plantes)
                    ├── OpenWeatherMap API   (météo par ville)
                    └── Bark API             (notification push iOS)
```

## Décisions clés

- Pas de serveur HTTP — pur cron, aucune interface exposée
- Supabase hébergé — pas de `db` local dans compose
- Bark — POST HTTP simple, pas de SDK
- App personnelle mono-utilisateur — `BARK_TOKEN` global
