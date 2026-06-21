<!-- docs/project-reference.md -->

# plantiq — Bilan exhaustif

**Version :** V1
**Dernière mise à jour :** 2026-06-21
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

plantiq est un cron job Python personnel qui surveille des plantes d'intérieur : il évalue chaque matin si une action de soin est nécessaire (arrosage, rempotage, fertilisation, brumisation) en croisant l'état de chaque plante avec la météo locale, et envoie les alertes pertinentes via notification push.

**Ce qu'il produit :** Des notifications push envoyées sur le topic ntfy `plantiq`, des lignes dans `weather_logs` et `notifications_log` dans Supabase, et des entrées dans `care_logs` et `notification_snooze` via CLI.

**Comment il tourne :** Conteneur Docker one-shot, sans port HTTP exposé, déployé sur Fly.io avec `cron = "0 7 * * *"` (7h UTC quotidien). En local : `make run` lance un conteneur éphémère.

---

## 2. Arborescence complète

```
plantiq/
├── .devcontainer/
│   └── devcontainer.json              ← ouvre VSCode dans le conteneur scheduler
├── .github/
│   └── workflows/
│       └── ci.yml                     ← lint ruff + pytest sur push/PR
├── scheduler/                         ← service unique, cron job Python
│   ├── .dockerignore                  ← exclut .env, .git, caches du contexte build
│   ├── Dockerfile                     ← image python:3.13-slim avec libpq-dev
│   ├── pyproject.toml                 ← dépendances + config pytest et ruff
│   ├── src/
│   │   └── plantiq/                   ← package Python principal
│   │       ├── __init__.py            ← vide
│   │       ├── run.py                 ← point d'entrée de la cron
│   │       ├── engine.py              ← moteur de règles (6 règles de notification)
│   │       ├── cli.py                 ← CLI interactif (log soin + snooze)
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
│       ├── test_database.py           ← test connexion + requête SQL mockée
│       ├── test_notify.py             ← test envoi ntfy mocké
│       ├── test_weather.py            ← test appel OWM mocké
│       └── test_simulation.py         ← simulation moteur, 6 fixtures, rapport MD
├── docs/
│   ├── architecture.md                ← doc initiale, partiellement obsolète (voir §9)
│   └── project-reference.md          ← ce document
├── .editorconfig                      ← UTF-8, LF, indent 4 (2 pour YAML/TOML)
├── .env                               ← secrets locaux (non commité)
├── .env.example                       ← template des 3 secrets requis
├── .gitignore                         ← exclut .env, caches, simulation_report.md
├── docker-compose.yml                 ← service scheduler + réseau bridge
├── fly.toml                           ← config déploiement Fly.io + cron schedule
├── Makefile                           ← raccourcis de toutes les commandes
└── README.md                          ← installation rapide + déploiement Fly.io
```

---

## 3. Fichiers racine

### `docker-compose.yml`

Définit un seul service `scheduler` (conteneur `plantiq_scheduler`), construit depuis `./scheduler`. `restart: "no"` confirme le caractère one-shot : le conteneur s'arrête après chaque exécution sans redémarrer. Deux volumes sont montés en mode dev : `./scheduler/src:/app/src` et `./scheduler/tests:/app/tests`, ce qui permet de modifier le code sans reconstruire l'image. Les variables d'env sont injectées depuis le `.env` racine via `env_file: .env`. Un réseau bridge `plantiq_network` est créé mais ne connecte aucun autre service — il n'y a pas de base de données locale, tout est dans Supabase cloud.

Modifier ce fichier : si un service d'infrastructure local est ajouté (cache, worker séparé…), ou pour changer les chemins de montage dev.

### `Makefile`

| Commande | Action exacte |
|---|---|
| `make build` | `docker compose build` — reconstruit l'image après modification du Dockerfile ou de `pyproject.toml` |
| `make run` | `docker compose run --rm scheduler python -m plantiq.run` — exécution manuelle de la cron |
| `make test` | `docker compose run --rm scheduler pytest` — lance les 4 fichiers de test |
| `make lint` | `docker compose run --rm scheduler ruff check .` — vérifie E, F, I, UP (sauf E501) |
| `make log` | `docker compose run --rm scheduler python -m plantiq.cli` — CLI interactif de saisie |
| `make simulate` | `docker compose run --rm scheduler python tests/test_simulation.py` — dry-run, génère rapport MD |
| `make sh` | `docker compose run --rm scheduler bash` — shell interactif dans le conteneur |
| `make logs` | `docker compose logs -f` — tail des logs du dernier run |
| `make deploy` | `fly deploy` — déploie sur Fly.io depuis le poste local |
| `make help` | Affiche toutes les commandes avec leur description |

### `.env` / `.env.example`

| Variable | Obligatoire | Exemple | Description |
|---|---|---|---|
| `DATABASE_URL` | oui | `postgresql+psycopg://postgres:<pwd>@db.<ref>.supabase.co:5432/postgres` | URL complète psycopg3 vers Supabase. Port 5432 (connexion directe) ou 6543 (transaction pooler). |
| `OPENWEATHERMAP_API_KEY` | oui | `a1b2c3d4...` | Clé API OWM. Plan gratuit suffisant (1 appel par lieu unique, 1x/jour). |
| `NTFY_TOPIC` | oui | `plantiq` | Nom du topic ntfy. Toutes les notifications vont sur `https://ntfy.sh/{NTFY_TOPIC}`. |
| `LOG_LEVEL` | non | `INFO` | Niveau de log Python. Défaut : `INFO` si absent. |

