<!-- docs/daily-run-migration.md -->

# plantiq — Audit scheduling & migration GitHub Actions

**Date :** 2026-06-26
**Statut :** Temporaire — à supprimer après décision

---

## Tâche 1 — Audit de l'état actuel

### 1. Scheduling dans `project-reference.md`

Trois mentions, toutes convergentes :

- **Ligne 35** : *"déployé sur Fly.io avec `cron = "0 18 * * *"` (18h UTC quotidien)"*
- **Ligne 85** : *"fly.toml — config déploiement Fly.io + cron schedule"*
- **Ligne 155** : *"`[schedule] cron = "0 18 * * *"` déclenche l'exécution quotidienne à 18h UTC"*

Le format décrit est une section `[schedule]` dans `fly.toml` avec une expression cron standard 5 champs.

---

### 2. Scheduling réel dans `fly.toml`

Le fichier réel (`fly.toml`, lignes 1–16) contient uniquement :

```toml
[build]
    dockerfile = 'scheduler/Dockerfile'
    context = '.'

[[vm]]
    size = 'shared-cpu-1x'
    memory = '256mb'
```

**La section `[schedule]` est totalement absente.** Aucune planification n'est configurée côté Fly.io dans ce fichier.

---

### 3. README.md — cohérence avec fly.toml et project-reference.md

`README.md` ligne 21 prescrit :

```bash
fly machine update <machine-id> --schedule daily
```

Incohérent sur deux points :

- **Format** : project-reference.md décrit `[schedule] cron = "0 18 * * *"` (section fly.toml, heure précise). Le README utilise `--schedule daily` (commande CLI machine-level, sans heure, granularité "une fois par jour" uniquement).
- **Mécanisme** : `[schedule]` dans fly.toml configure le scheduling au niveau de l'application au déploiement. `fly machine update --schedule daily` configure la machine individuellement post-déploiement. Ce sont deux mécanismes distincts.

`--schedule daily` ne permet pas de contrôler l'heure d'exécution à 18h UTC. Le README, project-reference.md et fly.toml décrivent donc trois états incompatibles.

---

### 4. CMD du Dockerfile — compatibilité one-shot

`scheduler/Dockerfile` ligne 18 :

```dockerfile
CMD ["python", "-m", "plantiq.run"]
```

Cette ligne **contredit directement project-reference.md ligne 193** qui dit explicitement *"Pas de `CMD`"*.

Concernant la compatibilité one-shot :

- Le `CMD` est fonctionnellement correct pour Fly.io avec schedule : le process démarre, exécute `run.py`, se termine avec code 0 (ou 1 si erreur) → Fly ne redémarre pas une machine schedulée après exit propre.
- Sans schedule configuré, Fly peut tenter de maintenir la machine active en relançant le process après chaque exit, créant des runs non désirés.
- Côté Docker Compose, toutes les commandes Makefile (`make test`, `make lint`, `make sh`) utilisent `docker compose run --rm scheduler <cmd>` qui écrase le CMD → aucun conflit en pratique.

Le CMD est compatible avec le one-shot **à condition qu'un schedule soit effectivement attaché** à la machine Fly.

---

### 5. Workflow CI/CD existant

`.github/workflows/ci.yml` existe avec les étapes suivantes :

| Étape | Détail |
|---|---|
| `actions/checkout@v4` | Clone le repo |
| `actions/setup-python@v5` Python 3.13 | Installation native, cache pip |
| `pip install -e ".[dev]"` dans `./scheduler` | Installe le package + ruff + pytest — sans Docker |
| `ruff check .` dans `./scheduler` | Lint (règles E, F, I, UP sauf E501) |
| `pytest` dans `./scheduler` | Tests avec 3 env vars placeholders hardcodées |

Déclencheurs : push sur `main`/`develop`, PR vers `main`. **Aucun déclencheur `schedule:`.**

Ce workflow peut servir de base directe : la step "Install package" et l'approche Python natif sur `ubuntu-latest` sont exactement ce qu'un workflow de run quotidien utiliserait.

---

### 6. Variables d'environnement côté CI

Dans `ci.yml` lignes 34–37 :

```yaml
env:
  DATABASE_URL: postgresql+psycopg://postgres:placeholder@db.placeholder.supabase.co:5432/postgres
  OPENWEATHERMAP_API_KEY: placeholder
  NTFY_TOPIC: plantiq
```

Valeurs hardcodées en clair, suffisantes pour les tests mockés. Pour une exécution de production, il faudrait des `${{ secrets.X }}` — **GitHub Secrets non créés**.

---

### Tableau de synthèse

