<!-- docs/test-batch-2026-08-16.md -->

# Rapport de test — batch quotidien

**Date d'exécution :** 2026-08-16, 21h33 UTC (23h33 Europe/Brussels)
**Version testée :** `plantiq.run` sur schéma à 17 tables
**Environnement :** conteneur `plantiq_web`, base Supabase de production, données réelles
**Testeur :** exécution manuelle via `make run`

---

## 1. Objet du test

Vérifier de bout en bout la chaîne quotidienne : relevé météo, calcul des besoins,
génération des rappels, envoi des notifications, traçabilité. Aucune donnée n'a été
fabriquée pour l'occasion — le test porte sur les deux plantes réellement enregistrées.

---

## 2. État initial

### 2.1 Référentiel

| Table | Lignes | Contenu |
|---|---|---|
| `site` | 1 | Meise (50.937056, 4.326048), fuseau `Europe/Brussels` |
| `species` | 2 | *Yucca gigantea*, *Spathiphyllum wallisii* |
| `species_watering` | 8 | 4 saisons × 2 espèces |
| `plant` | 2 | Yucca IKEA, Fleur de lune IKEA |
| `room` / `room_version` | 1 / 1 | Séjour, étage 2, intérieur |
| `room_vertex` | 5 | polygone à 5 sommets |
| `wall_element` | 4 | 1 fenêtre, 2 radiateurs, 1 climatiseur |
| `potting` | 2 ouverts | 1 pot plastique, 1 pot terre cuite |
| `care_log` | 3 | 3 arrosages saisis |
| `weather_log` | 2 | relevés du 15 et du 16 |
| `reminder` / `notification_log` / `batch_run` | 0 / 0 / 0 | tables vides avant test |

### 2.2 Espèces

| | Yucca gigantea | Spathiphyllum wallisii |
|---|---|---|
| Arrosage printemps / été / automne / hiver | 12 / 10 / 18 / 28 j | 7 / 5 / 9 / 10 j |
| Volume | 130 ml/L | 150 ml/L |
| Exposition tolérée | `indirect` → `direct` | `low` → `bright_indirect` |
| Soleil | filtré | filtré |
| Températures | 10 – 27 °C | 18 – 24 °C |
| Fertilisation | 30 j, avril → septembre | 15 j, mars → septembre |
| Rempotage | 36 mois, mars → avril | 24 mois, mars → mai |

### 2.3 Géométrie de la pièce

Sommets : (260,60) (400,60) (400,380) (300,400) (200,100).
Calibrage : mur 0 = 140 unités déclaré à 382 cm, soit **0,3665 unité/cm**.

| Mur | Longueur | Éléments |
|---|---|---|
| 0 | 382 cm | fenêtre, t 0,20 → 0,97 |
| 1 | 873 cm | — |
| 2 | 278 cm | — |
| 3 | 863 cm | radiateur, t 0,0275 → 0,1155 |
| 4 | 197 cm | radiateur t 0,527 → 0,858 · climatiseur t 0,100 → 0,427 |

Surface calculée : **37,82 m²**. Nord à 276° sur le plan.

### 2.4 Historique des soins avant test

| care_log | Plante | Action | Fait le | Volume |
|---|---|---|---|---|
| 3 | Yucca IKEA | arrosage | 13/08/2026 | 700 ml |
| 4 | Fleur de lune IKEA | arrosage | 13/08/2026 | 500 ml |
| 5 | Fleur de lune IKEA | arrosage | 16/08/2026 | 400 ml |

Les trois ont été saisis le 16/08 à 21h28-21h29 : `recorded_at` postérieur à `done_at`,
ce que la contrainte `recorded_at >= done_at` a accepté sans réserve.

---

## 3. Calculs attendus, établis avant l'exécution

### 3.1 Yucca IKEA

Fenêtre la plus proche : mur 0, orientation **est**, distance **1,66 m**, visible.

