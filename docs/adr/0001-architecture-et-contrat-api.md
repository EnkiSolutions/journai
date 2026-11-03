# ADR 0001 — Architecture de référence et contrat d’API

- **État** : accepté (decisions du contrat). Le jalon M1 n’est ni livré ni validé : ce document
  en est l’unité documentaire en cours.
- **Portée** : F01 — Socle exécutable, architecture et migrations
- **Preuves** : GitHub #1 · Multica JOUR-3 · PR #26
- **Critères couverts par le contrat** : C1 documenté par le présent ADR ; C2 (format des
  fixtures, conventions de migration et de configuration) et C3 (chaîne de démarrage, checks de
  la CI) décrits ici comme contrat, non implémentés à ce jalon
- **Références effectives** : `journai/__init__.py` et l’en-tête de
  `journai/migrations/0001_identite_espace_projet.sql` citent ce document. Aucune autre
  référence n’existe dans l’arbre Git : `journai/db.py`, `journai/migrations.py` et
  `pyproject.toml` ne le citent pas, ce dernier étant absent du dépôt.
- **Reste à faire** : M2 (config d’exemple, migrations et fixtures exécutées, tests), M3 (CLI,
  API, droits, validation), M4 (CI, types, démarrage vérifié)

## Contexte

La fiche de feature (`docs/features/F01-socle.md`) fixe trois critères d’acceptation, repris
dans leur ordre sous les étiquettes C1, C2 et C3 que ce document utilise pour les désigner.
Aucun critère n’est ajouté au socle.

| Critère réel de F01 | Ce qu’il impose au socle |
|---|---|
| C1 — Documenter les choix et le contrat API dans une ADR | Architecture de référence, conventions de migration, conventions de configuration et contrat d’API écrits avant toute feature métier : c’est le présent document |
| C2 — Fournir migrations versionnées, fixtures synthétiques, configuration exemple sans secrets et commandes de lancement | Migrations SQL journalisées, jeux de démonstration sans donnée réelle, configuration d’exemple versionnée, commandes de démarrage |
| C3 — La CI exécute les contrôles de typage, de qualité et les tests utiles ; le parcours de démarrage est vérifié | Chaîne de démarrage et vérifications exécutées par la CI, sans dépendance d’un environnement développeur |

Les règles de la spécification (`docs/specification.md`, sections « Conventions » et
« Règles métier ») que le socle doit rendre vérifiables par la base et par l’API sont
désignées ci-dessous par leur intitulé réel.

| Intitulé réel de la règle | Section |
|---|---|
| « Base relationnelle ; identifiants UUID ; véritables clés étrangères et tables d’association uniques, jamais de listes d’identifiants en texte » | Conventions |
| « Tout objet métier appartient à un espace » · « Les relations doivent rester dans le même espace » | Conventions |
| « Les objets principaux ont un auteur, des dates de création/modification, une révision et une date d’archivage » | Conventions |
| « Les étapes constituent un graphe avec alternatives, retours et abandons […]. Une transition reste dans une seule version. » | Règles métier |
| « Une version validée est immuable ; une révision crée un brouillon. Les clés stables identifient étapes et occurrences entre versions. » · « Les versions courantes appartiennent au bon parcours. » | Règles métier |
| « Le point de contact garde une identité stable ; une occurrence décrit sa présence dans une étape et un canal. » | Règles métier |
| « L’état d’une ressource est distinct de son intégration ; une opération définie n’est pas nécessairement assurée. » | Règles métier |
| « Une action mutualisée reste unique et peut bénéficier à plusieurs projets, contacts, opérations et ressources. » · « Les répartitions validées de charge et de budget totalisent chacune 100 %. » · « Les dépendances n’ont pas de cycle. » | Règles métier |
| « Une seule décision est courante. » | Règles métier |
| « Le registre objet relie les objets métier aux commentaires et événements avec intégrité du type. L’édition utilise la révision pour détecter les conflits et permettre la comparaison. » | Règles métier |
| « Rôles : administrateur d’espace ; pilote de projet ; contributeur ; commentateur ; lecteur. » | Règles métier |
| « Les suppressions d’objets utilisés passent par l’archivage. » | Règles métier |

Ces règles sont permanentes : un socle qui ne permet pas de les exprimer bloque toutes les
features métier. Les décisions ci-dessous sont prises pour qu’elles soient vérifiables par la
base et par l’API, et non pour un confort d’écriture.

## Décisions

### D1 — Langage, dépendances, outillage

