<!-- docs/test-batch-2026-08-19.md -->

# Rapport de test — moteur de décision

**Date d'exécution :** 2026-08-19, 21h05 UTC (23h05 Europe/Brussels)
**Version testée :** moteur unifié `assess` / `send_decision`, schéma à 18 tables
**Environnement :** conteneur `plantiq_web`, base Supabase de production, données réelles
**Testeur :** `make preview` — aucune écriture, aucun envoi

---

## 1. Objet et portée du test

Rejouer le protocole du 16/08 sur le moteur actuel : lissage saisonnier, six facteurs,
conversion intérieure, verdicts, politique de renvoi, messages.

**Ce que ce test est.** Un aperçu en lecture seule, complété par la lecture des traces
que le batch a réellement laissées le 18/08 dans `batch_run`, `reminder` et
`notification_log`. Les calculs du moteur ont été refaits à la main et comparés
chiffre par chiffre.

**Ce que ce test n'est pas.** Il n'y a pas eu de `make run` : rien n'a été écrit, rien
n'a été envoyé, et l'idempotence n'a donc pas été re-testée — le 16/08 l'avait établie
et les index qui la portent n'ont pas changé. Surtout, **la conversion intérieure n'a
pas pu être exercée** : voir l'anomalie 6.1, qui est le résultat principal de ce test.

---

## 2. État initial

### 2.1 Référentiel

| Table | Lignes | Contenu |
|---|---|---|
| `site` | 1 | Meise (50.937056, 4.326048), fuseau `Europe/Brussels` |
| `species` | 2 | *Yucca gigantea* (id 1), *Spathiphyllum wallisii* (id 4) |
| `species_watering` | 8 | 4 saisons × 2 espèces |
| `plant` | 2 | Yucca IKEA (id 2), Fleur de lune IKEA (id 3), achetées le 26/06/2021 |
| `room` / `room_version` | 1 / 1 | Séjour, étage 2, `indoor`, nord à 276° |
| `room_vertex` | 5 | polygone à 5 sommets |
| `wall_element` | 4 | 1 fenêtre (mur 0), 2 radiateurs (murs 3 et 4), 1 climatiseur (mur 4) |
| `equipment` | 10 | 3 pots, 2 cache-pots, 2 substrats, 1 engrais, 2 outils |
| `plant_equipment` | 5 | 4 attachements ouverts, 1 clos |
| `care_log` | 3 | 3 arrosages |
| `plant_health` | 1 | Fleur de lune, `stressed` le 10/08, « pointes brunes, air trop sec » |
| `weather_log` | 3 | 15/08, 16/08, 18/08 — **rien pour le 19/08** |
| `reminder` | 2 | 2 ouverts, tous deux sur le Yucca |
| `notification_log` | 2 | 2 envois du 18/08 |
| `batch_run` | 5 | 3 exécutions réelles, 2 artefacts de test |

### 2.2 Espèces

| | Yucca gigantea | Spathiphyllum wallisii |
|---|---|---|
| Arrosage printemps / été / automne / hiver | 12 / 10 / 18 / 28 j | 7 / 5 / 9 / 10 j |
| Volume | 130 ml/L | 150 ml/L |
| Exposition tolérée | `indirect` → `direct` | `low` → `bright_indirect` |
| Températures | 10 – 27 °C | 18 – 24 °C |
| Fertilisation | 30 j, avril → septembre | 15 j, mars → septembre |
| Rempotage | 36 mois, mars → avril | 24 mois, mars → mai |

### 2.3 Géométrie et calibrage

Sommets : (260,60) (400,60) (400,380) (300,400) (200,100).
Mur 0 = 140 unités déclaré à 382 cm, soit **0,36649 unité/cm**.
Fenêtre sur le mur 0, t 0,20 → 0,97, soit une ouverture de **2,94 m** — donnée que le
moteur du 16/08 ignorait.

### 2.4 Contenants — le changement le plus lourd depuis le 16/08