Circulation des variables : `.env` (racine) → Docker Compose (`env_file: .env`) → process du conteneur → `core/config.py` (`os.environ["KEY"]`). En production Fly.io, les secrets sont injectés directement par `fly secrets set` — aucun `.env` sur le serveur.

### `.gitignore`

- `.env` — secrets locaux, jamais commités
- `*.pyc`, `__pycache__/`, `.pytest_cache/`, `*.egg-info/`, `dist/` — artefacts Python
- `.venv/` — virtualenv local éventuel
- `scheduler/tests/simulation_report.md` — rapport de simulation (varie à chaque run, sans valeur de versionnage)

### `.editorconfig`

UTF-8, fins de ligne LF, indentation 4 espaces pour tous les fichiers. Exception : 2 espaces pour `.yml`, `.yaml`, `.toml`. Espaces de fin de ligne supprimés automatiquement. Newline finale obligatoire. Les fichiers `.md` conservent les espaces de fin (nécessaire pour les line breaks Markdown).

### `README.md`

Description en une phrase, `Getting started` (3 commandes : `cp .env.example .env`, `make build`, `make run`), et les commandes de déploiement Fly.io. Intentionnellement court — la documentation complète est dans `docs/`.

### `fly.toml`

Déploiement en région `cdg` (Paris). Pointe sur `scheduler/Dockerfile`. Le process `app` exécute `python -m plantiq.run`. `[schedule] cron = "0 7 * * *"` déclenche l'exécution quotidienne à 7h UTC. VM : `shared-cpu-1x`, 256 MB RAM. Aucun port exposé (`[[services]]` absent).

---

## 4. Infrastructure et environnement

### Vue d'ensemble de la stack

```
docker-compose.yml
  └── service: scheduler   ← cron job Python, one-shot
        build: ./scheduler
        container: plantiq_scheduler
        volumes: src/ + tests/ (hot-reload dev)
        env_file: .env
        network: plantiq_network

Services externes (pas dans compose) :
  ├── Supabase PostgreSQL   ← base de données (cloud)
  ├── OpenWeatherMap API    ← météo courante par coordonnées
  └── ntfy.sh               ← push notifications
```

### Service `scheduler`

Image construite localement depuis `./scheduler/Dockerfile`. `restart: "no"` — le conteneur ne redémarre pas après exécution. En production Fly.io, Fly.io gère le cycle de vie du conteneur selon le schedule cron. Pas de healthcheck (service one-shot, pas long-running).

### `Dockerfile` — service `scheduler`

| Étape | But |
|---|---|
| `FROM python:3.13-slim` | Image de base minimale Python 3.13 |
| `WORKDIR /app` | Répertoire de travail pour toutes les commandes suivantes |
| `apt-get install build-essential libpq-dev` | Compilateurs C et headers PostgreSQL — requis pour compiler psycopg |
| `COPY pyproject.toml .` + `pip install -e ".[dev]"` | Installe les dépendances **avant** de copier le code source — cette couche est mise en cache et ne se recrée que si `pyproject.toml` change |
| `mkdir -p src` | Crée `src/` pour satisfaire l'installation editable avant que le vrai code soit copié |
| `COPY src/ ./src/` | Copie le code source de production |
| `COPY tests/ ./tests/` | Copie les tests (nécessaire pour `make test` et `make simulate`) |
| Pas de `CMD` | La commande est définie par usage (`make run`, `make test`, `make sh`…), pas dans l'image |

### Dev Container

`.devcontainer/devcontainer.json` utilise le `docker-compose.yml` existant, service `scheduler`, workspace `/app`. `shutdownAction: stopCompose` arrête les conteneurs à la fermeture de VSCode. `overrideCommand: true` empêche le démarrage automatique d'un process.

Extensions installées automatiquement : `ms-python.python` (IntelliSense), `ms-python.vscode-pylance` (type checking avec `extraPaths: ["src"]`), `charliermarsh.ruff` (lint + format on save), `ms-azuretools.vscode-docker`.

Activation : `Ctrl+Shift+P → Dev Containers: Reopen in Container`. Pylance utilise l'interpréteur du conteneur (`/usr/local/bin/python`). Tout le code s'exécute dans le conteneur — aucun interpréteur local requis.

---

## 5. Package principal — structure interne

### Choix d'organisation

Le code de production vit dans `scheduler/src/plantiq/` — c'est le **src layout**. Le package `plantiq` n'est pas importable directement depuis le répertoire `scheduler/` : il faut qu'il soit installé (`pip install -e .`). Cette contrainte garantit que les imports fonctionnent identiquement en dev, en test et en production (pas de `sys.path` manipulé, pas de risque d'importer accidentellement le dossier `src/` au lieu du package installé).

Les tests dans `scheduler/tests/` sont séparés du package. `pyproject.toml` déclare `testpaths = ["tests"]` pour que pytest les trouve depuis `/app` dans le conteneur.

### `pyproject.toml`

**Dépendances de production :**

