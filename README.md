# cyber-dashboard-scheduler

Scheduler V1 du projet `cyber-dashboard`.

Il récupère périodiquement les évènements issues des sources OGO et Sérenicity, les normalise et les insère dans une base de donnée PostgreSQL.

## Variables d'environnement

Variables obligatoires :

- `DB_HOST` : hôte PostgreSQL
- `DB_PORT` : port PostgreSQL
- `DB_NAME` : nom de la base
- `DB_USER` : utilisateur PostgreSQL
- `DB_PASSWORD` : mot de passe PostgreSQL
- `LIMIT_REQUEST_PER_DAY` : nombre maximal de cycles de collecte par jour
- `LOG_LEVEL` : niveau de logs parmi `CRITICAL`, `ERROR`, `WARNING`, `INFO`, `DEBUG`
- `OGO_BASE_URL` : URL racine de l'API OGO
- `OGO_USERNAME` : identifiant OGO utilisé dans les endpoints
- `OGO_API_KEY` : clé d'API OGO
- `OGO_SITE_NAME_OR_ID` : identifiant ou url du site protégé par OGO
- `SERENICITY_BASE_URL` : URL racine de l'API Serenicity
- `SERENICITY_API_KEY` : clé d'API Serenicity

Variables optionnelles :

- `HTTP_TIMEOUT_SECONDS` : timeout réseau par requête HTTP, défaut `10`
- `POLL_SAFETY_WINDOW_SECONDS` : fenêtre de sécurité retranchée au `last_poll_at`, défaut `300`

Un exemple est fourni dans [.env.example](./.env.example).

## Flow

Le flow complet du scheduler est le suivant :

1. Chargement de la configuration et initialisation des logs.
2. Vérification de la connexion PostgreSQL.
3. Inventaire initial des sources :
   - OGO/WAF depuis la configuration locale
   - lurios et detoxio via l'api de Serenicity.
4. Mise à jour des tables `sources` et `scheduler_state`. ( représente l'état de l'inventaire, les bornes de collectes )
5. Entrée dans la boucle périodique de collecte.
6. Collecte OGO, puis collecte de tous les Detoxios, puis collecte de tous les Lurios enregistrés dans l'inventaire.
7. Normalisation des événements au format interne `Attack`.
8. Insertion idempotente dans `attacks` avec `correlation_status='pending'`.
9. Mise à jour de `scheduler_state` en succès ou en erreur.

## Mode de lancement

Pré-requis :

1. Créer un environnement virtuel Python.
2. Installer les dépendances avec `pip install -r requirements.txt`.
3. Copier `.env.example` vers `.env` et renseigner les variables.

Commande locale de démarrage :

```bash
cd cyber-dashboard-scheduler
python3 -m cyber_dashboard_scheduler.main
```

Exemple complet :

```bash
cd cyber-dashboard-scheduler
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python3 -m cyber_dashboard_scheduler.main
```

## Stratégie d'inventaire

- L'inventaire est exécuté au démarrage.
- La source OGO/WAF est créée à partir de la configuration locale, sans appel HTTP (Plus tard, une intégration avec l'API OGO pourra être ajoutée).
- Les lurios sont récupérés via `GET /lurios`.
- Les capteurs Serenicity sont récupérés via `GET /sensors`.
- Seules les sources dont le type existe déjà dans `sensor_types` sont conservées. ( actuellement `detoxio` et `lurio` plus tard cymealog)
- Les sources inactives sont ignorées.
- Les sources précédemment actives mais absentes du nouvel inventaire sont désactivées ! 
- Chaque source conserve son historique de `scheduler_state`.

## Stratégie de collecte des flux toxics

- Concernant OGO on collecte les évènements depuis un waf identifiée par `OGO_SITE_NAME_OR_ID`.
- Concernant le(s) detoxio(s) on collecte tous les évènements entrant et sortant et on ne prend que l'addresse ip public (ip1) `detoxio`.
- Concernant le(s) Lurio(s) on collecte tout simplement tous les flux du journal de log `lurio`.
- La borne basse de collecte vient de `scheduler_state.last_poll_at`. (en gros on prend la date de la dernière collecte validée pour ne pas relire les mêmes données)
- Si aucune collecte précédente n'existe, le scheduler remonte sur 24 heures.
- Une safety window est appliquée pour limiter les pertes de données entre deux cycles.
- Une erreur sur une source ou un collecteur ne bloque pas les autres collectes du cycle.

## Gestion des doublons

- Chaque attaque insérée reçoit un `deduplication_id`.
- Cette clé est calculée à partir de `source_id`, `attacker_ip` et `occured_at` normalisé en UTC.
- L'insertion utilise `ON CONFLICT (deduplication_id) DO NOTHING`.
- Une attaque possédant la même source et la même date de survenue est ignorée sans erreur.

## Structure

```text
cyber_dashboard_scheduler/
├── clients/
├── config/
├── db/
├── models/
├── repositories/
├── services/
├── utils/
└── main.py
```

- clients : clients HTTP pour les API OGO et Serenicity
- config : chargement de la configuration à partir des variables d'environnement
- db : gestion de la connexion PostgreSQL
- models : modèles de données representant les sources, les attaques, les états du scheduler
- repositories : Communication avec la base de données
- services : logique métier de collecte, normalisation et insertion
- utils : fonctions utilitaires (ex: gestion du temps)
- main.py : point d'entrée du scheduler

## Tests

Les tests unitaires du scheduler utilisent uniquement la bibliothèque standard `unittest`.