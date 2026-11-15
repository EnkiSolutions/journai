"""Lectures D9 : catalogue fermé et périmètre calculé en base à chaque appel.

Ce module est indépendant du transport HTTP ; QueryError.status est destiné à l'adaptateur API.
Les paramètres sont des chaînes uniques, après décodage et contrôle des doublons par le transport.
"""

import sqlite3
from dataclasses import dataclass
from typing import Mapping

from journai.auth import AuthContext


class QueryError(Exception):
    def __init__(self, status: int, fields: tuple[str, ...] = ()):
        self.status = status
        self.fields = fields
        super().__init__({400: "Paramètres invalides", 401: "Authentification refusée",
                          403: "Accès refusé", 404: "Ressource introuvable"}[status])


@dataclass(frozen=True)
class Resource:
    columns: tuple[str, ...]
    scope: str
    detail: bool = True


def resource(columns: str, scope: str, detail: bool = True) -> Resource:
    return Resource(tuple(columns.split()), scope, detail)


AUDIT = "revision cree_par cree_le modifie_par modifie_le archive_le"
# Chaque nom et chaque colonne interpolés dans le SQL proviennent uniquement de ce catalogue.
CATALOG = {
    "espace": resource(f"id nom {AUDIT}", "t.id = :space"),
    "structure": resource(f"id espace_id nom type_structure {AUDIT}", "1"),
    "public": resource(f"id espace_id parent_id nom role_interlocuteur description criteres_segment {AUDIT}", "1"),
    "canal": resource(f"id espace_id nom type_canal description {AUDIT}", "1"),
    "projet": resource(f"id espace_id structure_pilote_id nom finalite statut responsable_id date_debut date_fin {AUDIT}", "t.id IN (SELECT id FROM allowed_projects)"),
    "projet_structure": resource("projet_id structure_id espace_id role_dans_projet", "t.projet_id IN (SELECT id FROM allowed_projects)", False),
    "membre_projet": resource("projet_id utilisateur_id espace_id role capacite_hebdomadaire_h", "t.projet_id IN (SELECT id FROM allowed_projects)", False),
    "parcours": resource(f"id espace_id projet_id nom finalite responsable_id version_observee_id version_cible_id {AUDIT}", "t.projet_id IN (SELECT id FROM allowed_projects)"),
    "parcours_public": resource("parcours_id public_id espace_id", "t.parcours_id IN (SELECT id FROM allowed_parcours)", False),
    "version_parcours": resource(f"id parcours_id espace_id numero perspective statut version_source_id valide_par valide_le {AUDIT}", "t.parcours_id IN (SELECT id FROM allowed_parcours)"),
    "etape": resource(f"id version_parcours_id espace_id cle_stable titre objectif_public condition_entree condition_sortie ordre_affichage {AUDIT}", "t.version_parcours_id IN (SELECT id FROM allowed_versions)"),
    "transition_etape": resource(f"id version_parcours_id espace_id etape_source_id etape_destination_id condition_passage ordre_affichage {AUDIT}", "t.version_parcours_id IN (SELECT id FROM allowed_versions)"),
    "point_contact": resource(f"id espace_id projet_id nom intention responsable_id {AUDIT}", "t.projet_id IN (SELECT id FROM allowed_projects)"),
    "occurrence_contact": resource(f"id espace_id etape_id point_contact_id canal_id cle_stable besoin_public experience_attendue criticite frequence volume_estime etat_operationnel ordre_affichage {AUDIT}", "t.id IN (SELECT id FROM allowed_occurrences)"),
    "operation": resource(f"id espace_id projet_pilote_id nom description responsable_id frequence mode_execution etat_operationnel {AUDIT}", "t.projet_pilote_id IN (SELECT id FROM allowed_projects)"),
    "ressource": resource(f"id espace_id projet_pilote_id nom type_ressource etat emplacement responsable_id version date_revision_prevue {AUDIT}", "t.projet_pilote_id IN (SELECT id FROM allowed_projects)"),
    "occurrence_operation": resource("occurrence_contact_id operation_id espace_id role_operation", "t.occurrence_contact_id IN (SELECT id FROM allowed_occurrences) AND t.operation_id IN (SELECT id FROM allowed_operations)", False),
    "occurrence_ressource": resource("occurrence_contact_id ressource_id espace_id usage role_occurrence etat_utilisation", "t.occurrence_contact_id IN (SELECT id FROM allowed_occurrences) AND t.ressource_id IN (SELECT id FROM allowed_resources)", False),
    "constat": resource(f"id espace_id occurrence_contact_id auteur_id type_constat description source observe_le niveau_confiance statut_validation {AUDIT}", "t.occurrence_contact_id IN (SELECT id FROM allowed_occurrences)"),
    "action": resource(f"id espace_id projet_pilote_id action_parent_id titre description nature statut responsable_id date_debut_prevue date_butoir contrainte_imperative critere_acceptation {AUDIT}", "t.id IN (SELECT id FROM allowed_actions)"),
    "action_projet": resource("action_id projet_id espace_id part_charge part_budget motif_rattachement", "t.action_id IN (SELECT id FROM allowed_actions) AND t.projet_id IN (SELECT id FROM allowed_projects)", False),
    "action_occurrence": resource("action_id occurrence_contact_id espace_id effet_attendu etat_validation_effet", "t.action_id IN (SELECT id FROM owned_actions) AND t.occurrence_contact_id IN (SELECT id FROM allowed_occurrences)", False),
    "action_operation": resource("action_id operation_id espace_id nature_intervention", "t.action_id IN (SELECT id FROM owned_actions) AND t.operation_id IN (SELECT id FROM allowed_operations)", False),
    "action_ressource": resource("action_id ressource_id espace_id nature_intervention", "t.action_id IN (SELECT id FROM owned_actions) AND t.ressource_id IN (SELECT id FROM allowed_resources)", False),
    "action_constat": resource("action_id constat_id espace_id", "t.action_id IN (SELECT id FROM owned_actions) AND t.constat_id IN (SELECT id FROM allowed_constats)", False),
    "dependance_action": resource("action_id prerequis_id espace_id justification", "t.action_id IN (SELECT id FROM owned_actions) AND t.prerequis_id IN (SELECT id FROM owned_actions)", False),
    "contribution_action": resource("action_id utilisateur_id espace_id role_contribution charge_prevue_h charge_realisee_h", "t.action_id IN (SELECT id FROM owned_actions)", False),
    "estimation_action": resource("id action_id espace_id auteur_id charge_min_h charge_probable_h charge_max_h cout_min cout_probable cout_max devise complexite_technique complexite_organisationnelle incertitude justification cree_le revision", "t.action_id IN (SELECT id FROM owned_actions)"),
    "evaluation_action": resource("id action_id projet_id espace_id auteur_id importance impact_attendu confiance justification cree_le revision", "t.projet_id IN (SELECT id FROM allowed_projects) AND t.action_id IN (SELECT id FROM allowed_actions)"),
    "decision_priorite": resource("id action_id projet_id espace_id estimation_retenue_id evaluation_retenue_id classe_priorite rang motif decideur_id decide_le remplace_decision_id revision", "t.projet_id IN (SELECT id FROM allowed_projects) AND t.action_id IN (SELECT id FROM allowed_actions)"),
    "commentaire": resource("id espace_id objet_id auteur_id commentaire_parent_id contenu cree_le modifie_le resolu_par resolu_le revision", "t.objet_id IN (SELECT id FROM allowed_action_objects)"),
    "indicateur": resource(f"id espace_id projet_id occurrence_contact_id nom definition unite mode_calcul valeur_reference valeur_cible sens_amelioration periodicite responsable_id {AUDIT}", "t.id IN (SELECT id FROM allowed_indicators)"),
    "mesure_indicateur": resource("id espace_id indicateur_id periode_debut periode_fin valeur source auteur_id niveau_confiance cree_le revision", "t.indicateur_id IN (SELECT id FROM allowed_indicators)"),
}