| Plante | Pot | Matière | Drainage | Cache-pot | Drainage |
|---|---|---|---|---|---|
| Yucca IKEA | Pot original (culture), 5,70 L | Plastique | percé | RÅGKORN, depuis le 18/08 | **sans trou** |
| Fleur de lune | Deroma 21 cm, 3,30 L, depuis le 28/06 | Terre cuite | percé | GRADVIS blanc, depuis 2021 | **sans trou** |

### 2.5 Historique des soins

| care_log | Plante | Action | Fait le | Volume |
|---|---|---|---|---|
| 3 | Yucca IKEA | arrosage | 13/08/2026 | 700 ml |
| 4 | Fleur de lune | arrosage | 13/08/2026 | 500 ml |
| 5 | Fleur de lune | arrosage | 16/08/2026 | 400 ml |

Aucune fertilisation n'a jamais été enregistrée sur aucune des deux plantes.

---

## 3. Calculs attendus, établis à la main avant lecture de la sortie

### 3.1 Lissage saisonnier — commun aux deux plantes

Le 19/08 est à 13 jours de la borne du 1er septembre, dans la fenêtre de ±15 jours :

```text
poids_automne = (−13 + 15) / 30 = 0,0667      poids_été = 0,9333
Yucca         : 10 × 0,9333 + 18 × 0,0667 = 10,533 j
Fleur de lune :  5 × 0,9333 +  9 × 0,0667 =  5,267 j
```

### 3.2 Yucca IKEA — marqueur (390,36 · 120,85)

```text
ouverture   = 0,77 × 140 / 0,36649 / 100                    = 2,9414 m
distance    = 60,85 unités / 0,36649 / 100                  = 1,6603 m
azimut      = 0° sur le plan − 276° de nord = 84°           → est, poids 0,70
intensité   = 0,70 × 4 × (2,9414/3) / (1 + 1,6603)²         = 0,3879  → « indirect »
porosité    = plastique, et cache-pot présent               = 1,0000
drainage    = cache-pot sans trou, c'est lui qui décide      = 1,1500
exposition  = 1,15 − 0,25 × 0,3879                          = 1,0530
température = aucun relevé pour le 19/08                    = 1,0000
humidité    = aucun relevé pour le 19/08                    = 1,0000
radiateur   = 4,08 m, et août hors chauffe                  = 1,0000
produit                                                     = 1,2110  (dans [0,70 ; 1,40])
intervalle  = 10,533 × 1,2110 = 12,756                      → 13 jours
volume      = 5,70 L × 130 ml/L                             = 741 ml
```

Arrosage : 13/08 + 13 j → échéance 26/08, dans 7 jours.
Fertilisation : aucun antécédent → échue ce jour, dans la fenêtre avril-septembre.
Rempotage : 26/06/2021 + 1080 j → échéance 10/06/2024, soit **800 jours de retard**,
hors fenêtre mars-avril, donc rattrapage par le seuil d'un an → à planifier,
prochaine occasion mars 2027.

### 3.3 Fleur de lune IKEA — marqueur (388,71 · 373,58)

```text
distance    = 313,58 unités / 0,36649 / 100                 = 8,5563 m
intensité   = 0,70 × 4 × (2,9414/3) / (1 + 8,5563)²         = 0,0301  → « low »
porosité    = terre cuite poreuse, mais cache-pot présent   = 1,0000
drainage    = cache-pot sans trou                           = 1,1500
exposition  = 1,15 − 0,25 × 0,0301                          = 1,1425
température, humidité, radiateur                            = 1,0000
produit                                                     = 1,3139
intervalle  = 5,267 × 1,3139 = 6,919                        → 7 jours
volume      = 3,30 L × 150 ml/L                             = 495 ml
```

Arrosage : 16/08 + 7 j → échéance 23/08, dans 4 jours.
Fertilisation : échue, mais **rempotée il y a 52 jours** → bloquée, le délai est de 60 jours.
Rempotage : 28/06/2026 + 720 j → 17/06/2028, dans 668 jours.

**Attendu global : aucun envoi. Deux actions échues sur le Yucca, toutes deux retenues
par la politique de renvoi ; une action bloquée sur la Fleur de lune.**

---

## 4. Sortie observée

