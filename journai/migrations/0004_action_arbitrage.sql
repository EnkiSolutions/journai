-- Socle F01 : actions, mutualisation, dépendances, contributions, estimations, évaluations, décisions.
-- Une action partagée reste une seule ligne ; les tables d'association portent l'espace de l'action
-- et leurs clés étrangères composites imposent que chaque rattachement soit du même espace.

CREATE TABLE action (
  id TEXT NOT NULL PRIMARY KEY,
  espace_id TEXT NOT NULL,
  projet_pilote_id TEXT NOT NULL,
  action_parent_id TEXT,
  titre TEXT NOT NULL,
  description TEXT NOT NULL,
  nature TEXT NOT NULL CHECK (nature IN ('livrable', 'jalons', 'support', 'correctif', 'arbitrage', 'suivi')),
  statut TEXT NOT NULL DEFAULT 'propose' CHECK (statut IN ('propose', 'priorise', 'programme', 'en_cours', 'bloque', 'differe', 'suspendu', 'renonce', 'livre')),
  responsable_id TEXT NOT NULL REFERENCES utilisateur(id) ON DELETE RESTRICT,
  date_debut_prevue TEXT,
  date_butoir TEXT,
  contrainte_imperative TEXT,
  critere_acceptation TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
  cree_par TEXT NOT NULL REFERENCES utilisateur(id) ON DELETE RESTRICT,
  cree_le TEXT NOT NULL,
  modifie_par TEXT REFERENCES utilisateur(id) ON DELETE RESTRICT,
  modifie_le TEXT,
  archive_le TEXT,
  UNIQUE (id, espace_id),
  FOREIGN KEY (projet_pilote_id, espace_id) REFERENCES projet (id, espace_id) ON DELETE RESTRICT,
  -- Une action peut être décomposée sans devenir son propre ancêtre direct.
  FOREIGN KEY (action_parent_id, espace_id) REFERENCES action (id, espace_id) ON DELETE RESTRICT,
  CHECK (action_parent_id IS NULL OR action_parent_id <> id)
);

CREATE TABLE action_projet (
  action_id TEXT NOT NULL,
  projet_id TEXT NOT NULL,
  espace_id TEXT NOT NULL,
  part_charge NUMERIC CHECK (part_charge IS NULL OR (part_charge >= 0 AND part_charge <= 100)),
  part_budget NUMERIC CHECK (part_budget IS NULL OR (part_budget >= 0 AND part_budget <= 100)),
  motif_rattachement TEXT NOT NULL,
  PRIMARY KEY (action_id, projet_id),
  FOREIGN KEY (action_id, espace_id) REFERENCES action (id, espace_id) ON DELETE RESTRICT,
  FOREIGN KEY (projet_id, espace_id) REFERENCES projet (id, espace_id) ON DELETE RESTRICT
);

CREATE TABLE action_occurrence (
  action_id TEXT NOT NULL,
  occurrence_contact_id TEXT NOT NULL,
  espace_id TEXT NOT NULL,
  effet_attendu TEXT NOT NULL,
  etat_validation_effet TEXT NOT NULL DEFAULT 'non_valide' CHECK (etat_validation_effet IN ('non_valide', 'partiel', 'valide', 'invalide')),
  PRIMARY KEY (action_id, occurrence_contact_id),
  FOREIGN KEY (action_id, espace_id) REFERENCES action (id, espace_id) ON DELETE RESTRICT,
  FOREIGN KEY (occurrence_contact_id, espace_id) REFERENCES occurrence_contact (id, espace_id) ON DELETE RESTRICT
);

CREATE TABLE action_operation (
  action_id TEXT NOT NULL,
  operation_id TEXT NOT NULL,
  espace_id TEXT NOT NULL,
  nature_intervention TEXT NOT NULL CHECK (nature_intervention IN ('creer', 'modifier', 'arreter', 'controler')),
  PRIMARY KEY (action_id, operation_id),
  FOREIGN KEY (action_id, espace_id) REFERENCES action (id, espace_id) ON DELETE RESTRICT,
  FOREIGN KEY (operation_id, espace_id) REFERENCES operation (id, espace_id) ON DELETE RESTRICT
);

