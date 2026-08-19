<!-- docs/project-reference.md -->

# plantiq — Bilan exhaustif

**Version :** V5
**Dernière mise à jour :** 2026-08-19
**Statut :** En développement — chaîne technique fonctionnelle, moteur de décision unifié, trois consommateurs de données absents

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

plantiq suit les plantes d'intérieur d'un foyer unique : espèce, contenant, position exacte sur le plan d'une pièce, état de santé observé. Chaque jour il décide si un soin est dû, en tenant compte de ce que la plante vit à l'intérieur et non de ce que mesure la station météo.

**Ce qu'il produit :** notifications push ntfy, rappels et traçabilité dans PostgreSQL (Supabase), relevés météo quotidiens, exports JSON de la base entière.

**Comment il tourne :** un package Python, deux modes. Interface Flask dans un conteneur Docker sur le port 8000 pour la saisie et la consultation. Batch quotidien `python -m plantiq.run` sur GitHub Actions à 16:00 UTC, sans Docker.

**Changements depuis V3 :** aucun changement de code. V5 est une révision de fidélité du document, vérifiée par comptage contre les sources :

- arborescence remise à jour — 73 fichiers, `docs/test-batch-2026-08-19.md` était absent de l'arbre ;
- `context()` exécute neuf requêtes, pas huit ;
- l'exemple de payload du §11 est remplacé par un payload réellement observé, clé `alert` incluse ;
- les anomalies 5.1 à 5.5 du rapport du 19/08 deviennent des entrées de plein droit au §13, au lieu d'une mention incidente ;
- ajout au §13 du code mort et des duplications relevés à la lecture : `weather.for_site`, le paramètre `tolerance` de `point_in_polygon`, `Exposure.width_m`, `HEATING_MONTHS`, le double `assess()` par notification.

---

## 2. Arborescence complète

```text
plantiq/
├── .devcontainer/                     ← vide, aucun devcontainer.json
├── .github/
│   └── workflows/
│       ├── ci.yml                     ← lint et tests sur main
│       └── daily-run.yml              ← batch quotidien 16:00 UTC
├── app/                               ← service applicatif unique
│   ├── Dockerfile                     ← image python:3.13-slim
│   ├── pyproject.toml                 ← dépendances et config outils
│   ├── src/
│   │   └── plantiq/
│   │       ├── __init__.py            ← vide
│   │       ├── backup.py              ← export JSON de toutes les tables
│   │       ├── restore.py             ← rechargement d'un export
│   │       ├── run.py                 ← orchestrateur du batch
│   │       ├── schema.py              ← application de db/schema.sql
│   │       ├── weather.py             ← collecte des relevés
│   │       ├── adapters/
│   │       │   ├── __init__.py
│   │       │   ├── notify.py          ← publication ntfy
│   │       │   ├── probe.py           ← exploration des champs OWM
│   │       │   └── weather.py         ← appel et normalisation OWM
│   │       ├── core/
│   │       │   ├── __init__.py
│   │       │   ├── config.py          ← variables d'environnement
│   │       │   ├── database.py        ← connexion psycopg
│   │       │   └── logging.py         ← fabrique de loggers
│   │       ├── engine/
│   │       │   ├── __init__.py
│   │       │   ├── climate.py         ← conditions intérieures
│   │       │   ├── geometry.py        ← polygones et projections
│   │       │   ├── light.py           ← exposition lumineuse
│   │       │   └── rules.py           ← contexte, facteurs, verdicts, messages
│   │       └── web/
│   │           ├── __init__.py        ← vide
│   │           ├── app.py             ← fabrique Flask
│   │           ├── static/
│   │           │   └── plan.js        ← rendu SVG partagé
│   │           ├── templates/
│   │           │   ├── base.html      ← squelette et navigation
│   │           │   ├── home.html      ← compteurs
│   │           │   ├── equipment/     ← _form, index, edit
│   │           │   ├── notifications/ ← index
│   │           │   ├── plants/        ← index, new, detail, move, pot
│   │           │   ├── rooms/         ← index, editor
│   │           │   ├── runs/          ← index
│   │           │   ├── sites/         ← index, edit
│   │           │   ├── species/       ← _form, index, edit
│   │           │   └── weather/       ← index
│   │           └── views/
│   │               ├── __init__.py
│   │               ├── care.py        ← rappels, soins, santé
│   │               ├── equipment.py   ← pots, cache-pots, matériel
│   │               ├── home.py        ← page d'accueil
│   │               ├── notifications.py ← trace des envois
│   │               ├── plants.py      ← plantes, placement, contenants
│   │               ├── rooms.py       ← pièces et géométrie
│   │               ├── runs.py        ← exécutions du batch
│   │               ├── sites.py       ← lieux et coordonnées
│   │               ├── species.py     ← dictionnaire botanique
│   │               └── weather.py     ← relevés météo
│   └── tests/
│       ├── conftest.py                ← variables d'env de substitution
│       ├── test_geometry.py           ← polygones et appartenance
│       ├── test_light.py              ← azimut, distance, largeur
│       └── test_rules.py              ← verdicts, messages, climat, saisons
├── db/
│   ├── migrations/                    ← vide, aucun outil choisi
│   └── schema.sql                     ← DDL complet, 18 tables
├── docs/
│   ├── project-reference.md           ← ce document
│   ├── test-batch-2026-08-16.md       ← rapport de test du batch
│   └── test-batch-2026-08-19.md       ← rapport de test du moteur unifié
├── .dockerignore
├── .editorconfig
├── .env                               ← secrets réels, non commité
├── .env.example                       ← modèle commité
├── .gitignore
├── docker-compose.yml
├── Makefile
└── README.md                          ← vide
```

73 fichiers hors `.git` et caches Python. `.devcontainer/` et `db/migrations/` sont vides : Git ne suit pas les dossiers vides, ils disparaîtront au prochain clone.

---

## 3. Fichiers racine

### `docker-compose.yml`

Un seul service, `web`, conteneur `plantiq_web`.

- Build depuis la racine avec `app/Dockerfile` : le contexte est la racine, ce qui permet de copier `app/src` et `app/tests`.
- `restart: unless-stopped`, port 8000 publié sur 8000.
- `command: flask --app plantiq.web.app run --host 0.0.0.0 --port 8000 --debug`. Elle vit ici et non dans le Dockerfile, la même image servant le web, le batch et les outils CLI.
- Volumes `./app/src`, `./app/tests`, `./db`. Le troisième est indispensable à `make schema`, qui lit `db/schema.sql` depuis le répertoire de travail.
- `env_file: .env`.

Ni réseau ni volume nommé, ni `healthcheck`, ni `depends_on` : pas de base locale, pas de second service. La base est chez Supabase.

### `Makefile`

Quatorze cibles, toutes exécutées dans un conteneur. La première ligne extrait `BACKUP_PATH` du `.env` par `grep` ciblé et non par `include`, les valeurs pouvant contenir des `#` que `make` interpréterait.

| Commande | Action exacte |
|---|---|
| `make up` | `docker compose up -d` |
| `make down` | `docker compose down` |
| `make build` | `docker compose build` |
| `make logs` | `docker compose logs -f` |
| `make sh` | `bash` dans un conteneur `web` jetable |
| `make run` | `python -m plantiq.run` — batch complet, écrit et envoie |
| `make preview` | `python -m plantiq.run --preview` — évalue et affiche, sans écrire ni envoyer |
| `make schema` | `python -m plantiq.schema` — **détruit et reconstruit le schéma `public`** |
| `make backup` | Crée `BACKUP_PATH`, le monte sur `/backups`, exporte toutes les tables en JSON |
| `make restore` | Recharge le dernier export de `BACKUP_PATH` |
| `make weather` | `python -m plantiq.weather` — relève la météo de chaque site ouvert |
| `make weather-fields` | `python -m plantiq.adapters.probe` — liste les champs renvoyés par OWM |
| `make test` | `pytest` |
| `make lint` | `ruff check .` |

Aucun `.PHONY`, aucune cible `help` : les commentaires `##` sont décoratifs, rien ne les exploite.

### `.env` / `.env.example`

| Variable | Obligatoire | Exemple | Description |
|---|---|---|---|
| `DATABASE_URL` | oui | `postgresql://postgres:...@db.<ref>.supabase.co:5432/postgres` | Connexion Supabase. Lue à l'import de `core/config.py` : son absence fait échouer tout module du package |
| `OPENWEATHERMAP_API_KEY` | non au sens strict | `a1b2c3...` | Clé météo. Le web fonctionne sans ; `adapters/weather.py` lève une `RuntimeError` explicite |
| `NTFY_TOPIC` | non au sens strict | `plantiq-xyz` | Canal de notification. `adapters/notify.py` lève une `RuntimeError` explicite |
| `BACKUP_PATH` | non | `/mnt/c/Users/Pierre/OneDrive/plantiq/backups` | Dossier hôte des exports. Supporte les chemins WSL vers Windows |

Circulation : `.env` → `env_file` Compose → environnement du conteneur → `os.environ` dans `core/config.py`, seul point de lecture du package. `BACKUP_PATH` fait exception : elle n'entre jamais dans le conteneur. Le Makefile la lit sur l'hôte et s'en sert comme source d'un montage `-v "$(BACKUP_PATH):/backups"`. Côté Python, `backup.py` et `restore.py` ne connaissent que le point de montage fixe `/backups`, surchargeable par `BACKUP_DIR`.

Sur GitHub Actions, les trois premières variables viennent des secrets du dépôt.

### `.gitignore`

`.env`, `*.pyc`, `__pycache__/`, `*.egg-info/`. Les exports JSON échappent à Git parce qu'ils sont écrits hors du dépôt, pas parce qu'ils sont ignorés.

### `.dockerignore`