```text
=== Yucca IKEA — Yucca gigantea   (19/08/2026)
  arrosage       dans 7 jour(s)
  fertilisation  échue le 19/08/2026 — retenu : renvoi dans 6 jour(s), dernier envoi le 18/08/2026
  rempotage      échue le 10/06/2024 — retenu : renvoi dans 6 jour(s), dernier envoi le 18/08/2026

=== Fleur de lune IKEA — Spathiphyllum wallisii   (19/08/2026)
  arrosage       dans 4 jour(s)
  fertilisation  rempotée il y a 52 jour(s), substrat encore neuf (délai de 60 jours)
  rempotage      dans 668 jour(s)
```

Conforme à l'attendu, ligne par ligne. Les six facteurs, les deux intervalles, les deux
volumes, les trois échéances, le retard de 800 jours et le blocage à 52 jours
correspondent au dix-millième près aux valeurs calculées en section 3.

L'aperçu nomme désormais l'événement de référence de la décision de renvoi
— « dernier envoi le 18/08/2026 » — ce qui rend la retenue lisible sans lire le code.

### 4.1 Traces du batch réel du 18/08

Trois exécutions réelles, dont la première a produit les rappels et les envois :

| batch_run | Démarré | Durée | Sites | Rappels | Envois |
|---|---|---|---|---|---|
| 1 | 18/08 21:02:16 | 16,2 s | 1 | 2 | 2 |
| 2 | 18/08 21:28:36 | 14,7 s | 1 | 0 | 0 |
| 3 | 18/08 21:28:55 | 15,6 s | 1 | 0 | 0 |

Les deux rappels du batch 1 portent `batch_run_id = 1`, les deux notifications aussi :
la traçabilité par exécution fonctionne de bout en bout. Le relevé météo du 18/08 porte
`batch_run_id = 3`, la dernière exécution l'ayant rafraîchi — comportement attendu de
l'upsert, qui réécrit la colonne.

**Le rattrapage des retards est validé en production** : la notification de rempotage
envoyée le 18/08 porte sur une échéance de juin 2024, hors saison. Sur le moteur du
16/08 elle serait restée muette jusqu'en mars 2027.

Les batchs 2 et 3 confirment l'idempotence sans la re-tester : 0 rappel, 0 envoi.

---

## 5. Anomalies constatées

### 5.1 La conversion intérieure n'est jamais exercée par l'aperçu — **majeur**

`context()` lit la météo du jour, `WHERE observed_on = ctx.today`. Le relevé du 19/08
n'existe pas encore : c'est le batch qui l'écrit, à 16 h UTC. Conséquence, dans cet
aperçu comme dans tout aperçu lancé avant le batch du jour :

- `ctx.weather` vaut `None`,
- les facteurs de température et d'humidité restent neutres,
- **`engine/climate.py` n'est pas appelé du tout.**

L'écart n'est pas théorique. Avec le relevé de la veille — 20,7 °C, 86 %, 99 % de nuages —
le moteur aurait converti en 20,6 °C et 86,4 % à l'intérieur, l'humidité aurait plafonné
le facteur à 1,10, et le Yucca serait passé de **13 à 14 jours**.

L'anomalie 6.4 du 16/08 est donc corrigée sur le fond — l'aperçu génère ses propres
échéances — mais il subsiste sous une autre forme : l'aperçu n'est représentatif de la
décision du soir que si la météo du jour a déjà été relevée.

**Correction attendue :** faire retomber `context()` sur le dernier relevé disponible
quand celui du jour manque, en marquant l'âge de la donnée dans le payload ; ou, à
défaut, que `make preview` relève la météo avant de calculer.

**Conséquence pour ce rapport :** la conversion intérieure et le module `climate.py`
restent **non validés de bout en bout**. C'était l'objectif annoncé de ce test, il n'est
pas atteint.

### 5.2 `effective.converted` affirme une conversion qui n'a pas eu lieu — **modéré**

Le payload des deux plantes contient :

```json
"effective": {"temp_c": null, "humidity_pct": null, "converted": true}
```

`converted` est calculé comme `environment == "indoor"`, c'est-à-dire l'intention de
convertir, pas la conversion. Quand la météo manque, le champ affirme donc une
conversion qui n'a pas eu lieu, avec deux valeurs nulles à côté.