- **Python 3.12**, paquets `journai` (paquet d’application) et `scripts` (outillage de
  dérive/contrôle). **Aucune dépendance d’exécution** : `dependencies = []` dans
  `pyproject.toml`. La bibliothèque standard fournit tout le socle : `sqlite3`,
  `http.server`, `json`, `argparse`, `logging`, `hashlib`, `uuid`, `datetime`,
  `importlib.resources`.
- **Outil de développement, jamais d’exécution** : `ruff` (qualité + format), `mypy`
  (vérification de types) et `pyright` (types + config `pyrightconfig.json`) sont déclarés dans
  `requirements-dev.txt` et dans `[project.optional-dependencies] dev`. Une CI qui « exécute les
  checks utiles » (C3) a besoin d’un vérificateur de types et d’un lanceur de tests : `unittest`
  est la bibliothèque standard, `ruff`/`mypy`/`pyright` sont les outils standards de ces checks.
  Ils ne sont jamais importés par `journai/`.
- **Pourquoi pas de framework Web** : F01 livre une API de lecture sur `http.server`
  (`journai/api.py`). Un framework imposerait une dépendance d’exécution contredite par C1, et
  n’apporte au socle que du routage. Le socle a besoin de : contrat JSON stable, validation,
  cloisonnement, concurrence optimiste. Ces points sont implémentés à la main et testés.
- **Frontend** : hors de F01 (voir *Non objectifs*). Le point d’entrée de la chaîne de démarrage
  est le CLI `python -m journai`.

### D2 — Base de données : SQLite, un fichier par environnement

- **Moteur** : SQLite (bibliothèque standard `sqlite3`). Pourquoi : un fichier, aucune dépendance
  d’environnement (C3), transactions complètes, clés étrangères composites (D4), contraintes
  `CHECK` évaluées à l’écriture (C6), `PRAGMA foreign_key_check` pour auditer une base migrée.
- **Emplacement** : `var/journai-<env>.db`, chemin fourni par la configuration (jamais codé en
  dur). `var/` est ignoré par Git. Une base de démonstration est donc toujours séparée d’une base
  réelle, et le dépôt ne contient aucune donnée (C5).
- **Journal de migration** : table `schema_migration(version, applique_le, fichier)`
  (`journai/migrations.py`). `version` est le préfixe numérique du nom de fichier ; une version
  journalisée n’est jamais rejouée (démarrage sur une base existante, idempotence de C2) ; les
  fichiers sont découverts par `glob("*.sql")`, filtrés sur le préfixe numérique, triés, découpés
  par `sqlite3.complete_statement` et exécutés dans une transaction unique ; aucune version n’est
  journalisée si `PRAGMA foreign_key_check` et `PRAGMA integrity_check` échouent (la transaction
  est annulée, la base reste à la dernière version vérifiée) ; une migration est idempotente
  (`CREATE TABLE IF NOT EXISTS`).
- **Empreinte de contenu** : le journal stocke le nom du fichier, pas son empreinte. Limite
  connue, traitée en M2 : ajout d’une colonne `empreinte_sha256` et refus d’une migration dont le
  contenu change après journalisation — une migration validée est un contrat, pas un texte que la
  PR suivante réécrit.
- **Ouverture de connexion** (contractuelle, posée par `journai/db.py`) : `PRAGMA foreign_keys
  = ON`, `PRAGMA recursive_triggers = ON`, `PRAGMA journal_mode = WAL`, `foreign_keys="ON"` et
  `autocommit=False`. Sans `foreign_keys = ON`, toutes les clés étrangères du schéma sont
  silencieusement ignorées : c’est le point d’exécution de C6 côté base.

### D3 — Identité, dates, audit, versionnage, suppression

| Convention | Forme | Contrainte portée |
|---|---|---|
| Identifiant | `id TEXT NOT NULL PRIMARY KEY` | un seul format de clé, comparable et stable |
| Identifiant généré | UUID v4 (`str(uuid.uuid4())`) hors fixtures | collision évitée sans séquence globale |
| Dates | texte ISO-8601 **avec décalage** (`2026-01-05T09:00:00+00:00`) | comparables triées, sans ambiguïté de fuseau |
| Traçabilité | `cree_par`, `cree_le`, `modifie_par`, `modifie_le` maintenus par le serveur | C1 (jamais le client) |
| Suppression | `archive_le` (suppression douce) ; jamais de purge | invariants d’audit et de rétablissement |
| Concurrence | `revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1)` | C6 : version attendue obligatoire |
| Version d’un parcours | `version_parcours(numero, perspective, statut, version_source_id)` | invariants 2 et 4 |

