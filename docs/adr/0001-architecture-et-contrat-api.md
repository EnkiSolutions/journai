# ADR 0001 — Architecture de référence et contrat d’API

- **État** : décisions du contrat acceptées ; cette unité documentaire CI ne valide aucun jalon.
- **Portée** : F01 — Socle exécutable, architecture et migrations
- **Preuves** : GitHub #1 · Multica JOUR-3 · PR #26
- **Critères couverts par le contrat** : C1 documenté par le présent ADR ; C2 (format des
  fixtures, conventions de migration et de configuration) et C3 (chaîne de démarrage, checks de
  la CI) décrits ici comme contrat ; les preuves locales ne valent pas acceptation des critères.
- **Reste à faire** : écritures et règles métier des features dédiées ; réconciliation des
  preuves et validation des jalons par le pilotage.

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

D1–D11 définissent le contrat et, pour la CI, les contrôles livrés. Leur formulation
ne prouve pas à elle seule la présence des fichiers ni l’exécution des contrôles : ces états
sont distingués dans la section « État d’exécution du socle ». Ce checkpoint reste partiel ;
la validation documentaire de C1/M1 doit être établie par la vérification dédiée du SHA ;
la livraison de F01 exige aussi les preuves exécutables des jalons suivants.

### D1 — Langage, dépendances, outillage

- **Python 3.12 ou plus**, paquets `journai` (paquet d’application) et `scripts` (outillage de
  dérive/contrôle). **Choix cible : aucune dépendance d’exécution** : `dependencies = []` dans
  `pyproject.toml`. La bibliothèque standard fournit tout le socle : `sqlite3`,
  `http.server`, `json`, `argparse`, `logging`, `hashlib`, `uuid`, `datetime`,
  `importlib.resources`.
- **Outils de développement** : l’extra `dev` de `pyproject.toml` déclare `ruff==0.12.12`
  pour la qualité et `mypy==1.17.1` pour les types. `unittest` fournit le lanceur de tests
  dans la bibliothèque standard. Ce choix minimal couvre les contrôles livrés sans dépendance
  d’exécution ; Ruff format, pyright et pip-audit ne font pas partie du workflow livré.
- **Pourquoi pas de framework Web** : F01 prévoit une API de lecture sur `http.server`
  (`journai/api.py`). L’absence de framework est un choix d’architecture, pas une exigence de C1.
  Le socle prévoit un contrat JSON stable, la validation, le cloisonnement et la concurrence
  optimiste ; la lecture et son cloisonnement sont exercés localement en M3, tandis que les
  écritures et la concurrence optimiste restent à implémenter et vérifier par les features dédiées.
- **Frontend** : hors de F01 (voir *Non objectifs*). Le point d’entrée de la chaîne de démarrage
  est le CLI `python -m journai`.

### D2 — Base de données : SQLite, un fichier par environnement

- **Moteur** : SQLite (bibliothèque standard `sqlite3`). Pourquoi : un fichier, aucune dépendance
  d’environnement (C3), transactions complètes, clés étrangères composites (D4), contraintes
  `CHECK` évaluées à l’écriture (règles métier de la spécification), `PRAGMA foreign_key_check` pour auditer une base migrée.
- **Emplacement** : un fichier par environnement, au chemin fourni par la configuration ;
  le défaut actuel est `var/journai.db` et ne varie pas automatiquement avec `env`. Il faut
  configurer des chemins distincts pour séparer démonstration et données réelles. `var/` est
  ignoré par Git ; seules les fixtures synthétiques sont destinées au dépôt (C2).
- **Journal de migration** : table `schema_migration(version, applique_le, fichier, empreinte_sha256)`
  (`journai/migrations.py`). `version` est le préfixe numérique du nom de fichier ; une version
  journalisée n’est jamais rejouée (démarrage sur une base existante, idempotence de C2) ; les
  fichiers sont découverts par `glob("*.sql")`, filtrés sur le préfixe numérique, triés, découpés
  par `sqlite3.complete_statement` et exécutés dans une transaction par migration ; aucune version n’est
  journalisée si `PRAGMA foreign_key_check` et `PRAGMA integrity_check` échouent (la transaction
  est annulée, la base reste à la dernière version vérifiée) ; une migration est idempotente
  (`CREATE TABLE IF NOT EXISTS`).
- **Empreinte de contenu** : le journal stocke le SHA-256 des octets de chaque migration.
  Avant toute nouvelle application, `journai/migrations.py` refuse une empreinte différente ou
  invérifiable, un fichier manquant et un journal hérité sans colonne d’empreinte. Les tests de
  migration exercent ces refus : une migration validée est un contrat, pas un texte à réécrire.
- **Ouverture de connexion** (contractuelle, posée par `journai/db.py`) : `sqlite3.connect(..., autocommit=True)` (Python 3.12), puis, avant toute transaction,
  `PRAGMA foreign_keys = ON`, `PRAGMA recursive_triggers = ON` et `PRAGMA journal_mode = WAL`.
  Relire les PRAGMA : `foreign_keys` et `recursive_triggers` doivent valoir `1`, et
  `journal_mode` doit valoir `wal` ; sinon fermer la connexion et refuser le démarrage.
  Seulement après ces vérifications, passer `connexion.autocommit = False` pour les
  transactions applicatives. `foreign_keys` n’est pas un argument de `sqlite3.connect` ;
  l’activer dans une transaction est sans effet. Sans cette activation effective, les règles
  relationnelles ne sont pas garanties. `test_db` ouvre une connexion sur fichier, relit ces
  PRAGMA après le passage en transactions applicatives et vérifie le rejet d’une écriture
  violant une clé étrangère ; ce contrôle borné ne valide pas les règles métier d’écriture.