```
intensité   = 0,70 × 4 / (1 + 1,66)²        = 0,3957   → niveau « indirect »
porosité    = plastique                     = 1,0000
exposition  = 1,15 − 0,25 × 0,396           = 1,0511
température = 17,8 °C < 25 °C               = 1,0000
humidité    = 1 + 0,004 × (78 − 60)         = 1,0720
radiateur   = 4,08 m, et août hors chauffe  = 1,0000
produit                                     = 1,1268   (dans [0,70 ; 1,40])
intervalle  = 10 × 1,1268 = 11,27           → 11 jours
volume      = 5,70 L × 130 ml/L             = 741 ml
```

Dernier arrosage 13/08 + 11 j → **échéance 24/08**, donc pas de rappel d'arrosage.
Fertilisation : aucun antécédent, août dans la fenêtre avril-septembre → **échue ce jour**.
Rempotage : août hors fenêtre mars-avril → aucun rappel.

### 3.2 Fleur de lune IKEA

Fenêtre la plus proche : mur 0, orientation **est**, distance **8,56 m**, visible.

```
intensité   = 0,70 × 4 / (1 + 8,56)²        = 0,0306   → niveau « low »
porosité    = terre cuite, poreuse          = 0,8500
exposition  = 1,15 − 0,25 × 0,031           = 1,1423
température = 17,8 °C < 25 °C               = 1,0000
humidité    = 1 + 0,004 × (78 − 60)         = 1,0720
radiateur   = 2,54 m, et août hors chauffe  = 1,0000
produit                                     = 1,0409
intervalle  = 5 × 1,0409 = 5,20             → 5 jours
volume      = 3,30 L × 150 ml/L             = 495 ml
```

Dernier arrosage **le jour même** + 5 j → échéance 21/08, pas de rappel.
Fertilisation : aucun antécédent, août dans la fenêtre mars-septembre → **échue ce jour**.
Rempotage : hors fenêtre → aucun rappel.

**Attendu global : 2 rappels de fertilisation, 2 notifications, aucun rappel d'arrosage.**

---

## 4. Déroulement

### 4.1 Étape 1 — Météo

```
21:33:27  GET api.openweathermap.org/data/2.5/weather  200
21:33:27  Meise : 17.8 °C, 78 % humidité, 98 % nuages (2026-08-16)
```

La ligne du 16/08 existait déjà, écrite à 21h24. L'`ON CONFLICT (site_id, observed_on)`
a mis à jour au lieu de dupliquer : `observed_at` passe de 21:24:34 à 21:33:27,
`fetched_at` suit, la température de 18,4 à 17,8 °C. **Une seule ligne pour la journée.**

La date `observed_on` est calculée en heure belge. À 21h33 UTC, il est 23h33 à Bruxelles :
même jour, la distinction n'a pas joué ici, mais elle jouera après 22h UTC en été.

### 4.2 Étape 2 — Génération des rappels

2 rappels créés, exactement les 2 attendus :

| reminder | Plante | Action | Échéance | Généré |
|---|---|---|---|---|
| 14 | Yucca IKEA | fertilisation | 16/08/2026 | oui |
| 15 | Fleur de lune IKEA | fertilisation | 16/08/2026 | oui |

Aucun rappel d'arrosage. **Le comportement est correct et vaut d'être souligné** :
la Fleur de lune ayant été arrosée le jour même, le moteur ne la réclame pas.
Le Yucca, arrosé il y a 3 jours pour un intervalle de 11, n'est pas dû non plus.

### 4.3 Étape 3 — Notifications

```
21:33:46  Notification envoyée : Fertilisation — Yucca IKEA
21:33:47  Notification envoyée : Fertilisation — Fleur de lune IKEA
```

Contenu relevé **depuis ntfy**, donc tel que reçu et non tel qu'émis :

```
[21:33:46 UTC] Fertilisation — Yucca IKEA
     Aucun antécédent enregistré.

[21:33:47 UTC] Fertilisation — Fleur de lune IKEA
     Aucun antécédent enregistré.
```

