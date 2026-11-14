# JournAI

Concevoir les parcours des clients, bénévoles, bénéficiaires et partenaires, puis organiser les actions, opérations, ressources et priorités qui en découlent.

Le produit est en cours de réalisation. Les PR initiales sont des brouillons de cadrage ; elles seront enrichies par les agents avant revue.

- [Spécification et modèle relationnel](docs/specification.md)
- [Backlog, issues et PR dédiées](docs/backlog.md)
- [Workflow autonome et règles de revue](docs/workflow.md)
- [Consignes des agents](AGENTS.md)

Les quatre vues prévues sont **Parcours**, **Plan d’action**, **Arbitrage** et **Portefeuille**. Une action mutualisée reste unique et son travail est compté une seule fois.

## Réalisation

L’espace [Multica JournAI](https://multica.ai/journai/issues) pilote le développement avec Pi. Orchestrateur et Reviewer : GPT-6.1 Sol xHigh ; autres agents : Strata. CodeRabbit précède toute revue du Reviewer. Après validation de chaque ligne et fusion, la tâche est terminée automatiquement et la suivante est affectée.

## Vérifier le garde de revue

```sh
python -m unittest discover -s scripts -p 'test_*.py' -v
python scripts/review_gate.py --pr NUMERO
```

## Socle local (Python 3.12 ou plus)

Installer le paquet avec `python -m pip install .`, puis utiliser `journai` ou `python -m journai` :

```sh
journai --help
journai init                 # migrations versionnées, idempotentes
journai seed                 # fixtures synthétiques dans une base migrée vide
journai status               # versions et totaux par table, en lecture seule
journai selftest             # base temporaire, lecture HTTP et refus ; ne touche pas la base configurée
# Définir JOURNAI_JETON_DEV dans l'environnement, puis :
journai serve                # API de lecture locale uniquement (dev/test)
```

Sans argument, `journai` exécute `init` puis `seed`. Un second semis est refusé sans modifier
les données ; `journai seed --replace` autorise explicitement le remplacement des tables des
fixtures. Le semis est réservé aux environnements `dev` et `test`. `selftest` utilise une clé
aléatoire et des fixtures isolées, sans nécessiter de secret configuré ; ses ressources sont supprimées.
`serve` refuse `staging` et `prod` ainsi qu'une clé absente, non ASCII ou de moins de 32 caractères.
Définir une clé de démonstration aléatoire dans `JOURNAI_JETON_DEV` uniquement dans l'environnement
local ; ne jamais la publier. L'API accepte des jetons HMAC de démonstration en en-tête Bearer
(contrat dans l'ADR), et ne fournit aucune écriture. Ce mécanisme n'est pas une authentification de
production. La base doit avoir été initialisée et semée avant les lectures.

La configuration utilise les défauts, `config/journai.example.json` puis
`config/journai.json` dans le répertoire courant, ou un fichier explicite avec
`journai --config chemin/config.json init` ; les variables `JOURNAI_*` priment sur les fichiers.
L'exemple versionné ne contient aucun secret. Par défaut la base est `var/journai.db`, relative
au répertoire courant ; les migrations et fixtures fournies par le paquet restent disponibles hors
checkout. Un `schema_dir` personnalisé peut désigner un autre répertoire de migrations. Le niveau
`log_level` règle les journaux sur stdout ; les erreurs sont affichées sur stderr. Ne pas mettre de
secret dans les fichiers de configuration versionnés.

F01 reste partielle ; aucun déploiement n’est configuré à ce stade.