Exclut `.git`, `.env`, `.devcontainer/`, `.github/`, `docs/`, tous les `.md` et `__pycache__/`. Le `.env` est hors contexte : les secrets arrivent à l'exécution, jamais dans une couche d'image.

### `.editorconfig`

UTF-8, LF, indentation 4 espaces (2 en YAML et TOML), espaces de fin supprimés sauf en Markdown, saut de ligne final obligatoire.

### `README.md`

Vide.

---

## 4. Infrastructure et environnement

### Vue d'ensemble de la stack

```text
docker-compose.yml
  └── service: web              ← interface Flask, batch et CLI
        build: . / app/Dockerfile
        container_name: plantiq_web
        ports: 8000:8000
        volumes: ./app/src, ./app/tests, ./db
        env_file: .env

services externes
  ├── Supabase          ← PostgreSQL, seule persistance
  ├── OpenWeatherMap    ← météo courante par coordonnées
  ├── ntfy.sh           ← notifications push
  └── GitHub Actions    ← ordonnanceur du batch
```

Le batch n'utilise pas Docker : GitHub Actions installe le package sur un runner Ubuntu et lance le module. L'image sert au développement local et aux outils CLI.

### Service `web`

Trois rôles sur une seule image : serveur Flask lancé par `command`, batch et outils lancés par `docker compose run --rm`, shell de développement. Les volumes montent le code depuis l'hôte : une modification de `.py` ou de template est prise sans reconstruction, le rechargement automatique de Flask étant actif via `--debug`.

Aucun `healthcheck` : rien ne dépend de ce service.

### `Dockerfile` — service `web`

1. `FROM python:3.13-slim`.
2. `WORKDIR /app` — c'est lui qui rend `Path("db/schema.sql")` résolvable dans `schema.py`.
3. `apt-get install build-essential libpq-dev`.
4. `COPY app/pyproject.toml .` puis `RUN mkdir -p src && pip install -e ".[dev]"` — les dépendances sont installées avant le code, la couche n'étant invalidée que par un changement de `pyproject.toml`. Le `mkdir src` est requis : setuptools exige que le répertoire déclaré dans `[tool.setuptools.packages.find]` existe à l'installation.
5. `COPY app/src/ ./src/` et `COPY app/tests/ ./tests/`.

Pas de `CMD` : l'image est partagée, la commande est définie côté compose ou passée à `docker compose run`.

### Dev Container

`.devcontainer/` existe mais est vide. Aucun `devcontainer.json` : VSCode ne peut pas ouvrir le projet dans le conteneur.

---

## 5. Package principal — structure interne

### Choix d'organisation

Disposition `src/` : le code vit dans `app/src/plantiq/`, jamais à la racine du service. L'installation éditable rend `import plantiq` possible ; aucun `sys.path` n'est manipulé et un test ne peut pas importer par accident un module du répertoire courant. Les tests s'exécutent contre le package installé.

Un seul package pour trois usages — web, batch, CLI — les trois partageant le modèle de données et le moteur de règles.

### `pyproject.toml`

Package `plantiq` 0.1.0, Python 3.12 minimum, backend setuptools.

**Production :**

| Package | Version | Rôle |
|---|---|---|
| `flask` | non épinglée | Serveur web, blueprints, Jinja, `url_for` |
| `httpx` | `==0.27.2` | Appels HTTP synchrones vers OWM et ntfy, timeout 10 s |
| `psycopg[binary]` | `==3.3.4` | Pilote PostgreSQL. Le variant `binary` embarque libpq |

Aucune dépendance scientifique : `climate.py` implémente Magnus-Tetens avec le seul module `math`.

**Développement :**

| Package | Version | Rôle |
|---|---|---|
| `pytest` | `==8.3.3` | `testpaths = ["tests"]`, usage de `parametrize` et `approx` |
| `ruff` | `==0.7.1` | `line-length = 100`, règles `E`, `F`, `I`, `UP`, `E501` ignorée, `known-first-party = ["plantiq"]` |

`E501` ignorée alors que `line-length` vaut 100 : la longueur de ligne est une convention, pas une règle vérifiée.

### Architecture des sous-packages

| Sous-package | Rôle | Importe | N'importe pas |
|---|---|---|---|
| `core/` | Environnement, connexion, logs | rien du projet | tout le reste |
| `engine/` | Décision, géométrie, physique | `core.database`, dans `rules` seulement | `web`, `adapters` |
| `adapters/` | Frontières externes : OWM, ntfy | `core` | `engine`, `web` |
| `web/` | Interface HTTP | `core`, `engine.geometry`, autres vues | `adapters` |
| racine (`run`, `weather`, `backup`, `restore`, `schema`) | Orchestration et outils | tout | — |

La règle structurante : `geometry.py`, `light.py` et `climate.py` sont purs, sans base ni réseau. `rules.py` est le seul module d'`engine/` à toucher `core.database`, et il isole cette lecture dans la seule fonction `context()` — ce qui rend `assess()` et `message()` testables sur un `Context` construit à la main.

---

## 6. Modules — détail fonctionnel

### `core/config.py`

Unique point de lecture de l'environnement. Expose `DATABASE_URL` (obligatoire, `os.environ[...]`, échec bruyant à l'import), `OPENWEATHERMAP_API_KEY` et `NTFY_TOPIC` (chaîne vide par défaut).

Ne pas lire `os.environ` ailleurs. Deux exceptions assumées : `BACKUP_DIR` dans `backup.py` et `restore.py`, la valeur étant un point de montage et non un secret.

### `core/database.py`

Expose `connect() → psycopg.Connection` et `query(sql, params=(), *, fetch=None)`.

Une connexion par appel, ouverte et fermée par gestionnaire de contexte, sans pool. `query` renvoie des dictionnaires (`row_factory=dict_row`). Les écritures multi-instructions qui doivent être atomiques utilisent `connect()` directement pour tenir la transaction.

Paramétrage positionnel `%s`. Les noms de colonnes et de tables injectés en f-string — `sites.py`, `equipment.py`, `species.py`, `run.py`, `backup.py`, `restore.py` — proviennent de constantes du code ou du catalogue PostgreSQL, jamais d'une entrée utilisateur.

### `core/logging.py`

`get_logger(name) → Logger`, niveau INFO. Le module abaisse `httpx` à WARNING : sans cela httpx journaliserait l'URL complète des requêtes, clé OWM comprise, dans les logs publics de GitHub Actions.

### `adapters/weather.py`

Seul module qui connaît le format OpenWeatherMap.

| Fonction | Signature | Ce qu'elle fait |
|---|---|---|
| `current` | `(lat, lon) → dict` | `/data/2.5/weather`, payload brut |
| `forecast` | `(lat, lon) → dict` | `/data/2.5/forecast`, 40 pas de 3 h |
| `normalise` | `(raw) → dict` | Extrait `observed_at` (depuis `dt`, UTC), `temp_c`, `humidity_pct`, `cloud_pct` (`clouds.all`), `condition_id` (`weather[0].id`) |
| `flatten` | `(payload, prefix) → dict` | Aplatit récursivement en chemins pointés |

`normalise` est la frontière : en aval, plus rien ne connaît la forme du fournisseur. `cloud_pct` n'est pas décoratif, `climate.py` s'en sert pour l'apport solaire.

### `adapters/notify.py`

`send(title, message, *, tags=None, priority=3)`. Publication en JSON avec le topic dans le corps, plutôt que par en-têtes : l'en-tête `Title` de ntfy est encodé en latin-1 sur le fil, les accents y seraient mutilés. Le corps JSON est UTF-8 de bout en bout.

### `adapters/probe.py`

Outil de découverte, pas de test de régression. Appelle réellement l'API et liste chaque champ retourné avec son type et sa valeur, pour décider ce qui mérite d'être stocké. `--forecast` ajoute le premier pas des prévisions.

### `engine/geometry.py`

Géométrie plane pure, aucune dépendance au projet, aucune entrée-sortie.

| Fonction | Signature | Ce qu'elle fait |
|---|---|---|
| `walls` | `(vertices) → [(Point, Point)]` | Mur *i* du sommet *i* au sommet *i+1*, le dernier refermant le polygone |
| `segments_cross` | `(p1, p2, p3, p4) → bool` | Croisement propre, extrémités partagées exclues |
| `is_simple` | `(vertices) → bool` | Faux si le contour se croise — le nœud papillon que le lacet ne sait pas mesurer |
| `polygon_area` | `(vertices) → float` | Formule du lacet, valable sur contour simple seulement |
| `wall_lengths` | `(vertices) → [float]` | Longueurs en unités de plan |
| `project_on_segment` | `(point, a, b) → (t, Point)` | Projeté orthogonal borné à `[0,1]` |
| `closest_point_on_outline` | `(point, vertices) → (distance, Point)` | Mur le plus proche et point sur ce mur |
| `point_in_polygon` | `(point, vertices, tolerance=0) → bool` | Nombre de croisements, règle semi-ouverte |
| `pull_inside` | `(point, vertices, tolerance) → Point \| None` | Point inchangé s'il est dedans, rabattu sur le mur s'il déborde peu, `None` au-delà |

`point_in_polygon` n'est délibérément pas bâti sur `segments_cross` : celle-ci ignore les extrémités partagées, ce qui manquerait un rayon passant exactement par un sommet — cas fréquent, les sommets s'aimantant sur la grille et les clics étant entiers.

### `engine/light.py`

Quantité de lumière atteignant un point. Sortie : un `Exposure` portant `intensity`, `level`, `distance_m`, `width_m`, `cardinal`, `visible`.

