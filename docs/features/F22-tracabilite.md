# F22 — Registre objet, conflits, historique et archivage

Gérer objet, evenement et les révisions des entités.

Source : [spécification](../specification.md).

Dépendances : F02, F03.

## Critères d’acceptation

- [ ] Garantir la cohérence entre type du registre et table métier avec de vraies clés étrangères.
- [ ] Détecter une modification concurrente par revision et proposer la comparaison avant enregistrement.
- [ ] Conserver avant/après/auteur/date des changements significatifs ; archiver les objets utilisés au lieu de casser leurs liens.

## Livraison

- [ ] Code implémenté et vérifié
- [ ] CodeRabbit approuve le dernier SHA sans fil ouvert
- [ ] Reviewer justifie chaque ligne modifiée et valide le certificat

Issue : https://github.com/EnkiSolutions/journai/issues/22
Tâche : [JOUR-24](https://multica.ai/journai/issues/01a18e5b-902b-7e95-ac48-2498f8420bd3).