### D3 — Identité, dates, audit, versionnage, suppression

| Convention | Forme | Contrainte portée |
|---|---|---|
| Identifiant | `id TEXT NOT NULL PRIMARY KEY` | UUID canonique, comparable et stable |
| Identifiant généré | UUID v4 (`str(uuid.uuid4())`) pour les créations, UUID fixes dans les fixtures | collision évitée sans séquence globale |
| Dates d’audit et autres instants | texte ISO-8601 **normalisé en UTC**, avec six décimales et suffixe `+00:00` (`2026-01-05T09:00:00.000000+00:00`) | l’ordre lexical du stockage canonique correspond à l’ordre chronologique |
| Traçabilité | `cree_par`, `cree_le`, `modifie_par`, `modifie_le` maintenus par le serveur | convention d’audit (jamais le client) |
| Suppression | `archive_le` (suppression douce) ; jamais de purge | invariants d’audit et de rétablissement |
| Concurrence | `revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1)` | révision attendue pour détecter les conflits |
| Version d’un parcours | `version_parcours(numero, perspective, statut, version_source_id)` | règles de version validée immuable et de versions courantes du bon parcours |

- Les instants reçus avec un décalage sont analysés, convertis en UTC et sérialisés au
  format canonique avant stockage, comparaison ou tri ; les instants sans fuseau sont refusés.
  Des chaînes portant des décalages différents ne sont jamais comparées lexicalement telles
  quelles. Les contrôles F01/F22 prévus en M2/M3 devront vérifier l’égalité et le tri
  chronologique d’instants à décalages différents, dont un cas où l’ordre lexical brut est
  inversé. Ce sont des contrôles à réaliser, pas des résultats acquis.
- Les identifiants métier et leurs références sont des UUID canoniques stockés en texte. Les
  fixtures utilisent des UUID synthétiques fixes pour garder leurs références reproductibles.
  La conversion des identifiants hérités des fixtures fait partie de M2.
- `archive_le` porte la date de suppression : la purge matérielle est une décision
  d’exploitation (anonymisation), jamais un comportement de l’API (règle d’archivage des objets utilisés).

### D4 — Cloisonnement par espace, filiation par projet

- **`espace_id` est portée par toute table de données métier**, pas seulement par les tables de
  tête : `structure`, `projet`, `public`, `canal`, `parcours`, `etape`, `point_contact`,
  `action`, `ressource`, `constat`, etc. Une ligne sans `espace_id` est une ligne non cloisonnable.
- **Référence verrouillée par clé étrangère composite** : une référence entre lignes d’un même
  espace s’écrit `FOREIGN KEY (col_id, espace_id) REFERENCES table (id, espace_id)`, la table
  cible portant `UNIQUE (id, espace_id)`. Une référence vers une ligne d’un autre espace est
  alors **impossible à écrire** (règle « Les relations doivent rester dans le même espace »), sans contrôle
  applicatif et sans jointure de contrôle.
- **Filiation** : `projet_structure`, `parcours_public`, `action_projet`, `action_occurrence`,
  `action_operation`, `action_ressource`, `action_constat` sont des tables d’association avec la
  même discipline composite. Un parcours, une action, une ressource, un contact ne sont jamais
  rattachés par un texte libre : la convention relationnelle de la spécification impose des clés étrangères, pas du texte libre.
- **Sous-arborescence dans le même espace** : `public.parent_id` se référence lui-même par
  `(parent_id, espace_id)` et `CHECK (parent_id IS NULL OR parent_id <> id)` interdit la boucle
  immédiate.
- **Référence circulaire assumée** : `parcours.version_observee_id` / `version_cible_id` pointent
  vers `version_parcours`, qui pointe vers `parcours`. SQLite l’accepte ; la validité est
  contrôlée par `PRAGMA foreign_key_check` à la fin du lot de migration, jamais à la création de
  la table. L’ordre d’insertion des fixtures suit le même principe (D7).
- **Versions (F05)** : une version validée est immuable. Une révision crée un brouillon lié
  à sa version source du même parcours, sans déplacer les références historiques. Les versions
  courantes observée et cible doivent appartenir au parcours et à la perspective correspondante.
  Les contrôles de M2/M3 devront rejeter une source ou une version courante incohérente.
- **Graphe d’une version (F06)** : chaque étape appartient à une version et porte une clé
  stable conservée entre versions. Les transitions relient deux étapes de la même version
  et du même espace. Le graphe représente alternatives, retours et abandons indépendamment
  de l’ordre d’affichage. Les contrôles de M2/M3 devront refuser les liens inter-version.

### D5 — Contacts, occurrences, actions, droits

- **Identité stable d’un point de contact** : `point_contact(nom, intention, responsable_id)` est
  une identité, jamais un calcul. Les occurrences de contact portent la dépendance d’exécution
  (`occurrence_contact(etape_id, point_contact_id, canal_id, cle_stable, criticite, frequence, volume_estime, etat_operationnel)`) et
  sont ce que la planification et l’exécution consomment. La clé stable de l’occurrence est
  unique dans sa version, indépendamment de la clé des étapes, et permet de retrouver la même
  occurrence lors d’une révision. L’étape rattache l’occurrence à la version (F06/F07).
- **Opérations et ressources d’un contact** : F08 et F09 réutilisent les définitions
  d’opération et de ressource. Les associations `occurrence_operation` et
  `occurrence_ressource` les relient à une occurrence de contact dans le même espace.
  Le rôle, l’usage et l’état d’utilisation sont portés par l’association. Les contrôles
  futurs devront prouver la réutilisation et rejeter les références hors espace.