| Fonction | Signature | Ce qu'elle fait |
|---|---|---|
| `cardinal_of` | `(azimuth) → str` | Azimut vers l'une des huit directions |
| `wall_azimuth` | `(vertices, wall_index, north_angle) → float` | Orientation extérieure d'un mur, trouvée en s'écartant du mur et en testant l'appartenance — indépendante du sens de parcours |
| `is_visible` | `(point, target, vertices, ignore_wall) → bool` | Faux si un mur s'interpose ; le mur porteur est ignoré |
| `element_width` | `(vertices, element, units_per_cm) → float \| None` | Largeur de l'ouverture en mètres |
| `distance_to_element` | `(point, vertices, element, units_per_cm) → (m, Point)` | Distance au point le plus proche de l'élément |
| `nearest_of_type` | `(point, vertices, elements, kind, units_per_cm, north_angle) → dict \| None` | Élément visible le plus proche du type demandé |
| `exposure` | `(point, vertices, elements, north_angle, units_per_cm) → Exposure` | Intensité continue et niveau discret |
| `position_in_room` | `(point, vertices, units_per_cm) → str` | « dans un coin », « contre un mur », « près d'un mur », « en milieu de pièce » |

Pondération par orientation — `N` 0,30 · `NE` 0,45 · `E` 0,70 · `SE` 0,85 · `S` 1,00 · `SO` 0,85 · `O` 0,70 · `NO` 0,45 — puis

```text
intensité = poids × 4 × (largeur_m / 3,0) / (1 + distance_m)²
```

Largeur de référence 3 m : une baie de 4 m apporte un tiers de plus, une fenêtre d'un mètre trois fois moins. Sans calibrage la largeur est inconnue et le rapport vaut 1. Seuils de niveau : 1,5 `direct`, 0,6 `bright_indirect`, 0,2 `indirect`, `low` en dessous. Seuils de position : 30 et 100 cm, convertis une fois en unités de plan, repliés sur 15 et 50 unités sans calibrage.

Dégradation : aucune fenêtre, aucune visible, ou aucun calibrage — réponse `low` à intensité nulle. Le module ne lève jamais sur donnée manquante.

### `engine/climate.py`

Ce que la plante vit à l'intérieur, à partir du relevé extérieur. Module pur.

| Fonction | Signature | Ce qu'elle fait |
|---|---|---|
| `saturation_pressure` | `(temp_c) → float` | Pression de vapeur saturante en hPa, Magnus-Tetens, coefficients OMM |
| `dew_point` | `(temp_c, humidity_pct) → float` | Point de rosée — la grandeur qui ne change pas quand l'air entre |
| `indoor_temperature` | `(outdoor_c, cloud_pct, month) → float` | Mélange entre consigne et extérieur |
| `indoor_humidity` | `(outdoor_c, outdoor_humidity_pct, indoor_c) → float` | Humidité relative après réchauffement du même air |

- Consigne 20,5 °C. Couplage à l'extérieur 0,15 en chauffe (octobre à avril), 0,55 sinon : une pièce chauffée suit à peine le dehors, une pièce libre le suit franchement.
- Apport solaire 1,5 °C au plus, pondéré par `1 − nébulosité`, hors chauffe seulement.
- Résultat borné à `[20 ; 28] °C`.
- L'humidité est la correction qui compte : le contenu absolu en eau est le même dedans et dehors, réchauffer cet air fait monter la pression saturante et effondre l'humidité relative. À 5 °C et 85 % dehors, le même air à 20 °C dedans lit environ 32 %.

Invariant testé : le point de rosée survit à la conversion, à 0,1 °C près. C'est la formulation physique de « c'est le même air ».

### `engine/rules.py`

Cœur de décision. Assemble le contexte d'une plante, calcule l'intervalle d'arrosage, rend un verdict par action, ouvre les rappels, rédige les messages.

**Constantes**

| Constante | Valeur | Rôle |
|---|---|---|
| `SEASON_BOUNDARIES` | 1er mars, juin, septembre, décembre | Bornes de saison |
| `TRANSITION_DAYS` | 15 | Demi-largeur de la fenêtre de lissage |
| `FACTOR_FLOOR`, `FACTOR_CEILING` | 0,70 · 1,40 | Écrêtage du produit |
| `HEATING_MONTHS` | 10, 11, 12, 1, 2, 3, 4 | Période de chauffe, pour le radiateur |
| `OVERDUE_ESCALATION_DAYS` | 365 | Au-delà, une action hors fenêtre est notifiée comme à planifier |
| `REPOTTING_FERTILIZING_GAP_DAYS` | 60 | Blocage de la fertilisation après rempotage |
| `NO_DRAINAGE_FACTOR` | 1,15 | Contenant sans trou : l'intervalle s'allonge |

**Les six facteurs, tous neutres à 1,00**

| Facteur | Formule | Note |
|---|---|---|
| `factor_porous` | 0,85 si poreux, sinon 1,00 | Annulé par un cache-pot, qui scelle les parois |
| `factor_drainage` | 1,00 si percé, 1,15 si non, 1,00 si inconnu | Le contenant extérieur décide : un cache-pot sans trou l'emporte sur un pot percé |
| `factor_exposure` | `1,15 − 0,25 × min(intensité, 2)` | 1,00 si inconnue — une pièce sombre n'est pas une absence de donnée |
| `factor_temperature` | `max(0,85 ; 1 − 0,015 × max(0, t − 25))` | Sur la température intérieure convertie |
| `factor_humidity` | `1 + 0,004 × (h − 60)`, borné à `[0,90 ; 1,10]` | Sur l'humidité intérieure convertie |
| `factor_radiator` | 0,80 sous 1 m, 0,90 jusqu'à 2 m, 1,00 au-delà | Octobre à avril seulement |

Produit écrêté à `[0,70 ; 1,40]`, puis `interval = max(1, round(base_interval × produit))`.

**Lissage saisonnier**

| Fonction | Signature | Ce qu'elle fait |
|---|---|---|
| `season_blend` | `(today) → [(saison, poids)]` | Une saison hors fenêtre, deux voisines partageant le poids linéairement dedans — moitié-moitié sur la borne |
| `blended_interval` | `(today, intervals) → float \| None` | Intervalle du jour, interpolé ; renormalise sur les saisons présentes, `None` si aucune |

Une plante ne remarque pas minuit : avec été 10 j et automne 18 j, le 31 août et le 1er septembre ne diffèrent plus de huit jours mais de quelques heures d'interpolation. Une saison manquante en base ne fait pas échouer le calcul, elle sort de la moyenne pondérée.

**Le verdict**

`Verdict` est le point unique de vérité sur les échéances : `generate()`, `preview()` et `message()` s'y adossent, ce qui rend impossible la divergence entre ce que le batch fait et ce que l'aperçu annonce.

| Champ | Sens |
|---|---|
| `due_on` | Échéance, calculée quelle que soit la fenêtre de mois |
| `last_on`, `interval`, `unit` | Référence et rythme, en jours ou en mois |
| `window`, `in_window` | Fenêtre de mois de l'espèce, et si le mois courant y est |
| `is_due` | Échue, dans la fenêtre ou rattrapée, et non bloquée |
| `planning` | Échue depuis plus d'un an hors fenêtre : à planifier |
| `blocker` | Interdiction ferme, quelle que soit l'échéance |
| `late_days`, `next_window_on` | Retard et prochaine ouverture |
| `reason` | Phrase explicative, affichée par `make preview` |

`assess(ctx, action)` couvre `watering`, `fertilizing` et `repotting` ; toute autre action sort avec « hors du périmètre du moteur ». L'échéance de rempotage est calculée en jours, `last_on + 30 × interval_months`. Trois décisions y sont visibles :

- **L'échéance est calculée hors fenêtre aussi.** Dire « hors fenêtre » sans dire « en retard de deux ans » cache l'essentiel.
- **Le rattrapage à un an** évite qu'un rempotage dû depuis 2024 reste muet jusqu'en mars 2027.
- **Le blocage l'emporte sur le rattrapage.** Une plante rempotée le mois dernier ne reçoit pas de rappel de fertilisation, même en retard de deux ans : le substrat neuf porte déjà de l'engrais. Une date de rempotage inconnue ne bloque rien — une date absente n'est pas une date récente.

`next_window_start(today, start, end)` donne le premier jour de la prochaine ouverture, en traitant la fenêtre qui enjambe le nouvel an.

**Le contexte**

`context(plant_id)` est la seule fonction du module qui lise la base. Neuf requêtes : plante et espèce, emplacement et pièce, intervalles saisonniers, équipements attachés, sommets, éléments muraux, relevé météo du jour, derniers soins par action, dernière observation de santé.

- **Contenants** : les attachements ouverts sont indexés par type, ce qui donne pot et cache-pot en une requête. `ctx.last_potted_on` est la date d'attachement du **pot**, jamais du cache-pot.
- **Conversion intérieure** : si `room_version.environment` vaut `indoor` et qu'un relevé existe, `ctx.temp_c` et `ctx.humidity_pct` passent par `climate.py`. `ctx.weather` garde les valeurs extérieures brutes, le payload transporte les deux.
- **Santé** : la dernière ligne de `plant_health` est chargée dans `ctx.health`. `dormant` et `dying` bloquent la fertilisation, les quatre autres statuts n'ont aucun effet.
- **Géométrie** : exposition et distance au radiateur ne sont calculées qu'avec au moins trois sommets et un calibrage exploitable.

**Les messages**

| Fonction | Ce qu'elle produit |
|---|---|
| `_rhythm` | « Rythme : tous les 30 jours, fenêtre avril → septembre. » |
| `justification` | Uniquement les facteurs qui ont bougé ; vide si tous neutres |
| `message` | Titre et corps, lus depuis le verdict |

Trois formes de corps :

1. **Sans antécédent** : « Première fois, aucun antécédent enregistré. » puis le rythme, la saison pour l'arrosage, et la fenêtre s'il y en a une.
2. **Avec antécédent** : forme courte, « Dernier arrosage il y a 12 jours, intervalle de 11 jours », plus la justification pour l'arrosage.
3. **À planifier** : retard en jours et en mois, fenêtre possible, mois de la prochaine occasion. Le message dit *quand*, pas *quoi faire maintenant*.