| Package | Version | Rôle dans ce projet |
|---|---|---|
| `httpx` | `==0.27.2` | Appels HTTP synchrones vers OWM (`GET /data/2.5/weather`) et ntfy (`POST`) |
| `psycopg[binary]` | `==3.3.4` | Driver PostgreSQL psycopg3. Variante `[binary]` : wheel précompilé, évite la compilation C locale. Utilisé par SQLAlchemy via l'URL `postgresql+psycopg://`. |
| `python-dotenv` | `==1.0.1` | Charge `.env` au démarrage via `load_dotenv(find_dotenv())` dans `config.py` |
| `sqlalchemy` | `==2.0.36` | Gestion du pool de connexions PostgreSQL et paramètres nommés. Utilisé en mode SQL brut (`text()`) exclusivement — pas d'ORM. |

**Dépendances de développement :**

| Package | Rôle |
|---|---|
| `pytest==8.3.3` | Runner de tests. Config : `testpaths = ["tests"]`. Pas de plugins additionnels. |
| `ruff==0.7.1` | Lint + format. Règles actives : E (pycodestyle), F (pyflakes), I (isort), UP (pyupgrade). E501 ignorée. Longueur max : 100 caractères. `known-first-party = ["plantiq"]` pour le tri des imports. |

### Architecture des sous-packages

| Sous-package | Rôle | Peut importer | Ne doit pas importer |
|---|---|---|---|
| `core/` | Infrastructure transverse : config, DB, logs | stdlib uniquement | Tout module métier (`engine`, `notify`, `weather`, `cli`) |
| `engine.py` | Moteur de règles central | `core/`, `notify`, `weather`, stdlib | `cli`, `run` |
| `notify.py` | Envoi ntfy | `core/` | Autres modules métier |
| `weather.py` | Appel OWM | `core/` | Autres modules métier |
| `cli.py` | Interface interactive | `core/` | `engine`, `notify`, `weather` |
| `run.py` | Point d'entrée | `core/`, `engine` | Tout le reste |

---

## 6. Modules — détail fonctionnel

### `core/config.py`

**Rôle :** Point d'entrée unique pour les variables d'environnement. Exécuté à l'import — charge le `.env` immédiatement via `load_dotenv(find_dotenv())`, puis lit les variables.

**Expose :**

| Constante | Type | Comportement si absente |
|---|---|---|
| `DATABASE_URL` | `str` | Lève `KeyError` au démarrage |
| `OPENWEATHERMAP_API_KEY` | `str` | Lève `KeyError` au démarrage |
| `NTFY_TOPIC` | `str` | Lève `KeyError` au démarrage |
| `LOG_LEVEL` | `str` | Défaut `"INFO"` |

**Utilisé par :** `core/database.py`, `notify.py`, `weather.py`.

**Règle :** Ne jamais accéder à `os.environ` directement dans un autre module. Toujours passer par les constantes de `config.py`.

---

### `core/database.py`

**Rôle :** Crée et expose l'engine SQLAlchemy global. Module minimaliste — 2 lignes effectives.

**Expose :** `engine` (instance `sqlalchemy.Engine`)

**Pattern :** `engine.connect()` utilisé comme context manager dans chaque point d'usage (`engine.py`, `cli.py`). SQLAlchemy gère un pool de connexions implicitement. Les transactions sont explicites : `conn.commit()` et `conn.rollback()` sont appelés manuellement.

**Note :** L'engine est créé à l'import du module (pas lazy). Un `DATABASE_URL` au format invalide échoue ici, pas lors de la première requête.

---

### `core/logging.py`

**Rôle :** Fabrique de loggers nommés. Configure le handler racine à chaque appel.

**Expose :** `get_logger(name: str) → logging.Logger`

**Format de log :** `%(asctime)s %(levelname)s %(message)s`

**Usage :** `log = get_logger(__name__)` en tête de chaque module métier.

---

### `run.py`

**Rôle :** Point d'entrée de la cron. Appelé par `python -m plantiq.run` (Makefile et Fly.io).

**Ce qu'il fait :** Log "Scheduler starting", appelle `run_engine()`, log "Scheduler run complete". Pas de gestion d'erreur propre — une exception non catchée dans `run_engine` remonte et fait échouer le process avec code 1 (visible dans les logs Fly.io).

---

### `weather.py`

**Rôle :** Wrapper HTTP vers l'API OpenWeatherMap current weather. Retourne la réponse JSON brute sans transformation.

**Expose :** `get_weather(lat: float, lon: float) → dict`

| Fonction | Signature | Ce qu'elle fait |
|---|---|---|
| `get_weather` | `(lat: float, lon: float) → dict` | GET OWM `/data/2.5/weather`, params `units=metric`, timeout 10s, lève sur HTTP non-2xx |

**Sortie (structure OWM) :** Dict avec clés `main` (temp_min, temp_max, humidity), `weather` (liste, clé `main` = Clear/Clouds/Rain…), `wind` (speed). La normalisation vers les ENUMs internes est faite dans `engine._store_weather()`.

---

### `notify.py`

**Rôle :** Envoi d'une notification push via ntfy.sh.

**Expose :** `send(title: str, body: str) → None`

| Fonction | Signature | Ce qu'elle fait |
|---|---|---|
| `send` | `(title: str, body: str) → None` | POST ntfy avec body UTF-8 et header Title ASCII, log la confirmation |