Les accents et le tiret cadratin sont intacts — la publication en JSON tient ses promesses.

### 4.4 Étape 4 — Traçabilité

```
batch_run 6 : sites_ok=1  sites_failed=0  reminders_new=2  sent=2  send_failed=0  error=NULL
              started 21:33:26,437  finished 21:33:48,414   soit 21,98 s
```

Le `payload` de la première notification, intégralement :

```json
{
  "season": "summer",
  "base_interval": 10,
  "factors": {"porous": 1.0, "exposure": 1.051, "temperature": 1.0,
              "humidity": 1.072, "radiator": 1.0, "product": 1.127},
  "interval": 11,
  "volume_ml": 741,
  "exposure": {"intensity": 0.396, "level": "indirect",
               "distance_m": 1.66, "cardinal": "E"},
  "position": "contre un mur",
  "radiator_m": 4.08,
  "weather": {"temp_c": 17.8, "humidity_pct": 78.0}
}
```

Toutes les entrées du calcul sont reconstituables a posteriori. Vérification indépendante
faite à la main : les six facteurs, l'intensité, l'intervalle et le volume correspondent
au centième près aux valeurs attendues en section 3.

---

## 5. Test d'idempotence

Second `make run` lancé 52 secondes après le premier :

```
batch_run 7 : sites_ok=1  reminders_new=0  sent=0  send_failed=0
```

Aucun rappel recréé — l'index unique partiel `ux_reminder_open` a fait son office.
Aucune notification renvoyée — la politique de renvoi impose 7 jours pour la fertilisation.
`notification_log` reste à 2 lignes, `reminder` à 2.

Une seule ligne météo malgré deux appels à l'API : l'upsert tient.

---

## 6. Anomalies constatées

### 6.1 Message sans antécédent, inexploitable — **majeur**

```
Fertilisation — Yucca IKEA
Aucun antécédent enregistré.
```

C'est tout. Le message ne dit **ni quoi faire, ni à quelle fréquence**. L'information
existe pourtant : l'espèce demande une fertilisation tous les 30 jours d'avril à septembre.
Le code n'affiche l'intervalle que dans la branche « antécédent connu ».

Conséquence pratique : la toute première notification de chaque action, sur chaque plante,
est la moins informative de toutes. C'est exactement l'inverse du besoin.

**Correction attendue :** afficher l'intervalle même sans historique, par exemple
« Première fertilisation. Rythme conseillé : tous les 30 jours, d'avril à septembre. »

### 6.2 « Peu de lumière » pour une plante à 1,66 m d'une fenêtre — **modéré**

Le Yucca déclenche la mention « Peu de lumière » avec un facteur d'exposition de 1,0511,
alors que le seuil de déclenchement est 1,05. La marge est de 0,0011.

Or son exposition mesurée est `indirect`, ce qui est **dans la plage tolérée par l'espèce**
(`indirect` → `direct`). Annoncer un manque de lumière à une plante correctement exposée
est trompeur.

**Cause :** le seuil de 1,05 correspond à une intensité de 0,40, soit précisément le cas
d'une fenêtre est à 1,66 m — une situation banale, pas un cas sombre.

**Correction attendue :** relever le seuil, ou mieux, formuler la justification à partir
du niveau d'exposition comparé à la plage de l'espèce plutôt qu'à partir du facteur brut.

### 6.3 Les limites de l'espèce ne sont jamais évaluées — **majeur**

`species.exposure_min`, `exposure_max`, `temp_min_c` et `temp_max_c` sont saisis,
stockés, affichés dans l'interface — et **lus par aucune règle**.

| Plante | Tolérance | Mesuré | Alerte |
|---|---|---|---|
| Yucca IKEA | `indirect` → `direct` | `indirect` | aucune |
| Yucca IKEA | 10 – 27 °C | 17,8 °C | aucune |
| Fleur de lune IKEA | `low` → `bright_indirect` | `low` | aucune |
| Fleur de lune IKEA | **18 – 24 °C** | **17,8 °C** | **aucune** |