L'alerte d'exposition, quand elle existe, est ajoutée au message d'arrosage : c'est celui qui porte déjà le « pourquoi » et celui qui revient souvent. `exposure_alert()` compare le niveau mesuré à la plage de l'espèce et nomme l'écart ; il se tait hors plage inconnue, sans fenêtre visible ou sans calibrage. Le volet température est délibérément absent, voir §13.

L'intervalle, son unité et la fenêtre sont lus depuis le `Verdict`, jamais recalculés.

### `web/app.py`

`create_app()` enregistre dix blueprints dans un ordre fixe. La variable de module `app` est le point d'entrée visé par `flask --app plantiq.web.app`.

### `web/views/` — les 38 routes

| Blueprint | Préfixe | Routes |
|---|---|---|
| `home` | `/` | `GET /` |
| `sites` | `/sites` | `GET /`, `POST /`, `GET /<id>/edit`, `POST /<id>/edit`, `POST /<id>/close` |
| `rooms` | `/rooms` | `GET /`, `GET /new`, `POST /` *(JSON)*, `POST /<id>/close` |
| `species` | `/species` | `GET /`, `POST /`, `GET /<id>/edit`, `POST /<id>/edit` |
| `equipment` | `/equipment` | `GET /`, `POST /`, `GET /<id>/edit`, `POST /<id>/edit`, `POST /<id>/close` |
| `plants` | `/plants` | `GET /`, `GET /new`, `POST /` *(JSON)*, `GET /<id>`, `GET /<id>/move`, `POST /<id>/move` *(JSON)*, `GET /<id>/pot`, `POST /<id>/pot`, `POST /<id>/close` |
| `care` | `/care` | `POST /reminders/<id>/complete`, `POST /reminders/<id>/dismiss`, `POST /plants/<id>/add`, `POST /<id>/edit`, `POST /<id>/delete`, `POST /plants/<id>/health`, `POST /health/<id>/delete` |
| `weather` | `/weather` | `GET /` |
| `notifications` | `/notifications` | `GET /` |
| `runs` | `/runs` | `GET /` |

Les trois formulaires géométriques — dessin d'une pièce, création d'une plante, déplacement — dialoguent en JSON depuis le navigateur ; le reste est en formulaire HTML avec redirection après POST. Les erreurs de validation transitent par `?error=`.

### `web/views/home.py`

Quatre compteurs : sites, pièces, plantes ouvertes, relevés météo. Les trois derniers sont importés des blueprints concernés (`room_count`, `plant_count`, `reading_count`) plutôt que réécrits.

### `web/views/sites.py`

CRUD des lieux, piloté par la constante `FIELDS` qui sert au `SELECT`, à l'`INSERT`, à l'`UPDATE` et à l'en-tête du tableau. Les champs optionnels vides deviennent `NULL`. Latitude et longitude sont converties par `float()` sans garde : une saisie non numérique remonte en erreur serveur, ce que le code assume par commentaire. La clôture est un `closed_at = now()`.

### `web/views/rooms.py`

- `_measure` convertit les longueurs en centimètres et l'aire en mètres carrés depuis le mur de référence. Le rapport unités/centimètre n'est jamais stocké : il est recalculé, si bien que déplacer un sommet du mur de référence recalibre la pièce au lieu de la falsifier.
- `_validate` refuse une pièce sans site, un contour ouvert, un milieu inconnu, un angle de nord hors `[0, 360[`, un élément sur un mur inexistant, des bornes non numériques ou ne vérifiant pas `0 ≤ début < fin ≤ 1`, un mur de référence inexistant ou de longueur nulle.
- `is_simple` est appelé avant tout enregistrement : un contour qui se croise est rejeté, son aire ne voudrait rien dire.
- `_load_rooms` charge sommets et éléments de toutes les pièces en deux requêtes avec `ANY(%s)`.
- `_insert_room` écrit pièce, version, sommets et éléments dans une transaction unique.
- Clôturer une pièce clôt d'abord sa version ouverte.

### `web/views/species.py`

Dictionnaire botanique, ni clôturable ni supprimable. `_read_form` porte huit validations, dont deux que la base ne peut pas exprimer : l'ordre des expositions, comparé via `EXPOSURE_ORDER` qui reflète l'ordre de déclaration de l'énumération SQL, et la présence des quatre saisons. La création écrit l'espèce et ses quatre saisons dans une transaction ; la mise à jour utilise `ON CONFLICT (species_id, season) DO UPDATE` plutôt qu'un `DELETE` puis `INSERT`. `UniqueViolation` sur `scientific_name` est rattrapée et rendue comme message.

### `web/views/equipment.py`

- **Drainage à trois états** : `_tri_state` distingue percé, sans trou et non renseigné. `factor_drainage` reste neutre sur un inconnu, il n'assume pas l'absence de trou.
- La contrainte du pot de culture est portée des deux côtés : le formulaire vide les champs d'achat quand la case est cochée, la base refuse par `CHECK` un pot de culture porteur d'un prix.
- Le volume de substrat est proposé côté navigateur par un calcul de tronc de cône affecté d'un facteur de remplissage de 0,80, et redevient modifiable dès que l'utilisateur y touche.

Clôturer un objet détache l'attachement qui l'utilisait.

### `web/views/plants.py`

- Une plante n'existe pas hors d'un lieu : `create` écrit `plant` et `plant_placement` dans la même transaction.
- Le marqueur passe par `pull_inside` avec une tolérance de 10 unités de plan, valeur miroir de `Plan.TOLERANCE` dans `plan.js`. Garde contre un marqueur mal posé, jamais une mesure.
- `save_move` distingue deux intentions que seul l'utilisateur peut trancher : une **correction** met à jour la ligne existante sans historique, un **déplacement** clôt la période en cours et en ouvre une nouvelle.
- Les routes de contenant sont paramétrées par `?kind=` : la même page sert à choisir un pot ou un cache-pot.
- `save_pot` insère par `INSERT ... SELECT e.type FROM equipment` : le type dénormalisé est lu depuis l'équipement, jamais recopié du formulaire.
- `_available(plant_id, kind)` ne propose que les objets libres du type demandé, plus celui que la plante utilise déjà.
- Clôturer une plante clôt son emplacement et tous ses attachements.
- `detail` compose la fiche : identité, besoins de l'espèce, emplacement avec plan SVG, pot et cache-pot avec leur drainage, historique de santé, chronologie des soins, historique des contenants et des emplacements, volume d'arrosage suggéré.

### `web/views/care.py`

- `timeline` fusionne trois sources — rappels en attente, soins exécutés, notifications envoyées — triées par date décroissante, filtrables par `?care=`.
- Valider un rappel écrit le `care_log` et clôt le rappel dans une transaction ; un rappel de rempotage est clos seul, `care_log` interdisant l'action `repotting` par `CHECK`.
- Écarter un rappel le clôt avec une raison, ce qui le distingue d'un soin effectué.
- Supprimer un soin dénoue d'abord les rappels qui le référencent.
- `health_history` renvoie toutes les observations, la première étant l'état courant. `add_health` est append-only. `delete_health` existe pour la faute de frappe.

### `web/views/weather.py`, `notifications.py`, `runs.py`

Trois vues en lecture seule, alimentées par le batch.

- `weather` rend chaque instant dans le fuseau du site : la base stocke des instants absolus, afficher la valeur brute montrerait 21 h 37 pour une mesure prise à 23 h 37 à Bruxelles. Le filtre par site est construit par concaténation plutôt que passé en paramètre nullable, `%s IS NULL` empêchant PostgreSQL d'inférer le type.
- `notifications` affiche le `payload` JSON de chaque envoi.
- `runs` recoupe `batch_run` avec trois sous-requêtes de comptage sur `batch_run_id`, calcule la durée par `EXTRACT(EPOCH FROM ...)`, limite aux 60 dernières. Une exécution sans `finished_at` s'affiche comme interrompue ; l'absence totale de ligne signifie que le batch n'a pas démarré.

### `web/static/plan.js`

Moteur de rendu SVG partagé, sans dépendance externe et sans connaissance de l'éditeur. Expose `draw`, `mousePoint`, `clampInside`, `pullInside` et les primitives géométriques. Quatre vues l'utilisent : éditeur de pièce, création de plante, déplacement, fiche de plante.

Duplication assumée : `pointInPolygon` reproduit la règle semi-ouverte de `engine/geometry.py`, `TOLERANCE` reproduit `INSIDE_TOLERANCE` de `views/plants.py`. Le navigateur doit donner la même réponse que le serveur, faute de quoi un marqueur accepté à l'écran serait refusé à l'enregistrement. `mousePoint` passe par la matrice écran (`getScreenCTM`) et non par un rapport de largeurs, `preserveAspectRatio` centrant et encadrant le `viewBox`.

### `web/templates/`

Vingt gabarits Jinja, tous issus de `base.html`, sans feuille de style : tableaux à bordure et formulaires bruts. Deux partiels `_form.html`, espèces et équipement, partagés entre création et édition via `{% with %}` et `{% include %}`, `item` valant `None` en création. Le JavaScript d'`equipment/_form.html` calcule le volume et masque le bloc d'achat pour un pot de culture ; celui de `rooms/editor.html` porte l'outil de dessin complet — tracé, déplacement de sommets, pose d'éléments, calibrage, rose des vents interactive, raccourcis clavier.

### `db/schema.sql`

DDL complet du schéma Supabase. Le fichier commence par `DROP SCHEMA public CASCADE` : il reconstruit, il ne migre pas.