**Contrainte critique :** Le header HTTP `Title` doit être **ASCII uniquement**. Les caractères non-ASCII (accents, em-dashes…) causent une `UnicodeEncodeError`. Les titres de toutes les règles utilisent des tirets simples (` - `) et pas d'accents.

**Format de la requête :** `content=body.encode()` (bytes), `Content-Type: text/plain; charset=utf-8`. URL : `https://ntfy.sh/{NTFY_TOPIC}`. Timeout 10s. Pas d'authentification.

---

### `cli.py`

**Rôle :** Interface interactive en ligne de commande pour logger un soin ou snoozer une notification. Lancé manuellement avec `make log` — jamais par la cron.

**Ce qu'il fait :** Charge toutes les plantes depuis Supabase (triées par nom), affiche un menu à 3 choix, boucle jusqu'à quitter.

**Fonctions internes :**

| Fonction | Ce qu'elle fait |
|---|---|
| `_pick(prompt, options)` | Menu numéroté, boucle jusqu'à saisie valide |
| `_load_plants(conn)` | `SELECT id, name FROM plants ORDER BY name` |
| `_log_action(conn, plants)` | Saisie : plante → action → quantité ml (optionnel) → note (optionnel) → `INSERT care_logs` |
| `_snooze(conn, plants)` | Saisie : plante → type notif → date JJ/MM/AAAA (optionnel) → `INSERT notification_snooze` |

**ENUMs hardcodés :**
- `CARE_ACTIONS` : `watering`, `fertilizing`, `misting`, `repotting`, `pruning`, `treatment`
- `NOTIF_TYPES` : `warning`, `health_check`, `repotting`, `watering`, `misting`, `fertilizing`

**Pattern snooze :** `ON CONFLICT (plant_id, notif_type, done) DO UPDATE` — met à jour un snooze actif existant plutôt que d'en créer un doublon. La contrainte UNIQUE porte sur `(plant_id, notif_type, done)` — une seule ligne active (`done = false`) par combinaison plante + type.

---

### `engine.py`

**Rôle :** Moteur central. Charge les données depuis Supabase, évalue 6 règles de notification pour chaque plante dans l'ordre de priorité, et persiste la météo et les notifications.

**Constantes globales :**

| Constante | Valeur | Usage |
|---|---|---|
| `TZ` | `Europe/Brussels` | Toutes les comparaisons de dates |
| `SUMMER_MONTHS` | `range(4, 10)` (avril–septembre inclus) | Saison pour fréquence d'arrosage et activation de la fertilisation |
| `_OWM_CONDITION` | `Clear→sunny`, `Clouds→cloudy`, `Rain/Drizzle→rainy`, `Thunderstorm→stormy`, `Snow→snowy` | Normalisation OWM → ENUM `weather_condition` |
| `_WATERING_MODE_LABELS` | `soil_only`, `leaves`, `misting`, `mixed` → libellés FR | Corps des notifications d'arrosage |

**Helpers de calcul :**

| Fonction | Ce qu'elle fait |
|---|---|
| `has_mold(container)` | `True` si `soil_condition = "moldy"` ou `"mold"` dans `soil_issues` |
| `get_watering_quantity(profile, container)` | Quantité ml : `watering_quantity_ml` si défini, sinon π × r² × 0.3 × multiplicateur (`light=0.5`, `moderate=1.0`, `heavy=1.5`). Min 100 ml, arrondi à 50 ml. |
| `apply_quantity_modifiers(qty, weather, container, health)` | +20% si temp_max > 30, ×0.5 si pas de drainage, ×0.5 si surrosage, +10% si terracotta. Min 50 ml. |
| `_days_since(done_at, tz, today)` | Jours depuis une datetime ou date. Retourne 999 si `None`. |
| `_recently_notified(last, days, today, tz)` | `True` si `sent_at` dans `last` est il y a moins de `days` jours |
| `_season(today)` | `"summer"` (avril–septembre) ou `"winter"` |

**Helpers de persistance :**

| Fonction | Ce qu'elle fait |
|---|---|
| `_store_weather(conn, location_id, lat, lon, today)` | Appelle OWM, normalise, upsert `weather_logs` (`ON CONFLICT location_id + date DO UPDATE`). Retourne `None` si OWM échoue. |
| `_log_notification(conn, plant_id, notif_type, message, triggered_by)` | `INSERT notifications_log` avec `CAST(:type AS notif_type)` et `CAST(:triggered_by AS notif_trigger)` |
| `_notify(conn, plant, notif_type, title, body, triggered_by)` | Appelle `send()` (ntfy) puis `_log_notification()`. Si `send()` échoue, `_log_notification()` n'est pas appelé. |

**Les 6 règles — vue synthétique :**

| Règle | Type notif | Dédup | Bloqueurs principaux |
|---|---|---|---|
| `_rule_weather_warning` | `warning` | 1 jour | `dying`, snooze, pas de météo, aucun seuil dépassé |
| `_rule_health_check` | `health_check` | 3j (dying) / 7j (sick/recovering) / 15j (autres) | `healthy` ou `None`, snooze |
| `_rule_repotting` | `repotting` | 30 jours | `dying` sauf si `repotting_urgent`, snooze |
| `_rule_watering` | `watering` | = fréquence calculée | `dying`, `burned`, `waterlogged`, snooze |
| `_rule_misting` | `misting` | 3 jours | `humidity_level != "high"`, moisissures, humidité > 50% sans clim/chauffage, snooze |
| `_rule_fertilizing` | `fertilizing` | = fréquence profil | Hors saison, sol `exhausted`/`waterlogged`/moisi, `sick`/`dying`/`dormant`/`recovering`, rempotage < 60j, snooze |

