-- Socle F01 : opérations internes, ressources et constats rattachés aux occurrences de contact.
-- L'état d'une ressource (ressource.etat) reste distinct de son intégration (occurrence_ressource.etat_utilisation).

CREATE TABLE operation (
  id TEXT NOT NULL PRIMARY KEY,
  espace_id TEXT NOT NULL,
  projet_pilote_id TEXT NOT NULL,
  nom TEXT NOT NULL,
  description TEXT,
  responsable_id TEXT NOT NULL REFERENCES utilisateur(id) ON DELETE RESTRICT,
  frequence TEXT NOT NULL CHECK (frequence IN ('ponctuelle', 'quotidienne', 'hebdomadaire', 'mensuelle', 'trimestrielle', 'annuelle', 'continue')),
  mode_execution TEXT NOT NULL CHECK (mode_execution IN ('humain', 'automatise', 'mixte', 'externalise')),
  etat_operationnel TEXT NOT NULL CHECK (etat_operationnel IN ('prevu', 'assure', 'non_assure', 'degrade', 'arrete')),
  revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
  cree_par TEXT NOT NULL REFERENCES utilisateur(id) ON DELETE RESTRICT,
  cree_le TEXT NOT NULL,
  modifie_par TEXT REFERENCES utilisateur(id) ON DELETE RESTRICT,
  modifie_le TEXT,
  archive_le TEXT,
  UNIQUE (id, espace_id),
  UNIQUE (espace_id, nom),
  FOREIGN KEY (projet_pilote_id, espace_id) REFERENCES projet (id, espace_id) ON DELETE RESTRICT
);

CREATE TABLE ressource (
  id TEXT NOT NULL PRIMARY KEY,
  espace_id TEXT NOT NULL,
  projet_pilote_id TEXT NOT NULL,
  nom TEXT NOT NULL,
  type_ressource TEXT NOT NULL CHECK (type_ressource IN ('local', 'materiel', 'logiciel', 'support', 'budget', 'competence', 'autre')),
  etat TEXT NOT NULL CHECK (etat IN ('disponible', 'reserve', 'utilise', 'maintenance', 'hors_service', 'archive')),
  emplacement TEXT,
  responsable_id TEXT NOT NULL REFERENCES utilisateur(id) ON DELETE RESTRICT,
  version TEXT,
  date_revision_prevue TEXT,
  revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
  cree_par TEXT NOT NULL REFERENCES utilisateur(id) ON DELETE RESTRICT,
  cree_le TEXT NOT NULL,
  modifie_par TEXT REFERENCES utilisateur(id) ON DELETE RESTRICT,
  modifie_le TEXT,
  archive_le TEXT,
  UNIQUE (id, espace_id),
  UNIQUE (espace_id, nom),
  FOREIGN KEY (projet_pilote_id, espace_id) REFERENCES projet (id, espace_id) ON DELETE RESTRICT
);

CREATE TABLE occurrence_operation (
  occurrence_contact_id TEXT NOT NULL,
  operation_id TEXT NOT NULL,
  espace_id TEXT NOT NULL,
  role_operation TEXT NOT NULL CHECK (role_operation IN ('declencheur', 'realise', 'contributif', 'controle', 'evalue')),
  PRIMARY KEY (occurrence_contact_id, operation_id),
  FOREIGN KEY (occurrence_contact_id, espace_id) REFERENCES occurrence_contact (id, espace_id) ON DELETE RESTRICT,
  FOREIGN KEY (operation_id, espace_id) REFERENCES operation (id, espace_id) ON DELETE RESTRICT
);

CREATE TABLE occurrence_ressource (
  occurrence_contact_id TEXT NOT NULL,
  ressource_id TEXT NOT NULL,
  espace_id TEXT NOT NULL,
  usage TEXT NOT NULL,
  role_occurrence TEXT NOT NULL CHECK (role_occurrence IN ('necessaire', 'prevue', 'suffisante', 'bloquante', 'insuffisante')),
  etat_utilisation TEXT NOT NULL CHECK (etat_utilisation IN ('utilise', 'reserve', 'consomme', 'hors_service', 'non_utilise')),
  PRIMARY KEY (occurrence_contact_id, ressource_id),
  FOREIGN KEY (occurrence_contact_id, espace_id) REFERENCES occurrence_contact (id, espace_id) ON DELETE RESTRICT,
  FOREIGN KEY (ressource_id, espace_id) REFERENCES ressource (id, espace_id) ON DELETE RESTRICT
);

CREATE TABLE constat (
  id TEXT NOT NULL PRIMARY KEY,
  espace_id TEXT NOT NULL,
  occurrence_contact_id TEXT NOT NULL,
  auteur_id TEXT NOT NULL REFERENCES utilisateur(id) ON DELETE RESTRICT,
  type_constat TEXT NOT NULL CHECK (type_constat IN ('fait_valide', 'hypothese')),
  description TEXT NOT NULL,
  source TEXT NOT NULL,
  observe_le TEXT NOT NULL,
  niveau_confiance TEXT NOT NULL CHECK (niveau_confiance IN ('faible', 'moyenne', 'forte')),
  statut_validation TEXT NOT NULL DEFAULT 'a_valider' CHECK (statut_validation IN ('a_valider', 'valide', 'rejete')),
  revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
  cree_par TEXT NOT NULL REFERENCES utilisateur(id) ON DELETE RESTRICT,
  cree_le TEXT NOT NULL,
  modifie_par TEXT REFERENCES utilisateur(id) ON DELETE RESTRICT,
  modifie_le TEXT,
  archive_le TEXT,
  UNIQUE (id, espace_id),
  FOREIGN KEY (occurrence_contact_id, espace_id) REFERENCES occurrence_contact (id, espace_id) ON DELETE RESTRICT
);