**Huit énumérations :** `room_environment`, `wall_element_type`, `season`, `light_exposure`, `sun_tolerance`, `care_action`, `health_status`, `equipment_type`. L'ordre de déclaration de `light_exposure` est signifiant — c'est l'ordre de comparaison `low < indirect < bright_indirect < direct` — et `views/species.py` le reproduit côté Python.

**Dix-huit tables :**

| Table | Colonnes clés | Nature |
|---|---|---|
| `material` | `code`, `label`, `is_porous` | Référentiel, 6 lignes semées en fin de fichier |
| `site` | `latitude`, `longitude`, `timezone`, `closed_at` | Lieu géographique |
| `species` | `scientific_name` unique, fenêtres de mois, bornes d'exposition et de température | Dictionnaire botanique, ni clôturable ni supprimable |
| `species_watering` | `(species_id, season)` unique | Un intervalle par saison |
| `plant` | `species_id`, `name`, achat, `closed_at` | Individu |
| `room` | `site_id`, `floor`, `closed_at` | Pièce |
| `room_version` | `environment`, `north_angle`, `scale_wall_index`, `scale_cm` | Géométrie immuable, versionnée |
| `room_vertex` | `(room_version_id, position)` unique | Sommet du polygone |
| `wall_element` | `wall_index`, `t_start`, `t_end` | Fenêtre, radiateur ou climatiseur, en paramètre `[0,1]` sur un mur |
| `plant_placement` | `x`, `y`, `height_cm`, `closed_at` | Marqueur, rattaché à une **version** |
| `equipment` | `type`, `volume_l`, dimensions, `is_nursery_pot`, `has_drainage`, `UNIQUE (id, type)` | Objets achetés |
| `plant_equipment` | `plant_id`, `equipment_id`, `equipment_type`, `attached_on`, `detached_on` | Ce à quoi une plante est attachée, et depuis quand |
| `batch_run` | compteurs, `error` | Une ligne par exécution |
| `weather_log` | `(site_id, observed_on)` unique, `batch_run_id` | Un relevé par site et par jour local |
| `care_log` | `plant_id`, `action`, `done_at`, `recorded_at` | Soins effectués, source de vérité |
| `plant_health` | `status`, `noted_on`, `note`, `recorded_at` | Observations d'état, append-only |
| `reminder` | `due_on`, `completed_at`, `dismissed_reason`, `batch_run_id` | Tâche en attente |
| `notification_log` | `(plant_id, action, sent_on)` unique, `payload` jsonb, `batch_run_id` | Ce qui est parti |

**Dix-sept index**, dont cinq uniques partiels qui portent des invariants temporels : `ux_room_version_current`, `ux_plant_placement_current`, `ux_plant_equipment_current` (un objet ouvert de chaque type par plante), `ux_plant_equipment_item` (une plante par objet physique), `ux_reminder_open` (un rappel ouvert par plante et action). Deux index uniques portent l'idempotence : `weather_log (site_id, observed_on)` et `ux_notification (plant_id, action, sent_on)`.

**Patterns SQL notables :**

- **Clôture, jamais suppression.** Toutes les tables sauf le référentiel, le dictionnaire botanique et les journaux portent un `closed_at`. Toute lecture d'état courant filtre sur `closed_at IS NULL`.
- **Dénormalisation rendue infalsifiable.** `plant_equipment.equipment_type` duplique `equipment.type`, mais `equipment` porte un `UNIQUE (id, type)` qui sert de clé candidate à la clé étrangère composite `(equipment_id, equipment_type)`. La copie ne peut pas dériver, et c'est elle qui rend « un pot ouvert **et** un cache-pot ouvert par plante » exprimable comme un index. Aucun `CHECK` ne restreint les types attachables.
- **Append-only pour la santé.** Pas de colonne de statut sur `plant` : l'état courant est la ligne la plus récente de `plant_health`.
- **Date réelle contre date de saisie.** `plant_equipment.attached_on` / `created_at`, `care_log.done_at` / `recorded_at`, `plant_health.noted_on` / `recorded_at`. Un `CHECK` impose `recorded_at >= done_at`.
- **Séparation d'énumération et de table.** `care_action` porte `repotting` pour les rappels, un `CHECK` interdit cette valeur dans `care_log` : l'acte vit dans `plant_equipment`.
- **Fenêtres de mois enjambant l'année.** `start > end` signifie « d'octobre à mars ». Un `CHECK` impose la fenêtre entière ou rien.
- **Traçabilité par exécution.** `batch_run_id` nullable sur les trois journaux. `batch_run` est déclarée avant `weather_log` pour que les clés étrangères se résolvent.

**Onze invariants non exprimables en SQL**, énumérés en commentaire dans le fichier : au moins trois sommets par version, indices de murs inférieurs au nombre de sommets, gel d'une version référencée par un placement, absence de pièce sous un site clos, clôture en cascade, absence de placement dans une version close, marqueur dans le polygone, quatre saisons par espèce, cohérence de `reminder.care_log_id`, calcul des dates dans le fuseau du site, types attachables limités à ce qui appartient à une seule plante.

**Droits :** `GRANT` sur `public` aux quatre rôles standards Supabase. L'application se connecte avec le compte `postgres`.

### `run.py`

Orchestrateur du batch.

1. Insère une ligne `batch_run` et retient son identifiant, propagé à tout ce que l'exécution écrit.
2. Relève la météo de chaque site ouvert (`weather.collect(batch_id)`).
3. Pour chaque plante ouverte, appelle `generate(plant_id, batch_id)` puis mémorise son contexte. Une plante en échec est journalisée et n'interrompt pas les autres.
4. Pour chaque rappel échu, interroge `send_decision`, rédige le message, l'envoie, écrit `notification_log` avec `ON CONFLICT DO NOTHING`.
5. Met à jour `batch_run` — compteurs et erreur.
6. Sort en code 1 si quoi que ce soit a échoué. La ligne est écrite avant la sortie en erreur : un échec silencieux ressemblerait sinon à un succès.

`send_decision(plant_id, action, ctx) → (bool, str)` est la seconde moitié du moteur unifié. En lecture seule, elle rend la décision **avec sa raison** : le batch s'en sert pour filtrer, `preview()` pour l'afficher.

**Politique de renvoi (`RESEND`) :**

| Action | Délai entre deux envois | Renvois après le premier |
|---|---|---|
| `watering` | 3 jours | 3 |
| `fertilizing` | 7 jours | 2 |
| `repotting` | 7 jours | 2 |

Le délai court depuis le plus récent des deux événements — dernier soin ou dernier envoi. Un soin qui arrive remet le compteur à zéro.

`preview()` rejoue le même calcul sans rien écrire ni envoyer. Il liste chaque action de chaque plante, échue ou non, avec la raison, et pour celles qui passeraient, la décision d'envoi et le texte intégral du message. Il travaille sur `ctx.today`, jamais sur `date.today()`.

Deux commentaires `DETTE` signalent que la **sélection** des rappels échus compare `due_on` à une date UTC, alors que toutes les **décisions** raisonnent dans le fuseau du site. Voir §13.

### `weather.py`

`collect(batch_run_id=None)` boucle sur les sites ouverts, appelle l'adaptateur, calcule `observed_on` dans le fuseau du site puis fait un `INSERT ... ON CONFLICT (site_id, observed_on) DO UPDATE`. La mise à jour réécrit `batch_run_id` : la colonne montre la dernière exécution ayant rafraîchi la ligne, pas la première. Un site en échec est journalisé et n'arrête pas les autres ; retourne `(succès, échecs)`.

`for_site()` renvoie le relevé du jour ou `None`, `None` étant une réponse normale. La fonction n'a aujourd'hui aucun appelant : `rules.context()` interroge `weather_log` directement. Voir §13.

### `schema.py`

Lit `db/schema.sql` depuis le répertoire de travail et l'exécute en une transaction. **Destructif :** le script supprime d'abord le schéma `public`.

### `backup.py`

Exporte chaque table en JSON. La liste des tables est lue dans `information_schema` et non codée en dur, pour qu'une table ajoutée ne disparaisse pas silencieusement des sauvegardes. Un encodeur dédié sérialise les dates en ISO et les décimaux en flottants. Fichier `plantiq_backup_AAAA-MM-JJ_HHMMSS.json`.

### `restore.py`

Recharge le dernier export du dossier, ou celui passé en argument, dans une transaction unique.

- `TABLE_ORDER` fixe l'ordre des clés étrangères et couvre les 18 tables ; une table absente de la sauvegarde est ignorée, si bien qu'un fichier écrit avant l'existence d'une table se restaure quand même.
- Les tables sont vidées en ordre inverse avant rechargement, les lignes de référence semées par `schema.sql` entrant sinon en collision.
- Une colonne disparue depuis la sauvegarde est ignorée ; une colonne ajoutée ne bloque pas la restauration.
- `OVERRIDING SYSTEM VALUE` préserve les identifiants, puis `setval` réaligne chaque séquence.

`TABLE_ORDER` place `batch_run` avant les trois journaux qui portent `batch_run_id`, donc la purge le vide après eux. L'ordre a été corrigé le 19/08 : il plaçait `batch_run` en dernier, ce qui faisait échouer toute restauration d'une base ayant déjà tourné.

---

## 7. Tests

**Répertoire :** `app/tests/` — 47 fonctions, 59 cas avec les paramétrages, trois fichiers plus `conftest.py`. `ruff check .` et `pytest -q` passent au 19/08 : 59 passés.

### `conftest.py`

Aucun stub, aucune base de test. Le fichier pose trois variables d'environnement de substitution avant tout import de `plantiq.core.config`, qui lit `os.environ` à l'import et échouerait sinon dès la collecte.

```python
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
```

Rien dans la suite ne touche le réseau ni la base.

### Fichiers de test

