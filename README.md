<!-- README.md -->

# Plantiq

Tâche quotidienne automatisée qui surveille des plantes d'intérieur. Chaque soir, elle lit les plantes depuis Supabase, récupère la météo locale via OpenWeatherMap, applique six règles d'entretien, puis envoie les alertes nécessaires en notification push via ntfy (arrosage, rempotage, fertilisation, brumisation, mise en garde météo).

Application personnelle, sans interface graphique ni serveur permanent. Une seule exécution par jour, puis extinction. L'ensemble tient dans les paliers gratuits de chaque service.

## Prérequis

- Windows 11 avec WSL2 (Ubuntu)
- Docker Desktop, intégration WSL activée
- VS Code avec l'extension Dev Containers
- Un projet Supabase, une clé API OpenWeatherMap, l'app ntfy installée sur le téléphone

## Démarrage

```bash
git clone https://github.com/pietroch/plantiq.git
cd plantiq
cp .env.example .env   # remplir les trois secrets
make build
make run               # exécution manuelle, en conditions réelles
```

Les trois secrets à renseigner dans `.env` :

| Variable                 | Rôle                                                                  |
| ------------------------ | --------------------------------------------------------------------- |
| `DATABASE_URL`           | Connexion PostgreSQL Supabase (`postgresql+psycopg://...`, port 5432) |
| `OPENWEATHERMAP_API_KEY` | Clé API météo                                                         |
| `NTFY_TOPIC`             | Nom du topic de notification                                          |

Le fichier `.env` n'est jamais commité.

## Commandes

| Commande        | Action                                                                |
| --------------- | --------------------------------------------------------------------- |
| `make run`      | Lance le scheduler en conditions réelles                              |
| `make test`     | Suite de tests (sans appel réseau réel)                               |
| `make lint`     | Analyse statique avec ruff                                            |
| `make simulate` | Simule les règles sur des plantes fictives, sans base ni notification |
| `make log`      | Outil interactif : enregistrer un soin ou mettre une alerte en veille |
| `make backup`   | Exporte toutes les tables en JSON                                     |
| `make help`     | Liste toutes les commandes                                            |

## Planification (production)

Le run quotidien tourne via GitHub Actions, sans Docker. Le workflow `daily-run.yml` s'exécute automatiquement à 18h00 UTC, et peut être lancé manuellement (onglet **Actions → Daily run → Run workflow**).

Créer les trois secrets dans **Settings → Secrets and variables → Actions** : `DATABASE_URL`, `OPENWEATHERMAP_API_KEY`, `NTFY_TOPIC`.

Le workflow `ci.yml` valide le code (lint + tests) à chaque push et pull request.

## Documentation

La documentation complète (architecture, modèle de données, moteur de notifications, intégrations, exploitation) est sur Confluence, espace IT, section Plantiq.