- L’identifiant est une clé opaque : la base l’accepte en texte, ce qui permet d’une part les
  UUID v4 générés par l’application, d’autre part les identifiants lisibles des fixtures
  (`a-parc-insertion`), plus exploitables dans les journaux et les tests.
- `archive_le` porte la date de suppression : la purge matérielle est une décision
  d’exploitation (anonymisation), jamais un comportement de l’API (C5).

### D4 — Cloisonnement par espace, filiation par projet

- **`espace_id` est portée par toute table de données métier**, pas seulement par les tables de
  tête : `structure`, `projet`, `public`, `canal`, `parcours`, `etape`, `point_contact`,
  `action`, `ressource`, `constat`, etc. Une ligne sans `espace_id` est une ligne non cloisonnable.
- **Référence verrouillée par clé étrangère composite** : une référence entre lignes d’un même
  espace s’écrit `FOREIGN KEY (col_id, espace_id) REFERENCES table (id, espace_id)`, la table
  cible portant `UNIQUE (id, espace_id)`. Une référence vers une ligne d’un autre espace est
  alors **impossible à écrire** (invariant 3, contrainte « cloisonnement » de C6), sans contrôle
  applicatif et sans jointure de contrôle.
- **Filiation** : `projet_structure`, `parcours_public`, `action_projet`, `action_occurrence`,
  `action_operation`, `action_ressource`, `action_constat` sont des tables d’association avec la
  même discipline composite. Un parcours, une action, une ressource, un contact ne sont jamais
  rattachés par un texte libre : la spécification 3.4 est une clé étrangère, pas une convention.
- **Sous-arborescence dans le même espace** : `public.parent_id` se référence lui-même par
  `(parent_id, espace_id)` et `CHECK (parent_id IS NULL OR parent_id <> id)` interdit la boucle
  immédiate.
- **Référence circulaire assumée** : `parcours.version_observee_id` / `version_cible_id` pointent
  vers `version_parcours`, qui pointe vers `parcours`. SQLite l’accepte ; la validité est
  contrôlée par `PRAGMA foreign_key_check` à la fin du lot de migration, jamais à la création de
  la table. L’ordre d’insertion des fixtures suit le même principe (D7).
- **Version source→cible** : `version_parcours.version_source_id` référence une version validée
  du **même** parcours (`(version_source_id, parcours_id)`), avec
  `CHECK (version_source_id IS NULL OR version_source_id <> id)` et
  `CHECK (valide_le IS NOT NULL OR statut = 'brouillon')`. Un parcours cible est donc
  rattaché à sa source dès la base (invariant 2, C6 « version source→cible »).
- **Étapes attachées à une version, pas au parcours** : `etape` référence
  `(version_parcours_id, espace_id)` et porte `cle_stable` (`UNIQUE (version_parcours_id,
  cle_stable)`). La comparaison de deux versions (F11) et la stabilité lors d’une nouvelle version
  (F10, F13) reposent sur cette clé, pas sur l’ordre d’affichage.

### D5 — Contacts, occurrences, actions, droits

- **Identité stable d’un point de contact** : `point_contact(nom, intention, responsable_id)` est
  une identité, jamais un calcul. Les occurrences de contact portent la dépendance d’exécution
  (`occurrence_contact(etape_id, point_contact_id, canal_id, criticite, statut, quantite)`) et
  sont ce que la planification et l’exécution consomment (invariant 14).
- **Opérations, ressources, occurrences** : `operation(mode, charge, cout)`,
  `ressource(type, role, competences, etat, capacite)`,
  `occurrence_operation(etape_id, operation_id, role, quantite, duree)`,
  `occurrence_ressource(etape_id, ressource_id, role, quantite, etat_utilisation)`. Une
  opération/ressource est une définition ; son occurrence dans une étape est l’objet planifié.
  Le cloisonnement de l’occurrence est celui de l’étape, et l’occurrence est l’unité suivie.
- **État d’une ressource vs état d’utilisation** : `ressource.etat` (état de l’objet de
  référence) et `occurrence_ressource.etat_utilisation` (dégradé, indisponible, remplace, libere,
  bloque, inchange) sont deux colonnes distinctes. Modifier l’un ne réécrit pas l’autre
  (invariant 15).
- **Action = une ligne + des associations** : `action` porte le périmètre, la finalité, le
  statut, la criticité, le porteur, le responsable, le budget, la charge, le planning. Les
  rattachements à plusieurs projets, étapes, opérations, ressources, constats, arbitrages, et les
  contributions d’autres porteurs sont des tables dédiées (`action_projet`, `action_occurrence`,
  `action_operation`, `action_ressource`, `action_constat`, `dependance_action`,
  `contribution_action`). Une action n’est jamais recopiée par projet, porteur ou arbitrage
  (invariants 7, 8, 11).