# Les inclusions sont des relations nommées explicitement, jamais une jointure fournie par le client.
INCLUDES = {
    "projet": {"parcours": ("parcours", "projet_id"), "membre_projet": ("membre_projet", "projet_id"), "action_projet": ("action_projet", "projet_id")},
    "parcours": {"parcours_public": ("parcours_public", "parcours_id"), "version_parcours": ("version_parcours", "parcours_id")},
    "version_parcours": {"etape": ("etape", "version_parcours_id"), "transition_etape": ("transition_etape", "version_parcours_id")},
    "indicateur": {"mesure_indicateur": ("mesure_indicateur", "indicateur_id")},
    "action": {"action_projet": ("action_projet", "action_id"), "action_occurrence": ("action_occurrence", "action_id"), "action_operation": ("action_operation", "action_id"), "action_ressource": ("action_ressource", "action_id"), "action_constat": ("action_constat", "action_id"), "commentaire": ("commentaire", "objet_id")},
}

SCOPES = """
WITH allowed_projects AS (
 SELECT p.id FROM projet p JOIN membre_projet m ON m.projet_id=p.id AND m.espace_id=p.espace_id
 WHERE p.espace_id=:space AND m.utilisateur_id=:user
), allowed_parcours AS (
 SELECT id FROM parcours WHERE espace_id=:space AND projet_id IN (SELECT id FROM allowed_projects)
), allowed_versions AS (
 SELECT id FROM version_parcours WHERE espace_id=:space AND parcours_id IN (SELECT id FROM allowed_parcours)
), allowed_occurrences AS (
 SELECT o.id FROM occurrence_contact o JOIN etape e ON e.id=o.etape_id AND e.espace_id=o.espace_id
 JOIN point_contact p ON p.id=o.point_contact_id AND p.espace_id=o.espace_id
 WHERE o.espace_id=:space AND e.version_parcours_id IN (SELECT id FROM allowed_versions)
 AND p.projet_id IN (SELECT id FROM allowed_projects)
), allowed_operations AS (
 SELECT id FROM operation WHERE espace_id=:space AND projet_pilote_id IN (SELECT id FROM allowed_projects)
), allowed_resources AS (
 SELECT id FROM ressource WHERE espace_id=:space AND projet_pilote_id IN (SELECT id FROM allowed_projects)
), allowed_constats AS (
 SELECT id FROM constat WHERE espace_id=:space AND occurrence_contact_id IN (SELECT id FROM allowed_occurrences)
), owned_actions AS (
 SELECT id FROM action WHERE espace_id=:space AND projet_pilote_id IN (SELECT id FROM allowed_projects)
), allowed_actions AS (
 SELECT id FROM owned_actions UNION SELECT ap.action_id FROM action_projet ap
 WHERE ap.espace_id=:space AND ap.projet_id IN (SELECT id FROM allowed_projects)
), allowed_action_objects AS (
 SELECT id FROM objet WHERE espace_id=:space AND type_objet='action' AND id IN (SELECT id FROM allowed_actions)
), allowed_indicators AS (
 SELECT id FROM indicateur WHERE espace_id=:space
 AND (projet_id IS NULL OR projet_id IN (SELECT id FROM allowed_projects))
 AND (occurrence_contact_id IS NULL OR occurrence_contact_id IN (SELECT id FROM allowed_occurrences))
)
"""