Le défaut est dans le bloc ajouté précisément pour rendre le calcul reconstituable :
un lecteur de payload conclurait que 20 °C sont issus d'une conversion, alors qu'il n'y
avait rien à convertir.

**Correction attendue :** `"converted": self.environment == "indoor" and self.weather is not None`.

### 5.3 Le cache-pot est compté deux fois — **modéré, décision de modélisation**

Un cache-pot sans trou produit aujourd'hui deux effets cumulés :

- il annule le facteur de porosité, en scellant les parois du pot ;
- il applique `NO_DRAINAGE_FACTOR`, parce que l'eau stagne.

Sur la Fleur de lune, cela fait passer le produit de 0,97 — terre cuite poreuse seule —
à 1,3139, soit **+35 % d'intervalle pour un seul objet**, et à 0,09 du plafond d'écrêtage.
Le pot en terre cuite avait vraisemblablement été choisi pour respirer ; le cache-pot
annule cet avantage puis pénalise en plus.

Les deux effets sont physiquement distincts — parois scellées d'un côté, eau stagnante
de l'autre — donc le cumul est défendable. Mais il vient du même objet, et son ampleur
mérite d'être voulue explicitement plutôt que subie.

**À trancher :** conserver le cumul, ou ne retenir que le plus fort des deux.

### 5.4 Extinction silencieuse après les renvois — **mineur**

La politique de renvoi s'arrête à 2 renvois pour la fertilisation. Passé ce point,
`send_decision` renvoie faux définitivement, mais le rappel reste ouvert et `assess`
continue à le déclarer échu. Une tâche jamais traitée cesse donc d'être notifiée sans
que rien ne l'escalade ni ne la close.

Le cas est en cours de constitution : le rappel de fertilisation du Yucca n'a aucun
antécédent, il redevient échu chaque jour, et il s'éteindra le 01/09 après son troisième
envoi. Il restera visible sur la fiche de la plante et dans `/runs`, nulle part ailleurs.

**Correction attendue :** décider ce qu'est le comportement voulu — clôture automatique
avec `dismissed_reason`, escalade de priorité, ou renvoi indéfini plus espacé.

### 5.5 Deux artefacts dans `batch_run` — **mineur, à nettoyer**

Les lignes 4 et 5 ne correspondent à aucune exécution réelle : la 4 porte une durée de
60,000000 s exactement et l'erreur « OWM indisponible : timeout » avec `send_failed = 2`
alors que `sent = 0` ; la 5 n'a pas de `finished_at`. Elles ont visiblement servi à
éprouver l'affichage de `/runs`, qu'elles valident correctement — « en échec » pour l'une,
« interrompu » pour l'autre.

Elles faussent en revanche toute lecture statistique de l'historique.

### 5.6 Les limites de l'espèce ne sont toujours évaluées par aucune règle — **majeur, connu**

Anomalie 6.3 du 16/08, inchangée. Ce test fournit les mesures qui manquaient :

| Plante | Exposition tolérée | Mesurée | Verdict attendu | Alerte |
|---|---|---|---|---|
| Yucca IKEA | `indirect` → `direct` | `indirect` | dans la plage, à sa borne basse | aucune |
| Fleur de lune | `low` → `bright_indirect` | `low` | dans la plage, à sa borne basse | aucune |

Aucune des deux n'est hors plage aujourd'hui : les deux sont exactement sur leur minimum.
La comparaison resterait donc silencieuse — mais elle n'existe pas, et le silence n'est
pas une information.

Côté température, la comparaison est aujourd'hui **structurellement impossible** en
intérieur : `indoor_temperature` borne son résultat à `[20 ; 28] °C`, donc le minimum de
18 °C de la Fleur de lune ne peut jamais être franchi. C'est le franchissement que le
rapport du 16/08 signalait comme non détecté ; il est désormais hors d'atteinte du modèle.

### 5.7 L'état de santé n'agit que sur la fertilisation — **mineur**

*Corrigé après rédaction : ce point signalait à tort que l'état de santé n'était consulté
par aucune règle. Le branchement existe, la référence V4 fait foi.*