- **Droits, pas de rôle global** : `membre_espace(espace_id, utilisateur_id, role)`,
  `membre_projet(projet_id, utilisateur_id, role)`, plus les colonnes de portage
  (`porteur_id`, `responsable_id`). Il n’existe pas de rôle utilisateur global. Le rôle
  administrateur est **restreint à l’administration de l’espace** (invariant 20, règle 3.19) :
  `journai/rights.py` dérive une permission par espace + projet à partir de ces deux sources.

### D6 — Conventions de configuration

- **Une seule source de lecture : `config/journai.example.json`** (exempt de secret, versionnée),
  chargée par `journai/config.py`. Limite connue, traitée en M2 : ce fichier n’existe pas encore
  alors que `config.py` le charge déjà ; la configuration tourne aujourd’hui sur les seuls défauts
  du code, alors que C2 exige l’exemple versionné. Une copie locale `config/journai.json` l’écrase,
  et une variable d’environnement écrase la copie locale : priorité
  `variable d’environnement > config/journai.json > config/journai.example.json > défaut`.
- **Variables d’environnement, préfixe `JOURNAI_`** : `JOURNAI_ENV`, `JOURNAI_DB`,
  `JOURNAI_HOST`, `JOURNAI_PORT`, `JOURNAI_LOG_LEVEL`, `JOURNAI_SCHEMA_DIR`,
  `JOURNAI_JETON_DEV`, `JOURNAI_CORS_ORIGIN`. Aucun secret n’est lu depuis un fichier versionné.
- **Clés de configuration** : `env`, `db`, `host`, `port`, `log_level`, `schema_dir`, `cible_son`.
  Un environnement inconnu est refusé (`env` ∈ `dev`, `test`, `staging`, `prod`) : la CI et le
  CLI ne peuvent pas démarrer sur une valeur typographique.
- **Secrets** : `.env*` est ignoré par Git (`​.gitignore`), seule `.env.example` est versionnée et
  ne contient que des noms de variables. Le jeton de démonstration est fourni par
  `JOURNAI_JETON_DEV` (jamais par un fichier versionné) et n’est accepté que lorsque `env` est
  `dev` ou `test`.

### D7 — Format des fixtures

Un fixture est un fichier `journai/fixtures/<jeu>.json` qui décrit **des lignes, pas des
requêtes**. Format canonique :

```json
{
  "env": "dev",
  "tables": [
    { "table": "parcours", "rows": [ { "id": "a-parc-insertion", "...": "..." } ] }
  ],
  "updates": [
    { "table": "parcours", "id": "a-parc-insertion",
      "set": { "version_cible_id": "a-vp-cible-2" } }
  ]
}
```

- `tables` : insertion dans l’ordre du fichier, l’ordre suivant l’ordre de création des tables
  du schéma (parent avant enfant), `espace_id` incluse.
- `updates` : opérations `{table, id, set}` appliquées après toutes les insertions, pour les
  références circulaires assumées en D4. Une `update` cible une ligne existante (le nombre de
  lignes touchées est contrôlé) et ne contient aucune clause SQL écrite à la main. Limite connue,
  traitée en M2 : les fixtures actuelles expriment ces `updates` par une chaîne `UPDATE` et n’ont
  pas de champ `env` ; M2 convertit `journai/fixtures/espace-a.json` et
  `journai/fixtures/espace-b.json` au format ci-dessus, fait lire `env` (et le contrôle
  `allow_replace`) par `journai/seed.py`, et fait refuser au semis une clause SQL libre.
- `env` : environnement autorisé (`dev`, `test`). Un fixture `dev` est refusé sur `prod`, qui ne
  reçoit donc jamais de fixture.
- **Refus d’écrasement** : `journai/seed.py` refuse d’insérer dans une table déjà renseignée
  sans remplacement explicite (`--replace`). Une graine insérée est complète, ou n’est pas
  graine insérée est complète, ou n’est pas insérée.
- **Aucune donnée réelle** : identifiants préfixés par le jeu (`a-`, `b-`), noms et courriels en
  `.test`, valeurs numériques plausibles. Un contrôle de non-référence est possible hors ligne,
  il ne fait pas partie de la CI (C5).

### D8 — Chaîne de démarrage et CLI

