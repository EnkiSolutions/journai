# JournAI — spécification fonctionnelle

Source de cadrage : https://chatgpt.com/share/6ae4974d-25b4-83ed-86e3-2d50ac0105a2 (30 octobre 2026).

JournAI est un outil collaboratif de conception des parcours et de pilotage du travail qui en découle. Il relie publics, interactions, opérations, ressources, constats, actions et décisions. Les quatre vues synchronisées sont Parcours, Plan d’action, Arbitrage et Portefeuille.

## Conventions

Base relationnelle ; identifiants UUID ; véritables clés étrangères et tables d’association uniques, jamais de listes d’identifiants en texte. Tout objet métier appartient à un espace. Les objets principaux ont un auteur, des dates de création/modification, une révision et une date d’archivage. Les relations doivent rester dans le même espace.

## Modèle de données attendu

Les noms ci-dessous expriment le domaine ; les choix techniques sont documentés par la feature de socle.

```text
espace(id, nom)
utilisateur(id, nom_affiche, email, statut)
membre_espace(espace_id, utilisateur_id, role, statut)
structure(id, espace_id, nom, type_structure)
projet(id, structure_pilote_id, nom, finalite, statut, responsable_id, date_debut, date_fin)
projet_structure(projet_id, structure_id, role_dans_projet)
membre_projet(projet_id, utilisateur_id, role, capacite_hebdomadaire_h)

public(id, parent_id, nom, role_interlocuteur, description, criteres_segment)
parcours(id, projet_id, nom, finalite, responsable_id, version_observee_id, version_cible_id)
parcours_public(parcours_id, public_id)
version_parcours(id, parcours_id, numero, perspective, statut, version_source_id, valide_par, valide_le)
etape(id, version_parcours_id, cle_stable, titre, objectif_public, condition_entree, condition_sortie, ordre_affichage)
transition_etape(id, version_parcours_id, etape_source_id, etape_destination_id, condition_passage, ordre_affichage)
canal(id, nom, type_canal, description)
point_contact(id, projet_id, nom, intention, responsable_id)
occurrence_contact(id, etape_id, point_contact_id, canal_id, cle_stable, besoin_public, experience_attendue, criticite, frequence, volume_estime, etat_operationnel, ordre_affichage)

operation(id, projet_pilote_id, nom, description, responsable_id, frequence, mode_execution, etat_operationnel)
occurrence_operation(occurrence_contact_id, operation_id, role_operation)
ressource(id, projet_pilote_id, nom, type_ressource, etat, emplacement, responsable_id, version, date_revision_prevue)
occurrence_ressource(occurrence_contact_id, ressource_id, usage, etat_utilisation)
constat(id, occurrence_contact_id, auteur_id, type_constat, description, source, observe_le, niveau_confiance, statut_validation)

action(id, projet_pilote_id, action_parent_id, titre, description, nature, statut, responsable_id, date_debut_prevue, date_butoir, contrainte_imperative, critere_acceptation)
action_projet(action_id, projet_id, part_charge, part_budget, motif_rattachement)
action_occurrence(action_id, occurrence_contact_id, effet_attendu, etat_validation_effet)
action_operation(action_id, operation_id, nature_intervention)
action_ressource(action_id, ressource_id, nature_intervention)
action_constat(action_id, constat_id)
dependance_action(action_id, prerequis_id, justification)
contribution_action(action_id, utilisateur_id, role_contribution, charge_prevue_h, charge_realisee_h)

estimation_action(id, action_id, auteur_id, charge_min_h, charge_probable_h, charge_max_h, cout_min, cout_probable, cout_max, devise, complexite_technique, complexite_organisationnelle, incertitude, justification, cree_le)
evaluation_action(id, action_id, projet_id, auteur_id, importance, impact_attendu, confiance, justification, cree_le)
decision_priorite(id, action_id, projet_id, estimation_retenue_id, evaluation_retenue_id, classe_priorite, rang, motif, decideur_id, decide_le, remplace_decision_id)

objet(id, espace_id, type_objet, revision, cree_par, cree_le, modifie_par, modifie_le, archive_le)
commentaire(id, objet_id, auteur_id, commentaire_parent_id, contenu, cree_le, modifie_le, resolu_par, resolu_le)
abonnement(objet_id, utilisateur_id, niveau_notification)
evenement(id, objet_id, auteur_id, type_evenement, valeur_avant, valeur_apres, horodatage)
notification(id, destinataire_id, evenement_id, cree_le, lu_le)

indicateur(id, projet_id, occurrence_contact_id?, nom, definition, unite, mode_calcul, valeur_reference, valeur_cible, sens_amelioration, periodicite, responsable_id)
mesure_indicateur(id, indicateur_id, periode_debut, periode_fin, valeur, source, auteur_id, niveau_confiance)
```