CREATE TABLE action_ressource (
  action_id TEXT NOT NULL,
  ressource_id TEXT NOT NULL,
  espace_id TEXT NOT NULL,
  nature_intervention TEXT NOT NULL CHECK (nature_intervention IN ('creer', 'modifier', 'arreter', 'controler')),
  PRIMARY KEY (action_id, ressource_id),
  FOREIGN KEY (action_id, espace_id) REFERENCES action (id, espace_id) ON DELETE RESTRICT,
  FOREIGN KEY (ressource_id, espace_id) REFERENCES ressource (id, espace_id) ON DELETE RESTRICT
);

CREATE TABLE action_constat (
  action_id TEXT NOT NULL,
  constat_id TEXT NOT NULL,
  espace_id TEXT NOT NULL,
  PRIMARY KEY (action_id, constat_id),
  FOREIGN KEY (action_id, espace_id) REFERENCES action (id, espace_id) ON DELETE RESTRICT,
  FOREIGN KEY (constat_id, espace_id) REFERENCES constat (id, espace_id) ON DELETE RESTRICT
);

CREATE TABLE dependance_action (
  action_id TEXT NOT NULL,
  prerequis_id TEXT NOT NULL,
  espace_id TEXT NOT NULL,
  justification TEXT NOT NULL,
  PRIMARY KEY (action_id, prerequis_id),
  FOREIGN KEY (action_id, espace_id) REFERENCES action (id, espace_id) ON DELETE RESTRICT,
  FOREIGN KEY (prerequis_id, espace_id) REFERENCES action (id, espace_id) ON DELETE RESTRICT,
  CHECK (action_id <> prerequis_id)
);

CREATE TABLE contribution_action (
  action_id TEXT NOT NULL,
  utilisateur_id TEXT NOT NULL REFERENCES utilisateur(id) ON DELETE RESTRICT,
  espace_id TEXT NOT NULL,
  role_contribution TEXT NOT NULL CHECK (role_contribution IN ('responsable', 'contributeur', 'relais', 'consulte')),
  charge_prevue_h NUMERIC CHECK (charge_prevue_h IS NULL OR charge_prevue_h >= 0),
  charge_realisee_h NUMERIC CHECK (charge_realisee_h IS NULL OR charge_realisee_h >= 0),
  PRIMARY KEY (action_id, utilisateur_id),
  FOREIGN KEY (action_id, espace_id) REFERENCES action (id, espace_id) ON DELETE RESTRICT
);

CREATE TABLE estimation_action (
  id TEXT NOT NULL PRIMARY KEY,
  action_id TEXT NOT NULL,
  espace_id TEXT NOT NULL,
  auteur_id TEXT NOT NULL REFERENCES utilisateur(id) ON DELETE RESTRICT,
  charge_min_h NUMERIC CHECK (charge_min_h IS NULL OR charge_min_h >= 0),
  charge_probable_h NUMERIC CHECK (charge_probable_h IS NULL OR charge_probable_h >= 0),
  charge_max_h NUMERIC CHECK (charge_max_h IS NULL OR charge_max_h >= 0),
  cout_min NUMERIC CHECK (cout_min IS NULL OR cout_min >= 0),
  cout_probable NUMERIC CHECK (cout_probable IS NULL OR cout_probable >= 0),
  cout_max NUMERIC CHECK (cout_max IS NULL OR cout_max >= 0),
  devise TEXT CHECK (devise IS NULL OR length(devise) = 3),
  complexite_technique TEXT NOT NULL CHECK (complexite_technique IN ('faible', 'moyenne', 'forte')),
  complexite_organisationnelle TEXT NOT NULL CHECK (complexite_organisationnelle IN ('faible', 'moyenne', 'forte')),
  incertitude TEXT NOT NULL CHECK (incertitude IN ('faible', 'moyenne', 'forte')),
  justification TEXT NOT NULL,
  cree_le TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
  UNIQUE (id, action_id),
  UNIQUE (id, espace_id),
  FOREIGN KEY (action_id, espace_id) REFERENCES action (id, espace_id) ON DELETE RESTRICT,
  CHECK (charge_min_h IS NULL OR charge_probable_h IS NULL OR charge_probable_h >= charge_min_h),
  CHECK (charge_max_h IS NULL OR charge_probable_h IS NULL OR charge_max_h >= charge_probable_h),
  CHECK (cout_min IS NULL OR cout_probable IS NULL OR cout_probable >= cout_min),
  CHECK (cout_max IS NULL OR cout_probable IS NULL OR cout_max >= cout_probable)
);

