<!-- docs/project-reference.md -->

# plantiq — Bilan exhaustif

**Version :** V7
**Dernière mise à jour :** 2026-06-28
**Statut :** En développement

---

## Table des matières

1. [Vue d'ensemble](#1-vue-densemble)
2. [Arborescence complète](#2-arborescence-complète)
3. [Fichiers racine](#3-fichiers-racine)
4. [Infrastructure et environnement](#4-infrastructure-et-environnement)
5. [Package principal — structure interne](#5-package-principal--structure-interne)
6. [Modules — détail fonctionnel](#6-modules--détail-fonctionnel)
7. [Tests](#7-tests)
8. [CI/CD](#8-cicd)
9. [Documentation](#9-documentation)
10. [Flux d'exécution complet](#10-flux-dexécution-complet)
11. [Outputs produits](#11-outputs-produits)
12. [Glossaire des technologies](#12-glossaire-des-technologies)
13. [Risques et limites connus](#13-risques-et-limites-connus)

---

## 1. Vue d'ensemble

plantiq est un cron job Python personnel qui surveille des plantes d'intérieur : il évalue chaque soir si une action de soin est nécessaire (arrosage, rempotage, fertilisation, brumisation) en croisant l'état de chaque plante avec la météo locale, et envoie les alertes pertinentes via notification push.

**Ce qu'il produit :** Des notifications push sur le topic ntfy `plantiq`, des lignes dans `weather_logs` et `notifications_log` dans Supabase, des entrées dans `care_logs` (automatiquement après chaque arrosage notifié, ou manuellement via CLI) et dans `notification_snooze` (via CLI). En option : un export JSON de toute la base via `make backup`.

**Comment il tourne :** GitHub Actions (`daily-run.yml`, `cron: "0 18 * * *"`, 18h UTC quotidien). Python natif sur `ubuntu-latest`, sans Docker. En local : `make run` lance un conteneur Docker éphémère.

**Changements depuis V6 :**

- `weather.py` normalise désormais la réponse OWM — `_OWM_CONDITION` et l'extraction des champs y ont été déplacés depuis `engine._store_weather()`. `get_weather()` retourne le dict interne directement.
- `engine._store_weather()` utilise `log.exception()` à la place de `log.error()` — type d'exception + message + traceback complets dans les logs GitHub Actions.
- Coefficients d'arrosage nommés : `_WATERING_COEFFICIENTS` (constante module) remplace le dict inline dans `get_watering_quantity()`.

---

## 2. Arborescence complète

```
plantiq/
├── .devcontainer/
│   └── devcontainer.json              ← ouvre VSCode dans le conteneur scheduler
├── .github/
│   └── workflows/
│       ├── ci.yml                     ← lint ruff + pytest sur push/PR
│       └── daily-run.yml              ← run quotidien 18h UTC (GitHub Actions cron)
├── scheduler/                         ← service unique, cron job Python
│   ├── Dockerfile                     ← image python:3.13-slim avec libpq-dev
│   ├── pyproject.toml                 ← dépendances + config pytest et ruff
│   ├── src/
│   │   └── plantiq/                   ← package Python principal
│   │       ├── __init__.py            ← vide
│   │       ├── run.py                 ← point d'entrée de la cron
│   │       ├── engine.py              ← moteur de règles (6 règles de notification)
│   │       ├── cli.py                 ← CLI interactif (log soin + snooze)
│   │       ├── backup.py              ← export JSON de toutes les tables
│   │       ├── notify.py              ← envoi push via ntfy
│   │       ├── weather.py             ← appel OpenWeatherMap current weather
│   │       └── core/
│   │           ├── __init__.py        ← vide
│   │           ├── config.py          ← variables d'env centralisées
│   │           ├── database.py        ← engine SQLAlchemy partagé
│   │           └── logging.py         ← fabrique de loggers nommés
│   └── tests/
│       ├── __init__.py                ← vide
│       ├── conftest.py                ← force-set des env vars avant import config
│       ├── engine_dry.py              ← wrapper dry-run (infra test, pas production)
│       ├── simulation_report.md       ← rapport généré par make simulate (gitignored)
│       ├── test_database.py           ← test connexion + requête SQL mockée
│       ├── test_engine_rules.py       ← 43 tests unitaires des 6 règles engine.py
│       ├── test_notify.py             ← test envoi ntfy mocké
│       ├── test_weather.py            ← test appel OWM mocké
│       └── test_simulation.py         ← simulation moteur, 6 fixtures, rapport MD
├── docs/
│   └── project-reference.md          ← ce document
├── .dockerignore                      ← exclut .env, .git, caches du contexte build
├── .editorconfig                      ← UTF-8, LF, indent 4 (2 pour YAML/TOML)
├── .env                               ← secrets locaux (non commité)
├── .env.example                       ← template des variables d'env
├── .gitignore                         ← exclut .env, caches, simulation_report.md
├── docker-compose.yml                 ← service scheduler one-shot
├── Makefile                           ← raccourcis de toutes les commandes
└── README.md                          ← installation rapide + secrets GitHub Actions
```

---

## 3. Fichiers racine

### `docker-compose.yml`

Définit un seul service `scheduler` (conteneur `plantiq_scheduler`), construit depuis le contexte racine `.` avec `dockerfile: scheduler/Dockerfile`. `restart: "no"` confirme le caractère one-shot : le conteneur s'arrête après chaque exécution sans redémarrer. Deux volumes sont montés en mode dev : `./scheduler/src:/app/src` et `./scheduler/tests:/app/tests`, ce qui permet de modifier le code sans reconstruire l'image. Les variables d'env sont injectées depuis le `.env` racine via `env_file: .env`. Pas de réseau Docker défini — aucun service local à connecter, tout est dans Supabase cloud.

### `Makefile`

| Commande        | Action exacte                                                                                                                                        |
| --------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| `make up`       | `docker compose up -d` — démarre le stack en arrière-plan                                                                                            |
| `make down`     | `docker compose down` — arrête le stack                                                                                                              |
| `make build`    | `docker compose build` — reconstruit l'image après modification du Dockerfile ou de `pyproject.toml`                                                 |
| `make run`      | `docker compose run --rm scheduler python -m plantiq.run` — exécution manuelle de la cron                                                            |
| `make test`     | `docker compose run --rm scheduler pytest` — lance les 5 fichiers de test                                                                            |
| `make lint`     | `docker compose run --rm scheduler ruff check .` — vérifie E, F, I, UP (sauf E501)                                                                   |
| `make log`      | `docker compose run --rm scheduler python -m plantiq.cli` — CLI interactif de saisie                                                                 |
| `make simulate` | `docker compose run --rm scheduler python tests/test_simulation.py` — dry-run, génère rapport MD                                                     |
| `make backup`   | Monte `BACKUP_PATH` dans le conteneur et exécute `python -m plantiq.backup`. Lit `BACKUP_PATH` depuis le `.env` local, crée le répertoire si absent. |
| `make sh`       | `docker compose run --rm scheduler bash` — shell interactif dans le conteneur                                                                        |
| `make logs`     | `docker compose logs -f` — tail des logs du dernier run                                                                                              |
| `make help`     | Affiche toutes les commandes avec leur description                                                                                                   |

### `.env` / `.env.example`

| Variable                 | Obligatoire | Exemple                                                                  | Description                                                                                                                                          |
| ------------------------ | ----------- | ------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| `DATABASE_URL`           | oui         | `postgresql+psycopg://postgres:<pwd>@db.<ref>.supabase.co:5432/postgres` | URL complète psycopg3 vers Supabase. Port 5432 (connexion directe) ou 6543 (transaction pooler).                                                     |
| `OPENWEATHERMAP_API_KEY` | oui         | `a1b2c3d4...`                                                            | Clé API OWM. Plan gratuit suffisant (1 appel par lieu unique, 1x/jour).                                                                              |
| `NTFY_TOPIC`             | oui         | `plantiq`                                                                | Nom du topic ntfy. Toutes les notifications vont sur `https://ntfy.sh/{NTFY_TOPIC}`.                                                                 |
| `LOG_LEVEL`              | non         | `INFO`                                                                   | Niveau de log Python. Défaut : `INFO` si absent. Non déclaré dans `.env.example`.                                                                    |
| `BACKUP_PATH`            | non         | `/mnt/c/Users/Pierre/OneDrive/plantiq/backups`                           | Chemin absolu du répertoire de backup. Supporte les chemins WSL vers Windows/OneDrive. Défaut : répertoire courant. Uniquement lu par `make backup`. |

Circulation des variables en local : `.env` (racine) → Docker Compose (`env_file: .env`) → process du conteneur → `core/config.py` (`os.environ["KEY"]`). `BACKUP_PATH` est injecté séparément par `make backup` via `-e BACKUP_PATH="$(DEST)"`.

En production GitHub Actions : secrets injectés dans le step `env:` du workflow `daily-run.yml` via `${{ secrets.KEY }}`. Aucun `.env` sur le runner.

### `.dockerignore`

Fichier à la racine du repo (le contexte build Docker est `.`). Exclut : `.git`, `.env` — secrets et contrôle de version ; `.devcontainer/`, `.github/`, `docs/`, `*.md` — fichiers de dev ; `__pycache__/`, `*.py[cod]`, `.pytest_cache/`, `.venv/` — artefacts Python ; `scheduler/tests/simulation_report.md` — rapport de simulation généré.

### `.gitignore`

`.env` — secrets locaux ; `*.pyc`, `__pycache__/`, `.pytest_cache/`, `*.egg-info/`, `dist/` — artefacts Python ; `.venv/` — virtualenv local éventuel ; `scheduler/tests/simulation_report.md` — rapport de simulation (varie à chaque run).

### `.editorconfig`

UTF-8, fins de ligne LF, indentation 4 espaces. Exception : 2 espaces pour `.yml`, `.yaml`, `.toml`. Espaces de fin de ligne supprimés automatiquement. Newline finale obligatoire. Les fichiers `.md` conservent les espaces de fin (nécessaire pour les line breaks Markdown).

### `README.md`

Description en une phrase, `Getting started` (3 commandes : `cp .env.example .env`, `make build`, `make run`), section `Scheduling (GitHub Actions)` indiquant les 3 secrets à créer et la commande de déclenchement manuel. Intentionnellement court — la documentation complète est dans `docs/`.

---

## 4. Infrastructure et environnement

### Vue d'ensemble de la stack

```
docker-compose.yml (développement local uniquement)
  └── service: scheduler   ← cron job Python, one-shot
        build: . (dockerfile: scheduler/Dockerfile)
        container: plantiq_scheduler
        volumes: src/ + tests/ (hot-reload dev)
        env_file: .env

GitHub Actions (production)
  └── daily-run.yml        ← ubuntu-latest, Python natif, cron 0 18 * * *

Services externes :
  ├── Supabase PostgreSQL   ← base de données (cloud)
  ├── OpenWeatherMap API    ← météo courante par coordonnées
  └── ntfy.sh               ← push notifications
```

### Service `scheduler`

Image construite localement depuis `scheduler/Dockerfile` avec le contexte racine. `restart: "no"` — le conteneur ne redémarre pas après exécution. Pas de healthcheck (service one-shot). Utilisé en développement local uniquement — la production tourne via GitHub Actions sans Docker.

### `Dockerfile` — service `scheduler`

| Étape                                         | But                                                                                                                             |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `FROM python:3.13-slim`                       | Image de base minimale Python 3.13                                                                                              |
| `WORKDIR /app`                                | Répertoire de travail pour toutes les commandes suivantes                                                                       |
| `apt-get install build-essential libpq-dev`   | Compilateurs C et headers PostgreSQL — requis pour compiler psycopg                                                             |
| `COPY scheduler/pyproject.toml .`             | Copie uniquement le descripteur de dépendances — couche dédiée, mise en cache                                                   |
| `RUN mkdir -p src && pip install -e ".[dev]"` | Installe les dépendances avant le code source. `mkdir src` satisfait l'installation editable avant que le vrai code soit copié. |
| `COPY scheduler/src/ ./src/`                  | Copie le code source de production                                                                                              |
| `COPY scheduler/tests/ ./tests/`              | Copie les tests (nécessaire pour `make test` et `make simulate`)                                                                |
| `CMD ["python", "-m", "plantiq.run"]`         | Point d'entrée par défaut. Écrasé par `docker compose run --rm scheduler <cmd>` pour `make test`, `make lint`, `make sh`.       |

Note : Le contexte build est `.` (racine), donc les paths `COPY` préfixent `scheduler/`.

### Dev Container

`.devcontainer/devcontainer.json` utilise le `docker-compose.yml` existant, service `scheduler`, workspace `/app`. `shutdownAction: stopCompose` arrête les conteneurs à la fermeture de VSCode. `overrideCommand: true` empêche le démarrage automatique d'un process.

Extensions installées automatiquement : `ms-python.python` (IntelliSense), `ms-python.vscode-pylance` (type checking avec `extraPaths: ["src"]`), `charliermarsh.ruff` (lint + format on save), `ms-azuretools.vscode-docker`.

Activation : `Ctrl+Shift+P → Dev Containers: Reopen in Container`. Pylance utilise l'interpréteur du conteneur (`/usr/local/bin/python`). Aucun interpréteur local requis.

---

## 5. Package principal — structure interne

### Choix d'organisation

Le code de production vit dans `scheduler/src/plantiq/` — c'est le **src layout**. Le package `plantiq` n'est pas importable directement depuis `scheduler/` : il faut qu'il soit installé (`pip install -e .`). Cette contrainte garantit que les imports fonctionnent identiquement en dev, en test et en production — pas de `sys.path` manipulé, pas de risque d'importer accidentellement le dossier `src/` au lieu du package installé.

Les tests dans `scheduler/tests/` sont séparés du package. `pyproject.toml` déclare `testpaths = ["tests"]` pour que pytest les trouve depuis `/app` dans le conteneur.

### `pyproject.toml`

**Dépendances de production :**

| Package           | Version    | Rôle dans ce projet                                                                                                                                   |
| ----------------- | ---------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| `httpx`           | `==0.27.2` | Appels HTTP synchrones vers OWM (`GET /data/2.5/weather`) et ntfy (`POST`)                                                                            |
| `psycopg[binary]` | `==3.3.4`  | Driver PostgreSQL psycopg3. Variante `[binary]` : wheel précompilé, évite la compilation C. Utilisé par SQLAlchemy via l'URL `postgresql+psycopg://`. |
| `python-dotenv`   | `==1.0.1`  | Charge `.env` au démarrage via `load_dotenv(find_dotenv())` dans `config.py`                                                                          |
| `sqlalchemy`      | `==2.0.36` | Pool de connexions PostgreSQL et paramètres nommés. Utilisé en mode SQL brut (`text()`) exclusivement — pas d'ORM.                                    |

**Dépendances de développement :**

| Package         | Rôle                                                                                                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `pytest==8.3.3` | Runner de tests. Config : `testpaths = ["tests"]`. Pas de plugins additionnels.                                                                                           |
| `ruff==0.7.1`   | Lint + format. Règles actives : E (pycodestyle), F (pyflakes), I (isort), UP (pyupgrade). E501 ignorée. Longueur max : 100 caractères. `known-first-party = ["plantiq"]`. |

### Architecture des sous-packages

| Sous-package | Rôle                                         | Peut importer                        | Ne doit pas importer                    |
| ------------ | -------------------------------------------- | ------------------------------------ | --------------------------------------- |
| `core/`      | Infrastructure transverse : config, DB, logs | stdlib uniquement                    | Tout module métier                      |
| `engine.py`  | Moteur de règles central                     | `core/`, `notify`, `weather`, stdlib | `cli`, `run`, `backup`                  |
| `notify.py`  | Envoi ntfy                                   | `core/`                              | Autres modules métier                   |
| `weather.py` | Appel OWM                                    | `core/`                              | Autres modules métier                   |
| `cli.py`     | Interface interactive                        | `core/`                              | `engine`, `notify`, `weather`, `backup` |
| `backup.py`  | Export JSON de la base                       | `core/`                              | Autres modules métier                   |
| `run.py`     | Point d'entrée cron                          | `core/`, `engine`                    | Tout le reste                           |

---

## 6. Modules — détail fonctionnel

### `core/config.py`

**Rôle :** Point d'entrée unique pour les variables d'environnement. Exécuté à l'import — charge le `.env` immédiatement via `load_dotenv(find_dotenv())`, puis lit les variables.

**Expose :**

| Constante                | Type  | Comportement si absente      |
| ------------------------ | ----- | ---------------------------- |
| `DATABASE_URL`           | `str` | Lève `KeyError` au démarrage |
| `OPENWEATHERMAP_API_KEY` | `str` | Lève `KeyError` au démarrage |
| `NTFY_TOPIC`             | `str` | Lève `KeyError` au démarrage |
| `LOG_LEVEL`              | `str` | Défaut `"INFO"`              |

**Utilisé par :** `core/database.py`, `notify.py`, `weather.py`.

**Règle :** Ne jamais accéder à `os.environ` directement dans un autre module. Exception : `backup.py` lit `BACKUP_PATH` directement via `os.environ.get()` — variable optionnelle, hors scope du moteur.

---

### `core/database.py`

**Rôle :** Crée et expose l'engine SQLAlchemy global. Module minimaliste — 2 lignes effectives.

**Expose :** `engine` (instance `sqlalchemy.Engine`)

**Pattern :** `engine.connect()` utilisé comme context manager dans `engine.py`, `cli.py`, `backup.py`. SQLAlchemy gère un pool de connexions implicitement. Les transactions sont explicites : `conn.commit()` et `conn.rollback()` appelés manuellement.

**Note :** L'engine est créé à l'import (pas lazy). Un `DATABASE_URL` invalide échoue ici, pas lors de la première requête.

---

### `core/logging.py`

**Rôle :** Fabrique de loggers nommés. Configure le handler racine à chaque appel.

**Expose :** `get_logger(name: str) → logging.Logger`

**Format de log :** `%(asctime)s %(levelname)s %(message)s`

**Usage :** `log = get_logger(__name__)` en tête de chaque module métier.

---

### `run.py`

**Rôle :** Point d'entrée de la cron. Appelé par `python -m plantiq.run` (Makefile CMD et GitHub Actions `daily-run.yml`).

**Ce qu'il fait :** Log "Scheduler starting", appelle `run_engine()`, log "Scheduler run complete". Pas de gestion d'erreur propre — une exception non catchée dans `run_engine` remonte et fait échouer le process avec code 1 (visible dans les logs GitHub Actions).

---

### `weather.py`

**Rôle :** Wrapper HTTP vers l'API OpenWeatherMap current weather. Normalise la réponse OWM vers le dict interne avant de la retourner.

**Constantes :** `_OWM_CONDITION` — mapping `Clear→sunny`, `Clouds→cloudy`, `Rain/Drizzle→rainy`, `Thunderstorm→stormy`, `Snow→snowy`. Défaut si code inconnu : `cloudy`.

**Expose :** `get_weather(lat: float, lon: float) → dict`

| Fonction      | Signature                         | Ce qu'elle fait                                                                                                                                             |
| ------------- | --------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `get_weather` | `(lat: float, lon: float) → dict` | GET OWM `/data/2.5/weather`, params `units=metric`, timeout 10s, lève sur HTTP non-2xx via `raise_for_status()`, puis normalise et retourne le dict interne |

**Sortie (structure normalisée) :** `{"temperature_min": float, "temperature_max": float, "humidity": int, "condition": str, "wind_speed": float}`. Si OWM change sa structure de réponse JSON, seul ce fichier est à modifier.

---

### `notify.py`

**Rôle :** Envoi d'une notification push via ntfy.sh.

**Expose :** `send(title: str, body: str) → None`

| Fonction | Signature                        | Ce qu'elle fait                                                                                                                                |
| -------- | -------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `send`   | `(title: str, body: str) → None` | POST ntfy avec body UTF-8 et header Title ASCII, appelle `raise_for_status()` (lève `httpx.HTTPStatusError` sur 4xx/5xx), log la confirmation. |

**Contrainte critique :** Le header HTTP `Title` doit être **ASCII uniquement**. Les caractères non-ASCII causent une `UnicodeEncodeError`. Les titres de toutes les règles utilisent des tirets simples (`-`) et pas d'accents.

**Format de la requête :** `content=body.encode()` (bytes), headers `Title` et `Content-Type: text/plain; charset=utf-8`. URL : `https://ntfy.sh/{NTFY_TOPIC}`. Timeout 10s. Pas d'authentification.

**Gestion d'erreur :** Si ntfy retourne 4xx/5xx ou si la connexion échoue, une exception remonte dans `engine._notify()`, est catchée par le `try/except` individuel de la règle dans `run_engine()`, et déclenche `conn.rollback()` — seule cette règle est annulée, les autres règles de la plante continuent.

---

### `cli.py`

**Rôle :** Interface interactive en ligne de commande pour logger un soin ou snoozer une notification. Lancé manuellement avec `make log` — jamais par la cron.

**Ce qu'il fait :** Charge toutes les plantes depuis Supabase (triées par nom), affiche un menu à 3 choix, boucle jusqu'à quitter.

**Fonctions internes :**

| Fonction                                  | Ce qu'elle fait                                                                                          |
| ----------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `_pick(prompt, options)`                  | Menu numéroté, boucle jusqu'à saisie valide                                                              |
| `_load_plants(conn)`                      | `SELECT id, name FROM plants ORDER BY name`                                                              |
| `_load_enum(conn, typename)`              | `SELECT enumlabel FROM pg_enum JOIN pg_type` — retourne les valeurs de l'ENUM dans l'ordre de définition |
| `_log_action(conn, plants, care_actions)` | Saisie : plante → action → quantité ml (optionnel) → note (optionnel) → `INSERT care_logs`               |
| `_snooze(conn, plants, notif_types)`      | Saisie : plante → type notif → date JJ/MM/AAAA (optionnel) → `INSERT notification_snooze`                |

**ENUMs chargés depuis la DB au démarrage :** `_load_enum(conn, "care_action")` et `_load_enum(conn, "notif_type")` interrogent `pg_enum` — les valeurs suivent automatiquement le schéma.

**Pattern snooze :** `ON CONFLICT (plant_id, notif_type, done) DO UPDATE SET snoozed_at = NOW(), snoozed_until = EXCLUDED.snoozed_until` — met à jour un snooze actif existant plutôt que d'en créer un doublon. La contrainte UNIQUE porte sur `(plant_id, notif_type, done)` — une seule ligne active (`done = false`) par combinaison plante + type.

---

### `backup.py`

**Rôle :** Export complet de toutes les tables Supabase en JSON. Appelé par `make backup`, jamais par la cron.

**Expose :** `run() → None`

**Tables exportées (dans l'ordre) :**
`locations`, `plants`, `plant_profile`, `plant_location`, `plant_container`, `plant_accessories`, `plant_health`, `care_logs`, `notifications_log`, `notification_snooze`, `weather_logs`

**Ce qu'il fait :**

1. Lit `BACKUP_PATH` depuis l'environnement (défaut : `.`)
2. Génère un nom de fichier `plantiq_backup_YYYY-MM-DD.json`
3. Crée le répertoire si absent (`mkdir -p`)
4. Exécute `SELECT * FROM {table}` pour chaque table dans une connexion unique
5. Sérialise avec un `JSONEncoder` personnalisé : `datetime`/`date` → ISO 8601, `UUID` → string, `Decimal` → float
6. Écrit le JSON avec `ensure_ascii=False` (préserve les accents) et `indent=2`

**Format de sortie :**

```json
{
  "exported_at": "2026-06-27T18:00:00+00:00",
  "tables": {
    "locations": [ { "id": "uuid-...", "city": "Meise", ... } ],
    "plants": [ ... ]
  }
}
```

---

### `engine.py`

**Rôle :** Moteur central. Charge les données depuis Supabase, évalue 6 règles de notification pour chaque plante dans l'ordre de priorité, persiste la météo et les notifications.

**Constantes globales :**

| Constante                | Valeur                                                  | Usage                                                                          |
| ------------------------ | ------------------------------------------------------- | ------------------------------------------------------------------------------ |
| `TZ`                     | `Europe/Brussels`                                       | Toutes les comparaisons de dates                                               |
| `SUMMER_MONTHS`          | `range(4, 10)` (avril–septembre inclus)                 | Saison pour fréquence d'arrosage et activation de la fertilisation             |
| `_WATERING_COEFFICIENTS` | `light=0.025`, `moderate=0.04`, `heavy=0.06`            | Fraction du volume du pot à délivrer par arrosage, par niveau de besoin en eau |
| `_WATERING_MODE_LABELS`  | `soil_only`, `leaves`, `misting`, `mixed` → libellés FR | Corps des notifications d'arrosage                                             |

**Helpers de calcul :**

| Fonction                   | Signature                                        | Ce qu'elle fait                                                                                                                                                                                                                                                                         |
| -------------------------- | ------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `has_mold`                 | `(container: dict \| None) → bool`               | `True` si `soil_condition = "moldy"` ou `"mold"` dans `soil_issues` (insensible à la casse)                                                                                                                                                                                             |
| `get_watering_quantity`    | `(profile: dict, container: dict \| None) → int` | Quantité ml : `watering_quantity_ml` si défini dans le profil. Sinon calcule le volume du pot (`π × r² × height`) via `pot_diameter_cm` et `pot_height_cm`, et applique `_WATERING_COEFFICIENTS[watering_amount]`. Défaut si dimensions absentes : 300 ml. Min 100 ml, arrondi à 50 ml. |
| `apply_quantity_modifiers` | `(qty, weather, container, health) → int`        | +20% si temp_max > 30, ×0.5 si pas de drainage, ×0.5 si surrosage, +10% si terracotta. Min 50 ml, arrondi à 50 ml.                                                                                                                                                                      |
| `_days_since`              | `(done_at, tz, today) → int`                     | Jours depuis une datetime ou date. Retourne 999 si `None`.                                                                                                                                                                                                                              |
| `_recently_notified`       | `(last, days, today, tz) → bool`                 | `True` si `sent_at` dans `last` est il y a moins de `days` jours                                                                                                                                                                                                                        |
| `_season`                  | `(today: date) → str`                            | `"summer"` (avril–septembre) ou `"winter"`                                                                                                                                                                                                                                              |

**Helpers de persistance :**

| Fonction                                                               | Ce qu'elle fait                                                                                                                                                                                            |
| ---------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `_store_weather(conn, location_id, lat, lon, today)`                   | Appelle `get_weather()` (dict déjà normalisé), upsert `weather_logs` (`ON CONFLICT (location_id, date) DO UPDATE`). Retourne `None` si OWM échoue — `log.exception()` logué avec type + traceback complet. |
| `_log_notification(conn, plant_id, notif_type, message, triggered_by)` | `INSERT notifications_log` avec `CAST(:type AS notif_type)` et `CAST(:triggered_by AS notif_trigger)`                                                                                                      |
| `_notify(conn, plant, notif_type, title, body, triggered_by)`          | Appelle `_log_notification()` (DB) puis `send()` (ntfy). Si la DB échoue, ntfy n'est pas appelé. Si ntfy échoue après le log, le rollback individuel de la règle efface l'entrée.                          |

**Les 6 règles — vue synthétique :**

| #   | Règle                   | Type notif     | Dédup                                            | Bloqueurs principaux                                                                                             |
| --- | ----------------------- | -------------- | ------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------- |
| 1   | `_rule_weather_warning` | `warning`      | 1 jour                                           | snooze, `dying`, pas de météo, aucune des 3 conditions remplie                                                   |
| 2   | `_rule_health_check`    | `health_check` | 3j (dying) / 7j (sick/recovering) / 15j (autres) | `healthy` ou `None`, snooze                                                                                      |
| 3   | `_rule_repotting`       | `repotting`    | 30 jours                                         | `dying` sauf si `repotting_urgent`, snooze                                                                       |
| 4   | `_rule_watering`        | `watering`     | = fréquence calculée                             | `dying`, `burned`, `waterlogged`, snooze                                                                         |
| 5   | `_rule_misting`         | `misting`      | 3 jours                                          | `humidity_level != "high"`, moisissures, humidité >= 50% sans clim/chauffage, snooze                             |
| 6   | `_rule_fertilizing`     | `fertilizing`  | = fréquence profil                               | Hors saison, sol `exhausted`/`waterlogged`/moisi, `sick`/`dying`/`dormant`/`recovering`, rempotage < 60j, snooze |

**`_rule_weather_warning` — 3 conditions déclenchantes :**

Chaque condition ajoute une ligne au corps. Si aucune n'est remplie, la règle ne déclenche pas.

1. `temp_max > temp_max_c` du profil → "Arrosage prioritaire" (ou "surveiller l'humidité" si `issue_type = overwatering`)
2. `temp_min < temp_min_c` du profil → "Protéger la plante"
3. `temp_max > 35` + intérieur + pas de clim → "Chaleur critique en intérieur"

Titre : `"Alerte - {plant['name']}"`. `triggered_by = "weather"`.

**`_rule_health_check` :**

Déclenche si le statut de santé est défini et différent de `healthy`. Fenêtre de dédup : 3 jours si `dying`, 7 jours si `sick` ou `recovering`, 15 jours sinon. Corps : statut + type de problème + traitement en cours. Si `dying`, ajoute une ligne d'alerte critique. Titre : `"Sante - {plant['name']}"` (sans accent — contrainte ASCII). `triggered_by = "health_status"`.

**`_rule_repotting` — 3 déclencheurs dans l'ordre :**

- A (prioritaire) : `repotting_urgent = true` — déclenche même si la plante est mourante. Inclut `repotting_notes` si présent.
- B (calendaire) : `months_since_last_repotted >= repotting_frequency_months`. Si `last_repotted` inconnu, déclenche aussi.
- C (sol) : `soil_condition` in `("exhausted", "moldy", "compacted", "waterlogged")` OU moisissures dans `soil_issues`.

Si la plante est `sick` au moment d'envoyer : envoie un `warning` ("attendre stabilisation") à la place d'un `repotting`. Dédup : 30 jours. `triggered_by = "schedule"`.

**`_rule_watering` — modificateurs de fréquence :**

Fréquence de base : `watering_frequency_days_summer` ou `watering_frequency_days_winter` selon `_season(today)`.

| Condition                                | Modification              |
| ---------------------------------------- | ------------------------- |
| `temp_max > 35`                          | -5 jours                  |
| `temp_max > 30` (et <= 35)               | -3 jours                  |
| `temp_max < 10`                          | +3 jours                  |
| Extérieur + `humidity > 80`              | +2 jours                  |
| Extérieur + condition `rainy`            | +2 jours                  |
| Extérieur + condition `stormy`           | +3 jours                  |
| `shade = true`                           | +3 jours                  |
| `near_ac = true`                         | -1 jour                   |
| `near_heating = true`                    | -1 jour                   |
| `pot_type` in `("terracotta", "fabric")` | -2 jours                  |
| `has_drainage = false`                   | +2 jours                  |
| Cachepot présent                         | +1 jour                   |
| Cachepot sans billes d'argile            | +1 jour supplémentaire    |
| `issue_type = overwatering`              | +5 jours                  |
| `issue_type = underwatering`             | -3 jours                  |
| `status = dormant`                       | × 2 (appliqué en dernier) |

Résultat final : `max(1, int(freq))`. Déclenche si `jours >= freq` ET pas de dédup récent.

Quantité : `get_watering_quantity()` puis `apply_quantity_modifiers()`. Si `status = dormant` : quantité × 0.5 après modificateurs (min 50 ml). `triggered_by = "schedule"`.

**Auto-log après arrosage :** Immédiatement après `_notify()`, insère dans `care_logs` avec `action = "watering"`, `quantity_ml = qty_eff`, `note = "auto-logged by engine"`. Dans la même transaction que la règle — rollbackée si une exception survient.

**`_rule_misting` :**

Ne déclenche que si `humidity_level = "high"` dans le profil, et si `humidity < 50` OU `near_ac` OU `near_heating`. Bloqueurs : `issue_type = overwatering`, moisissures, `jours <= 3` depuis le dernier soin `misting`. Si `weather = None`, `humidity` prend 100 par défaut — la règle ne déclenche pas. Dédup : 3 jours. `triggered_by = "schedule"`.

**`_rule_fertilizing` :**

Bloqueurs dans l'ordre : hors saison → `soil_condition` in `("exhausted", "waterlogged")` ou moisissures → `status` in `("sick", "dying", "dormant", "recovering")` → rempotage récent (`< 60` jours) → fréquence non définie (`fertilizing_frequency_days = None`).

Note : `soil_condition = "compacted"` n'est pas un bloqueur — la règle déclenche mais ajoute : "Substrat compacté - fertiliser avec une dose réduite de moitié." Dédup : = fréquence profil. `triggered_by = "schedule"`.

**`run_engine()` — séquence complète :**

1. Calcule `today` en timezone `Europe/Brussels`
2. Charge toutes les plantes avec leur localisation (`SELECT plants JOIN locations`)
3. Pour chaque lieu unique : appelle OWM, upsert `weather_logs`, commit après tous les lieux
4. Batch load en 8 requêtes (`ANY(:ids)`) : `plant_profile`, `plant_location`, `plant_container`, `plant_accessories`, `plant_health` (DISTINCT ON), `care_logs` (DISTINCT ON), `notifications_log` (DISTINCT ON), `notification_snooze` (filtre `done = false` + date valide)
5. Pour chaque plante : résout ses snoozes actifs en `set`, saute si profil absent (log warning), évalue les 6 règles dans des **try/except individuels** — chaque règle `commit()` immédiatement après succès, `rollback()` sur exception (seule cette règle est annulée, les règles précédentes déjà commitées restent persistées)

---

## 7. Tests

**Répertoire :** `scheduler/tests/`

### `conftest.py`

Force-set des 3 variables d'environnement obligatoires **avant** tout import de `config.py`. Nécessaire car `config.py` appelle `os.environ["KEY"]` à l'import — sans ce patch, pytest lèverait `KeyError` lors de la collecte des modules.

```python
import os
os.environ["DATABASE_URL"] = "postgresql+psycopg://test:test@localhost:5432/test"
os.environ["OPENWEATHERMAP_API_KEY"] = "test_owm_key"
os.environ["NTFY_TOPIC"] = "plantiq"
```

`os.environ["KEY"] = "value"` et non `setdefault` : `load_dotenv()` dans `config.py` peut pré-charger un vrai `.env` local avant que `conftest.py` tourne ; `setdefault` ne surchargerait pas les valeurs déjà présentes.

### Fichiers de test

| Fichier                | Ce qu'il teste                                                                                 | Patterns utilisés                                                                                                            |
| ---------------------- | ---------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `test_database.py`     | Que l'engine SQLAlchemy peut exécuter une requête et retourner des lignes                      | `MagicMock`, `patch("plantiq.core.database.engine", ...)`, import side-effect explicite avant le patch                       |
| `test_engine_rules.py` | 43 tests unitaires des 6 règles de `engine.py` : bloqueurs, dédup, modificateurs, auto-log     | `patch("plantiq.engine.send")`, `MagicMock` pour `conn`, fixtures builders (`_profile`, `_container`, etc.)                  |
| `test_weather.py`      | Que `get_weather()` appelle OWM avec les bons paramètres lat/lon et retourne le dict normalisé | `patch("plantiq.weather.httpx.get", ...)`, assert sur `call_args` + champs normalisés (`temperature_max`, `condition`, etc.) |
| `test_notify.py`       | Que `send()` appelle ntfy avec `content=bytes`, le bon topic et les bons headers               | `patch("plantiq.notify.httpx.post", ...)`, assert sur les kwargs                                                             |
| `test_simulation.py`   | Dry-run des 6 règles sur 6 fixtures botaniques avec contexte aléatoire                         | `run_dry()` via `engine_dry.py`, génère `tests/simulation_report.md`                                                         |

**Note `test_database.py` :** `import plantiq.core.database  # noqa: F401` avant le `patch()` est obligatoire — sans cet import, le module n'est pas encore dans `sys.modules` et le patch échoue avec `AttributeError`.

### `engine_dry.py` (infrastructure test, pas un `test_*.py`)

Wrapper qui importe les 6 fonctions de règle depuis `engine.py` et les exécute sans DB ni ntfy :

- Monkey-patch de `eng.send` par `capture_send` qui accumule les notifications dans une liste
- `MockConn` qui ignore tous les appels (`execute`, `commit`, `rollback`)
- `last_notifs = {}` : aucun historique → toutes les règles peuvent déclencher
- `snoozes = set()` : aucun snooze actif
- `finally` : restaure `eng.send` même si une règle lève une exception

**Expose :** `run_dry(plant, profile, plant_location, container, accessories, health, care_logs, weather) → list[dict]`

Chaque notification retournée est un dict `{"title": str, "body": str}`.

### Lancer les tests

```bash
make test
# ou directement :
docker compose run --rm scheduler pytest

# Options utiles :
docker compose run --rm scheduler pytest -v
docker compose run --rm scheduler pytest tests/test_weather.py
docker compose run --rm scheduler pytest -k "test_send_posts_to_ntfy"
```

### Ajouter un test

Les tests de règles sont dans `scheduler/tests/test_engine_rules.py` (43 tests, 6 règles couvertes). Chaque règle dispose de builders de fixtures (`_profile`, `_container`, `_weather`, `_pl`, `_care_log`, `_notified`) définis en tête de fichier — s'en inspirer pour ajouter de nouveaux cas.

Pattern de base : `MagicMock()` pour `conn`, `patch("plantiq.engine.send")` pour capturer les notifications, `mock_send.assert_called_once()` ou `mock_send.assert_not_called()` pour l'assertion.

---

## 8. CI/CD

### `ci.yml` — Pipeline principal

**Déclencheurs :** Push sur `main` ou `develop`, pull request vers `main`.

**Étapes dans l'ordre :**

1. `actions/checkout@v4` — clone le repo
2. `actions/setup-python@v5` Python 3.13, cache `pip` (clé : `scheduler/pyproject.toml`)
3. `pip install -e ".[dev]"` dans `./scheduler` — installe package + ruff + pytest
4. `ruff check .` dans `./scheduler` — lint. Échoue si violation E, F, I ou UP (sauf E501)
5. `pytest` dans `./scheduler` avec les 3 env vars en placeholder — tests. Échoue si assertion ou exception

**Tourne sans Docker :** Python natif sur `ubuntu-latest`. Les 3 env vars sont injectées en `placeholder` ; `conftest.py` les surcharge avec des valeurs de test. Tous les appels réseau sont mockés.

**Artefacts produits :** Aucun.

**Ce qui fait échouer la CI :** violation ruff, test échoué, `KeyError` sur une variable d'env non couverte.

---

### `daily-run.yml` — Run quotidien de production

**Déclencheurs :** `cron: "0 18 * * *"` (18h UTC quotidien) + `workflow_dispatch` (déclenchement manuel).

**Étapes dans l'ordre :**

1. `actions/checkout@v4` — clone le repo
2. `actions/setup-python@v5` Python 3.13, cache `pip` (clé : `scheduler/pyproject.toml`)
3. `pip install -e "."` dans `./scheduler` — dépendances de production uniquement (pas `[dev]`)
4. `python -m plantiq.run` dans `./scheduler` avec les 3 secrets GitHub en `env:`

**Secrets requis :** `DATABASE_URL`, `OPENWEATHERMAP_API_KEY`, `NTFY_TOPIC` — à créer dans Settings → Secrets and variables → Actions du repo GitHub.

**Artefacts produits :** Aucun. Les sorties sont dans Supabase et ntfy.

**Ce qui fait échouer le run :**

- Secret manquant ou invalide → `KeyError` ou erreur de connexion
- OWM indisponible → exception catchée dans `_store_weather`, run continue sans météo
- Supabase indisponible → exception non catchée dans `run_engine`, process exit code 1, run marqué failed
- ntfy indisponible ou erreur HTTP → exception catchée par règle, `conn.rollback()` sur cette règle uniquement, autres règles non affectées

**Déclenchement manuel :** Actions → Daily run → Run workflow → Run workflow (branche `main`).

---

## 9. Documentation

| Fichier                     | Contenu                                           | Quand le consulter                          |
| --------------------------- | ------------------------------------------------- | ------------------------------------------- |
| `docs/project-reference.md` | Ce document — référence exhaustive et à jour      | Onboarding, compréhension globale, débogage |
| `README.md`                 | Démarrage en 3 commandes + secrets GitHub Actions | Premier contact avec le projet              |

---

## 10. Flux d'exécution complet

### Exécution nominale — production (`daily-run.yml` à 18h UTC)

```
GitHub Actions runner (ubuntu-latest)
  → python -m plantiq.run
  │
  ├─ run.py → run_engine()
  │
  ├─ Étape 1 : Chargement des plantes
  │    Lit  : plants JOIN locations (Supabase)
  │    Écrit : —
  │
  ├─ Étape 2 : Météo par lieu unique
  │    Lit  : OpenWeatherMap API (lat/lon de chaque lieu distinct)
  │    Écrit : weather_logs — upsert ON CONFLICT (location_id, date)
  │    Commit après tous les lieux
  │
  ├─ Étape 3 : Chargement batch de toutes les données satellites
  │    Lit  : plant_profile, plant_location, plant_container,
  │           plant_accessories, plant_health (DISTINCT ON),
  │           care_logs (DISTINCT ON), notifications_log (DISTINCT ON),
  │           notification_snooze (filtre done=false + date)
  │    Écrit : —
  │
  └─ Étape 4 : Évaluation des règles par plante
       Pour chaque plante (résout snoozes actifs, puis) :
         ├─ _rule_weather_warning  → ntfy + notifications_log (si déclenchée) → commit
         ├─ _rule_health_check     → ntfy + notifications_log (si déclenchée) → commit
         ├─ _rule_repotting        → ntfy + notifications_log (si déclenchée) → commit
         ├─ _rule_watering         → ntfy + notifications_log + care_logs (si déclenchée) → commit
         ├─ _rule_misting          → ntfy + notifications_log (si déclenchée) → commit
         └─ _rule_fertilizing      → ntfy + notifications_log (si déclenchée) → commit
              Chaque règle dans son propre try/except — rollback individuel sur exception
```

### Exécution locale (`make run`)

Même flux — mêmes variables d'env depuis `.env`, même connexion Supabase et OWM. Utilisé pour tester en conditions réelles depuis le poste local.

### Modes d'exécution alternatifs

| Commande        | Ce qu'elle fait                                                                    | Quand l'utiliser                                                     |
| --------------- | ---------------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| `make simulate` | Dry-run des 6 règles sur 6 fixtures sans DB ni ntfy, génère `simulation_report.md` | Valider la logique de règles sans toucher la production              |
| `make log`      | CLI interactif : log un soin ou snooze une notification dans Supabase              | Après une action réelle sur une plante, ou pour suspendre une alerte |
| `make backup`   | Export JSON de toutes les tables vers `BACKUP_PATH`                                | Sauvegarde manuelle avant une migration ou modification de schéma    |
| `make test`     | 5 fichiers de test (unitaires + règles engine) avec mocks réseau                   | Avant chaque commit                                                  |
| `make lint`     | Vérification ruff                                                                  | Avant chaque commit ou pour déboguer la CI                           |

---

## 11. Outputs produits

### Notifications ntfy

**Produit par :** `notify.send()`
**Écrit dans :** `https://ntfy.sh/plantiq` (POST HTTP)

**Format (exemple arrosage) :**

```
Header Title: Arrosage - Monstera

Dernier arrosage il y a 8 jours.
Paris : 32°C, sunny.

Comment : sur la terre uniquement - 350 ml.
Arroser au pied — ne pas mouiller les feuilles.
Chaleur importante - arrosage prioritaire.
```

**Cas particuliers :** Si ntfy est inaccessible ou retourne 4xx/5xx, `raise_for_status()` lève une exception, catchée par le `try/except` individuel de la règle dans `run_engine()`, `conn.rollback()` est appelé sur cette règle uniquement. Elle sera retentée le lendemain si les conditions persistent.

---

### Table `weather_logs`

**Produit par :** `engine._store_weather()`
**Stratégie :** Upsert `ON CONFLICT (location_id, date) DO UPDATE`. Une ligne par lieu par jour.

**Champs écrits :** `location_id`, `date`, `temperature_min`, `temperature_max`, `humidity`, `condition` (ENUM `weather_condition`), `wind_speed`, `fetched_at`.

**Exemple :**

| location_id  | date       | temperature_min | temperature_max | humidity | condition | wind_speed |
| ------------ | ---------- | --------------- | --------------- | -------- | --------- | ---------- |
| `uuid-loc-1` | 2026-06-27 | 17.2            | 28.5            | 62       | `sunny`   | 3.1        |

**Cas particuliers :** Si OWM échoue, rien n'est écrit. Les règles météo-dépendantes reçoivent `weather = None`.

---

### Table `notifications_log`

**Produit par :** `engine._log_notification()`
**Rôle principal :** Déduplication — `_recently_notified()` lit cette table pour éviter de renvoyer la même alerte le lendemain.

**Champs écrits :** `plant_id`, `type` (ENUM `notif_type`), `message`, `triggered_by` (ENUM `notif_trigger` : `schedule`, `weather`, `health_status`), `sent_at` (défaut `NOW()`).

**Exemple :**

| plant_id | type       | message                                 | triggered_by | sent_at                |
| -------- | ---------- | --------------------------------------- | ------------ | ---------------------- |
| `uuid-1` | `watering` | `Dernier arrosage il y a 8 jours.\n...` | `schedule`   | 2026-06-27 18:00:12+00 |

---

### Table `care_logs`

**Produit par deux sources :**

- `cli._log_action()` — saisie manuelle via `make log`
- `engine._rule_watering()` — auto-log après chaque notification d'arrosage

**Champs écrits :** `plant_id`, `action` (ENUM `care_action`), `quantity_ml`, `note`. `done_at` : défaut `NOW()` côté DB.

**Distinction :** Les lignes auto-loggées ont `note = "auto-logged by engine"`. Les lignes du CLI ont la note saisie (peut être `NULL`).

**Rôle dans le moteur :** Chargé au batch load via `DISTINCT ON (plant_id, action) ORDER BY done_at DESC`. L'auto-log garantit que le prochain run calcule `jours_depuis_arrosage` à partir de la date de la notification.

---

### Table `notification_snooze` (via CLI)

**Produit par :** `cli._snooze()`
**Champs écrits :** `plant_id`, `notif_type` (ENUM `notif_type`), `snoozed_until` (date ou `NULL`). `snoozed_at` mis à jour par le `ON CONFLICT DO UPDATE`.

**Logique de résolution :** Un snooze est actif si `done = false` ET (`snoozed_until IS NULL` OU `snoozed_until >= today`). Un snooze indéfini (`snoozed_until = NULL`) supprime la notification indéfiniment jusqu'à ce que `done = true` manuellement.

---

### `scheduler/tests/simulation_report.md`

**Produit par :** `test_simulation.run_simulation()`
**Écrit dans :** `scheduler/tests/simulation_report.md` (gitignored).

Rapport Markdown avec pour chaque fixture : contexte complet et liste des notifications qui auraient été envoyées. Reproductible avec un seed fixe (`python tests/test_simulation.py 42`).

**6 fixtures :** Cactus (`Opuntia microdasys`), Rose (`Rosa hybride`), Fougère de Boston (`Nephrolepis exaltata`), Yucca (`Yucca elephantipes`), Dionée (`Dionaea muscipula`), Orchidée Phalaenopsis (`Phalaenopsis amabilis`).

**Note :** La simulation génère `pot_diameter_cm` (choix parmi 12–32 cm) et `pot_height_cm` (choix parmi 10–30 cm), alignés sur les clés lues par `engine.get_watering_quantity()`. Le calcul de volume est donc effectivement exercé.

---

### Fichier `plantiq_backup_YYYY-MM-DD.json`

**Produit par :** `backup.run()`
**Écrit dans :** `BACKUP_PATH/plantiq_backup_YYYY-MM-DD.json` (local).

Export JSON des 11 tables, horodaté, avec sérialisation des types PostgreSQL (UUID, datetime, Decimal). Écrase le fichier du jour si `make backup` est relancé deux fois le même jour.

---

## 12. Glossaire des technologies

### Python 3.13

Langage principal. Dans ce projet : utilisé sans async (tout est synchrone), avec `zoneinfo` (stdlib) pour les fuseaux horaires, `math.pi` pour le calcul de volume de pot, `json`, `decimal`, `uuid` pour le module backup. Dicts Python simples privilégiés sur les dataclasses pour la flexibilité avec les données SQL.

### SQLAlchemy 2.0

Utilisé uniquement en **mode SQL brut** (`text("SELECT ...")`). Pas d'ORM, pas de modèles déclaratifs. Ce qui est utilisé : pool de connexions (`create_engine`), paramètres nommés (`:param`), compatibilité avec psycopg3. Pattern de transaction : `engine.connect()` + `conn.commit()` / `conn.rollback()` explicites.

### psycopg3 (`psycopg[binary]==3.3.4`)

Driver PostgreSQL nouvelle génération. Variante `[binary]` : wheel précompilé, évite de compiler les extensions C. Contrainte critique : `::type` PostgreSQL pour les casts ENUM est incompatible avec les paramètres nommés SQLAlchemy. Contournement systématique : `CAST(:param AS enum_type)`.

### httpx

Client HTTP synchrone moderne. Deux usages : `httpx.get()` pour OWM, `httpx.post()` pour ntfy. Timeout 10s sur chaque appel. `raise_for_status()` utilisé sur les deux.

### ntfy

Service de push notifications open-source. Abonnement via l'app mobile ntfy au topic `plantiq`. Notifications envoyées par POST HTTP : body = texte brut bytes, titre dans le header `Title` (ASCII only). Topic public non authentifié. `raise_for_status()` : les erreurs HTTP 4xx/5xx déclenchent un rollback de la règle concernée.

### Supabase

PostgreSQL hébergé avec dashboard web. Connexion directe psycopg3 via `DATABASE_URL` — pas de SDK Supabase. ENUMs PostgreSQL natifs : `notif_type` (`warning`, `health_check`, `repotting`, `watering`, `misting`, `fertilizing`), `notif_trigger` (`schedule`, `weather`, `health_status`), `weather_condition` (`sunny`, `cloudy`, `rainy`, `stormy`, `snowy`), `care_action` (`watering`, `fertilizing`, `misting`, `repotting`, `pruning`, `treating `).

### GitHub Actions

Deux workflows. `ci.yml` : lint + tests sur push/PR, Python natif sur `ubuntu-latest`, secrets en placeholder. `daily-run.yml` : run quotidien à 18h UTC via cron + `workflow_dispatch`, secrets de production injectés via `${{ secrets.KEY }}`. Aucune image Docker déployée — Python natif.

### Pattern — Batch loading

Toutes les données satellites de toutes les plantes sont chargées en 8 requêtes SQL (une par table), avec `WHERE plant_id = ANY(:ids)`, puis réorganisées en dicts Python indexés par `plant_id`. Évite N×8 requêtes et réduit la latence réseau avec Supabase cloud.

### Pattern — DISTINCT ON (PostgreSQL)

Retourne la première ligne de chaque groupe sans subquery. Dans ce projet : `DISTINCT ON (plant_id) ORDER BY plant_id, observed_at DESC NULLS LAST` pour `plant_health`, `DISTINCT ON (plant_id, action) ORDER BY plant_id, action, done_at DESC NULLS LAST` pour `care_logs` et `notifications_log`. Spécifique à PostgreSQL.

### Pattern — Monkey-patching en test

`engine_dry.py` remplace temporairement `eng.send` par `capture_send` pour intercepter les notifications sans modifier les règles. Le `finally` garantit la restauration même en cas d'exception.

### Pattern — Déduplication par `notifications_log`

Avant d'envoyer, `_recently_notified()` vérifie si une notification du même type a été envoyée dans la fenêtre de dédup (1j, 3j, 7j, 15j, 30j ou = fréquence calculée). Évite le spam sans état partagé externe.

### Pattern — CAST ENUM systématique

`CAST(:param AS notif_type)` dans tous les `INSERT` sur des colonnes ENUM. La notation `':param::notif_type'` est incompatible avec le parsing des paramètres nommés SQLAlchemy/psycopg3.

### Pattern — Commit par règle

Chaque règle dans `run_engine()` est enveloppée dans son propre `try/except`. Le `conn.commit()` est appelé immédiatement après le succès de la règle. Un `conn.rollback()` n'annule que la règle qui a échoué — les règles précédentes déjà commitées restent persistées. Garantit la cohérence entre les notifications ntfy envoyées et les entrées `notifications_log`.

---

## 13. Risques et limites connus

### Échec OWM silencieux

**Description :** `_store_weather()` catch toute exception et retourne `None`. Les règles reçoivent `weather = None`.
**Impact :** `_rule_weather_warning` ne déclenche pas. `_rule_watering` calcule sans modificateurs météo. `_rule_misting` ne déclenche pas (humidity par défaut = 100 >= 50).
**Mitigation actuelle :** `log.exception()` — type d'exception, message et traceback complets dans les logs GitHub Actions. L'échec est visible dans les logs du run sans faire échouer le run.
**Action corrective :** Vérifier les logs du step `Run scheduler` dans GitHub Actions → onglet job du run concerné.

### Topic ntfy public non authentifié

**Description :** Le topic `plantiq` sur ntfy.sh est public. N'importe qui connaissant le nom peut s'abonner.
**Impact :** Fuite d'informations personnelles sur les plantes.
**Mitigation actuelle :** Nom de topic non devinable. Pas de données critiques dans les notifications.
**Action corrective :** Self-host ntfy ou utiliser un token d'accès (`Authorization: Bearer ...`).

### ENUMs PostgreSQL rigides

**Description :** `notif_type`, `notif_trigger`, `weather_condition`, `care_action` sont des ENUMs natifs. Ajouter une valeur requiert `ALTER TYPE ... ADD VALUE` + migration.
**Impact :** Aucun changement de valeur sans migration DB et redéploiement coordonné.
**Mitigation actuelle :** ENUMs stables — risque faible à court terme.

### Pas de retry sur ntfy

**Description :** Si le POST ntfy timeout (10s), retourne une erreur réseau ou HTTP 4xx/5xx, l'exception n'est pas retentée dans le même run.
**Impact :** Notification perdue pour la session du jour. Retentée le lendemain si les conditions persistent.
**Mitigation actuelle :** Timeout 10s. Acceptable en usage personnel.