## Règles métier

- Un espace contient plusieurs structures et projets. Un projet a une structure pilote et peut en associer d’autres. L’accès est explicitement attribué au projet ; appartenir à une structure ne suffit pas.
- Les publics peuvent former des segments imbriqués. Un parcours peut concerner plusieurs publics.
- Le point de contact garde une identité stable ; une occurrence décrit sa présence dans une étape et un canal. Plusieurs canaux impliquent plusieurs occurrences.
- Les étapes constituent un graphe avec alternatives, retours et abandons ; l’ordre d’affichage ne définit pas les transitions. Une transition reste dans une seule version.
- Les perspectives observée et cible ont chacune plusieurs versions. Une version validée est immuable ; une révision crée un brouillon. Les clés stables identifient étapes et occurrences entre versions. Les liens historiques ne sont pas déplacés silencieusement. Les versions courantes appartiennent au bon parcours.
- Opérations et ressources sont réutilisables entre occurrences. L’état d’une ressource est distinct de son intégration ; une opération définie n’est pas nécessairement assurée. Les constats conservent source, date, confiance et distinction entre hypothèse et fait validé.
- Une action a un résultat attendu, un critère de fin, un responsable et plusieurs contributeurs possibles. Elle peut être décomposée sans devenir son propre ancêtre. Les dépendances n’ont pas de cycle.
- Une action mutualisée reste unique et peut bénéficier à plusieurs projets, contacts, opérations et ressources. Sa charge est comptée une fois dans le portefeuille. Les répartitions validées de charge et de budget totalisent chacune 100 %. Des livraisons indépendantes deviennent des actions distinctes.
- Criticité, importance, impact, complexité, charge et coût restent séparés. Les échelles sont explicites. Les estimations et évaluations successives restent consultables ; les désaccords ne sont pas effacés par une moyenne.
- La priorité appartient au couple action–projet. La décision conserve auteur, motif, estimation et évaluation retenues. Une seule décision est courante. L’estimation vise la même action et l’évaluation le même couple action–projet. Un classement calculé expose sa règle et ses données.
- Le registre objet relie les objets métier aux commentaires et événements avec intégrité du type. L’édition utilise la révision pour détecter les conflits et permettre la comparaison.
- Rôles : administrateur d’espace ; pilote de projet ; contributeur ; commentateur ; lecteur. Une action partagée expose son contenu commun et ses échanges aux membres autorisés des projets concernés, sans ouvrir les autres données de ces projets.
- Les suppressions d’objets utilisés passent par l’archivage. Les changements et décisions significatifs sont historisés.
- Un indicateur concerne un projet ou une occurrence. Une mesure conserve période, source et confiance. Livrer une action et valider son effet sont deux événements distincts.

## Vues

Parcours : étapes, transitions, besoins, contacts, supports, opérations internes et comparaison observé/cible. Depuis un contact : utilité, état, ressources, opérations, travail livré/manquant et priorités.

Plan d’action : listes et regroupements par projet, parcours, responsable, échéance, statut et priorité ; navigation vers l’origine de chaque action.

Arbitrage : matrice impact–charge, complexité, coût, contraintes, prérequis et capacité ; décision motivée de traiter, programmer, différer, suspendre ou renoncer.

Portefeuille : projets, actions mutualisées, ressources, blocages et charge/capacité des collaborateurs, sans double comptage.
