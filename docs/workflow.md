# Réalisation autonome de JournAI

## Équipe et exécution

Pi exécute tous les agents. L’Orchestrateur et le Reviewer utilisent GPT-6.1 Sol xHigh ; les développeurs Socle & Données, Métier & API, Interface & Collaboration et l’agent Gate CodeRabbit utilisent Strata.

Le projet Multica utilise D:\Prog\journai en mode worktree. La tâche de pilotage conserve la file ordonnée et les dépendances. Les fiches de features, issues, tâches et PR sont répertoriées dans docs/backlog.md. Le développeur garde la branche locale fournie par le daemon, y intègre la branche distante dédiée et le dernier main, puis pousse `HEAD:feature/N-nom` vers la PR existante.

## Transitions

1. L’Orchestrateur choisit une tâche dont les dépendances sont fusionnées, mémorise `developer_agent_id`, assigne le spécialiste disponible et la passe En cours. Sur la tâche parent, il inscrit un réveil `--until-issue UUID_FEATURE --until-issue-state done` afin d’être relancé dès sa clôture et d’affecter la suivante. Il ne dispatch qu’une feature à la fois au démarrage ; il peut paralléliser les features indépendantes après le socle.
2. Le développeur reprend la branche de la PR dédiée, implémente, teste, pousse, documente la validation et retire le brouillon quand la feature est réellement livrée. Il passe la tâche Attente CodeRabbit.
3. L’agent Gate CodeRabbit contrôle le dernier SHA, les résultats et les fils de revue. Il ne fait aucune revue de code. Tant qu’il manque l’approbation CodeRabbit ou qu’une erreur/remarque subsiste, le Reviewer ne reçoit rien. Les corrections retournent au développeur propriétaire ; une revue en cours fait l’objet d’un réveil différé du Gate.
4. Un passage réussi du script `python scripts/review_gate.py --pr N` autorise le Gate à passer En relecture, ce qui assigne et démarre le Reviewer.
5. Le Reviewer vérifie l’issue, l’implémentation et les tests, puis justifie **chaque ligne modifiée**. Son certificat a `head_sha`, `decision` (`approve` ou `request_changes`), `summary`, `validation` et `lines` (objets `path`, `side` = `LEFT`/`RIGHT`, `line`, `reason`). Chaque raison cite le besoin ou l’invariant servi. Le certificat couvre le diff complet, suppressions et renommages inclus. Pour un fichier binaire, ajouter une entrée dans `binary_files` avec `path` et `reason`.
6. Sur approbation : exécuter le gate avec le certificat, publier le certificat dans la PR, puis fusionner avec un contrôle atomique du SHA. Les certificats volumineux sont publiés en plusieurs commentaires indexés sans omettre de ligne. Un simple statut vert de CodeRabbit n’est pas une preuve suffisante ; le bot doit approuver le SHA courant et n’avoir aucun fil non résolu. Si GitHub refuse une auto-revue parce que les deux agents partagent le même compte, le certificat et le statut `JournAI Reviewer` constituent la validation de l’agent ; ne pas inventer une approbation GitHub native.
7. Une fois la fusion confirmée, mettre la tâche Terminée et notifier immédiatement l’Orchestrateur sur la tâche de pilotage. Celui-ci assigne la prochaine feature prête. Sur rejet : rendre immédiatement la tâche au `developer_agent_id`, passer En cours et fournir les corrections. Toute nouvelle révision repasse par CodeRabbit.

La fin d’une exécution Multica seule ne vaut ni validation ni livraison. La règle native `child_done` du parent réveille l’Orchestrateur dès qu’une feature se termine. Le réveil périodique du pilotage récupère les transitions manquées et reste silencieux si rien ne change. Le parent reste ouvert jusqu’à livraison de toutes les features.

## Contrôles de preuve

`scripts/review_gate.py` utilise un jeton GitHub déjà fourni par `GH_TOKEN`, `GITHUB_TOKEN` ou le gestionnaire Git, sans l’afficher ni le sauvegarder. Il refuse les revues absentes, périmées et les fils ouverts. Avec un certificat, il exige une couverture exhaustive des lignes du diff et un SHA identique. Son mode `--publish` pose le statut Reviewer seulement après ces vérifications. Son mode `--merge` vérifie de nouveau les contrôles et utilise le SHA attendu de l’API de fusion.

Les PR initiales sont des **brouillons de cadrage**, avec une fiche de feature et une case d’implémentation non cochée. Elles ne sont pas présentées comme du code livré. Leurs branches sont destinées aux agents qui y ajouteront le code.