- **Point d’entrée unique** : `python -m journai` (`journai/cli.py`), exposé en commande `journai`
  par `[project.scripts]` de `pyproject.toml`. Sous-commandes : `init` (migrations),
  `seed` (fixtures), `status` (schéma journalisé, total par table), `selftest` (chaîne complète
  sur une base temporaire), `serve` (API de lecture). Sans argument, la commande exécute
  `init` puis `seed` : le chemin « à partir d’un environnement vierge » est la commande par
  défaut, pas une suite de trois commandes à connaître.
- **Journalisation** : `logging` sur la sortie standard, niveau `log_level` de la configuration,
  format horodaté. Une commande qui échoue rend un code de sortie non nul et un message
  explicatif sur la sortie d’erreur : la CI et le développeur voient la même raison.
- **`selftest`** : migrations + graines + lecture API sur une base temporaire, hors du dépôt. La
  CI l’exécute, ce qui remplace C3 « la chaîne de démarrage est exécutée par la CI » par une
  commande unique et vérifiable.

### D9 — Contrat d’API de lecture (F01)

- **Base de version** : `/api/v1` (`BASE`). Une rupture de contrat se fait par une nouvelle base,
  pas par une modification silencieuse d’un champ.
- **Ressources** : une ressource par table du schéma, en lecture :
  `GET /api/v1/<ressource>` (liste) et `GET /api/v1/<ressource>/<id>` (détail). Le nom de
  ressource est le nom de la table ; le nom de champ est le nom de colonne, sans conversion. Il
  n’y a pas d’objet « surcouche » à inventer pour le socle : la base est le contrat.
- **Enveloppe de réponse** :

  ```json
  { "data": [ { "id": "a-parc-insertion", "espace_id": "a-espace", "revision": 1 } ],
    "meta": { "ressource": "parcours", "total": 3, "limit": 50, "offset": 0,
              "espace_id": "a-espace" } }
  ```

  Détail : `data` est l’objet unique. Le détail accepte `?include=<nom>`, qui renvoie en plus
  `included: {"<nom>": [...]}` les lignes d’une association déclarée par la clé étrangère.
- **Filtrage, tri, pagination** (paramètres de requête, tous optionnels) :
  `limit` (défaut 50, plafond 500), `offset` (défaut 0), `ordre=<colonne>`,
  `sens=asc|desc`, plus un filtre d’égalité `<colonne>=<valeur>` sur les colonnes retournées.
  Un nom de colonne inconnu, un `limit` hors plage et un `sens` invalide sont des erreurs `400`
  : la pagination est bornée pour que la lecture reste utilisable sous charge.
- **Cloisonnement à l’entrée** : l’accès est déterminé par un jeton d’accessibilité fourni par le
  serveur (`journai/auth.py`, jeton HMAC signé par `JOURNAI_JETON_DEV` en `dev`/`test`) transporté
  par `Authorization: Bearer <jeton>` ; le dépôt de la session porte les espaces et projets
  accessibles. Un accès non autorisé rend `403` avant toute lecture SQL, et une ressource d’un
  espace non accessible n’apparaît jamais dans une liste. L’identifiant d’espace est
  **déduit du dépôt**, jamais accepté comme paramètre de requête.
- **Concurrence optimiste exposée** : le détail rend `ETag: "<id>@<revision>"`. `If-Match`
  est exigé pour la mise à jour (F02) et contrôlé contre `revision` : une écriture sur une
  révision dépassée rend `409`, jamais un écrasement (C6, invariants 4 et 19).
- **Codes d’état** :

  | Code | Cas |
  |---|---|
  | `200` | lecture réussie |
  | `400` | paramètre, colonne, filtre ou corps invalide (message : liste des champs fautifs) |
  | `401` | jeton absent, expiré ou mal signé |
  | `403` | jeton valide, accès non autorisé (espace, projet, rôle insuffisant) |
  | `404` | ressource ou identifiant inconnu |
  | `409` | `revision` attendue absente ou dépassée ; référence active empêchant l’archive |
  | `415` | type de contenu autre qu’`application/json; charset=utf-8` |
  | `500` | erreur interne ; le message ne révèle ni données, ni contenu de requête |

- **Enveloppe d’erreur** : `{ "error": { "code": "acces_refuse", "message": "…",
  "champs": ["espace_id"] } }`. Les messages sont lisible par une personne bénéficiaire :
  une raison, pas un texte technique (3.18).
- **Corps refusé à la lecture** : une méthode autre que `GET`/`HEAD`/`OPTIONS` sur F01 rend
  `405` : l’API d’écriture est F02, et le socle n’accepte pas d’écriture non validée.