**`_rule_weather_warning` — 5 conditions déclenchantes :**
1. `temp_max > temp_max_c` du profil → arrosage prioritaire (ou "surveiller l'humidité" si surrosage en cours)
2. `temp_min < temp_min_c` du profil → protéger la plante
3. `temp_max > 35` en intérieur sans clim → chaleur critique
4. `uv_index > 8` avec lumière directe proche → risque de brûlure
5. `temp_min < 2` en extérieur → risque de gel

**`_rule_repotting` — 3 déclencheurs évalués dans l'ordre :**
- A (prioritaire) : `repotting_urgent = true` — passe même sur une plante mourante
- B (calendaire) : `months_since >= repotting_frequency_months` du profil
- C (sol) : `soil_condition` in `(exhausted, moldy, compacted, waterlogged)` ou moisissures dans `soil_issues`

Si `status = "sick"` au moment d'envoyer : envoie `warning` ("attendre stabilisation") et return, au lieu de `repotting`.

**`_rule_watering` — modificateurs de fréquence (appliqués sur la fréquence de base été/hiver) :**

| Condition | Modification |
|---|---|
| `temp_max > 35` | -5 jours |
| `temp_max > 30` | -3 jours |
| `temp_max < 10` | +3 jours |
| Extérieur + humidité > 80% | +2 jours |
| Extérieur + pluie | +2 jours |
| Extérieur + orage | +3 jours |
| Ombre | +3 jours |
| Près clim | -1 jour |
| Près chauffage | -1 jour |
| Terracotta ou fabric | -2 jours |
| Pas de drainage | +2 jours |
| Cachepot présent | +1 jour |
| Cachepot sans billes d'argile | +1 jour supplémentaire |
| `issue_type = overwatering` | +5 jours |
| `issue_type = underwatering` | -3 jours |
| `status = dormant` | × 2 (fréquence doublée) |

Résultat final : `max(1, int(freq))`. Si `status = dormant` : quantité également réduite de 50% après `apply_quantity_modifiers`.

**`_rule_fertilizing` — avertissement substrat compacté :**
N'est pas un bloqueur. Si `soil_condition = "compacted"`, ajoute dans le corps de la notification : "Substrat compacté - fertiliser avec une dose réduite de moitié."

**`run_engine()` — séquence complète :**

1. Charge toutes les plantes avec leur localisation (JOIN `plants` + `locations`)
2. Pour chaque lieu unique : appelle OWM, upsert `weather_logs`, commit
3. Batch load en 8 requêtes parallèles (une par table) via `ANY(:ids)` :
   `plant_profile`, `plant_location`, `plant_container`, `plant_accessories`, `plant_health`, `care_logs`, `notifications_log`, `notification_snooze`
4. Pour chaque plante : résout ses snoozes actifs (`set`), évalue les 6 règles dans l'ordre de priorité, commit. Exception → rollback (plante sautée, suivante traitée).

**Pattern DISTINCT ON :** Utilisé pour récupérer le dernier état de santé par plante (`plant_health`) et le dernier soin par action par plante (`care_logs`). Spécifique à PostgreSQL — plus efficace qu'une subquery avec `ROW_NUMBER()`.

**Pattern CAST ENUM :** `CAST(:param AS notif_type)` systématique dans tous les `INSERT`/`SELECT` sur des colonnes ENUM. La notation `::` PostgreSQL native (`':param::notif_type'`) est incompatible avec le parsing des paramètres nommés SQLAlchemy/psycopg3.

---

## 7. Tests

**Répertoire :** `scheduler/tests/`

### `conftest.py`

Force-set des 3 variables d'environnement obligatoires **avant** tout import de `config.py`. Nécessaire car `config.py` appelle `os.environ["KEY"]` à l'import (pas lazy) — sans ce patch, pytest lèverait `KeyError` lors de la collecte des modules.

```python
import os
os.environ["DATABASE_URL"] = "postgresql+psycopg://test:test@localhost:5432/test"
os.environ["OPENWEATHERMAP_API_KEY"] = "test_owm_key"
os.environ["NTFY_TOPIC"] = "plantiq"
```

`os.environ["KEY"] = "value"` (et non `setdefault`) est volontaire : `load_dotenv()` dans `config.py` peut pré-charger un vrai `.env` local avec de vraies clés avant que `conftest.py` tourne. `setdefault` ne surchargerait pas les valeurs déjà présentes.

### Fichiers de test

| Fichier | Ce qu'il teste | Patterns utilisés |
|---|---|---|
| `test_database.py` | Que l'engine SQLAlchemy peut exécuter une requête et retourner des lignes | `MagicMock`, `patch("plantiq.core.database.engine", ...)`, import side-effect explicite avant le patch |
| `test_weather.py` | Que `get_weather()` appelle OWM avec les bons paramètres lat/lon et retourne le JSON | `patch("plantiq.weather.httpx.get", ...)`, assert sur `call_args` |
| `test_notify.py` | Que `send()` appelle ntfy avec `content=bytes`, le bon topic et les bons headers | `patch("plantiq.notify.httpx.post", ...)`, assert sur les kwargs |
| `test_simulation.py` | Dry-run des 6 règles sur 6 fixtures botaniques avec contexte aléatoire | `run_dry()` via `engine_dry.py`, génère `tests/simulation_report.md` |