- **État d’une ressource vs état d’utilisation** : `ressource.etat` décrit l’état propre de
  l’objet de référence. `occurrence_ressource.etat_utilisation` prend les valeurs `utilise`,
  `reserve`, `consomme`, `hors_service` ou `non_utilise` : elles décrivent l’utilisation par
  occurrence, sans modifier l’état propre de la ressource. Cet état d’utilisation est distinct
  de `role_occurrence` et de l’usage ; modifier l’état de la ressource ou son intégration ne
  réécrit pas l’autre (règle de distinction entre état de ressource et intégration).
- **Action et associations** : `action` porte le titre, la nature, le statut, le responsable,
  les dates, la contrainte impérative et le critère d’acceptation. Les sous-actions se rattachent
  par `action_parent_id`. Les dépendances et contributions passent par leurs tables dédiées.
  Les projets, occurrences de contact, opérations, ressources et constats sont reliés par
  `action_projet`, `action_occurrence`, `action_operation`, `action_ressource` et `action_constat`.
  L’action reste unique et sa charge est comptée une fois au portefeuille. Des livraisons
  indépendantes deviennent des actions distinctes. Les estimations
  séparent charge, coût et complexité. Les évaluations historisent importance et impact
  sans effacer les désaccords. La criticité appartient à l’occurrence de contact.
- **Opération définie et occurrence assurée** : la définition réutilisable (F08) est distincte
  de la preuve d’exécution dans une occurrence. Une association seule ne prouve pas qu’une
  opération a été assurée. Les tests futurs devront distinguer les deux cas.
- **Effets et mesures (F12/F23)** : `action_occurrence` conserve `effet_attendu` et
  `etat_validation_effet`. La livraison d’une action et la validation de son effet restent
  deux événements distincts. Un indicateur vise un projet ou une occurrence ; ses mesures
  conservent période, source et confiance. Les validations et décisions significatives
  sont historisées selon D3.
- **Droits par espace et projet** : le rôle administrateur porte sur l’administration de
  l’espace. L’appartenance à une structure ou à un espace ne confère aucun droit automatique
  sur ses projets. L’habilitation projet est explicite dans `membre_projet` ; elle détermine les
  opérations autorisées pour le pilote, le contributeur, le commentateur ou le lecteur.
  Un membre autorisé sur le projet A peut consulter le contenu commun et les échanges d’une
  action partagée avec A. Il ne peut pas consulter les autres données d’un projet B sans
  habilitation propre sur B. Les relations restent dans le même espace.


### D6 — Conventions de configuration

- **Une seule source de lecture : `config/journai.example.json`** (exempt de secret, versionnée),
  chargée par `journai/config.py`. L'exemple versionné est présent. Une copie locale `config/journai.json` l’écrase,
  et une variable d’environnement écrase la copie locale : priorité
  `variable d’environnement > config/journai.json > config/journai.example.json > défaut`.
- **Variables d’environnement, préfixe `JOURNAI_`** : `JOURNAI_ENV`, `JOURNAI_DB`,
  `JOURNAI_HOST`, `JOURNAI_PORT`, `JOURNAI_LOG_LEVEL`, `JOURNAI_SCHEMA_DIR`,
  `JOURNAI_JETON_DEV`, `JOURNAI_CORS_ORIGIN`. Aucun secret n’est lu depuis un fichier versionné.
- **Clés de configuration** : `env`, `db`, `host`, `port`, `log_level`, `schema_dir` et
  `cors_origin` correspondent respectivement à `JOURNAI_ENV`, `JOURNAI_DB`, `JOURNAI_HOST`,
  `JOURNAI_PORT`, `JOURNAI_LOG_LEVEL`, `JOURNAI_SCHEMA_DIR` et `JOURNAI_CORS_ORIGIN`.
  Le secret de démonstration est fourni uniquement par `JOURNAI_JETON_DEV`, sans clé JSON.
  Un environnement inconnu est refusé (`env` ∈ `dev`, `test`, `staging`, `prod`) : la CI et le
  CLI ne peuvent pas démarrer sur une valeur typographique.
- **Secrets** : `.env*` est ignoré par Git (`.gitignore`), sauf `.env.example`, qui existe et
  ne contient que des noms de variables. `JOURNAI_JETON_DEV` fournit uniquement la clé de signature HMAC-SHA256 de démonstration :
  une valeur ASCII aléatoire d’au moins 32 caractères, utilisée telle quelle comme octets ASCII,
  sans valeur par défaut ni copie dans un fichier versionné. Ce n’est pas le jeton HTTP du client.
  La clé et les jetons ne sont jamais journalisés ni renvoyés dans une erreur ; la clé n’est
  jamais transmise au client. En `dev`/`test`, `serve` refuse de démarrer si cette clé est absente
  ou invalide. En `staging`/`prod`, l’API de démonstration F01 refuse de démarrer, même si la clé
  est fournie ; seule l’authentification réelle de F02 pourra y ouvrir l’API, sans repli sur ce
  mécanisme. Ces refus sont exercés par les tests locaux de démarrage et HTTP.

### D7 — Format des fixtures

Un fixture est un fichier `journai/fixtures/<jeu>.json` qui décrit **des lignes, pas des
requêtes**. Format canonique :

```json
{
  "env": "dev",
  "tables": [
    { "table": "parcours", "rows": [ { "id": "5aa92392-935c-4335-908b-11ef73226055", "...": "..." } ] }
  ],
  "updates": [
    { "table": "parcours", "id": "5aa92392-935c-4335-908b-11ef73226055",
      "set": { "version_cible_id": "adab9fb5-d793-41ca-96c0-f9db95c33375" } }
  ]
}
```