| Élément | État | Raison |
|---|---|---|
| Section `[schedule]` dans `fly.toml` | **MANQUANT** | Absente du fichier réel (lignes 1–16) malgré ce que dit project-reference.md |
| Cohérence doc scheduling | **INCOHÉRENT** | Trois descriptions divergentes : `[schedule]` (project-reference.md), `--schedule daily` (README), rien (fly.toml réel) |
| `CMD` dans Dockerfile | **INCOHÉRENT** | Présent ligne 18 du Dockerfile réel, mais project-reference.md ligne 193 dit "Pas de CMD" |
| Secrets CI (production) | **MANQUANT** | `ci.yml` utilise des valeurs hardcodées, aucun `${{ secrets.X }}` configuré |
| Tests + lint CI | **OK** | `ci.yml` tourne correctement en Python natif sur `ubuntu-latest` |
| Compatibilité one-shot (CMD) | **OK conditionnel** | Fonctionnellement correct si et seulement si un schedule est attaché |

---

## Tâche 2 — Plans de migration vers GitHub Actions

---

### Plan A — Python natif dans le runner (fichier dédié)

Un nouveau workflow `.github/workflows/daily-run.yml` déclenché par `schedule:` exécute `python -m plantiq.run` directement sur l'agent `ubuntu-latest`, sans Docker.

- **Fichiers** : créer `.github/workflows/daily-run.yml`
- **Avantages** : installation rapide (psycopg[binary] est un wheel précompilé, pas de compilation C), architecture identique au CI existant, aucun daemon Docker, exécution < 30 secondes, compatible repo privé (quota GitHub Actions gratuit : 2 000 min/mois)
- **Inconvénients** : environnement runner légèrement différent de l'image Docker (Ubuntu vs Debian slim), potentiel drift si des dépendances système sont ajoutées
- **Complexité** : Faible
- **Repo privé** : oui

---

### Plan B — Exécution via Docker dans le runner

Un nouveau workflow `.github/workflows/daily-run.yml` build l'image Docker depuis `scheduler/Dockerfile` puis lance un conteneur avec les secrets injectés.

- **Fichiers** : créer `.github/workflows/daily-run.yml`
- **Avantages** : environnement de production reproduit à l'identique, validation implicite du Dockerfile à chaque run
- **Inconvénients** : `apt-get install build-essential libpq-dev` + `pip install` à chaque run → 2–4 minutes de build sans cache efficace, complexité accrue
- **Complexité** : Moyenne
- **Repo privé** : oui

---

### Plan C — Réutilisation et extension du `ci.yml` existant

Ajouter un déclencheur `schedule:` au `ci.yml` existant et un second job `run:` conditionné à l'origine de l'événement.

- **Fichiers** : modifier `.github/workflows/ci.yml`
- **Avantages** : un seul fichier workflow à maintenir
- **Inconvénients** : mélange CI (lint/test) et production (run réel) dans un même fichier — un échec de lint peut bloquer le run de production, logique conditionnelle complexe (`if: github.event_name == 'schedule'`)
- **Complexité** : Moyenne
- **Repo privé** : oui

---

### Recommandation : Plan A

Plan A est la seule option rationnelle pour ce projet :

1. Le CI existant prouve déjà que Python natif sur `ubuntu-latest` fonctionne (même chaîne : `pip install -e ".[dev]"` dans `./scheduler`, Python 3.13, `psycopg[binary]`).
2. `psycopg[binary]` élimine le besoin de `libpq-dev` et de compilation.
3. Séparer CI (`ci.yml`) et run quotidien (`daily-run.yml`) : workflows indépendants, déclencheurs différents, échecs non couplés.
4. Overhead Docker (Plan B) injustifiable pour un process < 10 secondes.
5. Zéro coût, zéro carte bancaire, compatible repo privé.

---

### Workflow complet — Plan A

```yaml
# .github/workflows/daily-run.yml

name: Daily run

on:
  schedule:
    - cron: "0 18 * * *"
  workflow_dispatch:

jobs:
  run:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.13"
          cache: "pip"
          cache-dependency-path: "scheduler/pyproject.toml"

      - name: Install package
        working-directory: ./scheduler
        run: pip install -e "."

      - name: Run plantiq
        working-directory: ./scheduler
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
          OPENWEATHERMAP_API_KEY: ${{ secrets.OPENWEATHERMAP_API_KEY }}
          NTFY_TOPIC: ${{ secrets.NTFY_TOPIC }}
        run: python -m plantiq.run
```

**Trois actions requises pour activer ce workflow :**

1. Créer le fichier `.github/workflows/daily-run.yml` ci-dessus.
2. Créer les trois GitHub Secrets dans Settings → Secrets and variables → Actions :
   - `DATABASE_URL` — URL psycopg3 complète vers Supabase
   - `OPENWEATHERMAP_API_KEY` — clé OWM
   - `NTFY_TOPIC` — nom du topic ntfy
3. Décider du sort de Fly.io : si ce workflow remplace Fly, la VM peut être suspendue ou supprimée (`fly apps destroy`).

**Notes :**

- `workflow_dispatch` permet un déclenchement manuel depuis GitHub pour tester avant le premier run automatique.
- `pip install -e "."` (sans `[dev]`) évite d'installer ruff et pytest en production.
- `python-dotenv` tentera de charger un `.env` absent sur le runner — `find_dotenv()` ne trouvera rien et tombera silencieusement, les variables venant de l'`env:` du step.
