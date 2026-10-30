# JournAI — consignes communes

Lire docs/specification.md, docs/workflow.md et la fiche docs/features de l’issue avant de modifier le code.

- Dépôt : https://github.com/EnkiSolutions/journai ; espace Multica : JournAI.
- Harness obligatoire : Pi. Orchestrateur et Reviewer : openai-codex/gpt-6.1-sol avec thinking xhigh. Tous les autres agents : strata/strata. Ne pas remplacer silencieusement un modèle indisponible.
- Une feature = une issue GitHub = une tâche Multica = une branche et une PR dédiée. Réutiliser la PR en brouillon existante. Conserver `Closes #N` et l’identifiant JOUR de la tâche dans sa description.
- Conserver le propriétaire développeur dans les métadonnées de la tâche. Une correction revient à ce propriétaire, jamais à un nouveau développeur arbitraire.
- Travailler dans le worktree isolé fourni par Multica. Ne jamais modifier le checkout ou la branche d’un autre agent.
- Conserver la branche locale attribuée par le daemon. Y intégrer `origin/main` et la branche distante de la PR dédiée avant développement, puis pousser `HEAD:feature/N-nom` vers cette PR. Ne pas créer une seconde PR parce que le nom de la branche du worktree diffère de celui de la PR.
- Implémenter et vérifier les critères d’acceptation ; une fiche de spécification seule ne livre pas la feature. Ne pas élargir le périmètre sans justification dans l’issue.
- Ne jamais publier de secrets ni de données réelles de bénéficiaires. Les fixtures sont synthétiques.
- Une PR prête passe d’abord par CodeRabbit. Le Reviewer n’est ni assigné ni réveillé pour une revue de code avant que CodeRabbit ait approuvé le dernier SHA, sans remarque ouverte ni erreur. Une revue absente, ignorée, limitée ou périmée bloque le passage.
- Le Reviewer justifie chaque ligne ajoutée et supprimée du diff avec le critère servi et une raison précise ; les lignes vides et fichiers générés sont également couverts. Il produit un certificat JSON lié au SHA et le valide avec scripts/review_gate.py.
- Toute modification du SHA invalide la validation. Aucun `@coderabbitai approve` / `resolve` forcé, auto-résolution abusive ou contournement d’un contrôle.
- Après validation, fusionner la PR avec le SHA attendu, marquer la tâche Terminée automatiquement et réveiller l’Orchestrateur sur la tâche de pilotage. Aucune validation humaine n’est requise.
- En cas de rejet, poster les corrections précises, rendre la tâche au développeur propriétaire et la remettre En cours. Répéter CodeRabbit puis Reviewer.
- Ne pas déployer ni souscrire de service payant sans demande distincte.