- `tables` : insertion dans l’ordre du fichier, l’ordre suivant l’ordre de création des tables
  du schéma (parent avant enfant), `espace_id` incluse.
- `updates` : opérations `{table, id, set}` appliquées après toutes les insertions, pour les
  références circulaires assumées en D4. Une `update` cible une ligne existante (le nombre de
  lignes touchées est contrôlé) et ne contient aucune clause SQL écrite à la main. Les deux
  fixtures utilisent ce format et déclarent `env` ; `journai/seed.py` refuse le SQL libre et
  exige `replace` ainsi que `allow_replace` pour remplacer les données.
- `env` : le champ du fixture et l’environnement courant doivent chacun être `dev` ou `test` ;
  le semis refuse notamment `staging` et `prod`, sans exiger que les deux valeurs coïncident.
- **Refus d’écrasement** : `journai/seed.py` refuse d’insérer dans une table déjà renseignée
  sans remplacement explicite (`--replace`). Le semis est atomique : il est appliqué intégralement ou annulé.
- **Aucune donnée réelle** : UUID synthétiques fixes et distincts par jeu, noms et courriels en
  `.test`, valeurs numériques plausibles. `test_fixtures` vérifie notamment les UUID distincts,
  les références internes à chaque jeu et les domaines de courriel ; cela ne valide pas C2.

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
  CI exécute `python -I -m journai selftest` avec le paquet installé ; cette exécution seule
  ne valide pas C3.

### D9 — Contrat d’API de lecture (F01)

- **Base de version** : `/api/v1` (`BASE`). Une rupture de contrat se fait par une nouvelle base,
  pas par une modification silencieuse d’un champ.
- **Ressources** : une ressource par table métier autorisée, en lecture :
  `GET /api/v1/<ressource>` (liste). Le catalogue exclut les tables techniques comme
  `schema_migration`. Le nom de ressource est le nom de la table et les champs sont les colonnes.
  Seules les ressources dotées d’un `id` acceptent `GET /api/v1/<ressource>/<id>` (détail).
  Les associations à clé composée sans `id`, comme `parcours_public` et `action_constat`,
  sont lues par liste filtrée sur leurs colonnes de clé ; leur route de détail rend `404`.
  Aucun identifiant artificiel ni colonne de révision n’est ajouté à ces associations.
- **Enveloppe de réponse** :

  ```json
  { "data": [ { "id": "5aa92392-935c-4335-908b-11ef73226055", "espace_id": "fa5b89cc-72ab-49a4-aa1d-3b18695bc483", "revision": 1 } ],
    "meta": { "ressource": "parcours", "total": 3, "limit": 50, "offset": 0,
              "espace_id": "fa5b89cc-72ab-49a4-aa1d-3b18695bc483" } }
  ```

  Détail : `data` est l’objet unique. Le détail accepte `?include=<nom>`, qui renvoie en plus
  `included: {"<nom>": [...]}` les lignes d’une association déclarée par la clé étrangère.
- **Filtrage, tri, pagination** (paramètres de requête, tous optionnels) :
  `limit` (défaut 50, plafond 500), `offset` (défaut 0), `ordre=<colonne>`,
  `sens=asc|desc`, plus un filtre d’égalité `<colonne>=<valeur>` sur les colonnes retournées.
  Un nom de colonne inconnu, un `limit` hors plage et un `sens` invalide sont des erreurs `400`
  : la pagination est bornée pour que la lecture reste utilisable sous charge.
- **Protocole de démonstration F01 (`dev`/`test` seulement)** : chaque lecture `GET`/`HEAD`
  porte un unique en-tête `Authorization: Bearer <jeton>` ; aucun jeton en URL, cookie ou corps.
  Le prévol `OPTIONS` sans données autorise l’en-tête `Authorization` uniquement pour l’origine
  configurée selon les règles CORS ci-dessous ; il ne dispense pas la lecture d’authentification.
  Le jeton a exactement la forme `v1.<payload>.<signature>`. `payload` est l’encodage base64url
  sans remplissage d’un objet JSON UTF-8 sans clés dupliquées, contenant exclusivement `sub`
  (UUID canonique de l’utilisateur), `espace_id` (UUID canonique de l’espace sélectionné),
  `iat` et `exp` (entiers, secondes Unix UTC). `signature` est l’encodage base64url sans
  remplissage du HMAC-SHA256 des octets ASCII de `v1.<payload>`, avec la clé définie en D6.
  La signature est vérifiée en temps constant, sur les octets reçus, sans resérialiser le JSON ;
  aucun algorithme fourni par le client n’est accepté. Il faut `0 <= iat <= maintenant < exp`
  et `exp - iat <= 3600`. Transport absent ou mal formé, format, signature, revendications ou
  dates invalides rendent `401`, sans détail sensible.
  L’opérateur local de confiance construit et signe hors HTTP ces jetons à partir des seuls
  identifiants synthétiques ; F01 n’expose aucun point de connexion ou de signature HTTP.
  Le client reçoit seulement son jeton, jamais la clé. Changer d’espace exige un autre jeton
  signé pour cet espace : aucun paramètre ou en-tête ne peut remplacer le contexte signé.
  Une demande explicite pour un espace différent rend `403`.
- **Cloisonnement à l’entrée** : après vérification du jeton, le serveur charge l’utilisateur
  désigné par `sub` et exige un utilisateur actif (`401` sinon), puis vérifie son adhésion
  active à `espace_id` (`403` sinon). L’espace signé sélectionne le contexte, il n’accorde pas
  de droits : les rôles et les habilitations explicites par projet sont relus en base à chaque
  requête, jamais fournis par le jeton. Un accès à un projet non habilité rend `403`.
  Le périmètre doit être appliqué à chaque lecture, liste, détail et inclusion ; un projet
  hors périmètre ou une relation hors espace ne doit exposer ni données ni agrégats.
  Le partage d’une action autorise seulement son contenu commun et ses échanges dans le
  projet habilité. Le contrôle des droits n’est pas délégué au client.
