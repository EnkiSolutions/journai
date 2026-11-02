M1-R2 — correction du contrat, document seul (M1 reste partiel, non livré, non validé).

`docs/adr/0001-architecture-et-contrat-api.md` (seul fichier modifié ; +28 / -21) :

- l’en-tête ne déclare plus de liaison à `pyproject.toml`, absent du dépôt ; les références
  réellement vérifiées sont `journai/__init__.py` et l’en-tête de
  `journai/migrations/0001_identite_espace_projet.sql` ;
- C1 est le seul critère présenté comme documenté, C2 et C3 sont explicitement décrits comme
  contrat non implémenté ;
- la section d’état nomme les fichiers présents dans l’arbre Git sans affirmer leur branchement,
  et les validations M2/M3/M4 sont listées comme restant à produire ;
- le compte de lignes des fixtures est corrigé : `espace-a.json` 1156 lignes, `espace-b.json`
  284 lignes (la mention « 116 lignes » était fausse), et le tableau indique les livrables
  absents : `config/journai.example.json`, `pyproject.toml`, `cli.py`, `api.py`, `ci.yml`.

Preuves : `git diff --check` sans erreur ; aucun test M2 exécuté, et aucun test ajouté ; aucun
code applicatif, migration, fixture, test, workflow, `.gitignore` ou `AGENTS.md` modifié.

Checkpoint : `2c9e1af` (HEAD de départ) → `d424a844187b911dcf5a4effdad9e4e249f5e300` sur
`feature/1-socle`, contrôle `diff-check` OK. SHA distant vérifié :

```
d424a844187b911dcf5a4effdad9e4e249f5e300	refs/heads/feature/1-socle
```

Statut : M1 non satisfait (C1 partiel ; C2, C3 non satisfaits), M2 non démarré. Ce work unit
M1-R2 ne livre pas M1 et n’avance pas à M2.