Le dernier cas est un vrai franchissement : la Fleur de lune est sous son minimum
thermique, et rien ne le signale. La donnée est là, la comparaison n'existe pas.

C'était pourtant l'intention explicite du second usage d'`exposure()` — le niveau
d'énumération devait servir à l'alerte « hors plage ». Ce consommateur n'a jamais été écrit.

### 6.4 `make preview` aveugle avant le premier run — **mineur**

`preview()` liste les rappels **existants** ; il ne les génère pas. Avant le premier
`make run` de la journée, il n'affiche donc rien, alors que c'est le moment où l'on
voudrait contrôler le texte.

Constaté pendant ce test : l'aperçu lancé avant le batch n'a rien retourné, celui lancé
après a affiché les deux messages.

**Correction attendue :** calculer les échéances dans `preview()` sans les persister.

### 6.5 Trois actions de soin sans moteur — **mineur, connu**

`care_action` propose `pruning`, `treatment` et `cleaning`. Le moteur ne traite que
`watering`, `fertilizing` et `repotting`. Les trois autres ne peuvent être que saisies
à la main — ce qui est cohérent avec le modèle, mais mérite d'être écrit quelque part.

---

## 7. Points vérifiés et conformes

| Vérification | Résultat |
|---|---|
| Upsert météo sur `(site_id, observed_on)` | 1 ligne, mise à jour, pas de doublon |
| `observed_on` calculé en fuseau du site | conforme |
| Calcul d'intensité lumineuse | 0,3957 et 0,0306, écart nul avec la formule |
| Distance et orientation de fenêtre | 1,66 m et 8,56 m, est, visibles |
| Calibrage du plan | 0,3665 unité/cm, surface 37,82 m² |
| Les cinq facteurs | conformes au centième |
| Écrêtage du produit dans [0,70 ; 1,40] | non sollicité, produits à 1,127 et 1,041 |
| Volume d'arrosage | 741 ml et 495 ml, exacts |
| Fenêtres de mois | fertilisation active, rempotage inactif, corrects |
| Non-génération si soin récent | Fleur de lune arrosée le jour même, aucun rappel |
| Index `ux_reminder_open` | aucun doublon au rejeu |
| Index `ux_notification` | aucun renvoi au rejeu |
| Politique de renvoi 7 j pour la fertilisation | respectée |
| `batch_run` renseigné | compteurs exacts, `error` nul, 21,98 s |
| `payload` complet | 10 clés, calcul reconstituable |
| Encodage des accents en notification | intact de bout en bout |
| Code de sortie du batch | 0 en cas de succès, 1 sur échec d'envoi (testé séparément) |

---

## 8. Conclusion

**La chaîne technique fonctionne.** Aucune erreur, aucun envoi perdu, aucun doublon,
traçabilité complète, et les calculs sont exacts au centième — vérifiés indépendamment
du moteur.

**Le contenu envoyé, lui, n'est pas encore utilisable.** Les deux notifications de ce test
disaient « Aucun antécédent enregistré. » et rien d'autre. Un utilisateur recevant cela ne
sait ni quoi faire, ni quand, ni combien. Les anomalies 6.1 et 6.3 sont à traiter avant
toute mise en service : la première rend le message vide de sens, la seconde laisse passer
un dépassement de température réel sans le signaler.

Les anomalies 6.2, 6.4 et 6.5 sont du confort.

**Recommandation :** ne pas activer le déclenchement automatique GitHub Actions avant
correction de 6.1 et 6.3.

---

## 9. Nettoyage

Les artefacts de ce test — 2 `reminder`, 2 `notification_log`, 2 `batch_run` — sont à
supprimer. Les données métier (site, espèces, plantes, pièce, équipements, rempotages,
`care_log`, `weather_log`) ne doivent pas l'être : elles préexistaient au test.