- **Contrôles du protocole** : F01 prévoit en M3 un jeton synthétique valide, puis
  les refus `401` (absence, format, signature altérée, expiration, date future et utilisateur
  inactif), `403` (autre espace, adhésion inactive et projet non habilité), le changement
  d’espace par nouveau jeton, les prévols CORS et les refus de démarrage de D6. Les tests de
  listes, détails et inclusions devront prouver l’absence de fuite, y compris les agrégats et
  le partage limité d’actions ; F02/F24 reprendront ces invariants avec l’authentification réelle.
  Les tests locaux couvrent des lectures et refus authentifiés ; leur réussite ne valide ni
  toutes les règles applicatives, ni un jalon.
- **Concurrence optimiste exposée** : le détail d’une ressource dotée de `id` et `revision`
  rend `ETag: "<id>@<revision>"`. Un détail sans `revision` et les listes d’associations
  n’émettent pas cet ETag de révision. Les écritures des objets principaux, introduites par
  les features métier, exigeront `If-Match` contre leur `revision` ; une révision dépassée
  rendra `409`, jamais un écrasement. Ces features devront rattacher une mutation
  d’association sans révision à la révision de son objet principal dans la même transaction ;
  F01 reste en lecture seule et ne promet aucune écriture d’association autonome.
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
  "champs": ["espace_id"] } }`. Les messages sont lisibles par une personne bénéficiaire :
  une raison, pas un texte technique (exigence de lisibilité du contrat d’API).
- **Format HTTP et origine** : les réponses avec corps utilisent
  `Content-Type: application/json; charset=utf-8`. `HEAD` conserve les en-têtes de
  `GET` avec un corps vide. Pour une origine explicitement configurée, `OPTIONS`
  répond sans données avec les méthodes de lecture et les en-têtes autorisés ;
  `Access-Control-Allow-Origin` reprend cette seule origine et `Vary: Origin`
  prévient les réutilisations de cache entre origines. Le contrôle d’accès reste
  obligatoire sur les requêtes de lecture. Les tests HTTP locaux exercent `HEAD` et les
  prévols CORS ; ces preuves ne valident pas le jalon M3.
- **Corps refusé à la lecture** : une méthode autre que `GET`/`HEAD`/`OPTIONS` sur F01 rend
  `405` : les écritures relèvent des features métier concernées, et le socle n’accepte pas d’écriture non validée.

### D10 — Règles de validation applicative

La validation SQLite (`CHECK`, clés étrangères, `UNIQUE`) ne couvre que les règles exprimables en
DDL. `journai/validation.py` existe : le semis y valide les UUID canoniques et normalise les
instants ; le journal utilise aussi cette normalisation. Ces acquis sont bornés au semis et au
journal, sans validation générale des futures écritures. Celles-ci devront être contrôlées par
l’API et les features responsables dans l’ordre : type → plage → référence → cycle → obligation
conditionnelle → cloisonnement → concurrence.

| Règle du contrat | Contrôle et responsabilité |
|---|---|
| type | `CHECK` sur les colonnes énumérées ; validations futures des écritures pour les types non contraints (date, montant, entier borné) |
| valeur, plage | Contrôles futurs sur les colonnes du modèle : charge et coût non négatifs dans estimation_action, pourcentages de répartition entre 0 et 100 et total validé à 100 % par action |
| unicité | Contrôles futurs : une adhésion par couple espace–utilisateur, un membre par couple projet–utilisateur et des clés stables uniques par version pour les étapes et, séparément, pour les occurrences. Les clés techniques composites (id, espace_id) servent à vérifier le cloisonnement D4 |
| référence | clé étrangère + `PRAGMA foreign_key_check` ; contrôle futur de la cible **archivée** (référence à une ligne `archive_le` refusée en écriture) |
| cycle | contrôle futur de la chaîne `version_source_id` du même parcours (aucune boucle, source validée), porté par F05 |
| obligation conditionnelle | contrôles futurs définis par les features métier ; F11/F12 portent les champs et rattachements des actions, F13 les dépendances et F18 la vue Plan d’action |
| versions et transitions | Contrôles futurs D4 : refuser l’édition d’une version validée, les sources et versions courantes d’un autre parcours, et les transitions entre versions ; vérifier la création d’un brouillon et la conservation des clés stables |
| cloisonnement | clé étrangère composite D4 + dépôt d’accès D9 |
| concurrence optimiste | colonne `revision` + `If-Match` D9 |

Les règles de type, plage, unicité, référence, cycle, obligation, version, cloisonnement et
concurrence constituent le contrat cible (D3 à D5) : les acquis structurels M2 et la lecture M3
ne prouvent pas les écritures. Le certificateur de revue (`scripts/review_gate.py`)
vérifie un certificat lié au SHA ; il ne prouve pas l’implémentation de ces règles.

### D11 — Contrôles livrés pour la CI

Le flux `CI` (`.github/workflows/ci.yml`) se déclenche sur `push` et `pull_request`, avec la
permission `contents: read` ; son job utilise Ubuntu et Python 3.12. Il installe le paquet et
l’extra `dev` par `python -m pip install setuptools wheel '.[dev]'`, puis exécute dans l’ordre :

```sh
python -m ruff check journai
python -m mypy --check-untyped-defs journai
python -m unittest discover -s tests -p 'test_*.py' -v
python -m unittest discover -s scripts -p 'test_*.py' -v
python -I -m journai selftest
```

La suite `tests/` comprend notamment le wheel installé hors checkout et une lecture HTTP réelle.
Le selftest isolé utilise le paquet installé. Ruff format, pyright et pip-audit ne sont pas
exécutés par ce flux. `review-gate.yml` reste dédié au certificat de revue et à la validation du SHA.

## État d’exécution du socle — unité M4-CI-CONTRACT-1

Le contrat est plus large que les preuves : M2 apporte migrations `0001`–`0007`, fixtures,
configuration sans secret et paquet installable ; les limites des acquis sont détaillées dans
R1–R5 ci-dessous. La lecture M3 comprend `api.py`, `auth.py`, `queries.py` et `validation.py` ;
elle ne livre pas les écritures métier. `init`, `seed`, `status`, `selftest` et `serve` sont
exercés localement, y compris depuis le wheel installé hors checkout. Le selftest initialise sa
propre base temporaire, lit réellement par HTTP et vérifie des refus. Les six tests HTTP restent
dans `tests/test_api.py` ; `tests/test_http.py` n'existe pas.

La CI publiée a réussi au seul SHA `2737ac231966b1735133c6cab213f32e4da92445` :
[push 43637005726](https://github.com/EnkiSolutions/journai/actions/runs/43637005726) et
[pull_request 43637011571](https://github.com/EnkiSolutions/journai/actions/runs/43637011571).
Les contrôles locaux du checkpoint sont distincts de ces résultats GitHub ; ils ne prouvent pas
la réussite de la CI sur un nouveau SHA, qui sera relevée par le pilotage. Le flux de revue
commun ne remplace pas ces contrôles. Ces preuves ne valident aucun jalon M2, M3 ou M4,
aucun critère entier C1, C2 ou C3, ni F01 ; les décisions et contrôles futurs ci-dessous ne
sont pas des écritures déjà livrées.

## Traçabilité critère → fonctionnalité → invariant → jalon
| Critère réel de F01 | Décision | Règle visée (intitulé réel de `docs/specification.md`) | Feature responsable de la mise en œuvre | Contrôle attendu (base, API, tests) | Jalon de preuve |
|---|---|---|---|---|---|
| C1 | D2, D3 | « Base relationnelle ; identifiants UUID ; véritables clés étrangères et tables d’association uniques, jamais de listes d’identifiants en texte » | F01 (migrations du socle), première base consommée par F02 | Tests : vérifier le format UUID des identifiants métier, le rejet des identifiants invalides, les clés étrangères et l’unicité des associations | M2 (base), M3 (validation API) |
| C1 | D4 | « Tout objet métier appartient à un espace » · « Les relations doivent rester dans le même espace » | F02 (identité, espaces, adhésions), F24 (droits par espace et projet) | Base : clés composées sur `espace_id` ; API : filtrage d’espace et refus inter-espaces | M2 (base), M3 (API) |
| C1 | D3 | « Les objets principaux ont un auteur, des dates de création/modification, une révision et une date d’archivage » · « Les suppressions d’objets utilisés passent par l’archivage » | F22 (registre objet, conflits, historique, archivage) | Base : colonnes d’audit et `archive_le` sans purge ; API : `If-Match` sur la révision | M2 (base), M3 (API) |
| C1 | D3, D4, D10 | Versions de parcours, étapes en graphe et transitions au sein d’une même version | F05 (versions), F06 (étapes et transitions) | Tests : refuser la modification directe d’une version validée, vérifier qu’une révision crée un brouillon lié à sa source, préserver les clés stables des étapes et des occurrences et refuser une version courante d’un autre parcours ou une transition entre versions | M2 (intégrité), M3 (comportement API) |
| C1 | D5 | « Le point de contact garde une identité stable ; une occurrence décrit sa présence dans une étape et un canal. » | F07 (contacts, canaux, occurrences) | Base : unicité (étape, point de contact, canal) ; API : exposition de l’occurrence | M2 (base), M3 (API) |
| C1 | D4, D5 | Opérations et ressources réutilisées par occurrence de contact | F08, F09 | Contrôles futurs : réutilisation dans plusieurs occurrences et refus d’une association hors espace | M2 (intégrité), M3 (API) |
| C1 | D5 | « L’état d’une ressource est distinct de son intégration ; une opération définie n’est pas nécessairement assurée. » | F08 (opérations), F09 (ressources et intégration) | Base : colonnes d’état distinctes de l’intégration ; tests futurs : une opération définie et liée peut rester non assurée | M2 (base), M3 (API) |
| C1 | D5, D10 | « Une action mutualisée reste unique et peut bénéficier à plusieurs projets, contacts, opérations et ressources. » · « Les répartitions validées de charge et de budget totalisent chacune 100 %. » | F11 (actions et contributeurs), F12 (mutualisation et répartitions), F14 (estimations de charge et coût) | Base : action unique et tables de répartition ; API : refus d’une répartition dont le total n’est pas 100 % | M2 (base), M3 (validation) |
| C1 | D5, D10 | Une action ne peut devenir son propre ancêtre et ses dépendances restent sans cycle | F11 (actions et sous-actions), F13 (dépendances) | Tests distincts : refuser un cycle de filiation parent/enfant (F11) et un cycle dans le graphe de dépendances (F13), y compris indirects | M3 (validation applicative) |
| C1 | D5, D10 | La priorité appartient au couple action–projet. Chaque décision conserve auteur, motif, estimation de la même action et évaluation du même couple. Une seule décision est courante. | F14, F15, F16 | Contrôles futurs : refuser les références incohérentes, vérifier unicité, historique et explicabilité du classement | M2/M3, comportement F16 |
| C1 | D5, D9 | Habilitation explicite par projet, cloisonnement d’espace et partage limité au contenu commun d’une action et à ses échanges | F02, F03, F12, F24 | Tests futurs : refuser un projet sans habilitation, isoler listes/détails/inclusions, autoriser le contenu partagé sans exposer les autres données des projets | M3 (API et droits), contrôle complet en F24 |
| C1 | D9 | « Le registre objet relie les objets métier aux commentaires et événements avec intégrité du type. L’édition utilise la révision pour détecter les conflits et permettre la comparaison. » | F21 (commentaires, abonnements, notifications), F22 (registre objet) | API : lecture du registre avec intégrité de type, comparaison à partir de la révision ; tester liste filtrée des associations sans id, détail refusé à 404 et absence d’ETag de révision pour les lignes sans revision | M3 (API) |
| C1 | D4, D10 | Structure pilote et structures associées ; segments imbriqués et publics multiples par parcours. | F03, F04 | Contrôles futurs : rôles et rattachements explicites, refus des cycles et liens hors espace | M2/M3 et F03/F04 |
| C1 | D5, D10 | Constats : source, date, confiance et distinction hypothèse/fait validé. Estimations et évaluations : dimensions séparées, échelles explicites et historique des avis. | F10, F14, F15 | Contrôles futurs : conserver champs de preuve, révisions et divergences sans moyenne implicite | M2/M3 et F10/F14/F15 |
| C1 | D3, D5, D10 | Historiser les changements significatifs et les décisions. Relier les indicateurs à un projet ou à une occurrence ; conserver période, source et confiance des mesures. Distinguer livraison et validation de l’effet. | F16, F22, F23 | Contrôles futurs : relire l’historique, filtrer les mesures et vérifier la validation indépendante de la livraison | M2/M3 et F16/F22/F23 |
| C2 | D2, D3, D6, D7, D8 | Migrations versionnées, fixtures synthétiques, configuration d’exemple sans secrets et commandes de lancement | F01 (socle) ; F02 et F03 (bénéficiaires) | Appliquer les migrations et charger les fixtures (M2), puis exécuter les commandes de lancement D8 (M3) | M2 et M3 |
| C3 | D1, D8, D11 | « La CI exécute les contrôles de typage, de qualité et les tests utiles ; le parcours de démarrage est vérifié » | F01 (CI) ; autres features bénéficiaires | CI : typage, qualité, tests et selftest | M4 : job ci.yml exécuté et journal conservé |

La colonne « Contrôle attendu » décrit les obligations, non leur acceptation. Les preuves
structurelles M2 et la lecture M3 ne prouvent pas les comportements d'écriture : UUID serveur,
audit, archivage et conflits relèvent de F22 ; immutabilité et révisions des versions de F05 ;
exécution des opérations de F08 ; cycles d'actions de F11/F13. Priorité courante, historique,
immutabilité, remplacement au même couple et espace et absence de cycles relèvent de F16 ;
conservation des estimations et avis relève de F14/F15. Ces obligations demeurent ouvertes même
si les tests structurels ou de lecture réussissent. Les preuves CI, types et qualité relèvent
de M4 sans valider le jalon ni C3 à elles seules.

| Jalon | Nature | Contenu | Preuve associée |
|---|---|---|---|
| M1 | contrat documentaire | le présent ADR : critères C1–C3, décisions D1–D11, traçabilité ci-dessus | relecture documentaire, distincte des preuves d’exécution ultérieures |
| M2 | socle structurel | configuration, migrations `0001`–`0007`, fixtures et paquet | preuves partielles et limites explicitées en R1–R5 |
| M3 | exécution à prouver | chaîne de démarrage et CLI (D8), API de lecture (D9), droits et validation (D10) | appels CLI et API exécutés, droits et validations vérifiés par les tests |
| M4 | exécution à confirmer au SHA courant | CI, typage, qualité, tests, démarrage vérifié (D11) | job `ci.yml` exécuté et son journal |
| M5 | revue de livraison | Après M4, sortir la PR complète du brouillon puis soumettre son dernier SHA à CodeRabbit | Approbation CodeRabbit sans remarque ouverte ni erreur sur ce SHA, puis Reviewer et certificat justifiant chaque ligne avec scripts/review_gate.py |

Un nom de fichier cité dans ce tableau n’est pas une preuve. Cette unité ne valide aucun jalon
ni F01 ; le jugement des jalons appartient à l'Orchestrateur. M4 précède le retrait du brouillon
de la PR #26 et M5 désigne la revue de la PR complète, jamais le checkpoint d’une unité isolée.

## État partiel des preuves M2 (R1–R5)

Ces preuves portent sur le socle présent, pas sur des écritures serveur absentes ; elles ne
valident ni M2 ni F01. Les cinq textes du plan enregistré sont repris intégralement ci-dessous ;
les précisions qui les suivent situent les preuves disponibles sans accepter aucun critère.
M2-INTEGRATION-1 est publié au SHA `391f87439ebc014c5a49db2ca615640f81c6c863` ; sa baseline
initiale de comparaison est `d9e0b877d93ba14d6658b537a3ceafa6b9e0c40d`.

R1 — D3 : UUID/UTC applicatifs et contrôle des décalages ; audit/archive/révision ; versions validées immuables. Ces obligations restent ouvertes, sans preuve par les seuls tests d'estimations/évaluations. Acquis supplémentaire borné : M2-IDTIME-1 au SHA ab5c0a25c72b4ed474f8253584cf2ac6fd9b5db7 valide les UUID et normalise les instants dans le semis/journal seulement ; confirmation intégrée, génération serveur, audit/archive/conflits applicatifs et versions validées immuables restent ouverts.

Preuves partielles : `test_identite_dates` contrôle notamment la normalisation des dates et le
refus d'identifiants invalides au semis. `test_socle_integration` confirme les UUID et instants
stockés, les colonnes et l'état initial d'audit des objets principaux dans les deux fixtures.
Cela ne prouve pas la génération serveur d'UUID v4, le maintien de l'audit, l'archivage sans
purge, la détection des conflits de révision ni l'immutabilité des versions validées.

R2 — D5/D10 : exécution distincte de la définition/rattachement d'opération ; décisions/priorités par couple action–projet, références retenues et remplacement structurel. M2-DECREF-1 désormais reconnue au SHA 867b40af32bcb98ca4d9b27c5af2bf1514158656 pour la seule preuve structurelle. L’association d’opération sans assurance implicite est testée ; exécution métier, comportements applicatifs et confirmation intégrée restent ouverts. Le critère R2 intégral d’origine est conservé dans le plan enregistré.

Preuves partielles : `test_decisions_priorite` contrôle les valeurs, références retenues et la
chaîne structurelle de remplacement ; `test_operations_occurrences` montre qu'une opération
liée peut rester `non_assure`, sans prouver une exécution par occurrence. Le comportement métier
d'exécution et les comportements applicatifs de décision restent à réaliser et vérifier ; la
confirmation intégrée ne remplace pas ces preuves comportementales.

R3 — D5/D10 applicatif : priorité courante, historique et immutabilité des décisions, conservation des avis et estimations via le comportement applicatif ; même couple/espace et cycles indirects des remplacements restent à traiter en M3/F16. Les seuls snapshots et FK ne prouvent pas ces comportements.

Preuves partielles : `test_arbitrage_donnees` contrôle les contraintes et snapshots des
estimations et évaluations ; `test_decisions_priorite` vérifie les références et remplacements
structurels. Le DDL permet plusieurs racines pour un couple et des modifications directes : il
ne garantit ni priorité courante unique, ni immutabilité et historique applicatifs, ni conservation
des avis et estimations. Le prédécesseur dans le même couple et espace et le refus des cycles
indirects de remplacement restent à implémenter et tester en M3/F16.

R4 — Acquis bornés : M2-ACTLINK-1 couvre cinq associations, mutualisation/isolation/persistance au SHA 65d8d34c63b26213f88355fde628aba0de34e696 ; M2-ACTREL-1 couvre parents directs/dépendances/contributions au SHA a59b8261eeee475851b7d030a3e3b15dc41f0c9b ; M2-ARBDATA-1 couvre les contraintes et snapshots structurels d'estimations/évaluations au SHA 3de2bd35f6f37e13f5c502efa90f143fb5eb03a5. Aucun de ces acquis ne couvre les autres critères ouverts. Cycles indirects d'actions et habilitations restent applicatifs M3.

Preuves partielles : `test_actions_associations` vérifie les cinq liens, la mutualisation,
l'isolation structurelle et la persistance ; `test_actions_relations` couvre parent direct,
dépendances et contributions ; `test_arbitrage_donnees` couvre contraintes et snapshots des
estimations et évaluations. `test_associations_espace` et `test_actions_associations` ne
prouvent pas les droits de lecture ; les tests de lecture M3 exercent séparément l'habilitation
par projet et le masquage des données d'autres projets pour une action partagée. Ces tests ne
prouvent pas les droits d'écriture ; les cycles indirects de filiation et de dépendances restent
à interdire et vérifier par les features d'actions.

R5 — D1/C2 : packaging et contrôles intégrés base/fixtures. Acquis borné : M2-PACK-1 au SHA d9e0b877d93ba14d6658b537a3ceafa6b9e0c40d prouve construction, contenu et installation temporaires du paquet, migrations/semis installés et persistance des deux espaces hors checkout. M2-INTEGRATION-1 reste à réaliser ; aucune validation implicite de C2/C3 ni du démarrage CLI/API/CI.

Depuis ce texte du plan, `test_packaging_socle` vérifie le wheel installé avec migrations et
semis ; `test_socle_integration` utilise configuration, base, migrations et deux fixtures sur
disque, puis contrôle journal et empreintes, idempotence, refus du second semis sans changement,
PRAGMA, intégrité et réouverture. Les tests de démarrage M3 couvrent désormais la CLI et la
lecture HTTP, mais pas les écritures serveur ; la preuve CI bornée au SHA est décrite ci-dessus.
Les obligations et critères restent ouverts même lorsque les tests structurels réussissent.

## Non objectifs de F01

Le contrat F01 prévoit les tables, les règles et la lecture. Les écritures et comportements
métier restent à livrer par leurs features : identité et adhésions (F02), structures et projets
(F03), publics (F04), versions de parcours (F05), étapes et transitions (F06), estimations de
charge et de coût (F14). Sont également hors de F01 : toute interface graphique, tout rendu PDF,
tout envoi de courriel, toute intégration de service payant et l’import de données réelles.
La présence de migrations ne prouve ni leur conformité aux règles ni leur exécution.

## Conséquences

**Positif**

- Le contrat répartit les contrôles entre base et API (D10) ; les preuves structurelles M2 et
  de lecture M3 ne démontrent pas les validations des futures écritures métier.
- Le cloisonnement repose sur les clés étrangères composites et le périmètre d’accès de l’API ;
  les tests M2/M3 exercent des refus structurels et de lecture, sans prouver les écritures.
- La chaîne de démarrage est exercée par le selftest isolé de la CI ; le développeur peut
  également lancer `python -m journai selftest` localement, sans préjuger du résultat GitHub.
- L’absence de dépendance d’exécution est un choix cible ; elle ne dispense pas de
  contrôler l’approvisionnement des outils ni les secrets de configuration.

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