CREATE TABLE evaluation_action (
  id TEXT NOT NULL PRIMARY KEY,
  action_id TEXT NOT NULL,
  projet_id TEXT NOT NULL,
  espace_id TEXT NOT NULL,
  auteur_id TEXT NOT NULL REFERENCES utilisateur(id) ON DELETE RESTRICT,
  importance TEXT NOT NULL CHECK (importance IN ('faible', 'moyenne', 'forte')),
  impact_attendu TEXT NOT NULL CHECK (impact_attendu IN ('faible', 'moyenne', 'forte')),
  confiance TEXT NOT NULL CHECK (confiance IN ('faible', 'moyenne', 'forte')),
  justification TEXT NOT NULL,
  cree_le TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
  UNIQUE (id, action_id, projet_id),
  UNIQUE (id, espace_id),
  -- L'évaluation porte sur le même couple action-projet que le rattachement validé.
  FOREIGN KEY (action_id, projet_id) REFERENCES action_projet (action_id, projet_id) ON DELETE RESTRICT,
  FOREIGN KEY (action_id, espace_id) REFERENCES action (id, espace_id) ON DELETE RESTRICT
);

CREATE TABLE decision_priorite (
  id TEXT NOT NULL PRIMARY KEY,
  action_id TEXT NOT NULL,
  projet_id TEXT NOT NULL,
  espace_id TEXT NOT NULL,
  estimation_retenue_id TEXT NOT NULL,
  evaluation_retenue_id TEXT NOT NULL,
  classe_priorite TEXT NOT NULL CHECK (classe_priorite IN ('a_traiter', 'programme', 'differe', 'suspendu', 'renonce')),
  rang INTEGER NOT NULL CHECK (rang >= 1),
  motif TEXT NOT NULL,
  decideur_id TEXT NOT NULL REFERENCES utilisateur(id) ON DELETE RESTRICT,
  decide_le TEXT NOT NULL,
  remplace_decision_id TEXT REFERENCES decision_priorite(id) ON DELETE RESTRICT,
  revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
  UNIQUE (id, espace_id),
  FOREIGN KEY (action_id, projet_id) REFERENCES action_projet (action_id, projet_id) ON DELETE RESTRICT,
  -- L'estimation retenue vise la même action que la décision.
  FOREIGN KEY (estimation_retenue_id, action_id) REFERENCES estimation_action (id, action_id) ON DELETE RESTRICT,
  FOREIGN KEY (evaluation_retenue_id, action_id, projet_id) REFERENCES evaluation_action (id, action_id, projet_id) ON DELETE RESTRICT,
  FOREIGN KEY (estimation_retenue_id, espace_id) REFERENCES estimation_action (id, espace_id) ON DELETE RESTRICT,
  FOREIGN KEY (evaluation_retenue_id, espace_id) REFERENCES evaluation_action (id, espace_id) ON DELETE RESTRICT,
  CHECK (remplace_decision_id IS NULL OR remplace_decision_id <> id)
);

-- Une décision ne peut être remplacée qu'une fois (pas de bifurcation). La décision courante
-- par couple action-projet relève de la logique applicative de F16.
CREATE UNIQUE INDEX ux_decision_priorite_remplacee
  ON decision_priorite (remplace_decision_id)
  WHERE remplace_decision_id IS NOT NULL;