**Note `test_database.py` :** `import plantiq.core.database  # noqa: F401` avant le `patch()` est obligatoire. Sans cet import, `patch("plantiq.core.database.engine", ...)` échoue avec `AttributeError` car le module n'est pas encore chargé dans `sys.modules`.

### `engine_dry.py` (infrastructure test, pas un `test_*.py`)

Wrapper qui importe les 6 fonctions de règle depuis `engine.py` et les exécute sans DB ni ntfy. Mécanisme :
- Monkey-patch de `eng.send` par `capture_send` qui accumule les notifications dans une liste
- `MockConn` qui ignore tous les appels (`execute`, `commit`, `rollback`)
- `last_notifs = {}` : aucun historique → toutes les règles peuvent déclencher
- `snoozes = set()` : aucun snooze actif
- `finally` : restaure `eng.send` même si une règle lève une exception

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

```python
# scheduler/tests/test_engine_rules.py
from datetime import date
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from plantiq.engine import _rule_watering

def test_watering_skips_when_waterlogged():
    conn = MagicMock()
    plant = {"id": "abc", "name": "Monstera", "city": "Paris"}
    profile = {
        "watering_frequency_days_summer": 7, "watering_frequency_days_winter": 14,
        "watering_amount": "moderate", "watering_mode": "soil_only",
        "watering_quantity_ml": None, "watering_instructions": "",
    }
    container = {"soil_condition": "waterlogged", "pot_size_cm": 20,
                  "pot_type": "plastic", "has_drainage": True}
    with patch("plantiq.engine.send") as mock_send:
        _rule_watering(conn, plant, profile, None, container, [], None, None,
                       {}, {}, set(), date(2026, 6, 21), ZoneInfo("Europe/Brussels"))
    mock_send.assert_not_called()
```

---

## 8. CI/CD

### `ci.yml` — Pipeline principal

**Déclencheurs :** Push sur `main` ou `develop`, pull request vers `main`.

**Étapes dans l'ordre :**

1. `actions/checkout@v4` — clone le repo
2. `actions/setup-python@v5` Python 3.13, cache `pip`
3. `pip install -e ".[dev]"` dans `./scheduler` — installe le package + ruff + pytest
4. `ruff check .` dans `./scheduler` — lint. Échoue si violation E, F, I ou UP (sauf E501)
5. `pytest` dans `./scheduler` avec les 3 env vars en valeurs placeholder — tests. Échoue si assertion échouée ou exception non-catchée

**Tourne sans Docker** : Python installé directement sur l'agent `ubuntu-latest`. Les dépendances compilées (psycopg binary) sont téléchargées comme wheels précompilés.

**Variables CI :** Les 3 env vars obligatoires sont injectées en `placeholder` dans le workflow pour éviter que `config.py` lève `KeyError`. Elles sont ensuite surchargées par `conftest.py` avec des valeurs de test. Tous les appels réseau sont mockés — aucune connexion réelle n'est tentée.

**Artefacts produits :** Aucun.

**Ce qui fait échouer la CI :**
- Violation de règle ruff (E701 inline if, E741 variable ambiguë, imports non triés…)
- Test qui lève une exception ou assertion qui échoue
- `KeyError` sur une variable d'env non couverte par le workflow ou `conftest.py`

---

## 9. Documentation

| Fichier | Contenu | Quand le consulter |
|---|---|---|
| `docs/project-reference.md` | Ce document — référence exhaustive et à jour | Onboarding, compréhension globale, débogage |
| `docs/architecture.md` | Vue d'ensemble initiale (flux, décisions). **Partiellement obsolète** : référence encore Bark API et `BARK_TOKEN`, remplacés par ntfy. | Ne pas consulter sans vérification préalable. Nécessite une mise à jour. |
| `README.md` | Démarrage en 3 commandes + déploiement Fly.io | Premier contact avec le projet |

---

## 10. Flux d'exécution complet

### Exécution nominale (`make run`)

```
docker compose run --rm scheduler python -m plantiq.run
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
  │           plant_accessories, plant_health, care_logs,
  │           notifications_log, notification_snooze
  │    Écrit : —
  │
  └─ Étape 4 : Évaluation des règles par plante
       Pour chaque plante (résout snoozes actifs, puis) :
         ├─ _rule_weather_warning  → ntfy + notifications_log (si déclenchée)
         ├─ _rule_health_check     → ntfy + notifications_log (si déclenchée)
         ├─ _rule_repotting        → ntfy + notifications_log (si déclenchée)
         ├─ _rule_watering         → ntfy + notifications_log (si déclenchée)
         ├─ _rule_misting          → ntfy + notifications_log (si déclenchée)
         ├─ _rule_fertilizing      → ntfy + notifications_log (si déclenchée)
         └─ commit (ou rollback si exception dans une règle)
```

### Modes d'exécution alternatifs

