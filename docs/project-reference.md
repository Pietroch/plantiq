<!-- docs/project-reference.md -->

# plantiq

## Objet

plantiq surveille des plantes d'intérieur. Il lit leur état dans une base Supabase, récupère la météo locale, décide si un soin est nécessaire, et envoie une notification sur le téléphone. Une interface web sert à consulter et saisir les données.

## Contenu du projet

```text
plantiq/
├── .devcontainer/                    ← vide
├── .github/                          ← vide
├── app/                              ← service applicatif
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── src/plantiq/                  ← package Python
│   │   ├── __init__.py               ← vide
│   │   ├── adapters/                 ← vide
│   │   ├── core/                     ← vide
│   │   ├── engine/                   ← vide
│   │   └── web/
│   │       ├── __init__.py           ← vide
│   │       └── app.py                ← vide
│   └── tests/                        ← vide
├── db/
│   ├── schema.sql                    ← vide
│   └── migrations/                   ← vide
├── docs/
│   └── project-reference.md          ← ce document
├── .dockerignore
├── .editorconfig
├── .env                              ← secrets réels, non commité
├── .env.example                      ← modèle du .env, commité
├── .gitignore
├── docker-compose.yml
├── Makefile
└── README.md                         ← vide
```

Les dossiers vides ne sont pas suivis par Git : ils disparaîtront au prochain clone.

## Le service `app`

Un seul service, qui porte l'interface web, la tâche quotidienne et les outils en ligne de commande. Un seul package Python, une seule image.

### `app/Dockerfile`

Image `python:3.13-slim`. Installe `build-essential` et `libpq-dev`, puis le package en mode éditable avec ses dépendances de développement. Le code et les tests sont copiés ensuite.

Pas de `CMD` : la commande est définie dans `docker-compose.yml`.

### `app/pyproject.toml`

Package `plantiq`, Python 3.12 minimum, disposition `src/`.

| Dépendance | Type       | Rôle           |
|------------|------------|----------------|
| `flask`    | production | Serveur web    |
| `pytest`   | dev        | Tests          |
| `ruff`     | dev        | Lint et format |

Ruff est réglé sur 100 caractères, règles E, F, I et UP, E501 ignorée. Pytest cherche les tests dans `tests/`.

### `app/src/plantiq/`

| Dossier     | Rôle prévu                                         |
|-------------|----------------------------------------------------|
| `core/`     | Configuration, connexion à la base, journalisation |
| `engine/`   | Règles de décision                                 |
| `adapters/` | Accès à la météo et envoi des notifications        |
| `web/`      | Interface web Flask                                |

## Le dossier `db`

`schema.sql` porte la définition du schéma Supabase. `migrations/` accueillera les évolutions ultérieures — aucun outil de migration n'est encore choisi.

## Les fichiers de la racine

### `docker-compose.yml`

Un service, `web`, conteneur `plantiq_web`.

- Image construite depuis la racine, avec `app/Dockerfile`.
- `restart: unless-stopped` : le service tourne en continu.
- Port 8000 exposé.
- Commande : `flask --app plantiq.web.app run --host 0.0.0.0 --port 8000 --debug`.
- Deux volumes montent `app/src` et `app/tests`, pour modifier le code sans reconstruire l'image.
- Les variables viennent du `.env` de la racine.

Pas de réseau ni de volume nommé : il n'y a pas de base locale, tout est chez Supabase.

### `Makefile`

Huit raccourcis, tous exécutés dans un conteneur Docker.

| Commande     | Ce qu'elle fait                                      |
|--------------|------------------------------------------------------|
| `make up`    | Démarre le service en arrière-plan                   |
| `make down`  | Arrête le service                                    |
| `make build` | Construit l'image Docker                             |
| `make logs`  | Affiche les logs en continu                          |
| `make sh`    | Ouvre un shell dans le conteneur                     |
| `make run`   | Lance la tâche quotidienne (`python -m plantiq.run`) |
| `make test`  | Lance les tests (`pytest`)                           |
| `make lint`  | Vérifie le code (`ruff check .`)                     |

La ligne `.PHONY` déclare aussi `simulate`, `log`, `backup` et `help`, qui ne correspondent à aucune cible.

### `.env` et `.env.example`

`.env` porte les vraies valeurs et n'est jamais commité. `.env.example` est le modèle, avec les valeurs vidées.

| Variable                 | Obligatoire | Ce que c'est                                                  |
|--------------------------|-------------|---------------------------------------------------------------|
| `DATABASE_URL`           | oui         | Adresse de connexion à la base Supabase                       |
| `OPENWEATHERMAP_API_KEY` | oui         | Clé de l'API météo                                            |
| `NTFY_TOPIC`             | oui         | Nom du canal de notification                                  |
| `BACKUP_PATH`            | non         | Dossier où écrire les exports. Par défaut, le dossier courant |

Le `.env` contient des identifiants réels. Ils sont hors de Git, mais en clair sur le disque.

### `.gitignore`

Exclut `.env`, `*.pyc`, `__pycache__/` et `*.egg-info/`.

### `.dockerignore`

Exclut du contexte de build `.git`, `.env`, `.devcontainer/`, `.github/`, `docs/`, les fichiers Markdown et `__pycache__/`.

### `.editorconfig`

UTF-8, fins de ligne LF, indentation de 4 espaces — 2 pour les fichiers YAML et TOML. Les espaces en fin de ligne sont supprimés, sauf en Markdown où ils servent aux retours à la ligne.

## Services externes

| Service        | Rôle                             | Coût           |
|----------------|----------------------------------|----------------|
| Supabase       | Base de données PostgreSQL       | Palier gratuit |
| OpenWeatherMap | Météo courante par coordonnées   | Palier gratuit |
| ntfy.sh        | Notifications push sur téléphone | Gratuit        |

## Ce qui fonctionne aujourd'hui

`make build` aboutit. L'image contient Python, Flask et le package `plantiq` installé en mode éditable.

`make up` démarre le conteneur, qui s'arrête aussitôt : `app.py` est vide, Flask n'y trouve aucune application à servir. Le service redémarre en boucle tant que le fichier reste vide.

Les autres commandes visent des modules qui n'existent pas encore.

## Éléments attendus mais absents

| Attendu par          | Élément absent                                    |
|----------------------|---------------------------------------------------|
| `docker-compose.yml` | Une application Flask dans `plantiq/web/app.py`   |
| `Makefile`           | Le module `plantiq.run`, et des tests à exécuter  |
| `.devcontainer/`     | `devcontainer.json`                               |
| `.github/`           | `workflows/`                                      |
| `db/`                | Le contenu de `schema.sql`, un outil de migration |