| Fichier | Cas | Ce qu'il teste |
|---|---|---|
| `test_geometry.py` | 7 fonctions | Contour simple contre nœud papillon, aire d'un carré, appartenance dont le rayon passant par un sommet, exclusion de l'encoche d'une pièce en L, rabattement et rejet de `pull_inside` |
| `test_light.py` | 9 fonctions | Azimut du mur est, rotation du nord, décroissance avec la distance, occultation par un mur, dégradation sans calibrage, et quatre tests de largeur d'ouverture — référence à 3 m, fenêtre étroite, baie vitrée, largeur changeant le niveau à elle seule |
| `test_rules.py` | 31 fonctions | Blocage de la fertilisation par un rempotage récent et sa levée au soixantième jour, priorité du blocage sur le rattrapage, rattrapage au-delà d'un an, fenêtres de mois et prochaine ouverture, quatre formes de message, climat intérieur, plafond du facteur d'humidité, six tests de lissage saisonnier dont la monotonie sur toute la fenêtre, sept tests de plage d'exposition, deux tests de blocage par la santé |

`test_rules.py` teste `assess()` et `message()` sur un `Context` construit à la main, sans base — ce que permet la séparation entre `context()`, qui lit, et le reste du module, qui décide. Deux invariants y sont vérifiés plutôt que des valeurs : la conservation du point de rosée à la conversion, et la monotonie de l'intervalle interpolé sur les 31 jours d'une transition.

**Non couverts :** `context()` et toute lecture en base, les dix blueprints, `run.py`, `weather.py`, `backup.py`, `restore.py`, les adaptateurs. Aucun test d'intégration, aucun test HTTP.

### Lancer les tests

```bash
make test
# ou :
docker compose run --rm web pytest

pytest -v                        # verbeux
pytest tests/test_rules.py       # un fichier
pytest -k "season"               # filtre par nom
```

### Ajouter un test

```python
# app/tests/test_rules.py

def test_a_blocked_action_names_its_blocker():
    ctx = make_context(last_potted_on=TODAY - timedelta(days=10))
    verdict = assess(ctx, "fertilizing")
    assert not verdict.is_due
    assert "substrat encore neuf" in verdict.blocker
```

`make_context(**overrides)` est l'outil à réutiliser : il construit un `Context` complet et n'ouvre aucune connexion.

---

## 8. CI/CD

### `ci.yml` — Lint et tests

**Déclencheurs :** push sur `main`, pull request vers `main`.

1. `actions/checkout@v4`.
2. `actions/setup-python@v5` en 3.13, cache pip indexé sur `app/pyproject.toml`.
3. `pip install -e "./app[dev]"`.
4. `ruff check .` dans `./app` — toute violation E, F, I, UP fait échouer.
5. `pytest -q` dans `./app` — tout test rouge fait échouer.

**Docker :** non. La suite n'a besoin ni de base ni de réseau, `conftest.py` fournit les variables.

**Artefacts :** aucun.

### `daily-run.yml` — Batch quotidien

**Déclencheurs :** `cron: "0 16 * * *"` et `workflow_dispatch`. 16:00 UTC vaut 18 h en heure d'été belge et 17 h en hiver, le cron GitHub ignorant le changement d'heure.

**Étapes :** checkout, Python 3.13, `pip install -e ./app` — production seulement — puis `python -m plantiq.run` avec les trois secrets.

**Échec :** code 1 dès qu'un site échoue, qu'un envoi échoue, ou qu'une exception remonte. L'exécution passe au rouge, seul mécanisme d'alerte automatique du projet.

---

## 9. Documentation

| Fichier | Contenu | Quand le consulter |
|---|---|---|
| `docs/project-reference.md` | Ce document | Compréhension globale |
| `docs/test-batch-2026-08-16.md` | Test de bout en bout sur données réelles : état initial, calculs attendus établis avant exécution, déroulement, idempotence, cinq anomalies, dix-sept points vérifiés | Pour la méthode et l'historique des anomalies — **son schéma de référence est périmé**, voir §13 |
| `docs/test-batch-2026-08-19.md` | Rejeu du protocole sur le moteur unifié via `preview` : lissage saisonnier, largeur d'ouverture, rattrapage et blocage post-rempotage vérifiés à la main ; sept anomalies | Avant de toucher au moteur ou au modèle climatique |
| `README.md` | Vide | — |

---

## 10. Flux d'exécution complet

### Batch quotidien (`make run`, ou GitHub Actions à 16:00 UTC)

```text
python -m plantiq.run
  │
  ├─ Étape 0 : ouverture
  │    Écrit : batch_run (started_at) → l'id est propagé à toute l'exécution
  │
  ├─ Étape 1 : météo — weather.collect(batch_id)
  │    Lit   : site (closed_at IS NULL), API OpenWeatherMap
  │    Écrit : weather_log, upsert sur (site_id, observed_on), batch_run_id réécrit
  │    Échec : par site, compté dans sites_failed
  │
  ├─ Étape 2 : rappels — rules.generate(plant_id, batch_id) par plante
  │    Lit   : plant, species, species_watering, plant_placement, room_version,
  │            room_vertex, wall_element, plant_equipment, equipment, material,
  │            weather_log, care_log, plant_health
  │    Calcule : lissage saisonnier → six facteurs → intervalle,
  │              puis un Verdict par action (assess_all)
  │    Écrit : reminder, un par action échue sans rappel ouvert
  │    Échec : par plante, journalisé
  │
  ├─ Étape 3 : notifications
  │    Lit   : reminder échus, notification_log
  │    Filtre : send_decision — premier envoi, puis renvois selon la politique
  │    Envoie : ntfy.sh (titre, corps)
  │    Écrit : notification_log avec ON CONFLICT DO NOTHING, payload complet
  │    Échec : par notification, compté dans send_failed
  │
  └─ Étape 4 : clôture
       Écrit : batch_run (finished_at, compteurs, error)
       Sortie : code 1 si failure, send_failed ou sites_failed non nuls
```

### Interface web (`make up`)

Flask sert les dix blueprints sur le port 8000. Chaque vue ouvre ses propres connexions, sans pool ni cache. Les écritures multi-tables passent par des transactions explicites.

### Modes alternatifs

| Commande | Ce qu'elle fait | Quand l'utiliser |
|---|---|---|
| `make preview` | Évalue chaque action de chaque plante : échéance, raison, décision d'envoi, texte du message — sans rien écrire | Relire la formulation, comprendre pourquoi une action ne part pas |
| `make weather` | Relève la météo seule | Vérifier la clé API, rattraper un relevé |
| `make weather-fields` | Liste les champs renvoyés par OWM | Décider d'ajouter un champ au stockage |
| `make schema` | Reconstruit le schéma — **détruit les données** | Après modification du DDL |
| `make backup` | Exporte toutes les tables en JSON | Avant tout `make schema` |
| `make restore` | Recharge le dernier export | Après un `make schema` |

L'enchaînement `backup` → `schema` → `restore` tient lieu d'outil de migration : `db/migrations/` est vide, aucun outil n'a été choisi.

---

## 11. Outputs produits

### Notification ntfy

**Produite par :** `engine/rules.message()` — **envoyée par :** `adapters/notify.send()`

```text
Arrosage — Yucca IKEA
741 ml.
Dernier arrosage il y a 12 jours, intervalle de 11 jours.
Exposition lumineuse, air humide (68 %).
```

```text
Fertilisation — Yucca IKEA
Première fois, aucun antécédent enregistré.
Rythme : tous les 30 jours, fenêtre avril → septembre.
```

```text
Rempotage — Yucca IKEA
En retard de 1880 jours, soit environ 63 mois.
Fenêtre possible : mars → avril.
Prochaine occasion : mars 2027.
```

La ligne de justification et l'alerte d'exposition n'apparaissent que sur l'arrosage. Le volume n'apparaît que si un pot de volume connu est attaché.

### `notification_log.payload`

**Produit par :** `Context.payload()` — **écrit dans :** colonne `jsonb` de `notification_log`

Payload réellement observé, Yucca IKEA au 19/08, tel que le rapport de test le relève. Le relevé du jour n'existait pas encore à l'heure de l'aperçu, d'où les mesures nulles :

```json
{
  "season": "summer",
  "base_interval": 10.53,
  "season_weights": {"summer": 0.933, "autumn": 0.067},
  "factors": {"porous": 1.0, "drainage": 1.15, "exposure": 1.053,
              "temperature": 1.0, "humidity": 1.0, "radiator": 1.0,
              "product": 1.211},
  "interval": 13,
  "volume_ml": 741,
  "exposure": {"intensity": 0.388, "level": "indirect",
               "distance_m": 1.66, "cardinal": "E", "alert": null},
  "health": null,
  "container": {"material": "Plastique", "porous": false,
                "cachepot": "RÅGKORN", "drains": false},
  "position": "contre un mur",
  "radiator_m": 4.08,
  "weather": null,
  "environment": "indoor",
  "effective": {"temp_c": null, "humidity_pct": null, "converted": true}
}
```

`weather` reste le relevé extérieur brut, `effective` le couple sur lequel les facteurs ont réellement été calculés, `season_weights` explique un `base_interval` décimal. Une notification est reconstituable a posteriori sans rejouer le batch. Le `converted: true` de cet exemple est un défaut, voir §13.

### `batch_run` et la page Exécutions

**Produit par :** `run.run()` — une ligne par exécution.

```text
id=1  started 18/08 21:02:16  16,2 s  sites_ok=1  sites_failed=0
      reminders_new=2  sent=2  send_failed=0  error=NULL
```

La page `/runs` ajoute les comptages réels par `batch_run_id` : relevés écrits, rappels ouverts, notifications envoyées. L'écart entre `reminders_new` et le comptage des rappels liés est affiché.