| Commande | Ce qu'elle fait | Quand l'utiliser |
|---|---|---|
| `make simulate` | Dry-run des 6 règles sur 6 fixtures sans DB ni ntfy, génère `simulation_report.md` | Valider la logique de règles sans toucher la production |
| `make log` | CLI interactif : log un soin ou snooze une notification dans Supabase | Après une action réelle sur une plante, ou pour suspendre une alerte |
| `make test` | 4 tests unitaires avec mocks réseau | Avant chaque commit |
| `make lint` | Vérification ruff | Avant chaque commit ou pour déboguer la CI |
| `make deploy` | Reconstruit et déploie l'image sur Fly.io | Mise en production |

---

## 11. Outputs produits

### Notifications ntfy

**Produit par :** `notify.send()`
**Écrit dans :** `https://ntfy.sh/plantiq` (POST HTTP)

**Format :**

```
Header Title: Arrosage - Monstera

Dernier arrosage il y a 8 jours.
Paris : 32°C, sunny.

Comment : sur la terre uniquement - 350 ml.
Arroser au pied — ne pas mouiller les feuilles.
Chaleur importante - arrosage prioritaire.
```

**Cas particuliers :** Si ntfy est inaccessible (timeout ou erreur réseau), une exception est levée dans la règle, capturée par `run_engine`, et `conn.rollback()` est appelé. La notification n'est pas envoyée et n'est pas loggée. Elle sera retentée le lendemain si les conditions persistent. Voir §13.

---

### Table `weather_logs`

**Produit par :** `engine._store_weather()`
**Stratégie :** Upsert `ON CONFLICT (location_id, date) DO UPDATE`. Une ligne par lieu par jour.

**Exemple de ligne :**

| location_id | date | temperature_min | temperature_max | humidity | condition | uv_index | wind_speed |
|---|---|---|---|---|---|---|---|
| `uuid-loc-1` | 2026-06-21 | 17.2 | 28.5 | 62 | `sunny` | 7.3 | 3.1 |

**Cas particuliers :** Si OWM échoue, rien n'est écrit (pas de ligne avec valeurs NULL). Les règles météo-dépendantes reçoivent `weather = None` et ne déclenchent pas.

---

### Table `notifications_log`

**Produit par :** `engine._log_notification()`
**Rôle principal :** Déduplication — `_recently_notified()` lit cette table pour éviter de renvoyer la même alerte le lendemain.

**Exemple de ligne :**

| plant_id | type | message | triggered_by | sent_at |
|---|---|---|---|---|
| `uuid-1` | `watering` | `Dernier arrosage il y a 8 jours.\n...` | `schedule` | 2026-06-21 07:00:12+00 |

---

### Table `care_logs` (via CLI)

**Produit par :** `cli._log_action()`
**Format :** `INSERT care_logs (plant_id, action, quantity_ml, note)` avec CAST `care_action`. La colonne `done_at` est définie par `DEFAULT NOW()`.

---

### Table `notification_snooze` (via CLI)

**Produit par :** `cli._snooze()`
**Format :** Upsert `ON CONFLICT (plant_id, notif_type, done) DO UPDATE`. Active tant que `done = false` et `snoozed_until IS NULL OR snoozed_until >= today`. Un snooze indéfini (`snoozed_until = NULL`) supprime la notification jusqu'à ce que `done` soit mis à `true` manuellement.

---

### `scheduler/tests/simulation_report.md`

**Produit par :** `test_simulation.run_simulation()`
**Écrit dans :** Fichier local, gitignored.

Rapport Markdown avec pour chaque fixture : contexte complet (statut santé, météo, type de pot, condition du sol…) et liste des notifications qui auraient été envoyées. Reproductible avec un seed fixe (`python tests/test_simulation.py 42`). Utilisé pour valider la logique de règles sans connexion DB ni ntfy.

---

## 12. Glossaire des technologies

### Python 3.13

Langage principal. Dans ce projet : utilisé sans async (tout est synchrone), avec `zoneinfo` pour les fuseaux horaires, `math.pi` pour le calcul de volume de pot, et `dataclasses` non utilisées (dicts Python simples privilégiés pour la flexibilité avec les données SQL).

### SQLAlchemy 2.0

ORM Python, utilisé ici uniquement en **mode SQL brut** (`text("SELECT ...")`). Pas d'ORM, pas de modèles déclaratifs. Ce qui est utilisé : la gestion du pool de connexions (`create_engine`), les paramètres nommés (`:param`), la compatibilité avec psycopg3. Pattern de transaction : `engine.connect()` + `conn.commit()` / `conn.rollback()` explicites.

### psycopg3 (`psycopg[binary]==3.3.4`)

Driver PostgreSQL nouvelle génération. Dans ce projet : utilisé via SQLAlchemy (URL `postgresql+psycopg://`). Variante `[binary]` : wheel précompilé, évite de compiler les extensions C localement. Contrainte critique : `::type` PostgreSQL pour les casts ENUM est incompatible avec les paramètres nommés SQLAlchemy. Contournement systématique : `CAST(:param AS enum_type)`.

### httpx

Client HTTP synchrone moderne. Dans ce projet : deux usages — `httpx.get()` pour OWM, `httpx.post()` pour ntfy. Timeout 10s sur chaque appel. Pas de retry automatique.

### ntfy

Service de push notifications open-source. Abonnement via l'app mobile ntfy au topic `plantiq`. Notifications envoyées par POST HTTP : body = texte brut bytes, titre dans le header `Title` (ASCII only — contrainte HTTP headers). Topic public non authentifié.

### Supabase