def _validate_context(connection: sqlite3.Connection, context: AuthContext) -> None:
    if not connection.execute("SELECT 1 FROM utilisateur WHERE id=? AND statut='actif'", (context.utilisateur_id,)).fetchone():
        raise QueryError(401)
    if not connection.execute("SELECT 1 FROM membre_espace WHERE utilisateur_id=? AND espace_id=? AND statut='actif'", (context.utilisateur_id, context.espace_id)).fetchone():
        raise QueryError(403)


def _number(value: str, name: str, maximum: int) -> int:
    if not isinstance(value, str) or not value.isascii() or not value.isdigit() or len(value) > 18:
        raise QueryError(400, (name,))
    number = int(value)
    if number > maximum or (name == "limit" and number == 0):
        raise QueryError(400, (name,))
    return number


def _rows(cursor: sqlite3.Cursor) -> list[dict]:
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def read(connection: sqlite3.Connection, context: AuthContext, name: str,
         params: Mapping[str, str] | None = None, *, identifiant: str | None = None) -> dict:
    """Retourne l'enveloppe D9 ; un détail d'association est toujours introuvable."""
    _validate_context(connection, context)
    if name not in CATALOG:
        raise QueryError(404)
    spec = CATALOG[name]
    if identifiant is not None and not spec.detail:
        raise QueryError(404)
    params = dict(params or {})
    allowed = set(spec.columns) | {"limit", "offset", "ordre", "sens"}
    if identifiant is not None:
        allowed.add("include")
    invalid = tuple(sorted(key for key, value in params.items() if key not in allowed or not isinstance(value, str)))
    if invalid:
        raise QueryError(400, invalid)
    limit = _number(params.pop("limit", "50"), "limit", 500)
    offset = _number(params.pop("offset", "0"), "offset", 9223372036854775807)
    order = params.pop("ordre", spec.columns[0])
    direction = params.pop("sens", "asc")
    if order not in spec.columns:
        raise QueryError(400, ("ordre",))
    if direction not in {"asc", "desc"}:
        raise QueryError(400, ("sens",))
    include = params.pop("include", None)
    if include is not None and include not in INCLUDES.get(name, {}):
        raise QueryError(400, ("include",))
    if "espace_id" in params and params["espace_id"] != context.espace_id:
        raise QueryError(403, ("espace_id",))
    # Une demande explicite de projet hors habilitation ne devient pas un résultat vide.
    project = identifiant if name == "projet" else params.get("projet_id")
    if project is not None and connection.execute("SELECT 1 FROM projet WHERE id=? AND espace_id=?", (project, context.espace_id)).fetchone():
        if not connection.execute("SELECT 1 FROM membre_projet WHERE projet_id=? AND espace_id=? AND utilisateur_id=?", (project, context.espace_id, context.utilisateur_id)).fetchone():
            raise QueryError(403, ("projet_id",))
    bindings: dict[str, object] = {"space": context.espace_id, "user": context.utilisateur_id, "limit": limit, "offset": offset}
    # Les colonnes projet pilote et parent d'une action partagée ne révèlent pas les relations du pilote.
    projections = [f"t.{column}" for column in spec.columns]
    if name == "action":
        projections[spec.columns.index("projet_pilote_id")] = "CASE WHEN t.id IN (SELECT id FROM owned_actions) THEN t.projet_pilote_id END AS projet_pilote_id"
        projections[spec.columns.index("action_parent_id")] = "CASE WHEN t.id IN (SELECT id FROM owned_actions) AND t.action_parent_id IN (SELECT id FROM owned_actions) THEN t.action_parent_id END AS action_parent_id"
    if name == "commentaire":
        projections[spec.columns.index("commentaire_parent_id")] = "CASE WHEN EXISTS (SELECT 1 FROM commentaire parent WHERE parent.id=t.commentaire_parent_id AND parent.objet_id=t.objet_id AND parent.espace_id=t.espace_id) THEN t.commentaire_parent_id END AS commentaire_parent_id"
    if name == "decision_priorite":
        projections[spec.columns.index("estimation_retenue_id")] = "CASE WHEN t.action_id IN (SELECT id FROM owned_actions) THEN t.estimation_retenue_id END AS estimation_retenue_id"
        projections[spec.columns.index("remplace_decision_id")] = "CASE WHEN EXISTS (SELECT 1 FROM decision_priorite previous WHERE previous.id=t.remplace_decision_id AND previous.projet_id IN (SELECT id FROM allowed_projects) AND previous.espace_id=t.espace_id) THEN t.remplace_decision_id END AS remplace_decision_id"
    space_clause = "t.id = :space" if name == "espace" else "t.espace_id = :space"
    base = f"{SCOPES}, visible AS (SELECT {', '.join(projections)} FROM {name} t WHERE {space_clause} AND {spec.scope})"
    conditions = []
    if identifiant is not None:
        conditions.append("id = :identifier")
        bindings["identifier"] = identifiant
    for index, (column, value) in enumerate(params.items()):
        conditions.append(f"{column} = :filter{index}")
        bindings[f"filter{index}"] = value
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    total = connection.execute(f"{base} SELECT count(*) FROM visible{where}", bindings).fetchone()[0]
    rows = _rows(connection.execute(f"{base} SELECT * FROM visible{where} ORDER BY {order} {direction.upper()}, {', '.join(spec.columns[:2])} LIMIT :limit OFFSET :offset", bindings))
    if identifiant is not None:
        if not rows:
            raise QueryError(404)
        result = {"data": rows[0], "meta": {"ressource": name, "espace_id": context.espace_id}}
        if include is not None:
            target, foreign_key = INCLUDES[name][include]
            included = read(connection, context, target, {foreign_key: identifiant, "limit": "500"})
            result["included"] = {include: included["data"]}
            result["included_meta"] = {include: included["meta"]}
        return result
    return {"data": rows, "meta": {"ressource": name, "total": total, "limit": limit, "offset": offset, "espace_id": context.espace_id}}
