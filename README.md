# 🚉 IDFM Trains – Intégration Home Assistant

[![HACS Badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![Validate](https://github.com/fderoubaix/idfm-trains-ha/actions/workflows/validate.yml/badge.svg)](https://github.com/fderoubaix/idfm-trains-ha/actions/workflows/validate.yml)
[![Home Assistant](https://img.shields.io/badge/Home--Assistant-2024.5+-blue?logo=home-assistant)](https://www.home-assistant.io/)
[![Licence MIT](https://img.shields.io/badge/Licence-MIT-green)]()

Suivez les **prochains passages en temps réel** à votre gare Île-de-France directement dans Home Assistant, grâce à l'API officielle **PRIM (Île-de-France Mobilités)**.

Préconfigurée pour **Achères-Ville** (RER A + Ligne L Transilien), mais utilisable avec **n'importe quelle gare** du réseau IDFM.

---

## ✨ Fonctionnalités

- ⏱ **Temps réel** via l'API SIRI Lite PRIM (jusqu'à 1 000 000 requêtes/jour)
- 🚆 Capteurs individuels par **train** et par **ligne** (RER A, Ligne L…)
- 🕗 Heure théorique **et** heure prévue, avec calcul du **retard**
- 🏷 Destination, numéro de train, quai
- 🔁 Intervalle intelligent : fréquent pendant votre plage horaire, lent sinon
- 🖥 Configuration 100% UI (aucun YAML requis)
- 🔔 Prêt pour les automatisations (notifications, lumières, annonces vocales)

---

## 📦 Installation via HACS

> **Méthode recommandée**

1. Dans Home Assistant, ouvrez **HACS → Intégrations**
2. Cliquez sur le menu ⋮ → **Dépôts personnalisés**
3. Ajoutez l'URL : `https://github.com/fderoubaix/idfm-trains-ha`
   Catégorie : **Integration**
4. Cherchez **IDFM Trains** et installez
5. **Redémarrez** Home Assistant
6. Allez dans **Paramètres → Appareils & services → Ajouter une intégration**
7. Cherchez **IDFM Trains** et suivez l'assistant

---

## 🔧 Installation manuelle

1. Téléchargez la [dernière release](https://github.com/fderoubaix/idfm-trains-ha/releases/latest) (`idfm_trains.zip`)
2. Décompressez et copiez le dossier `idfm_trains/` dans `config/custom_components/`
3. **Redémarrez** Home Assistant

---

## 🔑 Clé API PRIM (gratuite, obligatoire)

1. Créez un compte sur [prim.iledefrance-mobilites.fr](https://prim.iledefrance-mobilites.fr)
2. Allez dans **Mon compte → Mes API**
3. Souscrivez à **« Prochains passages – Requête unitaire »**
4. Copiez votre `apiKey`

> Quota : **1 000 000 requêtes/jour** — largement suffisant.

---

## 🆔 Trouver l'ID de votre gare

L'intégration utilise la **Zone d'arrêt (ZdA)** IDFM.

### Achères-Ville (pré-configurée)

| Paramètre | Valeur |
|-----------|--------|
| ZdA ID | `46647` |
| MonitoringRef | `STIF:StopArea:SP:46647:` |
| RER A LineRef | `STIF:Line::C01742:` |
| Ligne L LineRef | `STIF:Line::C01740:` |

### Trouver l'ID d'une autre gare

**Option 1 – Script de test fourni** (`test_prim_api.py`) :
```bash
# Lister les lignes disponibles sur un ZdA
python test_prim_api.py --key VOTRE_CLE --stop VOTRE_ZdA_ID --list-lines
```

**Option 2 – Carte PRIM** :
1. [prim.iledefrance-mobilites.fr](https://prim.iledefrance-mobilites.fr) → Périmètre des données temps réel → onglet Carte
2. Cliquez sur votre gare → l'ID apparaît

**Option 3 – API Open Data** :
```
GET https://data.iledefrance-mobilites.fr/api/explore/v2.1/catalog/datasets/zones-d-arrets/records
    ?where=nom_zda like "NOM DE LA GARE"&limit=5
```

> ⚠️ Depuis le 13/03/2025, les données SNCF (RER, Transilien) ne sont disponibles **que par ZdA**, pas par quai individuel.

---

## ⚙️ Configuration

Tout se passe dans l'UI de Home Assistant :

1. **Paramètres → Appareils & services → Ajouter → IDFM Trains**
2. Renseignez la clé API, l'ID de zone et le nom de la gare

### Options dynamiques (sans redémarrage)

Cliquez sur **Configurer** dans la page de l'intégration :

| Option | Description | Défaut |
|--------|-------------|--------|
| Nombre de trains | Par ligne | 5 |
| Intervalle actif | Mise à jour pendant la plage horaire (min) | 2 |
| Intervalle inactif | Mise à jour hors plage (min) | 30 |
| Plage de début | Format HH:MM | 05:00 |
| Plage de fin | Format HH:MM | 23:30 |
| Filtre lignes | Restreindre à certaines lignes | toutes |

---

## 📊 Capteurs créés

### Capteur principal
`sensor.idfm_<nom_gare>` — nombre de prochains départs disponibles.

### Capteurs par train
`sensor.idfm_<nom_gare>_<ligne>_train_<N>` — timestamp du départ prévu.

| Attribut | Description |
|----------|-------------|
| `ligne` | Nom de la ligne (ex : `RER A`) |
| `destination` | Terminus de la course |
| `heure_theorique` | Heure au tableau des marches |
| `heure_prevue` | Heure temps réel (PRIM) |
| `retard_minutes` | Retard calculé en minutes |
| `quai` | Numéro de voie |
| `statut` | `onTime`, `delayed`, `cancelled`… |
| `numero_train` | Identifiant de course SNCF |

---

## 🗂 Structure du dépôt

```
.
├── custom_components/
│   └── idfm_trains/
│       ├── __init__.py
│       ├── coordinator.py
│       ├── sensor.py
│       ├── config_flow.py
│       ├── const.py
│       ├── manifest.json
│       └── translations/
│           ├── fr.json
│           └── en.json
├── .github/
│   ├── workflows/
│   │   ├── validate.yml   ← Hassfest + HACS validation (CI)
│   │   └── release.yml    ← Génération du zip à chaque release
│   └── ISSUE_TEMPLATE/
├── test_prim_api.py        ← Script de test local (stdlib Python)
├── exemple_dashboard.yaml
├── exemple_automatisations.yaml
├── hacs.json
└── README.md
```

---

## 🚀 Créer une release

```bash
git tag v1.0.0
git push origin v1.0.0
```
Puis créez la release sur GitHub → le workflow génère automatiquement `idfm_trains.zip`.

---

## 🛠 Notes techniques

- **Format API** : SIRI Lite JSON — `StopMonitoringDelivery`
- **Endpoint** : `https://prim.iledefrance-mobilites.fr/marketplace/stop-monitoring`
- **Authentification** : Header `apiKey`
- **Fenêtre de données** : −30 min à +2h par rapport à l'heure de la requête
- **Compatibilité HA** : 2024.5+

---

## 👨‍💻 Contribution

Pull Requests et Issues bienvenues !
Voir les [templates d'issues](.github/ISSUE_TEMPLATE/) pour signaler un bug ou proposer une fonctionnalité.

---

## 📄 Licence

MIT — libre d'utilisation et de modification.