`dormant` et `dying` bloquent la fertilisation. Les autres statuts, dont le `stressed`
de la Fleur de lune, ne changent rien au calcul — c'est un choix assumé : bloquer plutôt
que pondérer, un septième facteur serait avalé par l'écrêtage à 1,40.

L'arrosage n'est volontairement jamais bloqué : une plante en difficulté boit encore.

---

## 6. Points vérifiés et conformes

| Vérification | Résultat |
|---|---|
| Lissage saisonnier à 13 jours d'une borne | 0,9333 / 0,0667, intervalles de base 10,533 et 5,267 |
| Largeur d'ouverture dans l'intensité | 2,9414 m, rapport 0,98047, appliqué aux deux plantes |
| Azimut de la fenêtre avec nord à 276° | 84°, est, poids 0,70 |
| Distances aux fenêtres | 1,6603 m et 8,5563 m, écart nul avec le calcul manuel |
| Niveaux d'exposition | `indirect` et `low`, cohérents avec les seuils |
| Annulation de la porosité par un cache-pot | appliquée aux deux plantes |
| `NO_DRAINAGE_FACTOR` piloté par le contenant extérieur | 1,15 sur les deux, dicté par les cache-pots |
| Les six facteurs | conformes au dix-millième |
| Écrêtage dans [0,70 ; 1,40] | non sollicité, produits à 1,211 et 1,314 |
| Intervalles et volumes | 13 j / 741 ml, 7 j / 495 ml, exacts |
| Blocage rempotage → fertilisation | Fleur de lune bloquée à 52 jours, message explicite |
| Rattrapage des retards de plus d'un an | rempotage Yucca, 800 jours, notifié le 18/08 comme à planifier |
| `next_window_start` sur une fenêtre passée | mars 2027, correct |
| Fenêtres de mois | fertilisation active, rempotage inactif, corrects |
| Politique de renvoi | 7 jours pour la fertilisation, retenue à J+1, raison nommée |
| Unicité de `assess` entre aperçu et batch | mêmes échéances que celles inscrites en base le 18/08 |
| `batch_run_id` sur les trois journaux | rappels et notifications rattachés au batch 1, relevé au batch 3 |
| Affichage de `/runs` | « en échec » et « interrompu » rendus correctement |
| Aperçu sans écriture ni envoi | `notification_log` et `reminder` inchangés après l'aperçu |

---

## 7. Conclusion

**Le moteur est arithmétiquement juste.** Sept grandeurs vérifiées à la main sur deux
plantes se recoupent au dix-millième. Les trois mécanismes ajoutés depuis le 16/08 —
lissage saisonnier, rattrapage des retards, blocage post-rempotage — fonctionnent, et le
second est validé sur une notification réellement partie.

**L'unification a tenu sa promesse.** Les échéances que l'aperçu annonce sont celles que
le batch a inscrites la veille, et chaque décision de retenue nomme son motif.

**Mais la conversion intérieure n'a pas été testée**, faute de relevé du jour au moment de
l'aperçu, et l'anomalie 5.1 explique pourquoi ce sera le cas de tout aperçu lancé avant
16 h UTC. Le seul module physique du projet reste sans validation de bout en bout, et son
plafonnement à 20 °C met par ailleurs hors d'atteinte l'alerte de froid que le rapport
précédent réclamait.

**Deux données sont saisies et transportées sans effet** : les bornes de l'espèce (5.6) et
l'état de santé (5.7). Le producteur existe, le consommateur manque, dans les deux cas.

**Recommandation.** 5.1 et 5.2 sont des correctifs courts et devraient précéder tout
nouveau relevé de référence : sans eux, aucun rapport ne pourra attester du modèle
climatique. 5.6 et 5.7 sont des développements. 5.3 est une décision à prendre. 5.4 et
5.5 sont du confort.

---

## 8. Nettoyage

Aucun artefact produit par ce test : l'aperçu n'écrit rien.

Les lignes 4 et 5 de `batch_run`, antérieures et fabriquées, sont à supprimer une fois
l'affichage de `/runs` jugé satisfaisant. Les deux rappels ouverts et les deux
notifications du 18/08 sont des données réelles et doivent être conservés.
