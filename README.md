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

Le socle applicatif, son architecture et ses commandes de démarrage seront livrés dans F01. Aucun déploiement n’est configuré à ce stade.