**Limite écrite dans le schéma :** si la base est injoignable la ligne ne peut pas être écrite. La table enregistre les échecs *dans* une exécution, pas les échecs *de* l'exécution. L'absence de ligne pour la veille est le signal.

### `weather_log`

Une ligne par site et par jour local. Un second passage le même jour met la ligne à jour — `observed_at`, les quatre mesures, `batch_run_id`, `fetched_at` — sans doublon.

### Export JSON

**Produit par :** `backup.py` — `BACKUP_PATH/plantiq_backup_AAAA-MM-JJ_HHMMSS.json`

```json
{
  "exported_at": "2026-08-18T21:40:11.204Z",
  "tables": {
    "material": [{"id": 1, "code": "plastic", "label": "Plastique", "is_porous": false}],
    "site": [{"id": 1, "name": "Meise", "latitude": 50.937056, "...": "..."}]
  }
}
```

### Interface web

Dix sections HTML sans feuille de style, sur le port 8000. Météo, Notifications et Exécutions sont en lecture seule.

---

## 12. Glossaire des technologies

### Flask

Micro-framework web Python. Ici : dix blueprints enregistrés par `create_app()`, templates Jinja, `url_for` partout — aucune URL en dur. Ni extension, ni ORM, ni session, ni authentification.

### psycopg 3

Pilote PostgreSQL. Ici : variant `binary`, connexions à usage unique, `row_factory=dict_row`, paramétrage positionnel `%s`, `executemany` pour les insertions groupées, `INSERT ... SELECT` pour dériver une colonne depuis une autre table, rattrapage typé de `UniqueViolation`.

### Supabase

PostgreSQL hébergé, palier gratuit. Ici : seule persistance. Le schéma accorde les droits aux quatre rôles standards, mais l'application se connecte avec `postgres` et n'utilise ni l'API REST, ni l'authentification, ni le stockage.

### OpenWeatherMap

API météo, palier gratuit. Ici : `/data/2.5/weather` une fois par site et par jour, unités métriques. Cinq champs retenus sur la centaine renvoyée ; `cloud_pct` sert à l'apport solaire.

### ntfy.sh

Notification push par topic, sans compte. Ici : publication JSON pour préserver l'UTF-8, priorité 3 par défaut. Le topic est le seul secret protégeant le canal.

### GitHub Actions

Ordonnanceur et CI. Ici : deux workflows, lint/tests et batch quotidien. Le rouge d'une exécution est le seul mécanisme d'alerte.

### Magnus-Tetens

Formule empirique de la pression de vapeur saturante, coefficients OMM sur eau. Ici : `climate.py` s'en sert deux fois — convertir une humidité extérieure en humidité intérieure après réchauffement, et calculer le point de rosée qui sert d'invariant de test.

### ruff et pytest

Ici : ruff en règles E, F, I, UP, tri des imports paramétré sur `plantiq` ; pytest sur `tests/`, sans plugin, sans fixture de base.

### SVG sans bibliothèque

Ici : `plan.js` construit les nœuds par `createElementNS`, sans D3. Les événements souris sont convertis par la matrice écran, seule conversion fiable quand le `viewBox` est encadré.

### Pattern — moteur de décision à source unique

`Verdict` / `assess()` pour l'échéance, `send_decision()` pour l'envoi. Les deux sont en lecture seule et renvoient la décision **avec sa raison**. `generate()`, `preview()` et `message()` consomment les mêmes objets. L'aperçu ne peut pas mentir sur ce que fera le batch, et un « pourquoi ça n'est pas parti » se lit sans instrumenter le code.

### Pattern — clôture au lieu de suppression

Une ligne obsolète reçoit un `closed_at` et reste en base. Appliqué à `site`, `room`, `room_version`, `plant`, `plant_placement`, `equipment`, `plant_equipment`, `wall_element`. Un index unique partiel sur `closed_at IS NULL` porte alors l'unicité temporelle.

### Pattern — append-only pour l'état observé

`care_log` et `plant_health` ne se clôturent pas : une observation est un fait, corrigé sur place si mal saisi, jamais fermé. Pas de colonne de statut sur `plant` — l'état courant est la ligne la plus récente.

### Pattern — dénormalisation verrouillée par clé composite

`plant_equipment.equipment_type` duplique `equipment.type`, et une clé étrangère composite adossée à `UNIQUE (id, type)` interdit la dérive. La copie n'est pas une commodité : c'est ce qui rend « un pot et un cache-pot ouverts, pas deux pots » exprimable comme index partiel.

### Pattern — géométrie immuable et versionnée

Une pièce ne se modifie pas : tout changement structurel ouvre une `room_version`. Les emplacements référencent une **version**, jamais une pièce. La géométrie sous un marqueur ne peut pas changer sous lui.

### Pattern — calibrage dérivé, jamais stocké

Le rapport unités/centimètre est recalculé à la demande depuis `scale_wall_index` et `scale_cm`. Déplacer un sommet du mur de référence recalibre toute la pièce au lieu de laisser un rapport figé mentir. `rooms.py`, `rules.py` et `plan.js` appliquent le même calcul.

### Pattern — dégradation neutre

Une donnée manquante vaut 1,00, jamais zéro et jamais une exception. Pas de météo, pas de fenêtre, pas de calibrage, drainage non renseigné, saison absente : le calcul continue. Le tri-état du drainage est la forme explicite du principe — « je ne sais pas » n'est pas « non ».

### Pattern — facteurs multiplicatifs écrêtés

Six facteurs indépendants, neutres à 1,00, multipliés puis bornés à `[0,70 ; 1,40]`. L'écrêtage remplace une sensibilité par espèce abandonnée en conception et garantit qu'aucun empilement ne produit d'intervalle aberrant.

### Pattern — interpolation plutôt que seuil

Le lissage saisonnier remplace un saut discret par une transition linéaire de 30 jours. Même intention que l'écrêtage : un modèle qui bouge par paliers produit des décisions que l'utilisateur ne peut pas relier à la réalité.

### Pattern — conversion à la frontière du milieu

`room_version.environment` décide si le relevé extérieur est utilisé tel quel ou converti par `climate.py`. La conversion a lieu en un seul endroit, dans `context()`, et le payload conserve les deux couples.

### Pattern — idempotence par index unique

Trois index : `weather_log (site_id, observed_on)` avec `DO UPDATE`, `ux_notification` avec `DO NOTHING`, `ux_reminder_open` contre l'empilement. Rejouer le batch dans la journée ne duplique rien et n'envoie rien deux fois.

### Pattern — date réelle contre date de saisie

Chaque événement porte deux dates : celle du monde réel (`done_at`, `attached_on`, `noted_on`) et celle de l'enregistrement (`recorded_at`, `created_at`). L'interface les distingue, un `CHECK` impose le sens de l'écart sur `care_log`.

### Pattern — fuseau du site, jamais UTC

`weather_log.observed_on`, `reminder.due_on` et `notification_log.sent_on` sont des dates locales du site, calculées en Python via `zoneinfo`. La base ne stocke que des instants absolus ; le découpage en journées se fait dans le fuseau du site.

### Pattern — miroir navigateur / serveur

`plan.js` reproduit délibérément la règle semi-ouverte d'appartenance, la tolérance de rabattement et le calcul du calibrage. La duplication est le prix d'une interface qui ne propose jamais un geste que le serveur refusera.

---

## 13. Risques et limites connus

Les identifiants `5.x` et `6.x` renvoient aux rapports de test du 19/08 et du 16/08.

### `climate.py` n'est validé par aucun test de bout en bout — 5.1, majeur

**Description :** `context()` lit la météo du jour, `WHERE observed_on = ctx.today`. Le relevé du jour est écrit par le batch à 16 h UTC. Tout aperçu lancé avant : `ctx.weather` vaut `None`, les facteurs de température et d'humidité restent neutres, `climate.py` n'est pas appelé.
**Impact :** l'écart n'est pas théorique. Avec le relevé du 18/08 — 20,7 °C, 86 %, 99 % de nuages — la conversion donnait 20,6 °C et 86,4 % à l'intérieur, l'humidité plafonnait le facteur à 1,10, et le Yucca passait de 13 à 14 jours. Le seul module physique du projet reste sans validation bout en bout.
**Action corrective :** faire retomber `context()` sur le dernier relevé disponible en marquant l'âge de la donnée dans le payload, ou faire relever la météo par `make preview` avant de calculer.

### `effective.converted` affirme une conversion qui n'a pas eu lieu — 5.2, modéré

**Description :** `converted` est calculé comme `environment == "indoor"`, soit l'intention de convertir et non la conversion. Sans météo, le champ vaut `true` avec deux mesures nulles à côté.
**Impact :** le défaut est dans le bloc ajouté précisément pour rendre le calcul reconstituable. Un lecteur de payload conclurait que 20 °C viennent d'une conversion.
**Action corrective :** `"converted": self.environment == "indoor" and self.weather is not None`.

### Le cache-pot est compté deux fois — 5.3, décision de modélisation

**Description :** un cache-pot sans trou annule le facteur de porosité — parois scellées — **et** applique `NO_DRAINAGE_FACTOR` — eau stagnante. Sur la Fleur de lune, le produit passe de 0,97 à 1,31 : +35 % d'intervalle pour un seul objet, à 0,09 du plafond d'écrêtage.
**Impact :** les deux effets sont physiquement distincts, donc le cumul est défendable, mais il vient du même objet et son ampleur devrait être voulue explicitement.
**À trancher :** conserver le cumul, ou ne retenir que le plus fort des deux.

### Extinction silencieuse après les renvois — 5.4, mineur