### D10 — Règles de validation applicative

La validation SQLite (`CHECK`, clés étrangères, `UNIQUE`) ne couvre que les règles exprimables en
DDL. Le reste est validé dans `journai/validate.py`, appliqué par l’API, dans le même ordre :
type → plage → référence → cycle → obligation conditionnelle → cloisonnement → concurrence.

| Règle de C6 | Où elle est vérifiée |
|---|---|
| type | `CHECK` sur les colonnes énumérées ; `validate.py` pour les types non contraints (date, montant, entier borné) |
| valeur, plage | `CHECK` (montants `>= 0`, `quantite > 0`, pourcentages `0..100`, `notation 0..5`) ; `validate.py` sur les bornes non contraintes |
| unicité | contrainte `UNIQUE` (courriel, `(code, pays)`, `(id, espace_id)`, `(version_parcours_id, cle_stable)`, `(espace_id, code)`, `(abonnement_id, objet_id, objet_type)`) |
| référence | clé étrangère + `PRAGMA foreign_key_check` ; `validate.py` contrôle la cible **archivée** (référence à une ligne `archive_le` est refusée en écriture) |
| cycle | chaîne `version_source_id` du même parcours contrôlée par `validate.py` (aucune boucle, source validée) |
| obligation conditionnelle | `validate.py` : une écriture exige le porteur, le responsable, le périmètre et les liens de rattachement ; un élément du plan d’action (F13) exige `action_projet`, `action_occurrence` et le porteur |
| version source→cible | clé étrangère composite D4 + contrôle `validate.py` |
| cloisonnement | clé étrangère composite D4 + dépôt d’accès D9 |
| concurrence optimiste | colonne `revision` + `If-Match` D9 |

Les règles de type, plage, unicité, référence, cycle, obligation, version, cloisonnement et
concurrence sont **déclarées dans le schéma** (D3 à D5) et **nommées dans `validate.py`** :
un contrôle absent est visible dans ce tableau, et le certificateur de revue (`scripts/review_gate.py`)
ne valide un diff que si chaque colonne/migration ajoutée est rattachée à un critère.

### D11 — Checks exécutés par la CI

Le flux `CI` (`.github/workflows/ci.yml`, déclenché sur toute PR et sur `main`) exécute, dans
l’ordre : `ruff check` + `ruff format --check` (qualité), `mypy` et `pyright` (types),
`unittest discover` sur les tests du paquet **et** de `scripts/` (tests), `journai selftest`
(chaîne de démarrage), `pip-audit` (dépendances, aucune dépendance d’exécution). Le flux
`review-gate.yml` reste dédié au certificat de revue et à la validation du SHA.

## État d’exécution du socle au checkpoint courant de M1

Le contrat ci-dessus est plus large que le dépôt. Les lignes ci-dessous décrivent l’arbre Git
constaté par `git ls-tree -r HEAD` au checkpoint courant. La présence d’un fichier dans l’arbre
ne vaut ni intégration, ni exécution, ni validation.

| Élément du contrat | Dans l’arbre Git au checkpoint | Preuve à produire (jalon) |
|---|---|---|
| `journai/config.py`, `db.py`, `migrations.py`, `seed.py` | présents ; import groupé, application des migrations et exécution non démontrées | chaîne importée, migrations appliquées et exécution (M2) |
| 5 migrations `0001`–`0005`, 39 instructions `CREATE TABLE` | présentes dans l’arbre ; conformité D3/D4 non vérifiée | `tests/test_socle.py` à écrire et exécuter (M2) |
| `journai/fixtures/espace-a.json` (1156 lignes), `espace-b.json` (284 lignes) | présentes ; format D7 et clé `env` non vérifiés | contrôle D7 et chargement des fixtures (M2) |
| `config/journai.example.json` | absent | à créer (M2, exigence C2) |
| `pyproject.toml` (3.12, dépendances vides, `journai` en commande) | absent | à créer (M2) |
| `python -m journai`, `cli.py`, `init`, `seed`, `status`, `selftest` | absents | à créer (M3) |
| `api.py`, `auth.py`, `rights.py`, `validate.py` (D9, D10) | absents | à créer (M3) |
| `.github/workflows/ci.yml`, `requirements-dev.txt` (D11) | absents ; seul `review-gate.yml` existe dans l’arbre, son exécution n’est pas prouvée ici | à créer puis exécuter par la CI (M4, exigence C3) |