PostgreSQL hébergé avec dashboard web. Dans ce projet : base de données principale. Pas de SDK Supabase — connexion directe psycopg3 standard via `DATABASE_URL`. Schéma V5 avec ENUMs PostgreSQL natifs : `notif_type`, `notif_trigger`, `weather_condition`, `care_action`, et ENUMs implicites pour les statuts de santé et conditions de sol.

### Fly.io

Plateforme de déploiement de conteneurs Docker. Dans ce projet : héberge le scheduler comme cron job natif (`[schedule] cron = "0 7 * * *"`). VM partagée 256 MB. Secrets injectés via `fly secrets set`. Pas de scaling — une seule VM, un seul run par jour.

### Pattern — Batch loading

Toutes les données satellites de toutes les plantes sont chargées en **8 requêtes SQL** (une par table), avec `WHERE plant_id = ANY(:ids)`, puis réorganisées en dicts Python indexés par `plant_id`. Les règles lisent ensuite ces dicts en mémoire. Ce pattern évite N×8 requêtes (une par plante × 8 tables) et réduit la latence réseau avec Supabase cloud.

### Pattern — DISTINCT ON (PostgreSQL)

Retourne la première ligne de chaque groupe sans subquery. Dans ce projet : `DISTINCT ON (plant_id) ... ORDER BY plant_id, observed_at DESC NULLS LAST` pour `plant_health` (dernier état de santé par plante), et `DISTINCT ON (plant_id, action) ... ORDER BY plant_id, action, done_at DESC NULLS LAST` pour `care_logs` (dernier soin par action par plante). Spécifique à PostgreSQL, plus concis qu'un `ROW_NUMBER()` avec CTE.

### Pattern — Monkey-patching en test

`engine_dry.py` remplace temporairement `eng.send` au niveau du module par `capture_send`, ce qui permet d'intercepter les notifications sans passer de `send` en paramètre aux règles. Le `finally` garantit la restauration même en cas d'exception dans une règle. Les règles n'ont pas besoin de connaître leur contexte de test.

### Pattern — Déduplication par `notifications_log`

Chaque notification envoyée est loggée dans `notifications_log`. Avant d'envoyer, `_recently_notified()` vérifie si une notification du même type a été envoyée dans la fenêtre de dédup (1j, 3j, 7j, 15j, 30j ou = fréquence calculée). Ce mécanisme évite le spam sans état partagé externe (pas de Redis, pas de fichier).

---

## 13. Risques et limites connus

### Inconsistance send + log sur erreur

**Description :** `_notify()` appelle `send()` (ntfy POST) puis `_log_notification()` (write DB), dans cet ordre, dans le même bloc `try`. Si une exception survient après que `send()` réussit mais avant `conn.commit()`, le `rollback()` efface l'entrée `notifications_log`. La notification a été envoyée, mais le moteur n'en a aucune trace.
**Impact :** Doublon de notification possible le lendemain pour la même plante et le même type.
**Mitigation actuelle :** Aucune. Acceptable en usage mono-utilisateur personnel.
**Action corrective si ça arrive :** Inverser l'ordre (DB d'abord, ntfy ensuite), ou implémenter un pattern outbox (écrire en DB, envoyer en ntfy séparément).

### Échec OWM silencieux

**Description :** `_store_weather()` catch toute exception et retourne `None`. Les règles reçoivent `weather = None`.
**Impact :** `_rule_weather_warning` ne déclenche pas. `_rule_watering` calcule la fréquence sans modificateurs météo. `_rule_misting` assume humidité 100% (ne déclenche pas).
**Mitigation actuelle :** Log de l'erreur uniquement.
**Action corrective si ça arrive :** Vérifier la clé API OWM et les logs Fly.io.

### `docs/architecture.md` obsolète

**Description :** Référence encore Bark API (`BARK_TOKEN`) remplacée par ntfy au cours du projet.
**Impact :** Confusion pour toute personne lisant ce document.
**Action corrective :** Réécrire `docs/architecture.md` ou le supprimer (ce document le remplace).

### Topic ntfy public non authentifié

**Description :** Le topic `plantiq` sur ntfy.sh est public. N'importe qui connaissant le nom peut s'abonner et lire les notifications.
**Impact :** Fuite d'informations personnelles sur les plantes (et indirectement, patterns de présence/absence).
**Mitigation actuelle :** Nom de topic non devinable. Pas de données critiques dans les notifications.
**Action corrective :** Self-host ntfy ou utiliser un topic avec token d'accès (`Authorization: Bearer ...`).

### ENUMs PostgreSQL rigides

**Description :** Les types `notif_type`, `notif_trigger`, `weather_condition`, `care_action` sont des ENUMs PostgreSQL natifs. Ajouter une valeur requiert `ALTER TYPE ... ADD VALUE` + migration.
**Impact :** Aucun changement de valeur possible sans migration DB et redéploiement coordonné.
**Mitigation actuelle :** ENUMs stables en V1 — risque faible à court terme.

### Pas de retry sur ntfy

**Description :** Si le POST ntfy timeout (10s) ou retourne une erreur HTTP, l'exception n'est pas retentée dans le même run.
**Impact :** Notification perdue pour la session du jour. Elle sera retentée le lendemain si les conditions persistent (arrosage non fait, etc.).
**Mitigation actuelle :** Timeout 10s. Acceptable en usage personnel avec une plante par run.