**Description :** passé le nombre de renvois autorisés, `send_decision` renvoie faux définitivement, mais le rappel reste ouvert et `assess` continue à le déclarer échu.
**Impact :** une tâche jamais traitée cesse d'être notifiée sans que rien ne l'escalade ni ne la close. Le rappel de fertilisation du Yucca s'éteindra le 01/09 après son troisième envoi ; il restera visible sur la fiche et dans `/runs`, nulle part ailleurs.
**Action corrective :** décider entre clôture automatique avec `dismissed_reason`, escalade de priorité, ou renvoi indéfini plus espacé.

### Deux artefacts dans `batch_run` — 5.5, mineur

**Description :** les lignes 4 et 5 ne correspondent à aucune exécution réelle. La 4 porte une durée de 60,000000 s exactement, l'erreur « OWM indisponible : timeout » et `send_failed = 2` avec `sent = 0` ; la 5 n'a pas de `finished_at`. Elles ont servi à éprouver l'affichage de `/runs`.
**Impact :** elles faussent toute lecture statistique de l'historique.
**Action corrective :** les supprimer, l'affichage étant validé.

### La moitié température de 6.3 reste non surveillée, par décision

**Description :** le volet exposition est implémenté — `exposure_alert()` compare le niveau mesuré à la plage de l'espèce, dans la notification d'arrosage, dans `make preview` et dans le payload. Le volet température est délibérément absent : `indoor_temperature` borne la pièce à `[20 ; 28] °C`, donc un minimum d'espèce à 18 °C ne peut jamais être franchi en intérieur. La comparaison serait structurellement muette, ce qui se lit comme un feu vert et vaut moins que pas de comparaison. La raison est écrite dans la docstring d'`exposure_alert()`.
**Impact :** un dépassement thermique réel reste non signalé — le cas que le rapport du 16/08 citait.
**Action corrective :** trancher d'abord le plancher de 20 °C, puis brancher la comparaison de température au même endroit.

### Le plancher de température intérieure masque les alertes de froid

**Description :** `indoor_temperature` borne à `[20 ; 28] °C`. Une plante en intérieur ne peut jamais être vue sous 20 °C.
**Impact :** aujourd'hui invisible, `factor_temperature` ne mordant qu'au-dessus de 25 °C. Mais l'alerte que le risque précédent doit produire serait structurellement muette pour l'intérieur.
**Action corrective :** décider si le plancher est un modèle de confort du logement ou une hypothèse à assouplir.

### L'état de santé n'est consommé que pour deux de ses six valeurs — 5.7

**Description :** `dormant` et `dying` bloquent la fertilisation. L'arrosage n'est pas touché : une plante en difficulté boit encore. Les quatre autres statuts, dont `stressed` qui est celui de la Fleur de lune depuis le 10/08, n'ont aucun effet.
**Impact :** limité et voulu. Le choix a été de bloquer plutôt que de pondérer, un septième facteur ayant été écarté parce que l'écrêtage à 1,40 — déjà atteint à 1,31 — l'aurait avalé silencieusement.
**Action corrective :** aucune tant que `stressed` et `recovering` n'ont pas de sens métier arrêté.

### Deux notions de « aujourd'hui » dans le batch

**Description :** les chemins de **décision** sont unifiés dans le fuseau du site — `ctx.today` pour `assess`, `send_decision`, `preview`. La **sélection** des rappels échus compare `due_on` à `date.today()`, soit UTC sur GitHub Actions. Deux commentaires `DETTE` dans `run.py` documentent l'écart.
**Impact :** entre minuit et 2 h heure belge en été, le comparateur retarde d'un jour sur le reste du moteur. Sans effet à 16 h UTC ; un lancement manuel tardif l'exposerait.
**Action corrective :** passer la date du site à `_due_reminders`, comme le fait déjà `weather.py`.

### Interface web sans authentification, servie en mode debug

**Description :** aucune route protégée, aucun jeton CSRF, et `docker-compose.yml` lance Flask avec `--debug`, ce qui active le débogueur interactif de Werkzeug. Les routes d'écriture couvrent la santé et les contenants en plus du reste.
**Impact :** exposer le port 8000 hors de la machine locale donnerait un accès complet en écriture et, via le débogueur, une exécution de code arbitraire.
**Mitigation actuelle :** usage mono-utilisateur et local, rien ne l'impose techniquement.
**Action corrective :** retirer `--debug` de toute configuration exposée, ne publier le port que sur `127.0.0.1`.

### Couverture de tests : le moteur est couvert, la persistance ne l'est pas

**Description :** `geometry`, `light`, `climate` et la partie décisionnelle de `rules` sont testés — 59 cas. Sans test : `context()` et toute lecture en base, les dix blueprints, `run.py`, `weather.py`, `backup.py`, `restore.py`, les adaptateurs.
**Impact :** c'est exactement la zone où se situait le défaut d'ordre de `restore.py`. Une régression sur une requête, un `JOIN` ou un ordre de restauration passe la CI au vert.
**Raison du report :** tester ces chemins demande un service PostgreSQL en CI — un changement d'infrastructure, pas seulement des tests.

### `flask` non épinglée

**Description :** `httpx` et `psycopg` sont en `==`, `flask` non.
**Impact :** une reconstruction d'image ou une exécution de CI peut tirer une version majeure différente et casser sans changement de code.
**Action corrective :** épingler dans `app/pyproject.toml`.

### Absence d'outil de migration

**Description :** `db/schema.sql` reconstruit en détruisant, `db/migrations/` est vide. Le passage de `potting` à `plant_equipment` et l'ajout de `plant_health` se sont faits par reconstruction.
**Impact :** toute évolution du modèle impose `backup` → `schema` → `restore`, chemin manuel, non versionné, sans retour arrière au-delà du dernier export.
**Action corrective :** choisir un outil, ou formaliser l'enchaînement dans une cible unique du Makefile.

### Invariants métier portés par l'application seule

**Description :** onze invariants sont énumérés en commentaire dans `db/schema.sql`, un `CHECK` ne pouvant pas interroger une autre table. `plant_equipment` n'accepte en théorie que des types appartenant à une seule plante, mais rien n'empêche d'y attacher un substrat ou un outil.
**Impact :** une écriture contournant les vues — script, console SQL, restauration partielle — peut produire un état que le moteur lira sans broncher et interprétera de travers.
**Mitigation actuelle :** les blueprints valident avant écriture, les écritures multi-tables sont transactionnelles.

### Aucune supervision hors du rouge GitHub

**Description :** `batch_run` enregistre les échecs survenus *dans* une exécution ; si la base est injoignable, aucune ligne n'est écrite. `/runs` donne la lecture de l'historique mais n'émet aucune alerte.
**Impact :** une panne prolongée se remarque à l'absence de notifications, ou en consultant `/runs`.
**Mitigation actuelle :** code de sortie 1 propagé à GitHub Actions, qui notifie l'échec par courriel.

### Trois actions de soin sans moteur — 6.5

**Description :** `care_action` propose `pruning`, `treatment` et `cleaning` ; `ACTIONS` dans `rules.py` ne couvre que `watering`, `fertilizing`, `repotting`. `assess()` renvoie pour les autres « hors du périmètre du moteur ».
**Impact :** ces trois actions ne peuvent être que saisies à la main. Cohérent avec le modèle, explicite dans le code, mais aucune règle ne les déclenchera.

### Une connexion par requête

**Description :** `core.database.query()` ouvre et ferme une connexion à chaque appel. `context()` en déclenche neuf par plante, la fiche d'une plante une dizaine.
**Impact :** nul à l'échelle actuelle — un site, deux plantes. La latence deviendrait sensible avec une base plus fournie, et Supabase limite les connexions simultanées sur le palier gratuit.
**Raison du report :** dette assumée, documentée par un commentaire dans le module.

### Code mort et duplications

**Description :** relevé à la lecture des sources, sans impact fonctionnel aujourd'hui.

| Élément | Constat |
|---|---|
| `weather.for_site()` et `weather._today()` | Aucun appelant : `rules.context()` interroge `weather_log` directement |
| `geometry.point_in_polygon(tolerance=...)` | Le paramètre n'est passé par aucun appelant ; `pull_inside` porte la tolérance |
| `Exposure.width_m` | Calculé et transporté, absent du payload — seul `intensity` en garde la trace |
| `HEATING_MONTHS` | Défini à l'identique dans `climate.py` et `rules.py`, sans lien entre les deux |
| `message(ctx, action, verdict=None)` | Les deux appelants omettent `verdict`, donc `assess()` tourne deux fois par notification |
| Docstring de `adapters/probe.py` | Annonce `make weather` ; la cible est `make weather-fields` |

**Impact :** dérive silencieuse. Une modification de `HEATING_MONTHS` d'un seul côté désynchroniserait le modèle climatique du facteur radiateur.

### Le rapport de test du 16/08 décrit un schéma périmé

**Description :** il porte sur 17 tables avec `potting`, un moteur à cinq facteurs sans conversion intérieure, une intensité sans largeur d'ouverture et un intervalle de base entier. Ses sections 2, 3, 4 et 7 ne sont plus reproductibles.
**Impact :** le document reste précieux pour sa méthode — calculs attendus établis avant exécution, vérification indépendante à la main — et pour l'historique des anomalies, dont trois ont été corrigées. Ses chiffres ne servent plus de référence.
**Action corrective :** faite le 19/08, voir `docs/test-batch-2026-08-19.md`.

### Poids inutile dans l'image Docker

**Description :** le Dockerfile installe `build-essential` et `libpq-dev` alors que `psycopg[binary]` embarque libpq et ne compile rien.
**Impact :** temps de construction et taille d'image, sans effet fonctionnel.
**Action corrective :** retirer les deux paquets et vérifier que l'installation aboutit.

### Dev Container absent

**Description :** `.devcontainer/` est vide, sans `devcontainer.json`.
**Impact :** VSCode ne peut pas ouvrir le projet dans le conteneur ; l'analyse statique s'appuie sur un interpréteur hôte qui ne connaît pas les dépendances de l'image.