`scripts/review_gate.py` et `scripts/test_review_gate.py` existent dans le dépôt (flux de
livraison commun) et ne sont pas un livrable de F01. Aucun test de M2 n’a été exécuté à ce
checkpoint : M1 est un jalon documentaire en cours, ni livré ni validé.

## Traçabilité critère → fonctionnalité → invariant → jalon
| Critère réel de F01 | Décision | Règle visée (intitulé réel de `docs/specification.md`) | Feature responsable de la mise en œuvre | Contrôle attendu (base, API, tests) | Jalon de preuve |
|---|---|---|---|---|---|
| C1 | D2, D3 | « Base relationnelle ; identifiants UUID ; véritables clés étrangères et tables d’association uniques, jamais de listes d’identifiants en texte » | F01 (migrations du socle), première base consommée par F02 | Tests : vérifier le format UUID des identifiants métier, le rejet des identifiants invalides, les clés étrangères et l’unicité des associations | M2 (base), M3 (validation API) |
| C1 | D4 | « Tout objet métier appartient à un espace » · « Les relations doivent rester dans le même espace » | F02 (identité, espaces, adhésions), F24 (droits par espace et projet) | Base : clés composées sur `espace_id` ; API : filtrage d’espace et refus inter-espaces | M2 (base), M3 (API) |
| C1 | D3 | « Les objets principaux ont un auteur, des dates de création/modification, une révision et une date d’archivage » · « Les suppressions d’objets utilisés passent par l’archivage » | F22 (registre objet, conflits, historique, archivage) | Base : colonnes d’audit et `archive_le` sans purge ; API : `If-Match` sur la révision | M2 (base), M3 (API) |
| C1 | D3, D5, D10 | Versions de parcours, étapes en graphe et transitions au sein d’une même version | F05 (versions), F06 (étapes et transitions) | Tests : refuser la modification directe d’une version validée, vérifier qu’une révision crée un brouillon lié à sa source, préserver les clés stables et refuser une version courante d’un autre parcours ou une transition entre versions | M2 (intégrité), M3 (comportement API) |
| C1 | D5 | « Le point de contact garde une identité stable ; une occurrence décrit sa présence dans une étape et un canal. » | F07 (contacts, canaux, occurrences) | Base : unicité (étape, point de contact, canal) ; API : exposition de l’occurrence | M2 (base), M3 (API) |
| C1 | D5 | « L’état d’une ressource est distinct de son intégration ; une opération définie n’est pas nécessairement assurée. » | F08 (opérations), F09 (ressources et intégration) | Base : colonnes d’état distinctes de l’intégration ; API : lecture des deux états | M2 (base), M3 (API) |
| C1 | D5, D10 | « Une action mutualisée reste unique et peut bénéficier à plusieurs projets, contacts, opérations et ressources. » · « Les répartitions validées de charge et de budget totalisent chacune 100 %. » | F11 (actions et contributeurs), F12 (mutualisation et répartitions), F14 (estimations de charge et coût) | Base : action unique et tables de répartition ; API : refus d’une répartition dont le total n’est pas 100 % | M2 (base), M3 (validation) |
| C1 | D5, D10 | Une action ne peut devenir son propre ancêtre et ses dépendances restent sans cycle | F11 (actions et sous-actions), F13 (dépendances) | Tests distincts : refuser un cycle de filiation parent/enfant (F11) et un cycle dans le graphe de dépendances (F13), y compris indirects | M3 (validation applicative) |
| C1 | D5, D10 | « Une seule décision est courante. » | F16 (décisions de priorité historisées) | Base : index partiel d’unicité ; API : décision courante unique | M2 (base), M3 (API) |
| C1 | D5, D10 | « Rôles : administrateur d’espace ; pilote de projet ; contributeur ; commentateur ; lecteur. » · « Une action partagée expose son contenu commun et ses échanges aux membres autorisés des projets concernés, sans ouvrir les autres données de ces projets. » | F24 (droits par espace et projet, partage limité) | API : matrice rôle × droit, partage limité au contenu commun | M3 (API, droits) |
| C1 | D9 | « Le registre objet relie les objets métier aux commentaires et événements avec intégrité du type. L’édition utilise la révision pour détecter les conflits et permettre la comparaison. » | F21 (commentaires, abonnements, notifications), F22 (registre objet) | API : lecture du registre avec intégrité de type, comparaison à partir de la révision | M3 (API) |
| C2 | D2, D3, D6, D7 | Fixtures de démonstration sans donnée réelle et configuration d’exemple sans secrets (convention de `AGENTS.md`) | F02, F03 (premières features à charger des données de démonstration) | Migrations appliquées, fixtures chargées, configuration d’exemple sans secret | M2 : exécution des migrations et des fixtures |
| C3 | D1, D8, D11 | « La CI exécute les contrôles de typage, de qualité et les tests utiles ; le parcours de démarrage est vérifié » | Toutes les features (bénéficiaires du contrôle) | CI : typage, qualité, tests, `selftest` sur la chaîne de démarrage | M4 : job `ci.yml` exécuté |

