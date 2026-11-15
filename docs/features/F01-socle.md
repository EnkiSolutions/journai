# F01 — Socle exécutable, architecture et migrations

Définir une architecture web collaborative et une base relationnelle ; fournir un démarrage local reproductible et une CI.

Source : [spécification](../specification.md).

Dépendances : aucune.

## Critères d’acceptation

- [ ] Documenter les choix et le contrat API dans une ADR.
- [ ] Fournir migrations versionnées, fixtures synthétiques, configuration exemple sans secrets et commandes de lancement.
- [ ] La CI exécute les contrôles de typage, de qualité et les tests utiles ; le parcours de démarrage est vérifié.

La documentation relie les invariants de la spécification à l’[ADR](../adr/0001-architecture-et-contrat-api.md), aux features responsables et à leurs tests existants ou attendus. Cette traçabilité ne transfère pas à F01 les écritures et comportements métier des features futures.

## Livraison

- [ ] Code implémenté et vérifié
- [ ] CodeRabbit approuve le dernier SHA sans fil ouvert
- [ ] Reviewer justifie chaque ligne modifiée et valide le certificat

Issue : https://github.com/EnkiSolutions/journai/issues/1
Tâche : [JOUR-3](https://multica.ai/journai/issues/01a18e5a-cb94-74c2-a217-ce80992da4b5).