La colonne « Contrôle attendu » liste des preuves à produire, pas des preuves obtenues : aux
jalons M2 à M4, ces contrôles restent à exécuter, comme l’indique la section « État d’exécution
du socle ». Le tableau ne nomme aucun invariant chiffré : il relie un critère réel de F01 à une
règle identifiable de la spécification, à la décision qui l’exprime, à la feature qui la met en
œuvre et à la vérification attendue.

| Jalon | Nature | Contenu | Preuve associée |
|---|---|---|---|
| M1 | contrat documentaire | le présent ADR : critères C1–C3, décisions D1–D11, traçabilité ci-dessus | relecture de ce document ; M1 en cours, aucune preuve d’exécution |
| M2 | fichiers à créer, puis exécuter | `config/journai.example.json`, migrations `0001`–`0005`, fixtures `espace-a`/`espace-b`, `pyproject.toml`, `tests/test_socle.py` | migrations appliquées et fixtures chargées par une exécution réelle des tests |
| M3 | exécution à prouver | chaîne de démarrage et CLI (D8), API de lecture (D9), droits et validation (D10) | appels CLI et API exécutés, droits et validations vérifiés par les tests |
| M4 | exécution à prouver | CI, typage, qualité, tests, démarrage vérifié (D11) | job `ci.yml` exécuté et son journal |
| M5 | revue de livraison | PR #26 complète après M4 | certificat de revue justifiant chaque ligne, validé par `scripts/review_gate.py` |

Un nom de fichier cité dans ce tableau n’est pas une preuve : la section « État d’exécution du
socle » sépare les fichiers présents dans l’arbre Git des contrôles non exécutés. M1 ne revendique
que le contrat documentaire de C1 : le critère C1 global, M1 et F01 ne sont pas validés à ce
checkpoint. Les jalons restent séquentiels : M4 précède le retrait du brouillon de la PR #26 et M5
désigne la revue de la PR complète après M4, jamais le checkpoint d’un jalon isolé.

## Non objectifs de F01

Le socle fournit les tables, les règles et la lecture. Sont volontairement hors de F01 : les
enregistrements d’écriture (F02), les listes et enregistrements (F03, F04, F05), les calculs de
charge/coût (F06), toute interface graphique, tout rendu PDF, tout envoi de courriel, toute
intégration de service payant, et l’import de données réelles. Les tables de ces features existent
dans le schéma pour que les règles de C6 s’exercent dès le socle ; les comportements métier
arrivent avec leur feature.

## Conséquences

**Positif**

- Les neuf règles de C6 sont exerçables par la base, donc par toute feature future, sans
  redévelopper un contrôle dans chaque écran.
- Le cloisonnement n’est pas une convention d’équipe : une référence entre deux espaces ne peut
  pas s’écrire.
- La chaîne de démarrage tient en une commande, exécutée telle quelle par la CI : un
développeur qui réussit `python -m journai selftest` a la même base que la CI.
- Zéro dépendance d’exécution : aucune surface d’approvisionnement, aucun secret de service.

**Coût et limites assumées**

- `http.server` est monocouper par requête : la lecture de listes volumineuses doit rester
  paginée. Limite connue : le plafond `limit=500` est le garde-fou ; un besoin de recherche
  plein texte ou d’agrégats lourds est une raison de passer à un serveur asynchrone, pas de
  retirer la pagination.
- SQLite accepte un seul écrivain à la fois. Concurrence optimiste (`revision`, `If-Match`,
  `409`) est le mécanisme prévu ; le verrouillage pessimiste n’est pas utilisé. Limite connue :
  un usage multi-écrivains intensif (au-delà de l’équipe par espace) est une raison de changer de
  moteur, la couche d’accès reste la même (`journai/db.py` est le seul point de contact SQL).
- Le jeton de démonstration HMAC est propre à `dev`/`test` : l’authentification réelle (F02)
  reprend le même dépôt d’accès (`journai/auth.py`), pas un mécanisme parallèle.
- Les fixtures sont un jeu de démonstration, pas un jeu de tests de performance : les seuils de
  charge réels sont mesurés lors de la mise à l’échelle, pas à F01.
